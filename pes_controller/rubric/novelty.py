"""LLM + Baseline Rubric fine-grained novelty evaluation.

Stage 2 of the RND pipeline:
- 5 evaluation dimensions with dynamic LLM-determined weights
- Compares proposal against baseline rubrics and BGE-M3 nearest neighbors
- Produces novelty_fine (0-1)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)

RUBRIC_DIMENSIONS = [
    "problem_novelty",
    "method_novelty",
    "experiment_novelty",
    "theory_novelty",
    "essential_difference",
]

DIMENSION_DESCRIPTIONS = {
    "problem_novelty": "问题/动机新颖度 — 是否提出新问题、新场景或新视角? (1=已有问题的微小变体, 10=全新问题或范式转换)",
    "method_novelty": "方法/框架新颖度 — 是否提出新算法、新架构或已有方法的新组合? (1=直接复用已知方法, 10=全新的算法设计)",
    "experiment_novelty": "实验/评估新颖度 — 是否引入新评估指标、新数据集或新baseline对比? (1=标准评估, 10=全新的验证方式)",
    "theory_novelty": "理论/分析新颖度 — 是否提供新的理论证明、新的解释或新的分析视角? (1=纯实验无理论, 10=深刻的理论贡献)",
    "essential_difference": "与最相似baseline的本质差异 — 方案核心机制与最相关的已知方法的区别是否根本性? (1=仅表面修改/换说法, 10=底层机制完全不同)",
}


@dataclass
class BaselineRubric:
    """A known baseline used as an evaluation anchor."""
    name: str
    short_desc: str
    cc_atoms_summary: str = ""


@dataclass
class NoveltyReport:
    """Result of rubric evaluation."""
    novelty_score: float          # 0-1, 1 = most novel
    dimension_scores: dict[str, float]  # per-dimension 1-10
    weights: dict[str, float]     # LLM-determined dynamic weights
    explanation: str              # LLM's reasoning


class RubricNoveltyEvaluator:
    """LLM-powered 5-dimension rubric novelty evaluation."""

    def __init__(self, llm_call: Callable[[str], Awaitable[str]] | None = None,
                 baselines: dict[str, str] | None = None):
        self._llm_call = llm_call
        self._rubrics: dict[str, BaselineRubric] = {}
        if baselines:
            for name, desc in baselines.items():
                self._rubrics[name] = BaselineRubric(name=name, short_desc=desc)

    # ------------------------------------------------------------------
    # Rubric management
    # ------------------------------------------------------------------

    @classmethod
    def load_baselines_from_cc(
        cls, cc_atoms: list[dict],
        confirmed_baselines: list[str] | None = None,
    ) -> dict[str, str]:
        """Dynamically build baseline descriptions from CC atoms and confirmed baselines.

        Priority: (1) CC atoms with baseline tags, (2) confirmed_baselines from state.
        Returns empty dict if no baselines found — evaluator falls back to BGE-M3 neighbors.
        """
        descriptions: dict[str, str] = {}
        for a in (cc_atoms or []):
            tags = a.get("tags", [])
            if a.get("type") == "fact" and "baseline" in tags:
                name = a.get("title", "")
                content = a.get("content", "")
                if name and name not in descriptions:
                    try:
                        c = json.loads(content) if isinstance(content, str) else content
                        desc = c.get("description", c.get("method", content)) if isinstance(c, dict) else content
                    except (json.JSONDecodeError, TypeError):
                        desc = content
                    descriptions[name] = str(desc)[:300] if desc else name
        if not descriptions and confirmed_baselines:
            if isinstance(confirmed_baselines, dict):
                # Flatten dict-of-lists format from evo-pipeline SKILL.md Step 3
                for cat, items in confirmed_baselines.items():
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, str):
                                descriptions[item] = f"Baseline method: {item} ({cat})"
                            elif isinstance(item, dict):
                                descriptions[item.get("title", item.get("name", str(item)))] = (
                                    item.get("content", item.get("description", str(item)))[:300]
                                )
            else:
                for b in confirmed_baselines:
                    if isinstance(b, str):
                        descriptions[b] = f"Baseline method: {b}"
                    elif isinstance(b, dict):
                        descriptions[b.get("title", b.get("name", str(b)))] = (
                            b.get("content", b.get("description", str(b)))[:300]
                        )
        return descriptions

    def update_rubric_cc_atoms(self, name: str, cc_summary: str) -> None:
        """Update rubric with CodeGraph CC atoms (W4 phase 2 upgrade)."""
        if name in self._rubrics:
            self._rubrics[name].cc_atoms_summary = cc_summary

    @property
    def rubric_names(self) -> list[str]:
        return list(self._rubrics.keys())

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    async def evaluate(
        self, proposal: dict, rnd_result: dict | None = None
    ) -> NoveltyReport:
        """Evaluate a proposal's novelty on 5 dimensions with dynamic weights.

        Args:
            proposal: {title, hypothesis, method_sketch}
            rnd_result: output from RNDEvaluator.compute_rnd() (optional, for context)

        Returns:
            NoveltyReport with novelty_score and dimension breakdown
        """
        if self._llm_call is None:
            return self._fallback_evaluate(proposal)

        prompt = self._build_prompt(proposal, rnd_result)

        try:
            response = await self._llm_call(prompt)
            parsed = self._parse_response(response)
            return self._build_report(parsed)
        except Exception as e:
            logger.warning(f"Rubric LLM call failed: {e}, using fallback")
            return self._fallback_evaluate(proposal)

    async def evaluate_batch(
        self, proposals: list[dict], rnd_results: list[dict] | None = None
    ) -> list[NoveltyReport]:
        """Evaluate multiple proposals."""
        reports = []
        for i, p in enumerate(proposals):
            rnd_r = rnd_results[i] if rnd_results and i < len(rnd_results) else None
            reports.append(await self.evaluate(p, rnd_r))
        return reports

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    def _build_prompt(self, proposal: dict, rnd_result: dict | None) -> str:
        parts = []

        # System instruction
        parts.append("""You are an expert research evaluator. Your task is to evaluate the NOVELTY of a research proposal on 5 dimensions.

For each dimension, assign a score 1-10 AND a weight (0.0-1.0) reflecting how important that dimension is for evaluating THIS SPECIFIC proposal. Weights must sum to 1.0.

Be critical. A score of 8+ means truly exceptional novelty. A score of 3- means clearly non-novel.""")

        # Baseline rubrics
        if self._rubrics:
            parts.append("\n## Baseline Methods (anchor points)")
            for name, rubric in self._rubrics.items():
                extra = ""
                if rubric.cc_atoms_summary:
                    extra = f"\n  Code structure: {rubric.cc_atoms_summary[:300]}"
                parts.append(f"- **{name}**: {rubric.short_desc}{extra}")
        else:
            parts.append("\n## Baseline Methods")
            parts.append("(No static baselines configured. Use the BGE-M3 nearest neighbors below as the primary comparison reference.)")

        # Nearest neighbors from BGE-M3
        if rnd_result and rnd_result.get("nearest_neighbors"):
            parts.append("\n## Nearest Knowledge in Embedding Space (BGE-M3)")
            for i, nb in enumerate(rnd_result["nearest_neighbors"][:5]):
                parts.append(
                    f"{i+1}. [{nb.get('source_type', '?')}] "
                    f"distance={nb.get('distance', 0):.3f}: {nb.get('text', '')[:200]}"
                )

        # Proposal
        parts.append("\n## Proposal to Evaluate")
        parts.append(f"Title: {proposal.get('title', 'Untitled')}")
        parts.append(f"Hypothesis: {proposal.get('hypothesis', '')[:1000000]}")
        parts.append(f"Method: {proposal.get('method_sketch', '')[:1000000]}")

        # RND coarse score
        if rnd_result:
            parts.append(f"\nBGE-M3 RND coarse score: {rnd_result.get('novelty_coarse', 'N/A')}")

        # Output format
        parts.append("""
## Output Format
Respond with ONLY a JSON object (no markdown, no extra text):

{
  "problem_novelty": <1-10>,
  "method_novelty": <1-10>,
  "experiment_novelty": <1-10>,
  "theory_novelty": <1-10>,
  "essential_difference": <1-10>,
  "weights": {
    "problem_novelty": <0.0-1.0>,
    "method_novelty": <0.0-1.0>,
    "experiment_novelty": <0.0-1.0>,
    "theory_novelty": <0.0-1.0>,
    "essential_difference": <0.0-1.0>
  },
  "explanation": "Brief justification for scores and weights (2-4 sentences)"
}

IMPORTANT: weights MUST sum to 1.0.""")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_response(self, response: str) -> dict:
        text = response.strip()
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Try ```json fence
        import re
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        # Try first { ... }
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        raise ValueError(f"Could not parse LLM rubric response: {response[:200]}")

    def _build_report(self, parsed: dict) -> NoveltyReport:
        scores = {}
        for d in RUBRIC_DIMENSIONS:
            scores[d] = float(parsed.get(d, 5))

        raw_weights = parsed.get("weights", {})
        weights = {}
        for d in RUBRIC_DIMENSIONS:
            weights[d] = float(raw_weights.get(d, 0.2))

        # Normalize weights to sum to 1.0
        w_sum = sum(weights.values())
        if w_sum > 0:
            weights = {k: v / w_sum for k, v in weights.items()}

        # Weighted novelty score
        novelty = sum(scores[d] / 10.0 * weights[d] for d in RUBRIC_DIMENSIONS)
        novelty = max(0.0, min(1.0, novelty))

        return NoveltyReport(
            novelty_score=round(novelty, 4),
            dimension_scores=scores,
            weights=weights,
            explanation=parsed.get("explanation", ""),
        )

    def _fallback_evaluate(self, proposal: dict) -> NoveltyReport:
        """Conservative fallback when LLM is unavailable."""
        return NoveltyReport(
            novelty_score=0.5,
            dimension_scores={d: 5 for d in RUBRIC_DIMENSIONS},
            weights={d: 0.2 for d in RUBRIC_DIMENSIONS},
            explanation="Fallback: LLM unavailable, using neutral scores.",
        )
