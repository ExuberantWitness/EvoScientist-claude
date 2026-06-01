"""W5 代码实现 — 生成 BuildSpec 规格书"""
from pes_controller.base_phase import BasePhase

class W5GenerateCodeSpec(BasePhase):
    def run(self):
        return {
            "action": "generate_code_spec",
            "step": "generate_code_spec",
            "instruction": "从CC winner proposal + baseline机制对比提取结构化 BuildSpec，保存为 build_spec.json。用户审批后进入代码生成。"
        }
