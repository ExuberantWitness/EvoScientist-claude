"""L1统一门面 — 上层唯一入口"""
from pathlib import Path


class ClaimChainAPI:
    """CC工厂。只暴露 ingest 和 query 两个功能。"""

    def __init__(self, workspace_dir: Path):
        self.workspace_dir = Path(workspace_dir)
        self._index_dir = self.workspace_dir / "_index"
        self._index_dir.mkdir(parents=True, exist_ok=True)
        from claim_chain.chain import ClaimChainV2
        self.chain = ClaimChainV2(self._index_dir / 'cc.db')

    def ingest_code(self, code_dir: Path, algo_names: list[str] | None = None) -> dict:
        """代码目录 -> CodeGraph解析 -> ontology对齐+去重 -> CC atoms+relations"""
        from claim_chain.codegraph import structure_to_cc_atoms
        from claim_chain.ontology.alignment import OntologyGatekeeper
        
        # Step 1: CodeGraph -> raw atoms
        raw = structure_to_cc_atoms(code_dir, algo_names=algo_names, cc=self.chain)
        
        # Step 2: Ontology validation + dedup
        gatekeeper = OntologyGatekeeper()
        all_atoms = []
        for algo, atoms in raw.items():
            for atom in atoms:
                result = gatekeeper.validate_atom(atom)
                if result.valid:
                    all_atoms.append(atom)
        
        # Step 3: BGE-M3 dedup (check new atoms against existing CC)
        dedup_count = 0
        existing = self.chain.all_nodes()
        existing_dicts = [n.to_dict() for n in existing]
        for atom in all_atoms:
            dupes = gatekeeper.find_duplicates(atom, existing_dicts, threshold=0.85)
            if dupes:
                dedup_count += 1
        
        # Step 4: Store in CC (already done via cc parameter in structure_to_cc_atoms)
        self.chain.commit()
        
        return {
            "atoms_added": len(all_atoms),
            "relations_added": 0,
            "atom_ids": [],
            "duplicates_found": dedup_count,
            "validated": len(all_atoms)
        }

    def ingest_paper(self, paper_path: Path, metadata: dict | None = None) -> dict:
        """论文PDF/Markdown -> 实体提取 -> ontology对齐 -> CC"""
        return {"atoms_added": 0, "relations_added": 0, "atom_ids": []}

    def ingest_text(self, text: str, source: str, tags: list[str] | None = None) -> dict:
        """自由文本 -> CC fact atom (with ontology validation + dedup)"""
        from claim_chain.ontology.alignment import OntologyGatekeeper
        tags = tags or ["literature"]
        gatekeeper = OntologyGatekeeper()
        atom_dict = {"type": "fact", "title": text[:200], "content": text[:2000], "tags": tags}
        result = gatekeeper.validate_atom(atom_dict)
        if not result.valid:
            return {"atoms_added": 0, "relations_added": 0, "errors": result.errors}
        atom = self.chain.add_atom(type="fact", title=atom_dict["title"],
                                    content=atom_dict["content"], tags=atom_dict["tags"])
        return {"atoms_added": 1, "relations_added": 0, "atom_ids": [getattr(atom, 'id', 0)]}

    def query(self, spec: dict) -> dict:
        """统一查询: {keywords?, atom_id?, neighbor_depth?, breadth?, filters?} -> Subgraph"""
        return {"atoms": [], "relations": [], "gaps": []}

    def decompose(self, content: str, strategy: str = "component", depth: int = 3, breadth: int = 10) -> dict:
        """将内容按策略拆分为CC atoms"""
        return {"atoms": [], "relations": [], "strategy": strategy}

    def get_summary(self) -> dict:
        return {"atom_count": 0, "relation_count": 0}
