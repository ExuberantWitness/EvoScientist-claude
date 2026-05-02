"""IDE/IVE/ESE Evolution Memory — paper §D.1-D.2.

Three evolution mechanisms for structured memory distillation:

IDE (Idea Direction Evolution):
    Triggered after Elo Tournament completes.
    Extracts top-ranked proposals as PROMISING, bottom as FAILED.

IVE (Idea Validation Evolution):
    Triggered when eval score is below baseline.
    Records failed directions with specific failure reasons.

ESE (Experiment Strategy Evolution):
    Triggered when eval score is above baseline.
    Extracts effective strategies with applicability tags.

Memory Retrieval (inject_priors):
    Priority: FAILED (avoid) > SUCCESS (reuse) > PROMISING (build upon)
    Budget: 40% / 40% / 20% of max_chars
    Relevance by keyword overlap (Jaccard-like)

Storage: JSONL files under memory/ideation/ and memory/experiment/
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Common English stop words
_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "this", "that",
    "these", "those", "it", "its", "not", "no", "nor", "so", "if", "then",
    "than", "too", "very", "just", "about", "above", "after", "before",
    "between", "into", "through", "during", "each", "few", "more", "most",
    "other", "some", "such", "only", "own", "same", "also", "how", "what",
    "which", "who", "whom", "when", "where", "why", "all", "any", "both",
    "each", "every", "many", "much", "new", "old", "still", "use", "using",
    "we", "our", "they", "their", "them", "he", "she", "his", "her",
})

DEFAULT_BASELINE_SCORE = 0.3


class EvolutionMemory:
    """Structured evolution memory with IDE/IVE/ESE distillation."""

    def __init__(self, workspace_dir: str | Path):
        self.base_dir = Path(workspace_dir) / "memory"
        self.ideation_dir = self.base_dir / "ideation"
        self.experiment_dir = self.base_dir / "experiment"
        self.ideation_dir.mkdir(parents=True, exist_ok=True)
        self.experiment_dir.mkdir(parents=True, exist_ok=True)
        # Strategy-driven configuration
        from .strategy import StrategyManager
        self.strategy = StrategyManager(workspace_dir)
        self.strategy.ensure_defaults()

    # ══════════════════════════════════════════════════════════════
    # IDE: Idea Direction Evolution
    # ══════════════════════════════════════════════════════════════

    async def distill_ideation(
        self,
        proposals: list[dict],
        task_id: str = "",
        fail_threshold_ratio: float = 0.5,
    ) -> dict:
        """Extract promising and failed directions from Elo-ranked proposals.

        Paper §D.1: Top-ranked → PROMISING, bottom-ranked → FAILED.
        Dedup via keyword overlap (Jaccard > 0.8 → merge).

        Returns:
            {promising_count, failed_count, skipped_count}
        """
        if not proposals:
            return {"promising_count": 0, "failed_count": 0, "skipped_count": 0}

        # Read configurable threshold from strategy file
        kv = self.strategy.parse_kv(self.strategy.load_strategy("distillation_strategy.md"))
        fail_threshold_ratio = float(kv.get("ide_fail_threshold_ratio", fail_threshold_ratio))

        sorted_proposals = sorted(
            proposals, key=lambda p: p.get("elo_rating", 1500), reverse=True
        )
        top_score = sorted_proposals[0].get("elo_rating", 1500)

        # Top half → PROMISING
        median_idx = max(1, len(sorted_proposals) // 2)
        promising_count = 0
        for i, p in enumerate(sorted_proposals[:median_idx]):
            if p.get("elo_rating", 1500) <= sorted_proposals[median_idx - 1].get("elo_rating", 1500) - 0.1:
                break
            entry = {
                "id": f"dir_{int(time.time())}_{i}",
                "direction": p.get("title", ""),
                "status": "PROMISING",
                "reason": p.get("hypothesis", "")[:300],
                "source_task": task_id,
                "timestamp": time.time(),
                "score": p.get("elo_rating", 1500),
            }
            if self._append_ideation(entry):
                promising_count += 1

        # Bottom third → FAILED (if score < top_score * threshold)
        fail_threshold = top_score * fail_threshold_ratio
        bottom_n = max(1, len(sorted_proposals) // 3)
        failed_count = 0
        for i, p in enumerate(sorted_proposals[-bottom_n:]):
            if p.get("elo_rating", 1500) >= fail_threshold:
                continue
            entry = {
                "id": f"dir_{int(time.time())}_f{i}",
                "direction": p.get("title", ""),
                "status": "FAILED",
                "reason": p.get("hypothesis", "Low Elo ranking")[:300],
                "source_task": task_id,
                "timestamp": time.time(),
                "score": p.get("elo_rating", 1500),
                "priority": "HIGH",
            }
            if self._append_ideation(entry):
                failed_count += 1

        logger.info(
            f"[EvoMemory] IDE: {len(proposals)} proposals → "
            f"{promising_count} PROMISING, {failed_count} FAILED (task={task_id})"
        )
        return {
            "promising_count": promising_count,
            "failed_count": failed_count,
            "skipped_count": len(proposals) - promising_count - failed_count,
        }

    # ══════════════════════════════════════════════════════════════
    # IVE: Idea Validation Evolution
    # ══════════════════════════════════════════════════════════════

    async def record_failure(
        self,
        direction: str,
        reason: str,
        task_id: str = "",
        score: float = 0.0,
    ) -> bool:
        """Record a validation failure.

        Paper §D.1: When eval score < baseline, mark direction as FAILED
        with specific reason. Priority=HIGH ensures it appears first in
        future inject_priors calls.
        """
        entry = {
            "id": f"dir_{int(time.time())}_ive",
            "direction": direction[:200],
            "status": "FAILED",
            "reason": reason[:300],
            "source_task": task_id,
            "timestamp": time.time(),
            "score": score,
            "priority": "HIGH",
            "type": "IVE",
        }
        result = self._append_ideation(entry)
        logger.info(f"[EvoMemory] IVE: '{direction[:60]}' → FAILED (score={score})")
        return result

    # ══════════════════════════════════════════════════════════════
    # ESE: Experiment Strategy Evolution
    # ══════════════════════════════════════════════════════════════

    async def distill_experiment(
        self,
        strategy: str,
        outcome: str,
        task_id: str = "",
        details: str = "",
        score: float = 0.0,
        applicability: list[str] | None = None,
    ) -> bool:
        """Record an effective (or failed) experiment strategy.

        Paper §D.2: When eval score > baseline, extract the strategy
        that led to improvement, tagged with applicability domains.

        Args:
            strategy: The strategy/approach used.
            outcome: "SUCCESS", "PARTIAL", or "FAILED".
            task_id: Source task identifier.
            details: Additional context about the strategy.
            score: The eval score achieved.
            applicability: Which roles/phases this applies to.
        """
        entry = {
            "id": f"strat_{int(time.time())}",
            "strategy": strategy[:300],
            "outcome": outcome,
            "context": details[:500],
            "source_task": task_id,
            "timestamp": time.time(),
            "score": score,
            "applicability": applicability or ["general"],
        }
        result = self._append_experiment(entry)
        logger.info(
            f"[EvoMemory] ESE: '{strategy[:50]}' → {outcome} (score={score})"
        )
        return result

    # ══════════════════════════════════════════════════════════════
    # Memory Retrieval: inject_priors
    # ══════════════════════════════════════════════════════════════

    async def inject_priors(
        self,
        task_context: str,
        max_chars: int = 2000,
        caller_role: str = "",
    ) -> str:
        """Retrieve relevant evolution memory and format as prompt injection.

        Priority order:
        1. FAILED directions (avoid repeating) — 40% budget
        2. SUCCESS strategies (reuse proven approaches) — 40% budget
        3. PROMISING directions (build upon) — 20% budget

        Relevance scoring via keyword overlap between task_context and entries.
        """
        task_keywords = self._extract_keywords(task_context)

        # Read configurable budget from strategy file
        kv = self.strategy.parse_kv(self.strategy.load_strategy("memory_retrieval.md"))
        failed_pct = float(kv.get("failed_pct", 40)) / 100.0
        success_pct = float(kv.get("success_pct", 40)) / 100.0
        promising_pct = 1.0 - failed_pct - success_pct
        failed_budget = int(max_chars * failed_pct)
        success_budget = int(max_chars * success_pct)
        promising_budget = max_chars - failed_budget - success_budget

        sections = []

        # 1. FAILED directions (highest priority)
        failed_entries = self._read_ideation(status="FAILED", limit=30)
        if failed_entries and failed_budget >= 80:
            scored = [
                (self._relevance_score(task_keywords, e), e)
                for e in failed_entries
            ]
            scored.sort(key=lambda x: x[0], reverse=True)
            # Priority=HIGH entries first
            scored.sort(key=lambda x: (x[1].get("priority") != "HIGH", -x[0]))

            lines = ["## Failed Directions (AVOID)"]
            chars_used = len(lines[0])
            for rel_score, e in scored:
                direction = str(e.get("direction", ""))[:80]
                reason = str(e.get("reason", ""))[:100]
                line = f"- **{direction}**: {reason}"
                if chars_used + len(line) <= failed_budget:
                    lines.append(line)
                    chars_used += len(line)
                else:
                    break
            if len(lines) > 1:
                sections.append("\n".join(lines))

        # 2. SUCCESS strategies
        success_entries = self._read_experiments(outcome="SUCCESS", limit=20)
        if success_entries and success_budget >= 80:
            scored = [
                (self._relevance_score(task_keywords, e), e)
                for e in success_entries
            ]
            scored.sort(key=lambda x: x[0], reverse=True)

            lines = ["## Proven Strategies (REUSE)"]
            chars_used = len(lines[0])
            for rel_score, e in scored:
                strategy = str(e.get("strategy", ""))[:80]
                applic = ", ".join(e.get("applicability", ["general"])[:3])
                context = str(e.get("context", ""))[:80]
                line = f"- **{strategy}** [{applic}]: {context}"
                if chars_used + len(line) <= success_budget:
                    lines.append(line)
                    chars_used += len(line)
                else:
                    break
            if len(lines) > 1:
                sections.append("\n".join(lines))

        # 3. PROMISING directions
        promising_entries = self._read_ideation(status="PROMISING", limit=10)
        if promising_entries and promising_budget >= 80:
            scored = [
                (self._relevance_score(task_keywords, e), e)
                for e in promising_entries
            ]
            scored.sort(key=lambda x: x[0], reverse=True)

            lines = ["## Promising Directions (BUILD UPON)"]
            chars_used = len(lines[0])
            for rel_score, e in scored:
                direction = str(e.get("direction", ""))[:80]
                score = e.get("score", 0)
                line = f"- **{direction}** (elo: {score:.0f})"
                if chars_used + len(line) <= promising_budget:
                    lines.append(line)
                    chars_used += len(line)
                else:
                    break
            if len(lines) > 1:
                sections.append("\n".join(lines))

        if not sections:
            return ""

        header = "## Evolution Memory (from previous tasks)\n"
        injection = header + "\n\n".join(sections)

        logger.info(
            f"[EvoMemory] Injected {len(injection)} chars of priors "
            f"({len(task_keywords)} task keywords, role={caller_role or 'default'})"
        )
        return injection

    # ══════════════════════════════════════════════════════════════
    # Stats
    # ══════════════════════════════════════════════════════════════

    def get_stats(self) -> dict:
        """Return summary statistics of evolution memory."""
        ideation = self._read_ideation(limit=1000)
        experiments = self._read_experiments(limit=1000)

        n_failed = sum(1 for e in ideation if e.get("status") == "FAILED")
        n_promising = sum(1 for e in ideation if e.get("status") == "PROMISING")
        n_success_exp = sum(1 for e in experiments if e.get("outcome") == "SUCCESS")
        n_failed_exp = sum(1 for e in experiments if e.get("outcome") == "FAILED")

        return {
            "total_entries": len(ideation) + len(experiments),
            "ideation": {
                "total": len(ideation),
                "failed": n_failed,
                "promising": n_promising,
            },
            "experiments": {
                "total": len(experiments),
                "success": n_success_exp,
                "failed": n_failed_exp,
            },
        }

    # ══════════════════════════════════════════════════════════════
    # LLM-Driven Distillation
    # ══════════════════════════════════════════════════════════════

    async def llm_distill(
        self,
        conversation_history: list[dict],
        task_id: str = "",
    ) -> dict:
        """Extract structured insights from conversation history via LLM.

        Identifies promising directions, failed directions, effective strategies,
        and anti-patterns from recent agent interactions.

        Returns:
            {"promising": N, "failed": N, "strategies": N, "antipatterns": N}
        """
        if not conversation_history:
            return {"promising": 0, "failed": 0, "strategies": 0, "antipatterns": 0}

        # Summarize last 10 messages
        recent = conversation_history[-10:]
        history_text = "\n".join(
            f"[{m.get('role', 'unknown')}] {str(m.get('content', ''))[:500]}"
            for m in recent
        )

        system_prompt = """\
You are an evolution memory distiller. Analyze the conversation history and extract:
1. promising_directions: Research directions that look feasible and novel
2. failed_directions: Approaches that were tried and didn't work, with reasons
3. effective_strategies: Methods, techniques, or configurations that produced good results
4. anti_patterns: Common mistakes, pitfalls, or anti-patterns to avoid

Respond ONLY with valid JSON:
{"promising_directions": [{"direction": "...", "reason": "..."}], "failed_directions": [{"direction": "...", "reason": "..."}], "effective_strategies": [{"strategy": "...", "outcome": "..."}], "anti_patterns": [{"pattern": "...", "reason": "..."}]}"""

        user_prompt = f"## Conversation History\n{history_text}\n\nExtract insights."

        try:
            import httpx

            api_key = os.environ.get("DEEPSEEK_API_KEY", "")
            base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
            if not api_key:
                api_key = os.environ.get("OPENAI_API_KEY", "")
                base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

            if not api_key:
                logger.warning("[Memory] No API key for LLM distillation")
                return {"promising": 0, "failed": 0, "strategies": 0, "antipatterns": 0}

            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{base_url}/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "deepseek-chat",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": 0.2,
                        "max_tokens": 2000,
                    },
                )
                data = resp.json()
                raw = data["choices"][0]["message"]["content"]

            parsed = json.loads(self._extract_json_str(raw))
        except Exception as e:
            logger.error(f"[Memory] LLM distillation failed: {e}")
            return {"promising": 0, "failed": 0, "strategies": 0, "antipatterns": 0}

        counts = {"promising": 0, "failed": 0, "strategies": 0, "antipatterns": 0}

        # Write promising directions
        for item in parsed.get("promising_directions", []):
            entry = {
                "id": f"dir_{int(time.time())}_{counts['promising']}",
                "direction": str(item.get("direction", ""))[:300],
                "status": "PROMISING",
                "reason": str(item.get("reason", ""))[:300],
                "source_task": task_id,
                "timestamp": time.time(),
                "score": 0,
                "source": "llm_distill",
            }
            if self._append_ideation(entry):
                counts["promising"] += 1

        # Write failed directions
        for item in parsed.get("failed_directions", []):
            entry = {
                "id": f"dir_{int(time.time())}_{counts['failed']}",
                "direction": str(item.get("direction", ""))[:300],
                "status": "FAILED",
                "reason": str(item.get("reason", ""))[:300],
                "source_task": task_id,
                "timestamp": time.time(),
                "score": 0,
                "priority": "HIGH",
                "source": "llm_distill",
            }
            if self._append_ideation(entry):
                counts["failed"] += 1

        # Write effective strategies
        for item in parsed.get("effective_strategies", []):
            entry = {
                "id": f"exp_{int(time.time())}_{counts['strategies']}",
                "strategy": str(item.get("strategy", ""))[:300],
                "outcome": "SUCCESS",
                "details": str(item.get("outcome", ""))[:300],
                "source_task": task_id,
                "timestamp": time.time(),
                "score": 0,
                "applicability": ["general"],
                "source": "llm_distill",
            }
            if self._append_experiment(entry):
                counts["strategies"] += 1

        # Write anti-patterns as FAILED experiments
        for item in parsed.get("anti_patterns", []):
            entry = {
                "id": f"exp_{int(time.time())}_{counts['antipatterns']}",
                "strategy": str(item.get("pattern", ""))[:300],
                "outcome": "FAILED",
                "details": str(item.get("reason", ""))[:300],
                "source_task": task_id,
                "timestamp": time.time(),
                "score": 0,
                "applicability": ["general"],
                "source": "llm_distill",
            }
            if self._append_experiment(entry):
                counts["antipatterns"] += 1

        logger.info(f"[Memory] LLM distillation: {counts}")
        return counts

    @staticmethod
    def _extract_json_str(text: str) -> str:
        """Extract JSON string from LLM response."""
        import re as _re
        # Try direct parse
        text = text.strip()
        try:
            json.loads(text)
            return text
        except json.JSONDecodeError:
            pass
        # Try markdown code fence
        m = _re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, _re.DOTALL)
        if m:
            return m.group(1)
        # Try first { ... }
        m = _re.search(r"\{.*\}", text, _re.DOTALL)
        if m:
            return m.group(0)
        return "{}"

    # ══════════════════════════════════════════════════════════════
    # Internal: Keyword extraction & relevance
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def _extract_keywords(text: str) -> set[str]:
        """Extract meaningful 2+ character words, removing stop words."""
        words = re.findall(r"[a-zA-Z一-鿿]{2,}", text.lower())
        return {w for w in words if w not in _STOP_WORDS}

    @staticmethod
    def _keyword_overlap(kw_a: set[str], kw_b: set[str]) -> float:
        """Jaccard-like overlap: |A ∩ B| / max(|A|, |B|, 1)."""
        if not kw_a or not kw_b:
            return 0.0
        return len(kw_a & kw_b) / max(len(kw_a), len(kw_b))

    def _relevance_score(
        self, task_keywords: set[str], entry: dict, caller_role: str = ""
    ) -> float:
        """Compute relevance score between task keywords and a memory entry."""
        if not task_keywords:
            return 0.5

        entry_text = " ".join([
            str(entry.get("direction", "")),
            str(entry.get("reason", "")),
            str(entry.get("strategy", "")),
            str(entry.get("context", "")),
        ])
        entry_keywords = self._extract_keywords(entry_text)
        if not entry_keywords:
            return 0.0

        overlap = len(task_keywords & entry_keywords)
        score = overlap / max(len(task_keywords), 1)

        # Applicability boost
        applicability = entry.get("applicability", [])
        if applicability and caller_role:
            if caller_role in applicability or "general" in applicability:
                score = min(score + 0.2, 1.0)

        return score

    # ══════════════════════════════════════════════════════════════
    # Internal: JSONL read/write with dedup
    # ══════════════════════════════════════════════════════════════

    def _ideation_path(self) -> Path:
        return self.ideation_dir / "directions.jsonl"

    def _experiment_path(self) -> Path:
        return self.experiment_dir / "strategies.jsonl"

    def _append_ideation(self, entry: dict) -> bool:
        """Append an ideation entry with keyword-overlap dedup.

        If an existing entry has overlap > 0.8 with the same status, merge
        instead of duplicating. Returns True if entry was added/merged.
        """
        path = self._ideation_path()
        new_keywords = self._extract_keywords(
            f"{entry.get('direction', '')} {entry.get('reason', '')}"
        )

        if new_keywords and path.exists():
            merged = False
            lines_out = []
            for line_text in path.read_text().strip().split("\n"):
                if not line_text.strip():
                    continue
                try:
                    existing = json.loads(line_text)
                except json.JSONDecodeError:
                    lines_out.append(line_text)
                    continue

                if existing.get("status") != entry.get("status"):
                    lines_out.append(line_text)
                    continue

                existing_keywords = self._extract_keywords(
                    f"{existing.get('direction', '')} {existing.get('reason', '')}"
                )
                overlap = self._keyword_overlap(new_keywords, existing_keywords)

                if overlap > 0.8 and not merged:
                    merged_entry = {**existing}
                    if entry.get("score", 0) > existing.get("score", 0):
                        merged_entry["score"] = entry["score"]
                    if len(entry.get("reason", "")) > len(existing.get("reason", "")):
                        merged_entry["reason"] = entry["reason"]
                    merged_entry["timestamp"] = entry.get("timestamp", time.time())
                    lines_out.append(json.dumps(merged_entry, ensure_ascii=False))
                    merged = True
                else:
                    lines_out.append(line_text)

            if merged:
                path.write_text("\n".join(lines_out) + "\n")
                return True

        line = json.dumps(entry, ensure_ascii=False)
        with open(path, "a") as f:
            f.write(line + "\n")
        return True

    def _append_experiment(self, entry: dict) -> bool:
        """Append an experiment strategy entry."""
        path = self._experiment_path()
        line = json.dumps(entry, ensure_ascii=False)
        with open(path, "a") as f:
            f.write(line + "\n")
        return True

    def _read_ideation(
        self, status: str | None = None, limit: int = 50
    ) -> list[dict]:
        """Read ideation memory entries, optionally filtered by status."""
        path = self._ideation_path()
        if not path.exists():
            return []
        entries = []
        for line_text in path.read_text().strip().split("\n"):
            if not line_text.strip():
                continue
            try:
                e = json.loads(line_text)
                if status is None or e.get("status") == status:
                    entries.append(e)
            except json.JSONDecodeError:
                continue
        return entries[-limit:]

    def _read_experiments(
        self, outcome: str | None = None, limit: int = 50
    ) -> list[dict]:
        """Read experiment strategy entries, optionally filtered by outcome."""
        path = self._experiment_path()
        if not path.exists():
            return []
        entries = []
        for line_text in path.read_text().strip().split("\n"):
            if not line_text.strip():
                continue
            try:
                e = json.loads(line_text)
                if outcome is None or e.get("outcome") == outcome:
                    entries.append(e)
            except json.JSONDecodeError:
                continue
        return entries[-limit:]
