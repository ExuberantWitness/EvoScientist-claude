"""W8 审阅 Handler — 3轮 review+fix + 最终审稿 + 产物验证。

W8 使用 MiMo 模型（通过 use_mimo=True 获取独立的 LLMClient）。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from pes_controller.phases import register_handler
from pes_controller.phases.base import BasePhaseHandler
from pes_controller.types import StepResult

logger = logging.getLogger(__name__)

PHASE = "W8 审阅"


@register_handler(PHASE)
class W8Handler(BasePhaseHandler):
    phase_label = PHASE
    chain_steps = [
        "invoke_skill_review_round_1",
        "invoke_skill_review_fix_1",
        "invoke_skill_review_round_2",
        "invoke_skill_review_fix_2",
        "invoke_skill_review_round_3",
        "verify_deliverables",
    ]

    def build_step(self, step_name: str) -> StepResult:
        parts = step_name.replace("invoke_skill_review_", "").split("_")
        # round_N or fix_N
        suffix = parts[-1]
        is_round = "round" in step_name

        if is_round:
            return self._step_review(suffix)
        elif "fix" in step_name:
            return self._step_fix(suffix)
        elif step_name == "verify_deliverables":
            return self._step_verify()
        return StepResult(done=True, phase=PHASE, step=step_name,
                          step_index=self._step_index(), action="error",
                          data={"message": f"Unknown step: {step_name}"})

    def _step_review(self, round_num: str) -> StepResult:
        ws = self._ws()
        # W8 uses MiMo model — create a dedicated executor
        executor = self._get_mimo_executor()
        result = executor.execute("flux-review-loop", {
            "workspace_dir": str(ws),
            "round": round_num,
            "mode": "review",
            "research_topic": self._research_topic(),
            "venue": self._venue(),
        })
        return StepResult(
            done=False, phase=PHASE,
            step=f"invoke_skill_review_round_{round_num}",
            step_index=self._step_index(), action="skill_completed",
            data={"round": int(round_num), "mode": "review",
                  "success": result.success, "llm_response": result.llm_response},
        )

    def _step_fix(self, round_num: str) -> StepResult:
        ws = self._ws()
        executor = self._get_mimo_executor()
        result = executor.execute("flux-review-loop", {
            "workspace_dir": str(ws),
            "round": round_num,
            "mode": "fix",
            "venue": self._venue(),
        })
        return StepResult(
            done=False, phase=PHASE,
            step=f"invoke_skill_review_fix_{round_num}",
            step_index=self._step_index(), action="skill_completed",
            data={"round": int(round_num), "mode": "fix",
                  "success": result.success, "files_written": result.files_written},
        )

    def _step_verify(self) -> StepResult:
        ws = self._ws()
        checks = {
            "auto_review": (ws / "AUTO_REVIEW.md").exists(),
            "review_state": (ws / "REVIEW_STATE.json").exists(),
            "claims_from_results": (ws / "CLAIMS_FROM_RESULTS.md").exists(),
        }
        all_ok = all(checks.values())
        return StepResult(
            done=all_ok, phase=PHASE, step="verify_deliverables",
            step_index=self._step_index(),
            action="verify_passed" if all_ok else "verify_failed",
            data={"checks": checks, "all_ok": all_ok},
        )

    def _get_mimo_executor(self):
        """Create or reuse a SkillExecutor with MiMo model for W8.

        Falls back to DeepSeek if MIMO_* env vars are not set.
        """
        if not hasattr(self, '_mimo_executor') or self._mimo_executor is None:
            from pes_controller.llm_client import LLMClient
            from pes_controller.skill_executor import SkillExecutor

            mimo_key = os.environ.get("MIMO_API_KEY", "")
            if mimo_key:
                api_key = mimo_key
                base_url = os.environ.get("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1")
                model = os.environ.get("MIMO_MODEL", "mimo-v2.5-pro")
            else:
                # Fallback to DeepSeek when MiMo is not configured
                api_key = os.environ.get("DEEPSEEK_API_KEY", "")
                base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
                model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
            llm = LLMClient(api_key=api_key, base_url=base_url, model=model)
            skills_dir = Path(__file__).parent.parent.parent / "skills"
            self._mimo_executor = SkillExecutor(skills_dir=skills_dir, llm_client=llm)
        return self._mimo_executor
