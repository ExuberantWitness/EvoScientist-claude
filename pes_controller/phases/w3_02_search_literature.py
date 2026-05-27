"""W3 方案方向 — 自主上网查阅文献"""
from pes_controller.phases.w2_02_search_literature import W2SearchLiterature

class W3SearchLiterature(W2SearchLiterature):
    def run(self):
        topic = self.state.get("research_topic", "")
        return {"search_focus": "方法搜索", "topic": topic,
                "sources": ["tavily", "arxiv", "semantic_scholar", "github"]}
