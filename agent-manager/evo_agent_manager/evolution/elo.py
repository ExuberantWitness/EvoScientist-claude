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
        "dimensions": ["elo_novelty", "validity", "impact", "reliability", "product_satisfaction"],
        "elo_novelty": "科学创新性——是否具备相对于先前工作的非显而易见性？是否有合理的科学实用性？是否开辟专家认为值得探索的研究方向？",
        "validity": "潜在有效性——问题-方法-执行-结论链条是否合理？方法是否适当？证据是否支撑主张？",
        "impact": "潜在影响力——是否可能加速有意义的研究？成果是否可复用？是否有领域长期价值？",
        "reliability": "潜在可靠性——行为是否一致稳定？对扰动是否鲁棒？是否能检测并恢复故障？",
        "product_satisfaction": "产物规格满足度——方案是否完整覆盖了产物规格中所有必选项？每个必选项是否充分展开？",
        "scenario": "导师组会 — 问题讨论环节",
    },
    "W2.2 Solution Directions": {
        "dimensions": ["elo_novelty", "validity", "impact", "reliability", "product_satisfaction"],
        "elo_novelty": "科学创新性——方向是否具有非显而易见性？是否基于对难点的深入理解提出新路径？",
        "validity": "潜在有效性——方向的论证链条是否合理？技术路径是否有理论或实验依据？",
        "impact": "潜在影响力——该方向如果成功，是否可能显著提升Hopper-v4控制能力？",
        "reliability": "潜在可靠性——该方向是否足够稳健，不会因实现细节差异而完全失效？",
        "product_satisfaction": "产物规格满足度——方向描述是否完整覆盖了产物规格中的所有必选项？",
        "scenario": "导师组会 — 方向讨论环节",
    },
    "W2.3 Search Keywords": {
        "dimensions": ["elo_novelty", "validity", "impact", "reliability", "product_satisfaction"],
        "elo_novelty": "科学创新性——检索策略是否覆盖了非显而易见的子主题和跨领域关联？",
        "validity": "潜在有效性——检索词是否能命中相关文献而非噪声？覆盖是否全面？",
        "impact": "潜在影响力——检索策略是否可能发现具有高影响力的关键文献？",
        "reliability": "潜在可靠性——检索策略在不同数据库中是否一致有效？是否有鲁棒的同义词覆盖？",
        "product_satisfaction": "产物规格满足度——是否完整提供了检索词列表、搜索目标、预期文献类型和子主题覆盖？",
        "scenario": "导师组会 — 搜索策略讨论环节",
    },
    "W3 Research": {
        "dimensions": ["elo_novelty", "validity", "impact", "reliability", "product_satisfaction"],
        "elo_novelty": "科学创新性——方案是否具备相对于先前工作的非显而易见性？是否有合理的科学实用性？是否开辟专家认为值得探索的研究方向？",
        "validity": "潜在有效性——方案是否有文献依据？方法是否适当？论证链条是否合理？",
        "impact": "潜在影响力——方案如果成功，是否可能显著提升Hopper-v4控制能力？成果是否可复用？",
        "reliability": "潜在可靠性——方案在算力/时间约束下是否可实现？对实现细节是否鲁棒？",
        "product_satisfaction": "产物规格满足度——方案是否包含修改组件/文献依据/可行性估计/量化对比预期？",
        "scenario": "学术论文答辩 — 专家评审团",
    },
    "W3.5 Ideate": {
        "dimensions": ["elo_novelty", "validity", "impact", "reliability", "product_satisfaction"],
        "elo_novelty": "科学创新性——伪代码层面的实现是否体现了非显而易见的创新？",
        "validity": "潜在有效性——伪代码是否能直接翻译为可运行代码？架构改动是否合理？",
        "impact": "潜在影响力——该实现如果完成，是否可能对Hopper-v4控制产生显著影响？",
        "reliability": "潜在可靠性——实现是否对超参数/环境变化鲁棒？计算开销是否可接受？",
        "product_satisfaction": "产物规格满足度——是否包含伪代码/架构改动列表/损失函数签名/计算开销估计？",
        "scenario": "软件开发 — 专家评审团",
    },
}


# ── Structural pre-check: deterministic keyword validation per product spec ──
# Maps Chinese/English required-item descriptions to detection regex patterns.
# Each pattern list is OR'd — if NONE match, the item is deemed missing.
_STRUCTURAL_PATTERNS: dict[str, list[str]] = {
    # W2.1 Problem Analysis
    "具体难点": [r"(难点|瓶颈|问题|bottleneck|limitation|challenge)"],
    "因果分析": [r"(因果|causal|because|由于|导致|causes?)"],
    "baseline为何无法解决": [r"(baseline|基线|无法解决|cannot|cannot solve|局限|limitation)"],
    # W2.2 Solution Directions
    "方向描述": [r"(方向|direction|approach|方案|proposal|解决)"],
    "针对哪些难点": [r"(针对|address|target|关联|W2\\.1|难点)"],
    "技术路径概要": [r"(技术路径|technical|method|方法|architecture|架构|pipeline)"],
    "与baseline的区分点": [r"(区分|不同于|different|unlike|distinct|区别于|baseline)"],
    # W2.3 Search Keywords
    "检索词列表": [r"(检索词|search term|keyword|查询|query|搜索词)"],
    "搜索目标": [r"(搜索目标|search (target|goal|objective)|搜什么|search for)"],
    "预期命中": [r"(预期命中|expected|literature type|文献类型|paper type|conference|journal|预期找到)"],
    "子主题列表": [r"(子主题|subtopic|sub-topic|覆盖|coverage|领域|domain)"],
    # W3 Research
    "修改哪些组件": [r"(修改|modif|组件|component|module|Critic|Actor|网络|network|损失|loss)"],
    "文献依据": [r"(文献|literature|paper|引用|reference|citation|et al\\.|arXiv|ICML|NeurIPS)"],
    "可行性估计": [r"(可行|feasib|计算开销|comput\w* cost|复杂度|complexity|实现|implement)"],
    "量化对比预期": [r"(对比|compar\w*|baseline|基线|提升|improv|better|outperform|预期|expect)"],
    # W3.5 Ideate
    "伪代码": [r"(伪代码|pseudocode|python|def |class |```)"],
    "架构改动列表": [r"(架构改动|architect\w* (change|modif)|ADD|MODIFY|REMOVE|增|删|改)"],
    "损失函数签名": [r"(损失函数|loss function|def .*\\(.*\\)|fn_name|Tensor|损失.*签名)"],
    "计算开销估计": [r"(计算开销|comput\w* cost|复杂度|complexity|overhead|FLOPs|参数|param)"],
}


def _structural_check(proposals: list[dict], product_spec: dict) -> list[str]:
    """Deterministic structural check: verify required items exist in proposal text.

    Returns list of failure descriptions. Empty list = all checks passed.
    This catches format-level mismatches (e.g., W3 proposals submitted for W2.3 spec)
    BEFORE the expensive LLM judge runs.
    """
    required = product_spec.get("required", [])
    if not required:
        return []

    import re as _re_sc
    failures = []
    for item_desc in required:
        patterns = None
        for key, pats in _STRUCTURAL_PATTERNS.items():
            if key in item_desc:
                patterns = pats
                break

        if patterns is None:
            continue

        found = False
        for p in proposals:
            text = " ".join([
                p.get("method_sketch", ""),
                p.get("hypothesis", ""),
                p.get("title", ""),
            ])
            for pat in patterns:
                if _re_sc.search(pat, text, _re_sc.IGNORECASE):
                    found = True
                    break
            if found:
                break

        if not found:
            failures.append(
                f"MISSING: '{item_desc}' — no proposal contains required patterns: {patterns[:3]}"
            )

    return failures


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

        # ── Structural pre-check: deterministic keyword/pattern validation ──
        # Runs BEFORE LLM judge to catch format-level mismatches.
        if product_spec:
            struct_failures = _structural_check(ranked_proposals[:3], product_spec)
            if struct_failures:
                return {
                    "verdict": "missing",
                    "details": f"Structural check failed: {'; '.join(struct_failures[:5])}",
                    "supplemented_text": None,
                    "failures_per_proposal": {
                        p.get("title", "?")[:60]: "Required items missing per structural check"
                        for p in ranked_proposals[:3]
                    },
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
