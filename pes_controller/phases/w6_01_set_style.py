"""W6 结果分析 — 设定分析视角"""
from pes_controller.base_phase import BasePhase

class W6SetStyle(BasePhase):
    def run(self):
        return {"focus": "结果分析", "depth": "统计显著性+效应量+ablations",
                "perspective": "批判性自评", "constraints": ["不用幻觉编造数据", "必须诚实报告"]}
