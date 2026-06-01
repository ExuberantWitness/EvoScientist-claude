"""W6 结果分析 — 扫描 Island + Rubric 对比"""
from pes_controller.base_phase import BasePhase

class W6ScanIslandsRubrics(BasePhase):
    def run(self):
        return {
            "action": "scan_islands_rubrics",
            "step": "scan_islands_rubrics",
            "instruction": "扫描 Island 触发 Rubrics 对比。检查同CC条件下的异常性能差异。"
        }
