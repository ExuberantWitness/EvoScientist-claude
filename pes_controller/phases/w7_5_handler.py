"""W7.5 审稿修复 Handler — 2轮 review+fix + 产物验证。"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from pes_controller.phases import register_handler
from pes_controller.phases.base import BasePhaseHandler
from pes_controller.types import StepResult

logger = logging.getLogger(__name__)

PHASE = "W7.5 审稿修复"


@register_handler(PHASE)
class W7_5Handler(BasePhaseHandler):
    phase_label = PHASE
    chain_steps = [
        "invoke_skill_improve_review_1",
        "invoke_skill_improve_fix_1",
        "invoke_skill_improve_review_2",
        "invoke_skill_improve_fix_2",
        "verify_deliverables",
    ]

    def build_step(self, step_name: str) -> StepResult:
        if step_name.startswith("invoke_skill_improve_review_"):
            round_num = step_name.split("_")[-1]
            return self._step_review(round_num)
        elif step_name.startswith("invoke_skill_improve_fix_"):
            round_num = step_name.split("_")[-1]
            return self._step_fix(round_num)
        elif step_name == "verify_deliverables":
            return self._step_verify()
        return StepResult(done=True, phase=PHASE, step=step_name,
                          step_index=self._step_index(), action="error",
                          data={"message": f"Unknown step: {step_name}"})

    def _step_review(self, round_num: str) -> StepResult:
        ws = self._ws()
        result = self.executor.execute("flux-paper-improve", {
            "workspace_dir": str(ws),
            "round": round_num,
            "mode": "review",
            "research_topic": self._research_topic(),
            "venue": self._venue(),
        })
        return StepResult(
            done=False, phase=PHASE,
            step=f"invoke_skill_improve_review_{round_num}",
            step_index=self._step_index(), action="skill_completed",
            data={"round": int(round_num), "mode": "review",
                  "success": result.success, "llm_response": result.llm_response},
        )

    def _step_fix(self, round_num: str) -> StepResult:
        ws = self._ws()
        result = self.executor.execute("flux-paper-improve", {
            "workspace_dir": str(ws),
            "round": round_num,
            "mode": "fix",
            "venue": self._venue(),
        })
        return StepResult(
            done=False, phase=PHASE,
            step=f"invoke_skill_improve_fix_{round_num}",
            step_index=self._step_index(), action="skill_completed",
            data={"round": int(round_num), "mode": "fix",
                  "success": result.success, "files_written": result.files_written},
        )

    def _step_verify(self) -> StepResult:
        ws = self._ws()
        checks = {
            "main_pdf": (ws / "paper" / "main.pdf").exists(),
            "improvement_log": (ws / "PAPER_IMPROVEMENT_LOG.md").exists(),
        }
        all_ok = all(checks.values())
        return StepResult(
            done=all_ok, phase=PHASE, step="verify_deliverables",
            step_index=self._step_index(),
            action="verify_passed" if all_ok else "verify_failed",
            data={"checks": checks, "all_ok": all_ok},
        )
