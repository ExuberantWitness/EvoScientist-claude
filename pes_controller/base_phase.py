"""顶层基类 — 所有Phase和所有Step的最终祖先"""
class BasePhase:
    def __init__(self, state: dict, session=None):
        self.state = state
        self.session = session

    def run(self):
        """默认编排流程。子类可override。"""
        raise NotImplementedError

    def invoke_personas(self): raise NotImplementedError
    def evaluate_novelty(self): raise NotImplementedError
    def elo_tournament(self): raise NotImplementedError
    def verify_products(self): raise NotImplementedError
    def evolution_memory(self): raise NotImplementedError
    def write_claim_chain(self): raise NotImplementedError

    def build_cc_context(self):
        """从L1 CC获取上下文注入persona prompt"""
        return {}

    def build_experiment_feedback(self):
        """从上次实验结果提取反馈"""
        return {}

    def build_regeneration_feedback(self):
        """从上次验证失败提取反馈"""
        return {}
