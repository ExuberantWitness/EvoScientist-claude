"""W7 论文写作 — 调用 /evo-write skill"""
from pes_controller.base_phase import BasePhase

class W7InvokeSkillWrite(BasePhase):
    def run(self):
        return {
            "action": "invoke_skill",
            "skill": "/evo-write",
            "step": "invoke_skill_write",
            "instruction": "基于全部CC状态+实验结果生成论文markdown。不编造结果，包含负结果和局限性。"
        }
