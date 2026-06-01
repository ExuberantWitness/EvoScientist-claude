"""W5 代码实现 — 等待用户完成代码"""
from pes_controller.base_phase import BasePhase

class W5WaitUserCode(BasePhase):
    def run(self):
        return {
            "action": "wait_user_code",
            "step": "wait_user_code",
            "instruction": "等待用户在 Claude Code 中完成代码实现。完成后点击满意→下一步。"
        }
