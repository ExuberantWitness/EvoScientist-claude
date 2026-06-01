"""W6 结果分析 — STEP 管线分析 (实验结果分析版)"""
from pes_controller.base_phase import BasePhase

class W6RunStepPipeline(BasePhase):
    def run(self):
        return {
            "action": "run_step_pipeline",
            "step": "run_step_pipeline",
            "instruction": "读取实验数据 → 性能对比 → 统计检验。读取 code_results 和 experiment artifacts。"
        }
