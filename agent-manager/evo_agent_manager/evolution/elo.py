"""Elo Tournament — pairwise comparison for idea ranking (paper §3.3).

EvoScientist uses an Elo-based tournament because it relies on pairwise
comparisons and can produce a stable ranking under noisy judgments without
requiring calibrated absolute scores.

Phase-specific evaluation dimensions are defined in ELO_DIMENSIONS.
Every phase includes product_satisfaction as a universal dimension.

Full round-robin: N*(N-1)/2 comparisons. K=32, initial rating=1500.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Phase-specific ELO dimension definitions
# ---------------------------------------------------------------------------

ELO_DIMENSIONS: dict[str, dict] = {
    "W2.1 Problem Analysis": {
        "dimensions": ["clarity", "reasonableness", "product_satisfaction"],
        "clarity": "问题难点分析的清晰度——是否准确识别了核心瓶颈？表述是否具体而非笼统？",
        "reasonableness": "难点分析的合理度——是否基于对算法的深入理解？分析是否有因果逻辑链？",
        "product_satisfaction": "产物满足度——是否包含了该阶段要求的全部产物？每个产物的质量是否达标？",
        "scenario": "导师组会 — 问题讨论环节",
    },
    "W2.2 Solution Directions": {
        "dimensions": ["reasonableness", "product_satisfaction"],
        "reasonableness": "解决思路的合理性——方向是否针对识别的难点？是否有理论或实验依据？",
        "product_satisfaction": "产物满足度——是否包含了该阶段要求的全部产物？每个产物的质量是否达标？",
        "scenario": "导师组会 — 方向讨论环节",
    },
    "W2.3 Search Keywords": {
        "dimensions": ["detail", "reasonableness", "product_satisfaction"],
        "detail": "检索词的详细度——是否覆盖了方向的所有子主题？是否包含同义词和变体？",
        "reasonableness": "检索词的合理性——是否能命中相关文献而非噪声？",
        "product_satisfaction": "产物满足度——是否包含了该阶段要求的全部产物？每个产物的质量是否达标？",
        "scenario": "导师组会 — 搜索策略讨论环节",
    },
    "W3 Research": {
        "dimensions": ["feasibility", "novelty", "relevance", "product_satisfaction"],
        "feasibility": "方案可行性——在给定算力和时间内能否实现？依赖是否合理？",
        "novelty": "方案创新性——是否与已有工作有明确区分？贡献点是否清晰？",
        "relevance": "方案相关性——是否直接针对问题难点？是否基于文献依据？",
        "product_satisfaction": "产物满足度——是否包含了该阶段要求的全部产物？每个产物的质量是否达标？",
        "scenario": "学术论文答辩 — 专家评审团",
    },
    "W3.5 Ideate": {
        "dimensions": ["feasibility", "relevance", "product_satisfaction"],
        "feasibility": "伪代码可实现性——是否能直接翻译为代码？架构改动是否清晰？计算开销是否可接受？",
        "relevance": "方案与原始问题的一致性——是否偏离了问题难点和解决思路？",
        "product_satisfaction": "产物满足度——是否包含了该阶段要求的全部产物？每个产物的质量是否达标？",
        "scenario": "软件开发 — 专家评审团",
    },
}


class RegenerationVerdict(Enum):
    """Result of post-ELO regeneration/product-verification judgment."""
    PASS = "pass"                  # All good, proceed
    MISSING_ITEMS = "missing"      # Required items entirely absent → regenerate
    INSUFFICIENT_INFO = "insufficient"  # Info present but quality insufficient → regenerate
    FORMAT_ISSUE = "format"        # Info there but poorly formatted → judge supplements


def _build_judge_prompt(phase: str) -> str:
    """Build the judge system prompt for a specific phase."""
    dims = ELO_DIMENSIONS.get(phase, ELO_DIMENSIONS.get("W3 Research", {}))
    dim_names = dims.get("dimensions", ["novelty", "feasibility", "relevance", "clarity"])
    scenario = dims.get("scenario", "学术评审")

    dim_descriptions = []
    for d in dim_names:
        desc = dims.get(d, d)
        dim_descriptions.append(f"{dim_names.index(d) + 1}. **{d}** — {desc}")

    dim_list = "\n".join(dim_descriptions)
    dim_scores_json = ", ".join(f'"{d}": N' for d in dim_names)

    return f"""You are an expert scientific research judge evaluating proposals.
Scenario: {scenario}

Compare two proposals across {len(dim_names)} dimensions and determine a winner.

For each proposal, assign scores 1-10 on:
{dim_list}

Be critical and precise. A score of 5 means average/acceptable. Only give 8+ for truly exceptional work.

Respond with ONLY a JSON object (no markdown, no extra text):
{{"winner": "A"|"B"|"tie", "scores": {{"A": {{{dim_scores_json}}}, "B": {{{dim_scores_json}}}}}, "reasoning": "brief justification"}}"""


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

    Supports phase-specific evaluation dimensions (ELO_DIMENSIONS).
    Every phase includes product_satisfaction as a universal dimension.
    Post-ELO: judges regeneration needs (missing/insufficient/format issues).
    """

    def __init__(
        self,
        judge_model: str = "deepseek-chat",
        k_factor: float = 32.0,
        initial_rating: float = 1500.0,
        max_rounds: int | None = None,
        phase: str = "W3 Research",
    ):
        self.judge_model = judge_model
        self.k_factor = k_factor
        self.initial_rating = initial_rating
        self.max_rounds = max_rounds  # None = full round-robin
        self.phase = phase
        self._dims = ELO_DIMENSIONS.get(phase, {})
        self._dim_names = self._dims.get("dimensions", ["novelty", "feasibility", "relevance", "clarity"])
        self._judge_prompt = _build_judge_prompt(phase)

    @property
    def dimension_names(self) -> list[str]:
        return list(self._dim_names)

    async def rank(self, proposals: list[dict]) -> list[dict]:
        """Rank proposals via Elo tournament.

        Args:
            proposals: [{id, title, hypothesis, method_sketch}, ...]

        Returns:
            Proposals sorted by elo_rating (descending), each with:
            elo_rating and per-dimension averaged scores.
        """
        n = len(proposals)
        if n < 2:
            for p in proposals:
                p["elo_rating"] = self.initial_rating
            return proposals

        ratings = {p["id"]: self.initial_rating for p in proposals}
        dim_scores: dict[str, dict[str, list[float]]] = {
            p["id"]: {d: [] for d in self._dim_names}
            for p in proposals
        }

        # Generate all matchups (full round-robin)
        matchups = [(i, j) for i in range(n) for j in range(i + 1, n)]
        if self.max_rounds and self.max_rounds < len(matchups):
            import random
            matchups = random.sample(matchups, self.max_rounds)

        logger.info(
            f"[EloTournament] Starting: {n} proposals, {len(matchups)} matchups, "
            f"phase={self.phase}, dims={self._dim_names}"
        )

        sem = asyncio.Semaphore(5)
        tasks = [
            self._process_matchup(i, j, proposals, ratings, dim_scores, sem)
            for i, j in matchups
        ]
        await asyncio.gather(*tasks)

        # Compute final scores
        for p in proposals:
            p["elo_rating"] = ratings[p["id"]]
            ds = dim_scores[p["id"]]
            for dim in self._dim_names:
                scores = ds[dim]
                p[dim] = sum(scores) / len(scores) if scores else 0.0

        ranked = sorted(proposals, key=lambda p: p["elo_rating"], reverse=True)

        logger.info(
            f"[EloTournament] Complete: winner='{ranked[0].get('title', 'N/A')[:50]}' "
            f"(elo={ranked[0]['elo_rating']:.0f})"
        )
        return ranked

    async def verify_and_judge_regeneration(
        self, ranked_proposals: list[dict], product_spec: dict | None = None
    ) -> dict:
        """Post-ELO product verification and regeneration judgment.

        Returns:
            {
                "verdict": "pass" | "missing" | "insufficient" | "format",
                "details": "explanation of the judgment",
                "supplemented_text": "corrected text if format issue, else null",
                "failures_per_proposal": {"proposal_id": "reason", ...}
            }
        """
        if not ranked_proposals:
            return {"verdict": "missing", "details": "No proposals to verify", "supplemented_text": None}

        # Check product_satisfaction scores first
        ps_threshold = 4.0  # Below this is insufficient
        any_passing = False
        failures = {}

        for p in ranked_proposals:
            ps = p.get("product_satisfaction", 0.0)
            if ps >= ps_threshold:
                any_passing = True
            else:
                failures[p.get("id", "?")] = f"product_satisfaction={ps:.1f} below threshold {ps_threshold}"

        if not any_passing:
            return {
                "verdict": "insufficient",
                "details": f"All proposals below product_satisfaction threshold ({ps_threshold}). "
                           f"Lowest: {min(p.get('product_satisfaction', 0) for p in ranked_proposals):.1f}",
                "supplemented_text": None,
                "failures_per_proposal": failures,
            }

        # Use LLM judge for deeper verification: check for missing items / format issues
        top3 = ranked_proposals[:3]
        try:
            verify_prompt = self._build_verification_prompt(top3, product_spec)
            response = await self._call_judge(verify_prompt)
            parsed = _parse_json_response(response)

            if parsed:
                verdict_str = parsed.get("verdict", "pass")
                try:
                    verdict = RegenerationVerdict(verdict_str)
                except ValueError:
                    verdict = RegenerationVerdict.PASS
                return {
                    "verdict": verdict.value,
                    "details": parsed.get("details", ""),
                    "supplemented_text": parsed.get("supplemented_text"),
                    "failures_per_proposal": parsed.get("failures_per_proposal", failures),
                }
        except Exception as e:
            logger.warning(f"[EloTournament] Verification call failed: {e}")

        return {"verdict": "pass", "details": "Verification skipped (API error)", "supplemented_text": None}

    def _build_verification_prompt(self, proposals: list[dict], product_spec: dict | None) -> str:
        """Build the verification/judgment prompt for post-ELO analysis."""
        proposals_text = []
        for i, p in enumerate(proposals):
            proposals_text.append(
                f"Proposal {i+1}: {p.get('title', 'Untitled')}\n"
                f"Hypothesis: {p.get('hypothesis', '')[:500]}\n"
                f"Method: {p.get('method_sketch', '')[:500]}\n"
                f"Scores: { {d: p.get(d, 0) for d in self._dim_names} }"
            )

        spec_text = json.dumps(product_spec, ensure_ascii=False, indent=2) if product_spec else "Use the phase's default product specification rules to judge completeness."

        return f"""You are a product verification judge for phase: {self.phase}.
Your job: check if the winning proposals meet the product specification.

## Product Specification
{spec_text}

## Proposals to Verify
{chr(10).join(proposals_text)}

## Judgment Instructions
For each proposal, check:
1. Are ALL required items from the product spec present? (MISSING = any required item absent)
2. Is the information sufficient in quality and depth? (INSUFFICIENT = present but too shallow)
3. Is the information well-formatted and clearly expressed? (FORMAT = info is there but messy)

Output ONLY JSON:
{{
  "verdict": "pass" | "missing" | "insufficient" | "format",
  "details": "explanation of the judgment for each proposal",
  "supplemented_text": "if format issue, provide the cleaned-up version of the best proposal's content",
  "failures_per_proposal": {{"proposal_title": "what is missing or insufficient"}}
}}

If verdict is "format", supply the FIXED version in supplemented_text.
If ALL proposals have missing items, verdict is "missing".
If proposals have the info but it's not deep enough, verdict is "insufficient"."""

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
                for dim in self._dim_names:
                    if "A" in scores and dim in scores["A"]:
                        dim_scores[a_id][dim].append(scores["A"][dim])
                    if "B" in scores and dim in scores["B"]:
                        dim_scores[b_id][dim].append(scores["B"][dim])

    async def _compare(self, a: dict, b: dict) -> tuple[str | None, dict | None]:
        """LLM judge pairwise comparison using phase-specific prompt."""
        prompt = f"""Proposal A: {a.get('title', 'Untitled')}
{a.get('hypothesis', '')[:800]}

{a.get('method_sketch', '')[:800]}

---

Proposal B: {b.get('title', 'Untitled')}
{b.get('hypothesis', '')[:800]}

{b.get('method_sketch', '')[:800]}"""

        try:
            response = await self._call_judge(prompt, use_phase_prompt=True)
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

    async def _call_judge(self, prompt: str, use_phase_prompt: bool = False) -> str:
        """Call the LLM judge model."""
        system_prompt = self._judge_prompt if use_phase_prompt else _build_judge_prompt(self.phase)

        try:
            import os

            api_key = os.environ.get("DEEPSEEK_API_KEY", "")
            base_url = os.environ.get(
                "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
            )

            if not api_key:
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
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.1,
                        "max_tokens": 1500,
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
        """Standard Elo rating update."""
        k = 32.0
        ea = 1.0 / (1.0 + 10.0 ** ((rb - ra) / 400.0))
        eb = 1.0 - ea

        if winner_is_a is True:
            sa, sb = 1.0, 0.0
        elif winner_is_a is False:
            sa, sb = 0.0, 1.0
        else:
            sa, sb = 0.5, 0.5

        ra_new = ra + k * (sa - ea)
        rb_new = rb + k * (sb - eb)
        return ra_new, rb_new
