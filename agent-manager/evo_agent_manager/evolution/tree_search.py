"""Idea Tree Search — paper §3.2: K-way parallel exploration with Elo pruning.

The Researcher Agent (RA) uses Idea Tree Search to generate research ideas:
  1. EXPLORE:  K parallel directions → K candidate ideas
  2. BRANCH:   Each candidate → N refined variants
  3. PRUNE:    Elo tournament → top-K survival
  4. EXPAND:   Top-1 → full research proposal

Integration with evolution memory:
  - inject_priors() before explore (avoid known failures, reuse successes)
  - IDE distillation after prune (record promising directions)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from .elo import EloTournament, _parse_json_response

logger = logging.getLogger(__name__)

# ── Prompts ──────────────────────────────────────────────────────────────────

EXPLORE_SYSTEM_PROMPT = """You are a senior research scientist. Given a research goal and literature context, propose {k} distinct research directions. Each direction must be fundamentally different from the others — vary the approach, methodology, or problem framing.

For each direction, provide:
- A concise title
- A one-paragraph hypothesis
- A method sketch (datasets, baselines, evaluation approach)
- Which gap in the literature it addresses (cite specific papers from context)

Output as JSON array:
[{"title": "...", "hypothesis": "...", "method_sketch": "...", "literature_gap": "..."}]"""

BRANCH_SYSTEM_PROMPT = """You are a senior research scientist. Given a seed research idea, generate {n} refined variants. Each variant should explore a different angle:

1. Enhancement: strengthen with additional literature grounding
2. Simplification: strip to the cleanest testable hypothesis
3. Cross-domain: import an insight from a different field
4. Combination: merge with another concept from the literature
5. Pivot: abandon the core mechanism, propose alternative approach

Output as JSON array:
[{"title": "...", "hypothesis": "...", "method_sketch": "...", "variant_type": "enhancement|simplification|cross_domain|combination|pivot"}]"""

EXPAND_SYSTEM_PROMPT = """You are a senior research scientist. Expand the following research idea into a full research proposal suitable for a top-tier conference submission.

Sections:
1. Abstract (150-250 words)
2. Problem Definition (formal statement, scope, assumptions)
3. Related Work (key gaps addressed)
4. Proposed Method (detailed, with architecture/algorithm sketch)
5. Experimental Design (datasets, baselines, metrics, ablation plan)
6. Expected Contributions and Limitations

Output as JSON:
{"title": "...", "abstract": "...", "problem_definition": "...", "related_work": "...", "proposed_method": "...", "experimental_design": "...", "contributions": "...", "limitations": "..."}"""


def _extract_json_array(text: str) -> list | None:
    """Extract a JSON array from LLM response."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try ```json fence
    m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Try finding first [ ... ] block
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


@dataclass
class TreeNode:
    """A node in the idea search tree."""
    id: str
    title: str
    hypothesis: str = ""
    method_sketch: str = ""
    literature_gap: str = ""
    variant_type: str = "seed"
    parent_id: str | None = None
    depth: int = 0
    elo_rating: float = 1500.0
    novelty: float = 0.0
    feasibility: float = 0.0
    relevance: float = 0.0
    clarity: float = 0.0
    metadata: dict = field(default_factory=dict)


class IdeaTreeSearch:
    """K-way parallel idea exploration with Elo-based pruning.

    Paper §3.2:
        The RA retrieves relevant historical strategies from M_I and generates
        multiple candidate ideas. These undergo an Elo Tournament competition,
        with the top-ranked idea being synthesized into a complete Research
        Proposal.
    """

    def __init__(
        self,
        tournament: EloTournament | None = None,
        memory=None,  # EvolutionMemory, optional for prior injection
        model: str = "deepseek-chat",
    ):
        self.tournament = tournament or EloTournament(judge_model=model)
        self.memory = memory
        self.model = model

    # ── Public API ───────────────────────────────────────────────────────

    async def search(
        self,
        research_goal: str,
        literature_context: str = "",
        k_directions: int = 3,
        n_branches: int = 3,
        top_k: int = 3,
    ) -> dict:
        """Run full Idea Tree Search pipeline.

        Returns:
            {
                "winner": {...},           # top-1 expanded proposal
                "ranked": [{...}, ...],    # all ranked candidates
                "tree_depth": 3,
                "nodes_explored": N,
                "priors_injected": bool,
            }
        """
        priors = ""
        if self.memory:
            try:
                priors = await self.memory.inject_priors(
                    research_goal, max_chars=1500, caller_role="researcher"
                )
                if priors:
                    research_goal = f"{priors}\n\n---\n\n{research_goal}"
            except Exception as e:
                logger.warning(f"[IdeaTreeSearch] Prior injection failed: {e}")

        # Phase 1: Explore K parallel directions
        logger.info(f"[IdeaTreeSearch] EXPLORE: {k_directions} directions")
        seeds = await self.explore(research_goal, literature_context, k_directions)

        # Phase 2: Branch each seed into N variants
        logger.info(f"[IdeaTreeSearch] BRANCH: {len(seeds)} seeds × {n_branches}")
        all_candidates = list(seeds)
        for seed in seeds:
            branches = await self.branch(seed, research_goal, literature_context, n_branches)
            all_candidates.extend(branches)

        # Phase 3: Elo prune
        logger.info(f"[IdeaTreeSearch] PRUNE: {len(all_candidates)} → top-{top_k}")
        ranked = await self.prune(all_candidates, top_k=top_k)

        # Phase 4: Expand top-1
        logger.info(f"[IdeaTreeSearch] EXPAND: {ranked[0].get('title', 'N/A')[:60]}")
        expanded = await self.expand(ranked[0], research_goal, literature_context)

        return {
            "winner": expanded,
            "ranked": ranked,
            "tree_depth": 3,
            "nodes_explored": len(all_candidates),
            "priors_injected": bool(priors),
        }

    async def explore(
        self,
        research_goal: str,
        literature_context: str = "",
        k: int = 3,
    ) -> list[dict]:
        """Phase 1: Generate K distinct research directions."""
        prompt = EXPLORE_SYSTEM_PROMPT.format(k=k) + f"""

Research Goal:
{research_goal}

Literature Context:
{literature_context[:4000] if literature_context else "No prior literature provided."}

Generate exactly {k} distinct research directions."""
        response = await self._call_llm(prompt)
        items = _extract_json_array(response)
        if not items:
            logger.warning("[IdeaTreeSearch] Could not parse explore response")
            return self._fallback_seeds(k)

        seeds = []
        for i, item in enumerate(items[:k]):
            seeds.append({
                "id": f"seed-{i+1}",
                "title": item.get("title", f"Direction {i+1}"),
                "hypothesis": item.get("hypothesis", ""),
                "method_sketch": item.get("method_sketch", ""),
                "literature_gap": item.get("literature_gap", ""),
                "depth": 0,
                "variant_type": "seed",
            })
        return seeds

    async def branch(
        self,
        seed: dict,
        research_goal: str,
        literature_context: str = "",
        n: int = 3,
    ) -> list[dict]:
        """Phase 2: Branch a seed idea into N refined variants."""
        prompt = BRANCH_SYSTEM_PROMPT.format(n=n) + f"""

Research Goal:
{research_goal}

Seed Idea:
Title: {seed.get('title', 'Untitled')}
Hypothesis: {seed.get('hypothesis', '')[:600]}
Method Sketch: {seed.get('method_sketch', '')[:600]}

Literature Context:
{literature_context[:2000] if literature_context else "No prior literature."}

Generate exactly {n} variants."""
        response = await self._call_llm(prompt)
        items = _extract_json_array(response)
        if not items:
            logger.warning("[IdeaTreeSearch] Could not parse branch response")
            return []

        seed_id = seed.get("id", "seed-0")
        branches = []
        for i, item in enumerate(items[:n]):
            branches.append({
                "id": f"{seed_id}-b{i+1}",
                "parent_id": seed_id,
                "title": item.get("title", f"Variant {i+1}"),
                "hypothesis": item.get("hypothesis", ""),
                "method_sketch": item.get("method_sketch", ""),
                "variant_type": item.get("variant_type", "enhancement"),
                "depth": 1,
            })
        return branches

    async def prune(
        self,
        candidates: list[dict],
        top_k: int = 3,
    ) -> list[dict]:
        """Phase 3: Elo tournament pruning to top-K."""
        if len(candidates) <= top_k:
            for c in candidates:
                c["elo_rating"] = 1500.0
            return candidates

        ranked = await self.tournament.rank(candidates)
        return ranked[:top_k]

    async def expand(
        self,
        idea: dict,
        research_goal: str,
        literature_context: str = "",
    ) -> dict:
        """Phase 4: Expand top-1 idea into a full research proposal."""
        prompt = f"""Research Goal:
{research_goal}

Selected Idea:
Title: {idea.get('title', 'Untitled')}
Hypothesis: {idea.get('hypothesis', '')}
Method Sketch: {idea.get('method_sketch', '')}

Literature Context:
{literature_context[:3000] if literature_context else "No prior literature."}

Expand this idea into a full research proposal."""
        response = await self._call_llm(prompt, system=EXPAND_SYSTEM_PROMPT)
        parsed = _parse_json_response(response)

        if parsed:
            return {
                "id": idea.get("id", "top-1"),
                "title": parsed.get("title", idea.get("title", "")),
                "abstract": parsed.get("abstract", ""),
                "problem_definition": parsed.get("problem_definition", ""),
                "related_work": parsed.get("related_work", ""),
                "proposed_method": parsed.get("proposed_method", ""),
                "experimental_design": parsed.get("experimental_design", ""),
                "contributions": parsed.get("contributions", ""),
                "limitations": parsed.get("limitations", ""),
                "elo_rating": idea.get("elo_rating", 1500.0),
            }
        # Fallback: return raw response as proposal
        return {
            "id": idea.get("id", "top-1"),
            "title": idea.get("title", ""),
            "proposed_method": response,
            "elo_rating": idea.get("elo_rating", 1500.0),
        }

    # ── Internal ──────────────────────────────────────────────────────────

    async def _call_llm(self, user_prompt: str, system: str = "") -> str:
        """Call LLM via OpenAI-compatible API."""
        try:
            api_key = os.environ.get("DEEPSEEK_API_KEY", "")
            base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

            if not api_key:
                api_key = os.environ.get("OPENAI_API_KEY", "")
                base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

            import httpx

            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.post(
                    f"{base_url}/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system or "You are a senior research scientist. Respond with ONLY valid JSON."},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": 0.3,
                        "max_tokens": 4000,
                    },
                )
                data = resp.json()
                return data["choices"][0]["message"]["content"]

        except Exception as e:
            logger.error(f"[IdeaTreeSearch] LLM call failed: {e}")
            raise

    def _fallback_seeds(self, k: int) -> list[dict]:
        """Generate minimal fallback seeds when LLM fails."""
        return [
            {
                "id": f"fallback-{i+1}",
                "title": f"Direction {i+1}",
                "hypothesis": f"Alternative research direction {i+1}.",
                "method_sketch": "To be refined.",
                "depth": 0,
                "variant_type": "seed",
            }
            for i in range(k)
        ]
