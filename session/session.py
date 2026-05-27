"""Session核心数据结构 (OpenRath-style): 结构化Chunks + Lineage图"""
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Session:
    session_id: str
    workspace_dir: str
    chunks: list = field(default_factory=list)
    lineage_graph: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    created_at: str = ""

    def fork(self) -> "Session":
        """创建分支session"""
        return Session(
            session_id=f"{self.session_id}_fork",
            workspace_dir=self.workspace_dir,
            metadata={"parent": self.session_id},
        )

    def merge(self, other: "Session") -> "Session":
        """合并两个session"""
        merged = Session(
            session_id=f"{self.session_id}_merged",
            workspace_dir=self.workspace_dir,
            chunks=self.chunks + other.chunks,
            lineage_graph={**self.lineage_graph, **other.lineage_graph},
        )
        return merged
