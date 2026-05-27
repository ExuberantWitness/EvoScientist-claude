"""W4 具体方案生成 — 确定研究风格"""
from pes_controller.base_phase import BasePhase

class W4SetStyle(BasePhase):
    def run(self):
        return {"focus": "具体方案生成", "depth": "到伪代码/公式级别",
                "perspective": "工程化思维", "constraints": ["必须有可用原型", "必须可复现"]}
