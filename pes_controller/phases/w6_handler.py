"""W6 结果分析 Handler — 分析实验结果 + 多智能体讨论 + Claim Chain。"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from pes_controller.phases import register_handler
from pes_controller.phases.base import BasePhaseHandler
from pes_controller.types import StepResult

logger = logging.getLogger(__name__)

PHASE = "W6 结果分析"


@register_handler(PHASE)
class W6Handler(BasePhaseHandler):
    phase_label = PHASE
    chain_steps = [
        "run_step_pipeline", "scan_islands_rubrics",
        "multi_agent_discuss", "evolution_memory",
        "island_assign", "refine_atoms", "write_claim_chain",
        "web_research",
    ]

    def build_step(self, step_name: str) -> StepResult:
        dispatch = {
            "run_step_pipeline": self._step_pipeline,
            "scan_islands_rubrics": self._step_scan,
            "multi_agent_discuss": self._step_discuss,
            "evolution_memory": self._step_memory,
            "island_assign": self._step_island_assign,
            "refine_atoms": self._step_refine,
            "write_claim_chain": self._step_claim_chain,
            "web_research": self._step_research,
        }
        handler = dispatch.get(step_name)
        if handler is None:
            return StepResult(done=True, phase=PHASE, step=step_name,
                              step_index=self._step_index(), action="error",
                              data={"message": f"Unknown step: {step_name}"})
        return handler()

    def _step_pipeline(self) -> StepResult:
        return StepResult(
            done=False, phase=PHASE, step="run_step_pipeline",
            step_index=self._step_index(), action="pipeline_completed",
        )

    def _step_scan(self) -> StepResult:
        ws = self._ws()
        result = self.executor.execute("w6-scan-islands", {
            "workspace_dir": str(ws),
        })
        return StepResult(
            done=False, phase=PHASE, step="scan_islands_rubrics",
            step_index=self._step_index(), action="skill_completed",
            data={"success": result.success},
        )

    def _step_discuss(self) -> StepResult:
        ws = self._ws()
        result = self.executor.execute("w6-discuss", {
            "workspace_dir": str(ws),
            "research_topic": self._research_topic(),
        })
        return StepResult(
            done=False, phase=PHASE, step="multi_agent_discuss",
            step_index=self._step_index(), action="skill_completed",
            data={"success": result.success, "llm_response": result.llm_response},
        )

    def _step_memory(self) -> StepResult:
        return StepResult(
            done=False, phase=PHASE, step="evolution_memory",
            step_index=self._step_index(), action="memory_updated",
        )

    def _step_island_assign(self) -> StepResult:
        ws = self._ws()
        result = self.executor.execute("w6-island-assign", {
            "workspace_dir": str(ws),
        })
        return StepResult(
            done=False, phase=PHASE, step="island_assign",
            step_index=self._step_index(), action="skill_completed",
            data={"success": result.success},
        )

    def _step_refine(self) -> StepResult:
        return StepResult(
            done=False, phase=PHASE, step="refine_atoms",
            step_index=self._step_index(), action="atoms_refined",
        )

    def _step_claim_chain(self) -> StepResult:
        ws = self._ws()
        result = self.executor.execute("w6-write-claim-chain", {
            "workspace_dir": str(ws),
        })
        return StepResult(
            done=False, phase=PHASE, step="write_claim_chain",
            step_index=self._step_index(), action="chain_written",
            data={"success": result.success},
        )

    def _step_research(self) -> StepResult:
        ws = self._ws()
        topic = self._research_topic()
        result = self.executor.execute(
            "w6-research",
            variables={
                "workspace_dir": str(ws),
                "research_topic": topic,
            },
            pre_search=topic,
        )
        return StepResult(
            done=True, phase=PHASE, step="web_research",
            step_index=self._step_index(), action="skill_completed",
            data={"success": result.success},
        )
