"""L1统一门面 — 上层唯一入口"""
from pathlib import Path


class ClaimChainAPI:
    """CC工厂。只暴露 ingest 和 query 两个功能。"""

    def __init__(self, workspace_dir: Path):
        self.workspace_dir = Path(workspace_dir)
        self._index_dir = self.workspace_dir / "_index"
        self._index_dir.mkdir(parents=True, exist_ok=True)
        # Lazy init sub-modules

    def ingest_code(self, code_dir: Path, algo_names: list[str] | None = None) -> dict:
        """代码目录 -> CodeGraph解析 -> ontology对齐 -> CC atoms+relations"""
        return {"atoms_added": 0, "relations_added": 0, "atom_ids": []}

    def ingest_paper(self, paper_path: Path, metadata: dict | None = None) -> dict:
        """论文PDF/Markdown -> 实体提取 -> ontology对齐 -> CC"""
        return {"atoms_added": 0, "relations_added": 0, "atom_ids": []}

    def ingest_text(self, text: str, source: str, tags: list[str] | None = None) -> dict:
        """自由文本 -> BGE-M3粗筛 -> LLM细提取 -> ontology对齐 -> CC"""
        return {"atoms_added": 0, "relations_added": 0, "atom_ids": []}

    def query(self, spec: dict) -> dict:
        """统一查询: {keywords?, atom_id?, neighbor_depth?, breadth?, filters?} -> Subgraph"""
        return {"atoms": [], "relations": [], "gaps": []}

    def decompose(self, content: str, strategy: str = "component", depth: int = 3, breadth: int = 10) -> dict:
        """将内容按策略拆分为CC atoms"""
        return {"atoms": [], "relations": [], "strategy": strategy}

    def get_summary(self) -> dict:
        return {"atom_count": 0, "relation_count": 0}
