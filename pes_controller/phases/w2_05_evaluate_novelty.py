"""W2 问题分析 — RND+Rubric新颖性评价"""
from pes_controller.base_phase import BasePhase

class W2EvaluateNovelty(BasePhase):
    def run(self):
        return {"rubric_novelty": 0.5, "rnd_coarse": 0.5, "rnd_fine": 0.5}
