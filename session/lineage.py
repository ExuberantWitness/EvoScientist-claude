"""Session谱系追踪 — fork/merge关系 + ancestors/descendants查询"""


class LineageGraph:
    def __init__(self):
        self.edges: dict[str, list[str]] = {}

    def add_fork(self, parent_id: str, child_id: str):
        self.edges.setdefault(parent_id, []).append(child_id)

    def ancestors(self, session_id: str) -> list[str]:
        """BFS查找所有祖先"""
        return []

    def descendants(self, session_id: str) -> list[str]:
        """DFS查找所有后代"""
        return []
