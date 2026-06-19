"""W7.3 LaTeX写作 Handler — 基于论文计划和图表生成 LaTeX 论文。"""
from __future__ import annotations

import logging
from pathlib import Path

from pes_controller.phases import register_handler
from pes_controller.phases.base import BasePhaseHandler
from pes_controller.types import StepResult

logger = logging.getLogger(__name__)

PHASE = "W7.3 LaTeX写作"


@register_handler(PHASE)
class W7_3Handler(BasePhaseHandler):
    phase_label = PHASE
    chain_steps = ["invoke_skill_paper_write", "verify_deliverables"]

    def build_step(self, step_name: str) -> StepResult:
        if step_name == "invoke_skill_paper_write":
            return self._step_write()
        elif step_name == "verify_deliverables":
            return self._step_verify()
        return StepResult(done=True, phase=PHASE, step=step_name,
                          step_index=self._step_index(), action="error",
                          data={"message": f"Unknown step: {step_name}"})

    def _step_write(self) -> StepResult:
        ws = self._ws()
        result = self.executor.execute("flux-paper-write", {
            "workspace_dir": str(ws),
            "paper_plan": self._read_file(ws / "PAPER_PLAN.md"),
            "figures_includes": self._read_file(ws / "figures" / "latex_includes.tex"),
            "venue": self._venue(),
            "research_topic": self._research_topic(),
        })
        return StepResult(
            done=False, phase=PHASE, step="invoke_skill_paper_write",
            step_index=self._step_index(), action="skill_completed",
            data={"success": result.success, "files_written": result.files_written},
        )

    def _step_verify(self) -> StepResult:
        ws = self._ws()
        checks = {
            "main_tex": (ws / "paper" / "main.tex").exists(),
            "sections_dir": (ws / "paper" / "sections").is_dir(),
            "references": (ws / "paper" / "references.bib").exists(),
        }
        all_ok = all(checks.values())
        return StepResult(
            done=all_ok, phase=PHASE, step="verify_deliverables",
            step_index=self._step_index(),
            action="verify_passed" if all_ok else "verify_failed",
            data={"checks": checks, "all_ok": all_ok},
        )

    @staticmethod
    def _read_file(path: Path) -> str:
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""
