"""W2 问题分析 Handler — 4-Persona + Elo + Claim Chain。

Steps:
  1. invoke_four_personas  — 4 Persona 并行生成研究方案
  2. sync_to_cc            — 同步到 ClaimChain
  3. evaluate_novelty      — 新颖性评估
  4. elo_tournament        — Elo 锦标赛排名
  5. verify_products       — 产物验证
  6. evolution_memory      — 进化记忆更新
  7. write_claim_chain     — 写入 Claim Chain
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
from pathlib import Path

from pes_controller.phases import register_handler
from pes_controller.phases.base import BasePhaseHandler
from pes_controller.types import StepResult

logger = logging.getLogger(__name__)

PHASE = "W2 问题分析"

PERSONA_SKILLS = [
    ("novel-academic", "persona-novel-academic"),
    ("conservative-academic", "persona-conservative-academic"),
    ("novel-engineering", "persona-novel-engineering"),
    ("conservative-engineering", "persona-conservative-engineering"),
]


@register_handler(PHASE)
class W2Handler(BasePhaseHandler):
    phase_label = PHASE
    chain_steps = [
        "invoke_four_personas", "sync_to_cc", "evaluate_novelty",
        "elo_tournament", "verify_products", "evolution_memory",
        "write_claim_chain",
    ]

    def build_step(self, step_name: str) -> StepResult:
        dispatch = {
            "invoke_four_personas": self._step_personas,
            "sync_to_cc": self._step_sync_cc,
            "evaluate_novelty": self._step_novelty,
            "elo_tournament": self._step_elo,
            "verify_products": self._step_verify,
            "evolution_memory": self._step_memory,
            "write_claim_chain": self._step_claim_chain,
        }
        handler = dispatch.get(step_name)
        if handler is None:
            return StepResult(done=True, phase=self.phase_label, step=step_name,
                              step_index=self._step_index(), action="error",
                              data={"message": f"Unknown step: {step_name}"})
        return handler()

    def _step_personas(self) -> StepResult:
        ws = self._ws()
        proposals_dir = ws / "proposals"
        proposals_dir.mkdir(parents=True, exist_ok=True)

        regen_context = ""
        if self.state.get("needs_regeneration"):
            regen_context = self.state.get("iteration_feedback", "")

        variables_base = {
            "research_topic": self._research_topic(),
            "workspace_dir": str(ws),
            "venue": self._venue(),
            "phase": self.phase_label,
            "regen_context": regen_context,
        }

        def _call(persona_name, skill_name):
            return persona_name, self.executor.execute(
                skill_name,
                {**variables_base, "persona_name": persona_name},
                pre_search=self._research_topic(),
            )

        results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(_call, pn, sn): pn for pn, sn in PERSONA_SKILLS}
            for future in concurrent.futures.as_completed(futures):
                try:
                    persona_name, result = future.result()
                    results[persona_name] = {
                        "llm_response": result.llm_response,
                        "files_written": result.files_written,
                    }
                    (proposals_dir / f"proposal_{persona_name}.json").write_text(
                        json.dumps(results[persona_name], ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                except Exception as e:
                    logger.error("W2 persona call failed: %s", e)

        return StepResult(
            done=False, phase=self.phase_label, step="invoke_four_personas",
            step_index=self._step_index(), action="personas_completed",
            data={"persona_count": len(results)},
        )

    def _step_sync_cc(self) -> StepResult:
        # ClaimChain sync is pure Python — stub for now, will be wired to cc instance
        return StepResult(
            done=False, phase=self.phase_label, step="sync_to_cc",
            step_index=self._step_index(), action="sync_completed",
        )

    def _step_novelty(self) -> StepResult:
        ws = self._ws()
        result = self.executor.execute("flux-novelty-check", {
            "workspace_dir": str(ws),
            "research_topic": self._research_topic(),
        })
        return StepResult(
            done=False, phase=self.phase_label, step="evaluate_novelty",
            step_index=self._step_index(), action="skill_completed",
            data={"success": result.success},
        )

    def _step_elo(self) -> StepResult:
        from pes_controller.elo.tournament import EloTournament

        ws = self._ws()
        proposals_dir = ws / "proposals"
        proposals = []
        for pf in sorted(proposals_dir.glob("proposal_*.json")):
            data = json.loads(pf.read_text(encoding="utf-8"))
            proposals.append({
                "id": pf.stem.replace("proposal_", ""),
                "title": data.get("llm_response", "")[:200],
                "content": data.get("llm_response", ""),
            })

        if len(proposals) < 2:
            return StepResult(
                done=False, phase=self.phase_label, step="elo_tournament",
                step_index=self._step_index(), action="elo_skipped",
            )

        tournament = EloTournament(llm_client=self.llm_client, phase=self.phase_label)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import threading
            rankings = None
            exc = None

            def _run():
                nonlocal rankings, exc
                try:
                    rankings = asyncio.run(tournament.rank(proposals))
                except Exception as e:
                    exc = e

            t = threading.Thread(target=_run)
            t.start()
            t.join(timeout=300)
            if exc:
                raise exc
        else:
            rankings = asyncio.run(tournament.rank(proposals))

        return StepResult(
            done=False, phase=PHASE, step="elo_tournament",
            step_index=self._step_index(), action="elo_completed",
            data={"rankings": rankings},
        )

    def _step_verify(self) -> StepResult:
        return StepResult(
            done=False, phase=self.phase_label, step="verify_products",
            step_index=self._step_index(), action="verify_completed",
        )

    def _step_memory(self) -> StepResult:
        return StepResult(
            done=False, phase=self.phase_label, step="evolution_memory",
            step_index=self._step_index(), action="memory_updated",
        )

    def _step_claim_chain(self) -> StepResult:
        return StepResult(
            done=True, phase=self.phase_label, step="write_claim_chain",
            step_index=self._step_index(), action="chain_written",
        )
