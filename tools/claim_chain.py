"""Claim Chain: Local file-based Atom Graph for algorithm development.

Stores Atoms (claims + evidence + status) and typed Relations in JSONL files.
Designed as the knowledge hub (L4) in the four-layer architecture:
  L1 (scores) ↔ L4 (Claim Chain) ↔ L2 (Rubric)
                      ↔ L3 (Islands)

Atom types (OpenResearch-compatible):
  fact, method, theorem, verification

Relation types:
  motivates, derives, validates, contradicts, implements,
  compares_to, causes, boundary_of, specializes

Usage:
  from claim_chain import ClaimChain
  cc = ClaimChain("/path/to/project")
  cc.add_atom(type="method", title="PPO baseline", content="...", tags=["algorithm", "ppo"])
  cc.add_relation(source_id=1, target_id=2, type="validates", evidence="score=18")
"""

import json
import time
from pathlib import Path


class ClaimChain:
    """File-based Atom Graph with JSONL storage."""

    def __init__(self, workspace_dir: str | Path, base_dir: str | Path | None = None):
        if base_dir:
            self.base_dir = Path(base_dir)
        else:
            self.base_dir = Path(workspace_dir) / "claim_chain"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.atoms_path = self.base_dir / "atoms.jsonl"
        self.relations_path = self.base_dir / "relations.jsonl"
        self._next_atom_id = self._max_numeric_id(self.atoms_path) + 1
        self._next_rel_id = self._max_numeric_id(self.relations_path) + 1

    @staticmethod
    def _max_numeric_id(path: Path) -> int:
        """Find the maximum numeric ID in a JSONL file (handles mixed int/str IDs)."""
        if not path.exists():
            return 0
        max_id = 0
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                    n = int(d.get("id", 0))
                    if n > max_id:
                        max_id = n
                except (json.JSONDecodeError, ValueError, TypeError):
                    pass
        return max_id

    @staticmethod
    def _count_lines(path: Path) -> int:
        if not path.exists():
            return 0
        count = 0
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count

    def add_atom(
        self,
        type: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
        evidence_level: str = "experiment",
        metadata: dict | None = None,
    ) -> dict:
        """Add an Atom to the chain.

        Args:
            type: One of fact, method, theorem, verification
            title: Short human-readable title
            content: Full claim description
            tags: Categorization tags (e.g., ["algorithm", "ppo"])
            evidence_level: experiment, literature, or llm_analysis
            metadata: Extra structured data

        Returns:
            The created Atom dict with assigned id.
        """
        assert type in ("fact", "method", "theorem", "verification"), f"Invalid atom type: {type}"
        assert evidence_level in ("experiment", "literature", "llm_analysis")

        atom = {
            "id": self._next_atom_id,
            "type": type,
            "title": title,
            "content": content,
            "tags": tags or [],
            "evidence_level": evidence_level,
            "status": "active",
            "metadata": metadata or {},
            "created_at": time.time(),
        }
        self._next_atom_id += 1

        with open(self.atoms_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(atom, ensure_ascii=False) + "\n")

        return atom

    def add_relation(
        self,
        source_id: int,
        target_id: int,
        type: str,
        evidence: str = "",
        metadata: dict | None = None,
    ) -> dict:
        """Add a typed Relation between two Atoms.

        Args:
            source_id: Source Atom ID
            target_id: Target Atom ID
            type: One of motivates, derives, validates, contradicts,
                  compares_to, causes, boundary_of, specializes
            evidence: Why this relation holds
            metadata: Extra structured data

        Returns:
            The created Relation dict with assigned id.
        """
        valid_types = (
           "motivates", "derives", "validates", "contradicts", "implements",
            "compares_to", "causes", "boundary_of", "specializes",
        )
        assert type in valid_types, f"Invalid relation type: {type}"

        relation = {
            "id": self._next_rel_id,
            "source_id": source_id,
            "target_id": target_id,
            "type": type,
            "evidence": evidence,
            "metadata": metadata or {},
            "created_at": time.time(),
        }
        self._next_rel_id += 1

        with open(self.relations_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(relation, ensure_ascii=False) + "\n")

        return relation

    def get_atoms(
        self,
        type: str | None = None,
        tags: list[str] | None = None,
        status: str = "active",
        limit: int = 100,
    ) -> list[dict]:
        """Query atoms with optional filters."""
        results = []
        if not self.atoms_path.exists():
            return results

        with open(self.atoms_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    atom = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if status and atom.get("status") != status:
                    continue
                if type and atom.get("type") != type:
                    continue
                if tags:
                    atom_tags = set(atom.get("tags", []))
                    if not all(t in atom_tags for t in tags):
                        continue
                results.append(atom)
                if len(results) >= limit:
                    break

        return results

    def get_relations(
        self,
        source_id: int | None = None,
        target_id: int | None = None,
        type: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Query relations with optional filters."""
        results = []
        if not self.relations_path.exists():
            return results

        with open(self.relations_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rel = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if source_id is not None and rel.get("source_id") != source_id:
                    continue
                if target_id is not None and rel.get("target_id") != target_id:
                    continue
                if type and rel.get("type") != type:
                    continue
                results.append(rel)
                if len(results) >= limit:
                    break

        return results

    def get_atom(self, atom_id: int) -> dict | None:
        """Get a single atom by ID."""
        for atom in self.get_atoms(status=None):
            if atom["id"] == atom_id:
                return atom
        return None

    def get_related(self, atom_id: int, direction: str = "both") -> list[dict]:
        """Get all atoms related to a given atom.

        Args:
            atom_id: The atom to find relations for
            direction: "outgoing" (source=atom_id), "incoming" (target=atom_id), or "both"
        """
        related_atoms = []
        seen = set()

        if direction in ("outgoing", "both"):
            for rel in self.get_relations(source_id=atom_id):
                target = self.get_atom(rel["target_id"])
                if target and target["id"] not in seen:
                    related_atoms.append({"relation": rel, "atom": target})
                    seen.add(target["id"])

        if direction in ("incoming", "both"):
            for rel in self.get_relations(target_id=atom_id):
                source = self.get_atom(rel["source_id"])
                if source and source["id"] not in seen:
                    related_atoms.append({"relation": rel, "atom": source})
                    seen.add(source["id"])

        return related_atoms

    def deactivate_atom(self, atom_id: int) -> bool:
        """Mark an atom as superseded (soft delete)."""
        atoms = []
        if not self.atoms_path.exists():
            return False

        with open(self.atoms_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    atom = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if atom["id"] == atom_id:
                    atom["status"] = "superseded"
                atoms.append(atom)

        with open(self.atoms_path, "w", encoding="utf-8") as f:
            for atom in atoms:
                f.write(json.dumps(atom, ensure_ascii=False) + "\n")

        return True

    def get_graph_summary(self) -> dict:
        """Return summary statistics of the claim chain."""
        atoms = self.get_atoms(status=None)
        relations = self.get_relations()

        active_atoms = [a for a in atoms if a.get("status") == "active"]
        type_counts = {}
        for a in active_atoms:
            t = a["type"]
            type_counts[t] = type_counts.get(t, 0) + 1

        rel_type_counts = {}
        for r in relations:
            t = r["type"]
            rel_type_counts[t] = rel_type_counts.get(t, 0) + 1

        return {
            "total_atoms": len(atoms),
            "active_atoms": len(active_atoms),
            "atom_types": type_counts,
            "total_relations": len(relations),
            "relation_types": rel_type_counts,
        }

    def get_atoms_index(self) -> dict:
        """返回结构索引不含完整内容，供渐进式发现用。

        Agent 看到结构形状（哪些类型存在/缺失、孤原子数量、tag词汇表），
        但不直接看到数据。必须通过 pes_cli 查询才能获取详情。
        """
        atoms = self.get_atoms(status=None)
        relations = self.get_relations()

        type_counts = {}
        for a in atoms:
            t = a["type"]
            type_counts[t] = type_counts.get(t, 0) + 1

        related_ids = set()
        for r in relations:
            related_ids.add(r["source_id"])
            related_ids.add(r["target_id"])

        all_ids = set()
        for a in atoms:
            try:
                all_ids.add(int(a["id"]))
            except (ValueError, TypeError):
                pass  # skip non-numeric IDs from Markdown parser
        orphan_count = len(all_ids - related_ids)

        rel_type_counts = {}
        for r in relations:
            t = r["type"]
            rel_type_counts[t] = rel_type_counts.get(t, 0) + 1

        # Tag vocabulary
        all_tags = set()
        for a in atoms:
            for tag in a.get("tags", []):
                all_tags.add(tag)

        # Missing atom types (common research pipeline types)
        all_known_types = {"fact", "method", "theorem", "verification", "hypothesis", "observation"}
        missing_types = sorted(all_known_types - set(type_counts.keys()))

        # Missing relation types
        all_known_rels = {"validates", "contradicts", "derives", "boundary_of", "motivates",
                         "specializes", "compares_to", "causes", "implements"}
        missing_rels = sorted(all_known_rels - set(rel_type_counts.keys()))

        return {
            "total_atoms": len(atoms),
            "type_counts": type_counts,
            "missing_atom_types": missing_types,
            "total_relations": len(relations),
            "relation_type_counts": rel_type_counts,
            "missing_relation_types": missing_rels,
            "orphan_atom_count": orphan_count,
            "max_atom_id": max(all_ids) if all_ids else 0,
            "tag_vocabulary": sorted(all_tags),
            "empty": len(atoms) == 0,
        }

    def export_dot(self) -> str:
        """Export the graph as a DOT format string for visualization."""
        atoms = self.get_atoms()
        relations = self.get_relations()
        atom_map = {a["id"]: a for a in atoms}

        lines = ["digraph ClaimChain {"]
        lines.append('  rankdir=LR;')
        lines.append('  node [shape=box];')

        for atom in atoms:
            label = atom["title"].replace('"', '\\"')
            color = {"fact": "lightblue", "method": "lightgreen", "theorem": "lightyellow", "verification": "lightsalmon"}
            c = color.get(atom["type"], "white")
            lines.append(f'  a{atom["id"]} [label="{label}" style=filled fillcolor={c}];')

        for rel in relations:
            if rel["source_id"] in atom_map and rel["target_id"] in atom_map:
                label = rel["type"].replace("_", " ")
                style = {"validates": "solid,color=green", "contradicts": "solid,color=red",
                         "derives": "dashed", "specializes": "dashed,color=blue"}.get(rel["type"], "solid")
                lines.append(f'  a{rel["source_id"]} -> a{rel["target_id"]} [label="{label}" {style}];')

        lines.append("}")
        return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Claim Chain CLI")
    sub = parser.add_subparsers(dest="command")

    # summary
    sub.add_parser("summary", help="Show claim chain summary")

    # add-atom
    aa = sub.add_parser("add-atom", help="Add an atom")
    aa.add_argument("--type", required=True, choices=["fact", "method", "theorem", "verification"])
    aa.add_argument("--title", required=True)
    aa.add_argument("--content", required=True)
    aa.add_argument("--tags", default="", help="Comma-separated tags")
    aa.add_argument("--evidence-level", default="experiment", choices=["experiment", "literature", "llm_analysis"])

    # add-relation
    ar = sub.add_parser("add-relation", help="Add a relation")
    ar.add_argument("--source", type=int, required=True)
    ar.add_argument("--target", type=int, required=True)
    ar.add_argument("--type", required=True,
                    choices=["motivates", "derives", "validates", "contradicts",
                             "compares_to", "causes", "boundary_of", "specializes"])
    ar.add_argument("--evidence", default="")

    # list-atoms
    la = sub.add_parser("list-atoms", help="List atoms")
    la.add_argument("--type", choices=["fact", "method", "theorem", "verification"])
    la.add_argument("--tags", default="", help="Comma-separated tags to filter")
    la.add_argument("--limit", type=int, default=20)

    # list-relations
    lr = sub.add_parser("list-relations", help="List relations")
    lr.add_argument("--type", choices=["motivates", "derives", "validates", "contradicts",
                                       "compares_to", "causes", "boundary_of", "specializes"])
    lr.add_argument("--source", type=int)
    lr.add_argument("--target", type=int)
    lr.add_argument("--limit", type=int, default=20)

    # graph
    sub.add_parser("dot", help="Export DOT format for visualization")

    # related
    rd = sub.add_parser("related", help="Get related atoms")
    rd.add_argument("--id", type=int, required=True)
    rd.add_argument("--direction", default="both", choices=["outgoing", "incoming", "both"])

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    cc = ClaimChain(".")

    if args.command == "summary":
        print(json.dumps(cc.get_graph_summary(), indent=2, ensure_ascii=False))

    elif args.command == "add-atom":
        tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []
        atom = cc.add_atom(type=args.type, title=args.title, content=args.content,
                           tags=tags, evidence_level=args.evidence_level)
        print(json.dumps(atom, indent=2, ensure_ascii=False))

    elif args.command == "add-relation":
        rel = cc.add_relation(source_id=args.source, target_id=args.target,
                              type=args.type, evidence=args.evidence)
        print(json.dumps(rel, indent=2, ensure_ascii=False))

    elif args.command == "list-atoms":
        tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else None
        atoms = cc.get_atoms(type=args.type, tags=tags, limit=args.limit)
        for a in atoms:
            print(f"  [{a['id']}] {a['type']}/{a.get('tags', [])} {a['title']}")

    elif args.command == "list-relations":
        rels = cc.get_relations(source_id=args.source, target_id=args.target,
                                type=args.type, limit=args.limit)
        for r in rels:
            print(f"  [{r['id']}] a{r['source_id']} --{r['type']}--> a{r['target_id']}  ({r.get('evidence', '')})")

    elif args.command == "dot":
        print(cc.export_dot())

    elif args.command == "related":
        related = cc.get_related(atom_id=args.id, direction=args.direction)
        for entry in related:
            rel = entry["relation"]
            atom = entry["atom"]
            direction_label = "→" if rel["source_id"] == args.id else "←"
            print(f"  {direction_label} [{rel['type']}] a{atom['id']}: {atom['title']}")
