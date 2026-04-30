"""Research Pipeline — 3-phase orchestration with auto-distillation.

Phase 0: Memory Injection (inject_priors from EvolutionMemory)
Phase 1: Parallel Exploration
  1a. K plan agents parallel → K research proposals
  1b. Elo Tournament → ranked proposals (top-3 retained, top-1 extended)
  1c. M research agents parallel → literature survey brief
  → IDE distillation (auto)
Phase 2: Execution (serial)
  → IVE if score < baseline (auto)
  → ESE if score > baseline (auto)
Phase 3: Analysis + Writing
  3a. N analyze agents parallel
  3b. Writer agent → final article

Checkpoint: JSON file saved after each phase for recovery.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .elo import EloTournament
from .memory import EvolutionMemory

logger = logging.getLogger(__name__)

BASELINE_SCORE = 0.3


@dataclass
class PipelineCheckpoint:
    """State saved after each phase for recovery."""

    phase: int = 0
    task_id: str = ""
    query: str = ""
    proposals: list[dict] = field(default_factory=list)
    ranked: list[dict] = field(default_factory=list)
    research_brief: str = ""
    article_draft: str = ""
    timestamp: str = ""

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "phase": self.phase,
                    "task_id": self.task_id,
                    "query": self.query,
                    "proposals": self.proposals,
                    "ranked": self.ranked,
                    "research_brief": self.research_brief,
                    "article_draft": self.article_draft,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> PipelineCheckpoint | None:
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                phase=data.get("phase", 0),
                task_id=data.get("task_id", ""),
                query=data.get("query", ""),
                proposals=data.get("proposals", []),
                ranked=data.get("ranked", []),
                research_brief=data.get("research_brief", ""),
                article_draft=data.get("article_draft", ""),
                timestamp=data.get("timestamp", ""),
            )
        except Exception:
            return None


class ResearchPipeline:
    """3-Phase research pipeline with auto memory distillation.

    Designed for DRB benchmark: deterministic execution with phase-boundary
    IDE/IVE/ESE triggers. Can be called via evo_run_pipeline MCP tool or
    programmatically.

    Usage:
        pipeline = ResearchPipeline(manager, session)
        article = await pipeline.run("research question", task_id="1")
    """

    def __init__(
        self,
        manager: Any,  # AgentManager
        session: Any,  # AgentSession
        tournament: EloTournament | None = None,
        memory: EvolutionMemory | None = None,
    ):
        self.manager = manager
        self.session = session
        self.tournament = tournament or EloTournament()
        self.memory = memory or EvolutionMemory(session.workspace_dir)
        self._checkpoint_path = (
            Path(session.workspace_dir) / ".pipeline_checkpoint.json"
        )

    async def run(
        self,
        query: str,
        task_id: str = "",
        exploration_workers: int = 1,
    ) -> str:
        """Run complete 3-phase pipeline. Returns final article text."""
        start_time = time.time()
        logger.info(f"[Pipeline] Starting task {task_id or 'unnamed'}")

        # ── Phase 0: Memory Injection ──
        logger.info("[Pipeline] Phase 0: Memory Injection")
        priors = await self.memory.inject_priors(query, max_chars=2000)
        if priors:
            logger.info(f"[Pipeline] Injected {len(priors)} chars of evolution memory")

        # ── Phase 1: Parallel Exploration ──
        logger.info(f"[Pipeline] Phase 1: {exploration_workers} exploration worker(s)")
        proposals = await self._run_phase1(query, priors, exploration_workers)

        if not proposals:
            logger.error("[Pipeline] No proposals generated — aborting")
            return ""

        # Save checkpoint for recovery
        cp = PipelineCheckpoint(
            phase=1,
            task_id=task_id,
            query=query,
            proposals=[
                {
                    "id": p.get("id", ""),
                    "title": p.get("title", ""),
                    "hypothesis": p.get("hypothesis", ""),
                    "method_sketch": p.get("method_sketch", ""),
                    "elo_rating": p.get("elo_rating", 1500),
                }
                for p in proposals
            ],
            ranked=proposals,  # already sorted
            research_brief="",
        )
        cp.save(self._checkpoint_path)

        # 1b. Elo Tournament (if multiple proposals)
        if len(proposals) >= 2:
            logger.info("[Pipeline] Phase 1b: Elo Tournament")
            ranked = await self.tournament.rank(proposals)
            top3 = ranked[:3]
            winner = ranked[0]
        else:
            ranked = proposals
            top3 = ranked
            winner = ranked[0]

        logger.info(
            f"[Pipeline] Elo winner: '{winner.get('title', 'N/A')[:60]}' "
            f"(elo={winner.get('elo_rating', 1500):.0f})"
        )

        # 1c. Extend top-1 into full proposal + research
        winner_content = winner.get("hypothesis", "")
        if winner.get("method_sketch"):
            winner_content += "\n\n" + winner["method_sketch"]

        research_brief = await self._run_research(query, priors, winner_content)
        cp.research_brief = research_brief
        cp.ranked = ranked
        cp.phase = 1
        cp.save(self._checkpoint_path)

        # IDE distillation
        if top3:
            top3_for_distill = [
                {
                    "title": p.get("title", ""),
                    "hypothesis": p.get("hypothesis", ""),
                    "elo_rating": p.get("elo_rating", 1500),
                }
                for p in top3
            ]
            await self.memory.distill_ideation(top3_for_distill, task_id)

        # ── Phase 2: Execution ──
        logger.info("[Pipeline] Phase 2: Execution")
        phase2_prompt = f"""## Research Proposal (Elo Winner)
{winner_content}

## Literature Survey
{research_brief}

## Evolution Memory
{priors}

Based on the above, conduct deep research and write a comprehensive article on this topic.
Use WebSearch to gather information, cross-reference sources, and provide specific data.
Write the complete article with clear structure: title, abstract, background, analysis, conclusion, references."""

        article = await self._run_phase2(phase2_prompt, task_id)
        cp.article_draft = article
        cp.phase = 2
        cp.save(self._checkpoint_path)

        # Compute approximate eval score
        eval_score = min(len(article) / 10000, 1.0) if article else 0.0

        # IVE/ESE based on score
        if eval_score < BASELINE_SCORE:
            await self.memory.record_failure(
                direction=winner.get("title", query[:80]),
                reason=f"Article too short ({len(article)} chars), score={eval_score:.2f}",
                task_id=task_id,
                score=eval_score,
            )
            logger.info(f"[Pipeline] IVE triggered: score={eval_score:.2f} < baseline={BASELINE_SCORE}")
        elif eval_score >= BASELINE_SCORE:
            await self.memory.distill_experiment(
                strategy=winner.get("title", "Research pipeline"),
                outcome="SUCCESS" if eval_score > 0.6 else "PARTIAL",
                task_id=task_id,
                details=f"Generated {len(article)} chars article",
                score=eval_score,
                applicability=["writing", "research"],
            )

        # ── Phase 3: Analysis + Writing ──
        logger.info("[Pipeline] Phase 3: Analysis + Writing")
        final = await self._run_phase3(article, query, priors, task_id)
        cp.phase = 3
        cp.save(self._checkpoint_path)

        elapsed = time.time() - start_time
        logger.info(
            f"[Pipeline] Task {task_id or 'unnamed'} complete: "
            f"{len(final)} chars in {elapsed:.0f}s"
        )

        # Clean up checkpoint on success
        if self._checkpoint_path.exists():
            self._checkpoint_path.unlink()

        return final

    async def resume(self) -> str:
        """Resume from last checkpoint after interruption."""
        cp = PipelineCheckpoint.load(self._checkpoint_path)
        if cp is None:
            raise RuntimeError("No checkpoint found. Run run() first.")

        logger.info(f"[Pipeline] Resuming from phase {cp.phase} (task={cp.task_id})")

        priors = await self.memory.inject_priors(cp.query, max_chars=2000)

        if cp.phase <= 1:
            # Need to re-run phase 1 extension and research
            winner = cp.ranked[0] if cp.ranked else None
            winner_content = ""
            if winner:
                winner_content = winner.get("hypothesis", "")
                if winner.get("method_sketch"):
                    winner_content += "\n\n" + winner["method_sketch"]

            if not cp.research_brief:
                cp.research_brief = await self._run_research(cp.query, priors, winner_content)
                cp.phase = 1
                cp.save(self._checkpoint_path)

        if cp.phase <= 2:
            phase2_prompt = f"## Winner Proposal\n{winner_content}\n\n## Research\n{cp.research_brief}\n\n## Priors\n{priors}\n\nConduct deep research and write a comprehensive article."
            cp.article_draft = await self._run_phase2(phase2_prompt, cp.task_id)
            cp.phase = 2
            cp.save(self._checkpoint_path)

        final = await self._run_phase3(
            cp.article_draft, cp.query, priors, cp.task_id
        )

        if self._checkpoint_path.exists():
            self._checkpoint_path.unlink()

        return final

    # ══════════════════════════════════════════════════════════════
    # Phase implementations
    # ══════════════════════════════════════════════════════════════

    async def _run_phase1(
        self, query: str, priors: str, workers: int
    ) -> list[dict]:
        """Run K plan agents in parallel to generate diverse proposals."""
        prompts = []
        for k in range(workers):
            diversity_hint = ""
            if workers > 1:
                angles = [
                    "regulatory/legal",
                    "technical/engineering",
                    "economic/market",
                    "social/ethical",
                    "institutional/governance",
                ]
                angle = angles[k % len(angles)]
                diversity_hint = f"\nFocus on the **{angle}** perspective."

            prompts.append(
                f"""You are a research planner. Generate ONE innovative research proposal
for the following topic. Be specific and concrete.

Topic: {query}{diversity_hint}

{priors if priors else ""}

Output format (Markdown):
## Proposal Title
(A specific, descriptive title)

## Hypothesis
(The core research claim or approach, 2-3 sentences)

## Method Sketch
(How to investigate this — specific methods, data sources, analysis approach.
Include concrete steps and expected outcomes, 3-5 sentences)

Generate exactly ONE proposal. Be specific — avoid vague language."""
            )

        # Run plan prompts in parallel
        tasks = []
        for i, prompt in enumerate(prompts):
            # Rotate thread for each parallel call
            old_thread = self.session.thread_id
            self.manager._rotate_thread(self.session)
            tasks.append(self.manager._run_agent(self.session, prompt))

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        proposals = []
        for i, resp in enumerate(responses):
            if isinstance(resp, Exception):
                logger.warning(f"[Pipeline] Plan agent {i} failed: {resp}")
                continue
            if isinstance(resp, str) and len(resp) > 20:
                proposal = self._parse_proposal(resp, i)
                if proposal:
                    proposals.append(proposal)

        logger.info(
            f"[Pipeline] Phase 1: {len(proposals)}/{workers} plan agents succeeded"
        )
        return proposals

    def _parse_proposal(self, text: str, idx: int) -> dict | None:
        """Parse a proposal from agent response text."""
        title = ""
        hypothesis = ""
        method = ""

        lines = text.split("\n")
        in_hypothesis = False
        in_method = False

        for line in lines:
            stripped = line.strip()
            lower = stripped.lower()

            if "## proposal title" in lower or "## title" in lower:
                continue  # skip heading
            if not title and (
                stripped.startswith("##") or stripped.startswith("# ")
            ):
                title = stripped.lstrip("#").strip()
                continue
            if "hypothesis" in lower and (
                stripped.startswith("##") or stripped.startswith("###")
            ):
                in_hypothesis = True
                in_method = False
                continue
            if "method" in lower and (
                stripped.startswith("##") or stripped.startswith("###")
            ):
                in_method = True
                in_hypothesis = False
                continue
            if stripped.startswith("##") or stripped.startswith("# "):
                in_hypothesis = False
                in_method = False
                continue

            if in_hypothesis and stripped and not stripped.startswith("#"):
                hypothesis += stripped + " "
            elif in_method and stripped and not stripped.startswith("#"):
                method += stripped + " "

            # Fallback: if no explicit headings, use first substantial paragraph
            if not title and not hypothesis and len(stripped) > 30 and not stripped.startswith("#"):
                # Use first line as title
                title = stripped[:120]

        hypothesis = hypothesis.strip()
        method = method.strip()

        # Fallback: use whole text
        if not hypothesis and not method:
            hypothesis = text[:500]

        if not title:
            title = f"Proposal {idx + 1}"

        return {
            "id": f"prop_{idx}",
            "title": title[:120],
            "hypothesis": hypothesis or text[:300],
            "method_sketch": method or "",
        }

    async def _run_research(
        self, query: str, priors: str, winner_content: str
    ) -> str:
        """Run a research agent to survey literature on the winning proposal."""
        prompt = f"""You are a research agent. Conduct a literature and method survey
for the following research proposal.

## Research Query
{query}

## Winning Proposal
{winner_content[:1500]}

{priors if priors else ""}

Search for and summarize:
1. Key methods and approaches in this area
2. Relevant datasets and benchmarks
3. State-of-the-art results and baselines
4. Gaps and open challenges

Be specific — include method names, metric values, and source references.
Format as a structured research brief (500-1000 words)."""

        self.manager._rotate_thread(self.session)
        response = await self.manager._run_agent(self.session, prompt)
        return response if isinstance(response, str) else ""

    async def _run_phase2(self, prompt: str, task_id: str) -> str:
        """Execute Phase 2: deep research and article writing."""
        self.manager._rotate_thread(self.session)
        response = await self.manager._run_agent(self.session, prompt)
        return response if isinstance(response, str) else ""

    async def _run_phase3(
        self, article: str, query: str, priors: str, task_id: str
    ) -> str:
        """Phase 3: Analyze and improve the article."""
        # 3a. Analysis
        analyze_prompt = f"""You are a research analyst. Review and critique the following article:

## Article
{article[:5000]}

## Original Query
{query}

Provide:
1. Strengths (2-3 specific points)
2. Weaknesses and gaps (2-3 specific points)
3. Specific suggestions for improvement
4. Missing data or citations that should be added

Be constructive and specific."""

        self.manager._rotate_thread(self.session)
        analysis = await self.manager._run_agent(self.session, analyze_prompt)

        # 3b. Revised writing
        writer_prompt = f"""You are a research writer. Improve the following article based on the analysis.

## Original Article
{article[:6000]}

## Analyst Feedback
{analysis if isinstance(analysis, str) else ""}

{priors if priors else ""}

## Instructions
1. Address all weaknesses identified in the analysis
2. Add missing data, citations, and depth where suggested
3. Improve structure and readability
4. Keep the original strengths
5. Write the complete revised article (not just changes)

Output the complete revised article in Markdown format."""

        self.manager._rotate_thread(self.session)
        final = await self.manager._run_agent(self.session, writer_prompt)
        final_text = final if isinstance(final, str) else ""

        # If writer produced nothing useful, return original
        if not final_text or len(final_text) < 200:
            logger.warning("[Pipeline] Writer produced insufficient output, using original")
            return article

        return final_text
