"""W8 审阅 — 调用 /evo-review skill"""
from pes_controller.base_phase import BasePhase

class W8InvokeSkillReview(BasePhase):
    def run(self):
        return {
            "action": "invoke_skill",
            "skill": "/evo-review",
            "step": "invoke_skill_review",
            "instruction": "外部LLM审阅论文。不满则回到W7重写。"
        }
