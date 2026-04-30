"""Elo Tournament — pairwise comparison for idea ranking (paper §3.3).

EvoScientist uses an Elo-based tournament because it relies on pairwise
comparisons and can produce a stable ranking under noisy judgments without
requiring calibrated absolute scores.

Four evaluation dimensions:
- Novelty: new methods or perspectives
- Feasibility: technically achievable, reasonable resource needs
- Relevance: closely aligned with user goal
- Clarity: clear expression, specific experiment plan

Full round-robin: N*(N-1)/2 comparisons. K=32, initial rating=1500.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

JUDGE_SYSTEM_PROMPT = """You are an expert scientific research judge evaluating research proposals.
Compare two proposals across 4 dimensions and determine a winner.

For each proposal, assign scores 1-10 on:
1. **Novelty** — Does it propose genuinely new methods, perspectives, or combinations?
2. **Feasibility** — Is it technically achievable with reasonable resources? Are the methods concrete?
3. **Relevance** — How closely does it address the core research question?
4. **Clarity** — Is the hypothesis clear? Is the experiment plan specific and actionable?

Be critical and precise. A score of 5 means average/acceptable. Only give 8+ for truly exceptional work.

Respond with ONLY a JSON object (no markdown, no extra text):
{"winner": "A"|"B"|"tie", "scores": {"A": {"novelty": N, "feasibility": N, "relevance": N, "clarity": N}, "B": {"novelty": N, "feasibility": N, "relevance": N, "clarity": N}}, "reasoning": "brief justification"}"""


def _parse_json_response(response: str) -> dict | None:
    """Robust JSON extraction from LLM response that may have markdown fences."""
    text = response.strip()
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try extracting from ```json fence
    import re
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Try finding first { ... } block
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


@dataclass
class Idea:
    """A research idea / proposal with Elo rating."""

    id: str
    title: str
    hypothesis: str = ""
    method_sketch: str = ""
    novelty: float = 0.0
    feasibility: float = 0.0
    relevance: float = 0.0
    clarity: float = 0.0
    elo_rating: float = 1500.0
    source_agent: str = ""
    metadata: dict = field(default_factory=dict)


class EloTournament:
    """Elo-based tournament for ranking research proposals.

    Paper §3.3:
        {r_1, ..., r_{N_I}} = EloRank(I_{1:N_I})
        Top-3 retained for direction summarization.
        Top-1 extended into a full research proposal.
    """

    def __init__(
        self,
        judge_model: str = "deepseek-chat",
        k_factor: float = 32.0,
        initial_rating: float = 1500.0,
        max_rounds: int | None = None,
    ):
        self.judge_model = judge_model
        self.k_factor = k_factor
        self.initial_rating = initial_rating
        self.max_rounds = max_rounds  # None = full round-robin

    async def rank(self, proposals: list[dict]) -> list[dict]:
        """Rank proposals via Elo tournament.

        Args:
            proposals: [{id, title, hypothesis, method_sketch}, ...]

        Returns:
            Proposals sorted by elo_rating (descending), each with:
            elo_rating, novelty, feasibility, relevance, clarity fields added.
        """
        n = len(proposals)
        if n < 2:
            for p in proposals:
                p["elo_rating"] = self.initial_rating
            return proposals

        ratings = {p["id"]: self.initial_rating for p in proposals}
        # Track per-dimension scores for averaging later
        dim_scores: dict[str, dict[str, list[float]]] = {
            p["id"]: {"novelty": [], "feasibility": [], "relevance": [], "clarity": []}
            for p in proposals
        }

        # Generate all matchups (full round-robin)
        matchups = [(i, j) for i in range(n) for j in range(i + 1, n)]
        if self.max_rounds and self.max_rounds < len(matchups):
            import random
            matchups = random.sample(matchups, self.max_rounds)

        logger.info(
            f"[EloTournament] Starting tournament: {n} proposals, "
            f"{len(matchups)} matchups, judge={self.judge_model}"
        )

        # Process matchups sequentially to avoid rate limits
        # (can be parallelized later with semaphore)
        sem = asyncio.Semaphore(5)  # max 5 concurrent comparisons
        tasks = [
            self._process_matchup(i, j, proposals, ratings, dim_scores, sem)
            for i, j in matchups
        ]
        await asyncio.gather(*tasks)

        # Sort by Elo rating descending
        for p in proposals:
            p["elo_rating"] = ratings[p["id"]]
            # Average dimension scores
            ds = dim_scores[p["id"]]
            for dim in ["novelty", "feasibility", "relevance", "clarity"]:
                scores = ds[dim]
                p[dim] = sum(scores) / len(scores) if scores else 0.0

        ranked = sorted(proposals, key=lambda p: p["elo_rating"], reverse=True)

        logger.info(
            f"[EloTournament] Complete: winner='{ranked[0].get('title', 'N/A')[:50]}' "
            f"(elo={ranked[0]['elo_rating']:.0f}), "
            f"range={ranked[0]['elo_rating'] - ranked[-1]['elo_rating']:.0f}"
        )
        return ranked

    async def _process_matchup(
        self,
        i: int,
        j: int,
        proposals: list[dict],
        ratings: dict[str, float],
        dim_scores: dict[str, dict[str, list[float]]],
        sem: asyncio.Semaphore,
    ) -> None:
        """Process a single pairwise comparison."""
        async with sem:
            try:
                winner_id, scores = await self._compare(proposals[i], proposals[j])
            except Exception as e:
                logger.warning(f"[EloTournament] Comparison failed for {i}-{j}: {e}")
                return

            a_id = proposals[i]["id"]
            b_id = proposals[j]["id"]

            # Update Elo ratings
            ra = ratings[a_id]
            rb = ratings[b_id]
            if winner_id == a_id:
                ra_new, rb_new = self._elo_update(ra, rb, winner_is_a=True)
            elif winner_id == b_id:
                ra_new, rb_new = self._elo_update(ra, rb, winner_is_a=False)
            else:  # tie
                ra_new, rb_new = self._elo_update(ra, rb, winner_is_a=None)
            ratings[a_id] = ra_new
            ratings[b_id] = rb_new

            # Record dimension scores
            if scores:
                for dim in ["novelty", "feasibility", "relevance", "clarity"]:
                    if "A" in scores and dim in scores["A"]:
                        dim_scores[a_id][dim].append(scores["A"][dim])
                    if "B" in scores and dim in scores["B"]:
                        dim_scores[b_id][dim].append(scores["B"][dim])

    async def _compare(self, a: dict, b: dict) -> tuple[str | None, dict | None]:
        """LLM judge pairwise comparison.

        Returns:
            (winner_id, scores_dict) — winner_id is the winning proposal's id,
            or None for tie. scores_dict has {"A": {...}, "B": {...}}.
        """
        prompt = f"""Proposal A: {a.get('title', 'Untitled')}
{a.get('hypothesis', '')[:800]}

{a.get('method_sketch', '')[:800]}

---

Proposal B: {b.get('title', 'Untitled')}
{b.get('hypothesis', '')[:800]}

{b.get('method_sketch', '')[:800]}"""

        try:
            # Import dynamically to avoid hard dependency
            response = await self._call_judge(prompt)
            parsed = _parse_json_response(response)
            if parsed is None:
                logger.warning("[EloTournament] Could not parse judge response")
                return None, None

            winner = parsed.get("winner", "tie").upper()
            scores = parsed.get("scores", {})

            if winner == "A":
                return a["id"], scores
            elif winner == "B":
                return b["id"], scores
            else:
                return None, scores  # tie

        except Exception as e:
            logger.warning(f"[EloTournament] Judge call failed: {e}")
            return None, None

    async def _call_judge(self, comparison_prompt: str) -> str:
        """Call the LLM judge model.

        Uses the mcp__llm-chat__chat tool if available (deepseek-reasoner),
        otherwise falls back to OpenAI-compatible API call.
        """
        # Try to use the existing LLM chat MCP tool pattern
        # Since we're inside an MCP server, we call the LLM API directly
        try:
            import os

            api_key = os.environ.get("DEEPSEEK_API_KEY", "")
            base_url = os.environ.get(
                "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
            )

            if not api_key:
                # Fallback: try OpenAI-compatible endpoint
                api_key = os.environ.get("OPENAI_API_KEY", "")
                base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

            import httpx

            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{base_url}/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.judge_model,
                        "messages": [
                            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                            {"role": "user", "content": comparison_prompt},
                        ],
                        "temperature": 0.1,
                        "max_tokens": 1000,
                    },
                )
                data = resp.json()
                return data["choices"][0]["message"]["content"]

        except Exception as e:
            logger.error(f"[EloTournament] LLM call failed: {e}")
            raise

    @staticmethod
    def _elo_update(
        ra: float, rb: float, winner_is_a: bool | None
    ) -> tuple[float, float]:
        """Standard Elo rating update.

        Args:
            ra, rb: Current Elo ratings.
            winner_is_a: True if A won, False if B won, None for tie.

        Returns:
            (ra_new, rb_new)
        """
        k = 32.0
        ea = 1.0 / (1.0 + 10.0 ** ((rb - ra) / 400.0))
        eb = 1.0 - ea

        if winner_is_a is True:
            sa, sb = 1.0, 0.0
        elif winner_is_a is False:
            sa, sb = 0.0, 1.0
        else:  # tie
            sa, sb = 0.5, 0.5

        ra_new = ra + k * (sa - ea)
        rb_new = rb + k * (sb - eb)
        return ra_new, rb_new
