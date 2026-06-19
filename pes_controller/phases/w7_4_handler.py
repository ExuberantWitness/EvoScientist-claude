"""W7.4 编译 Handler — latexmk 编译 LaTeX 论文。"""
from __future__ import annotations

import logging
from pathlib import Path

from pes_controller.phases import register_handler
from pes_controller.phases.base import BasePhaseHandler
from pes_controller.types import StepResult

logger = logging.getLogger(__name__)

PHASE = "W7.4 编译"


@register_handler(PHASE)
class W7_4Handler(BasePhaseHandler):
    phase_label = PHASE
    chain_steps = ["invoke_skill_paper_compile", "verify_deliverables"]

    def build_step(self, step_name: str) -> StepResult:
        if step_name == "invoke_skill_paper_compile":
            return self._step_compile()
        elif step_name == "verify_deliverables":
            return self._step_verify()
        return StepResult(done=True, phase=PHASE, step=step_name,
                          step_index=self._step_index(), action="error",
                          data={"message": f"Unknown step: {step_name}"})

    def _step_compile(self) -> StepResult:
        ws = self._ws()
        result = self.executor.execute("flux-paper-compile", {
            "workspace_dir": str(ws),
        })
        return StepResult(
            done=False, phase=PHASE, step="invoke_skill_paper_compile",
            step_index=self._step_index(), action="skill_completed",
            data={"success": result.success, "files_written": result.files_written,
                  "actions_executed": result.actions_executed},
        )

    def _step_verify(self) -> StepResult:
        ws = self._ws()
        pdf_path = ws / "paper" / "main.pdf"
        has_pdf = pdf_path.exists()
        size_ok = False
        if has_pdf:
            size_ok = pdf_path.stat().st_size > 100 * 1024  # > 100KB
        all_ok = has_pdf and size_ok
        return StepResult(
            done=all_ok, phase=PHASE, step="verify_deliverables",
            step_index=self._step_index(),
            action="verify_passed" if all_ok else "verify_failed",
            data={"has_pdf": has_pdf, "size_ok": size_ok, "all_ok": all_ok},
        )
