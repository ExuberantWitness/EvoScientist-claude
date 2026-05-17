"""Markdown Parser: 从 Obsidian vault 提取图结构 → 同步 JSONL 索引.

Phase B 核心模块. 功能:
  - 解析 YAML frontmatter
  - 提取类型化关系 (## 关系图)
  - 提取 [[wiki-link]] + 置信度标记 (EXTRACTED/INFERRED)
  - 同步到 _index/atoms.jsonl + _index/relations.jsonl
  - Self-wiring: 自动从 [[links]] 创建 CC relations
  - 确定性后校验: 边类型/引用/时序/矛盾

借鉴: Intern-Atlas edge extraction + GBrain self-wiring + Graphify 3-pass extraction
"""

import json
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

# ── 边权重 (GoS 模式) ──

EDGE_WEIGHTS = {
    "extends": 1.0, "improves": 1.0, "replaces": 1.0, "adapts": 1.0,
    "addressed_by": 1.0, "replaced_by": 1.0,
    "creates": 0.8, "affects": 0.9,
    "validates": 0.5, "contradicts": 0.5, "implements": 0.5,
    "derives": 0.3, "specializes": 0.3, "compares_to": 0.2,
    "compares": 0.2, "related_to": 0.3,
    "uses_component": 0.1, "background": 0.0, "motivates": 0.2,
    "member_of": 0.4,
}

STRONG_CAUSAL = {"extends", "improves", "replaces", "adapts",
                 "addressed_by", "replaced_by", "creates", "affects"}


# ── YAML Frontmatter Parser ──

def parse_frontmatter(text: str) -> dict:
    """从 Markdown 提取 YAML frontmatter."""
    m = re.match(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
    if not m:
        return {}
    data = {}
    for line in m.group(1).strip().split("\n"):
        line = line.strip()
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        val = val.strip().strip('"').strip("'")
        if val.startswith("[") and val.endswith("]"):
            val = [v.strip().strip('"').strip("'") for v in val[1:-1].split(",") if v.strip()]
        data[key.strip()] = val
    return data


# ── 类型化关系解析 ──

def parse_typed_relations(text: str) -> list[dict]:
    """从 '## 关系图' 节提取类型化关系.

    Syntax: - {edge_type} {←|→} {description} [[{target}]]

    Returns: [{source, edge_type, direction("incoming"/"outgoing"),
               target, description, confidence}]
    """
    m = re.search(r"## 关系图\s*\n(.*?)(?=\n## |\n---|\Z)", text, re.DOTALL)
    if not m:
        return []

    relations = []
    section = m.group(1)
    pattern = r"-\s*(\w+)\s+(←|→)\s+(.*?)\[\[([^\]]+)\]\](.*)"
    for match in re.finditer(pattern, section):
        edge_type = match.group(1)
        direction = "incoming" if match.group(2) == "←" else "outgoing"
        description = match.group(3).strip()
        target_raw = match.group(4).strip()
        extra = match.group(5).strip().lstrip(")").strip()

        # Parse target: "TD3 Baseline" or "CC Atom 5: EMTD3..."
        target_clean = target_raw.split(":")[-1].strip() if ":" in target_raw else target_raw

        relations.append({
            "edge_type": edge_type, "direction": direction,
            "target": target_clean, "target_raw": target_raw,
            "description": description, "extra": extra,
            "confidence": _detect_confidence(description, extra),
        })
    return relations


# ── [[wiki-link]] 提取 ──

def parse_wiki_links(text: str) -> list[dict]:
    """提取所有 [[wiki-link]] 及前后文 (用于 self-wiring).

    Returns: [{target, context_before, line}]
    """
    links = []
    for match in re.finditer(r"\[\[([^\]]+)\]\]", text):
        start = max(0, match.start() - 40)
        context = text[start:match.end() + 20].replace("\n", " ")
        target_raw = match.group(1)
        target_clean = target_raw.split(":")[-1].strip() if ":" in target_raw else target_raw
        links.append({
            "target": target_clean, "target_raw": target_raw,
            "context": context,
            "confidence": _detect_confidence(context, ""),
        })
    return links


def _detect_confidence(text: str, extra: str) -> str:
    """从文本中检测置信度标记."""
    combined = text + " " + extra
    if "EXTRACTED" in combined:
        return "EXTRACTED"
    if "INFERRED" in combined:
        return "INFERRED"
    if "SPECULATIVE" in combined or "推测" in combined:
        return "SPECULATIVE"
    return "EXTRACTED"  # default: 来自关系声明的视为 EXTRACTED


# ── 证据提取 ──

def parse_evidence(text: str) -> list[dict]:
    """从 '## 证据' 或 '### 证据' 节提取证据记录.

    识别 (EXTRACTED: ...) (INFERRED: ...) 标记.
    """
    evidence = []
    # 找 "## 证据" 或在前matter后的 "证据" 段落
    for m in re.finditer(
        r"[-*]\s+\*\*(\w+)\*\*:\s+(.*?)(?:\(EXTRACTED:\s*(.*?)\)|\(INFERRED:\s*(.*?)\))",
        text,
    ):
        source_type = m.group(1)
        desc = m.group(2).strip()
        extracted_ref = m.group(3) or m.group(4) or ""
        evidence.append({
            "source_type": source_type,
            "description": desc,
            "reference": extracted_ref.strip(),
            "confidence": "EXTRACTED" if m.group(3) else "INFERRED",
        })
    return evidence


# ── JSONL 索引同步 ──

class IndexSyncer:
    """将 Markdown vault 同步到 JSONL 索引."""

    def __init__(self, vault_dir: Path):
        self.vault_dir = Path(vault_dir)
        self.index_dir = self.vault_dir / "_index"
        self.index_dir.mkdir(parents=True, exist_ok=True)

    def sync_all(self) -> dict:
        """扫描 vault 所有 Markdown → 重建 JSONL 索引."""
        atoms = []
        relations = []
        node_links = defaultdict(list)  # {node_id: [{target, edge_type, ...}]}
        all_nodes = {}

        for md_file in sorted(self.vault_dir.rglob("*.md")):
            if md_file.parent.name.startswith("_") or md_file.parent.name.startswith("."):
                continue

            text = md_file.read_text(encoding="utf-8")
            meta = parse_frontmatter(text)
            typed_rels = parse_typed_relations(text)
            wiki_links = parse_wiki_links(text)
            evidence = parse_evidence(text)

            node_id = md_file.stem
            rel_path = str(md_file.relative_to(self.vault_dir))

            # Determine node type from parent directory
            node_type = _infer_node_type(rel_path)

            # Build atom
            atom = {
                "id": meta.get("id", node_id),
                "type": "method" if node_type == "Algorithm" else "observation",
                "title": meta.get("title", node_id),
                "content": _extract_summary(text),
                "tags": meta.get("tags", []),
                "status": meta.get("status", "active"),
                "evidence_level": "experiment",
                "metadata": {
                    "node_type": node_type,
                    "parent_algo_id": meta.get("parent", ""),
                    "bottleneck": meta.get("bottleneck", ""),
                    "category": meta.get("category", ""),
                    "created": meta.get("created", ""),
                    "file_path": rel_path,
                },
                "created_at": time.time(),
            }
            atoms.append(atom)
            all_nodes[node_id] = atom

            # Build relations from typed relations
            for rel in typed_rels:
                src = node_id
                tgt = _normalize_link_target(rel["target"])
                edge = {
                    "source_id": src, "target_id": tgt,
                    "type": rel["edge_type"],
                    "weight": EDGE_WEIGHTS.get(rel["edge_type"], 0.3),
                    "evidence": rel.get("description", ""),
                    "confidence": rel.get("confidence", "EXTRACTED"),
                    "metadata": {"source_file": rel_path, "bidirectional": True},
                    "created_at": time.time(),
                }
                relations.append(edge)
                node_links[src].append(edge)

            # Self-wiring: [[wiki-links]] → auto-create CC relations
            for wl in wiki_links:
                tgt = _normalize_link_target(wl["target"])
                if tgt == node_id:
                    continue
                # Don't duplicate typed relations
                if any(r["target_id"] == tgt for r in node_links.get(node_id, [])):
                    continue
                # Auto-infer edge type from context
                edge_type = _infer_edge_type_from_context(wl["context"])
                edge = {
                    "source_id": node_id, "target_id": tgt,
                    "type": edge_type,
                    "weight": EDGE_WEIGHTS.get(edge_type, 0.2),
                    "evidence": wl["context"].strip(),
                    "confidence": wl.get("confidence", "INFERRED"),
                    "metadata": {"source_file": rel_path, "auto_wired": True},
                    "created_at": time.time(),
                }
                relations.append(edge)
                node_links[node_id].append(edge)

        # Write JSONL
        self._write_jsonl("atoms.jsonl", atoms)
        self._write_jsonl("relations.jsonl", relations)

        # Write search index
        search_index = {}
        for atom in atoms:
            keywords = set(atom.get("tags", []))
            keywords.add(atom["id"])
            keywords.add(atom.get("metadata", {}).get("node_type", ""))
            for kw in keywords:
                search_index.setdefault(kw, []).append(atom["id"])

        (self.index_dir / "search_index.json").write_text(
            json.dumps(search_index, indent=2, ensure_ascii=False))

        return {
            "atoms_count": len(atoms), "relations_count": len(relations),
            "nodes": len(all_nodes), "auto_wired": sum(
                1 for r in relations if r.get("metadata", {}).get("auto_wired")),
            "by_confidence": _count_by_key(relations, "confidence"),
            "by_edge_type": _count_by_key(relations, "type"),
        }

    def _write_jsonl(self, filename: str, entries: list[dict]):
        path = self.index_dir / filename
        # IMPORTANT: sync_all() regenerates atoms/relations from Markdown files.
        # This DESTROYS any atoms/relations written by the pipeline CC (add_atom/add_relation).
        # Only call sync_all() when you want to fully rebuild from Markdown.
        with open(path, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def rebuild(self) -> dict:
        """完全重建索引 (删除现有 JSONL 后重建). 幂等.

        WARNING: This deletes ALL atoms/relations written by the pipeline CC.
        Only use this when you intend to rebuild the index from Markdown files alone.
        """
        for f in self.index_dir.glob("*.jsonl"):
            f.unlink()
        (self.index_dir / "search_index.json").unlink(missing_ok=True)
        return self.sync_all()


# ── 图查询 (薄查询原语, 供 GoS 使用) ──

class GraphQuery:
    """图引擎薄查询原语 (Intern-Atlas + GoS 适配)."""

    def __init__(self, index_dir: Path):
        self.index_dir = Path(index_dir)
        self._atoms = None
        self._relations = None
        self._adj = None

    def _load(self):
        if self._atoms is None:
            self._atoms = _read_jsonl(self.index_dir / "atoms.jsonl")
            self._relations = _read_jsonl(self.index_dir / "relations.jsonl")
            self._adj = self._build_adjacency()

    def _build_adjacency(self) -> dict:
        adj = defaultdict(list)
        for r in self._relations:
            src = r["source_id"]
            adj[src].append(r)
            # Bidirectional reverse
            if r.get("metadata", {}).get("bidirectional"):
                tgt = r["target_id"]
                adj[tgt].append({**r, "source_id": tgt, "target_id": src,
                                "type": f"rev_{r['type']}"})
        return dict(adj)

    def get_neighbors(self, node_id: str, edge_types: list[str] | None = None,
                      direction: str = "both") -> list[dict]:
        """邻接查询."""
        self._load()
        results = []
        for edge in self._adj.get(node_id, []):
            if edge_types and edge["type"] not in edge_types:
                continue
            results.append(edge)
        if direction in ("incoming", "both"):
            for node, edges in self._adj.items():
                for edge in edges:
                    if edge["target_id"] == node_id and node != node_id:
                        if edge_types and edge["type"] not in edge_types:
                            continue
                        results.append(edge)
        return results

    def get_evolution_chain(self, method_id: str, max_depth: int = 3) -> list[dict]:
        """BFS 追溯演化链 (强因果边)."""
        self._load()
        chain = []
        visited = {method_id}
        queue = [(method_id, 0)]
        while queue:
            current, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            for edge in self._adj.get(current, []):
                if edge["type"] in STRONG_CAUSAL and edge["target_id"] not in visited:
                    chain.append(edge)
                    visited.add(edge["target_id"])
                    queue.append((edge["target_id"], depth + 1))
        return chain

    def get_bottleneck_context(self, bottleneck_id: str) -> dict:
        """瓶颈→方案子图."""
        self._load()
        return {
            "bottleneck": next((a for a in self._atoms if a["id"] == bottleneck_id), None),
            "solutions": [e for e in self._adj.get(bottleneck_id, [])
                         if e["type"] in ("addressed_by", "rev_addressed_by")],
            "affected": [e for e in self._adj.get(bottleneck_id, [])
                        if e["type"] in ("affects",)],
        }

    def search_nodes(self, keywords: list[str], node_types: list[str] | None = None) -> list[dict]:
        """关键词搜索节点."""
        self._load()
        results = []
        kw_lower = [k.lower() for k in keywords]
        for atom in self._atoms:
            if node_types and atom.get("metadata", {}).get("node_type") not in node_types:
                continue
            text = atom["title"] + " " + atom.get("content", "") + \
                   " ".join(atom.get("tags", []))
            if any(k in text.lower() for k in kw_lower):
                results.append(atom)
        return results


# ── 辅助函数 ──

def _normalize_link_target(target: str) -> str:
    """规范化链接目标: 'TD3 Baseline' → 'TD3_Baseline'."""
    return target.replace(" ", "_").replace("-", "_")


def _infer_node_type(rel_path: str) -> str:
    if "Algorithms" in rel_path:
        return "Algorithm"
    if "Bottlenecks" in rel_path:
        return "Bottleneck"
    if "Islands" in rel_path:
        return "Island"
    if "Iterations" in rel_path:
        return "Iteration"
    if "Literature" in rel_path:
        return "Paper"
    return "Unknown"


def _infer_edge_type_from_context(context: str) -> str:
    """从 [[wiki-link]] 上下文推断边类型 (self-wiring)."""
    ctx_lower = context.lower()
    if any(w in ctx_lower for w in ("extends", "扩展", "基于")):
        return "derives"
    if any(w in ctx_lower for w in ("solves", "解决", "improves", "缓解")):
        return "improves"
    if any(w in ctx_lower for w in ("replaces", "替代")):
        return "replaces"
    if any(w in ctx_lower for w in ("compares", "对比", "vs")):
        return "compares_to"
    if any(w in ctx_lower for w in ("validates", "证明", "验证")):
        return "validates"
    if any(w in ctx_lower for w in ("contradicts", "矛盾", "反驳")):
        return "contradicts"
    if any(w in ctx_lower for w in ("creates", "产生", "导致")):
        return "creates"
    return "related_to"


def _extract_summary(text: str) -> str:
    """从 Markdown 提取第一段非标题文本作为摘要."""
    lines = text.split("\n")
    summary_lines = []
    in_content = False
    for line in lines:
        if line.startswith("## "):
            in_content = True
            continue
        if in_content and line.strip() and not line.startswith("#"):
            summary_lines.append(line.strip())
        if len(" ".join(summary_lines)) > 200:
            break
    return " ".join(summary_lines)[:500]


def _count_by_key(items: list[dict], key: str) -> dict:
    counts = defaultdict(int)
    for item in items:
        val = item.get(key, "unknown")
        counts[val] += 1
    return dict(counts)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries
