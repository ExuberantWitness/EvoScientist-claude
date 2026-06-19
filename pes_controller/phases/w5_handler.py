"""W5 代码实现 Handler — 生成代码规范 + 等待用户实现。"""
from __future__ import annotations

import logging

from pes_controller.phases import register_handler
from pes_controller.phases.base import BasePhaseHandler
from pes_controller.types import StepResult

logger = logging.getLogger(__name__)

PHASE = "W5 代码实现"


@register_handler(PHASE)
class W5Handler(BasePhaseHandler):
    phase_label = PHASE
    chain_steps = ["generate_code_spec", "run_step_pipeline",
                   "generate_code_plan", "wait_user_code"]

    def build_step(self, step_name: str) -> StepResult:
        dispatch = {
            "generate_code_spec": self._step_code_spec,
            "run_step_pipeline": self._step_pipeline,
            "generate_code_plan": self._step_code_plan,
            "wait_user_code": self._step_wait,
        }
        handler = dispatch.get(step_name)
        if handler is None:
            return StepResult(done=True, phase=PHASE, step=step_name,
                              step_index=self._step_index(), action="error",
                              data={"message": f"Unknown step: {step_name}"})
        return handler()

    def _step_code_spec(self) -> StepResult:
        ws = self._ws()
        result = self.executor.execute("flux-code-agent-pre", {
            "workspace_dir": str(ws),
            "research_topic": self._research_topic(),
        })
        return StepResult(
            done=False, phase=PHASE, step="generate_code_spec",
            step_index=self._step_index(), action="skill_completed",
            data={"success": result.success},
        )

    def _step_pipeline(self) -> StepResult:
        return StepResult(
            done=False, phase=PHASE, step="run_step_pipeline",
            step_index=self._step_index(), action="pipeline_completed",
        )

    def _step_code_plan(self) -> StepResult:
        return StepResult(
            done=False, phase=PHASE, step="generate_code_plan",
            step_index=self._step_index(), action="plan_generated",
        )

    def _step_wait(self) -> StepResult:
        # Set state to wait for user code
        self.state["status"] = "awaiting_user_code"
        self._write_state(self.state)
        return StepResult(
            done=True, phase=PHASE, step="wait_user_code",
            step_index=self._step_index(), action="wait_for_user_code",
            data={"message": "等待用户在 Claude Code 中完成代码实现..."},
        )

    def _write_state(self, state):
        from pes_controller.protocol import atomic_write
        import time
        from pathlib import Path
        ws = self._ws()
        state["timestamp"] = time.time()
        atomic_write(ws / "PIPELINE_STATE.json", state)
