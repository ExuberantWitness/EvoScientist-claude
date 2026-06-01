"""W6 结果分析 - 精炼CC atoms"""
from pes_controller.base_phase import BasePhase
class W6RefineAtoms(BasePhase):
    def run(self):
        return {"action":"refine_atoms","step":"refine_atoms","instruction":"CC atoms翻译为算法规格，含实验结果反馈。"}
