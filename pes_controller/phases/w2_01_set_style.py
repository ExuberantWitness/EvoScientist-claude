"""W2 问题分析 — 确定研究风格"""
from pes_controller.base_phase import BasePhase

class W2SetStyle(BasePhase):
    def run(self):
        return {"focus": "问题分析", "depth": "到网络组件/loss项级别",
                "perspective": "批判性分析", "constraints": ["具体而非笼统", "必须有因果链"]}
