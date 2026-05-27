"""W2 问题分析 — 自主上网查阅文献"""
from pes_controller.base_phase import BasePhase

class W2SearchLiterature(BasePhase):
    def run(self):
        # 调用 L2 sdk/web_process.py 搜索
        topic = self.state.get("research_topic", "")
        return {"search_focus": "方向搜索", "topic": topic,
                "sources": ["tavily", "arxiv", "semantic_scholar"]}
