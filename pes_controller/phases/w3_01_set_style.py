"""W3 方案方向 — 确定研究风格"""
from pes_controller.phases.w2_01_set_style import W2SetStyle

class W3SetStyle(W2SetStyle):
    def run(self):
        return {"focus": "方案方向", "depth": "针对难点提出解决路径",
                "perspective": "建设性思考", "constraints": ["必须有技术路径", "必须区分baseline"]}
