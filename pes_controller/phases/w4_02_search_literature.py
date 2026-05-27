"""W4 具体方案生成 — 自主上网查阅文献"""
from pes_controller.base_phase import BasePhase

class W4SearchLiterature(BasePhase):
    def run(self):
        topic = self.state.get("research_topic", "")
        return {"search_focus": "实现搜索", "topic": topic,
                "sources": ["tavily", "github", "arxiv"]}
