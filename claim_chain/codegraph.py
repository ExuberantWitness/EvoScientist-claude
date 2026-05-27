"""CodeGraph integration for EvoScientist.

Reads CodeGraph's SQLite DB directly for programmatic extraction.
MCP mode (codegraph serve --mcp) is used by agents in SKILL.md.

DB schema:
  nodes: id, kind, name, qualified_name, file_path, language, start_line, end_line
  edges: id, source, target, kind, metadata
  files: path, content_hash, language, size, node_count
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CodeGraph indexing (CLI)
# ---------------------------------------------------------------------------

async def index_code_directory(code_dir: Path) -> bool:
    """Initialize CodeGraph and index a directory."""
    if not code_dir.exists():
        logger.warning(f"CodeGraph: directory not found: {code_dir}")
        return False
    try:
        import asyncio
        proc = await asyncio.create_subprocess_exec(
            "npx", "@colbymchenry/codegraph", "init", "-i",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(code_dir),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        ok = proc.returncode == 0
        if ok:
            logger.info(f"CodeGraph indexed: {code_dir}")
        else:
            logger.warning(f"CodeGraph index failed: {stderr.decode()[:200]}")
        return ok
    except Exception as e:
        logger.warning(f"CodeGraph index error: {e}")
        return False


# ---------------------------------------------------------------------------
# DB extraction
# ---------------------------------------------------------------------------

def _db_path(code_dir: Path) -> Path:
    return code_dir / ".codegraph" / "codegraph.db"


def extract_structure(code_dir: Path) -> dict[str, dict]:
    """Extract code structure from CodeGraph SQLite DB.

    Returns: {filename: {nodes: [...], edges: [...]}}
    """
    db = _db_path(code_dir)
    if not db.exists():
        logger.warning(f"CodeGraph DB not found: {db}")
        return {}

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        # Get all files
        files = conn.execute("SELECT path, language, node_count FROM files").fetchall()

        result = {}
        for frow in files:
            fpath = frow["path"]
            # Get nodes for this file (exclude 'file' and 'import' kinds)
            nodes = conn.execute(
                "SELECT id, kind, name, qualified_name, start_line, end_line "
                "FROM nodes WHERE file_path = ? AND kind NOT IN ('file', 'import') "
                "ORDER BY start_line",
                (fpath,),
            ).fetchall()

            # Get edges where source or target is in this file
            node_ids = {n["id"] for n in nodes}
            node_ids.add(f"file:{fpath}")  # include file-level edges

            # Build placeholders for IN clause (SQLite doesn't support list params well)
            edges = []
            if node_ids:
                # Get all edges and filter in Python
                all_edges = conn.execute(
                    "SELECT source, target, kind FROM edges"
                ).fetchall()
                for e in all_edges:
                    if e["source"] in node_ids or e["target"] in node_ids:
                        edges.append(dict(e))

            result[fpath] = {
                "nodes": [dict(n) for n in nodes],
                "edges": edges,
            }

        return result
    finally:
        conn.close()


def get_all_nodes(code_dir: Path, kinds: list[str] | None = None) -> list[dict]:
    """Get all nodes of specified kinds from CodeGraph DB."""
    db = _db_path(code_dir)
    if not db.exists():
        return []

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        if kinds:
            placeholders = ",".join("?" * len(kinds))
            rows = conn.execute(
                f"SELECT * FROM nodes WHERE kind IN ({placeholders}) ORDER BY file_path, start_line",
                kinds,
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM nodes WHERE kind NOT IN ('file', 'import') ORDER BY file_path, start_line"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_edges_for_node(code_dir: Path, node_id: str) -> list[dict]:
    """Get all edges connected to a node."""
    db = _db_path(code_dir)
    if not db.exists():
        return []

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM edges WHERE source = ? OR target = ?", (node_id, node_id)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CC atom conversion
# ---------------------------------------------------------------------------

def structure_to_cc_atoms(
    code_dir: Path,
    algo_names: list[str] | None = None,
    cc=None,
) -> dict[str, list[dict]]:
    """Convert CodeGraph structure to CC atoms, grouped by algorithm.

    Args:
        code_dir: directory with .codegraph/codegraph.db
        algo_names: which files to process (e.g. ['cdr_critic', 'sgcc'])
        cc: ClaimChain instance (with add_atom, add_relation)

    Returns:
        {algo_name: [created_atom_dicts]}
    """
    structure = extract_structure(code_dir)
    if not structure:
        return {}

    if algo_names is None:
        # Auto-detect: all .py files except config/utils/train
        skip = {"config", "utils", "train", "smoke_test"}
        algo_names = []
        for fname in structure:
            stem = Path(fname).stem
            if not any(s in stem for s in skip):
                algo_names.append(stem)

    result = {}
    for fname, data in structure.items():
        stem = Path(fname).stem
        if algo_names and stem not in algo_names:
            continue

        atoms = []
        # Pre-extract all source snippets for this directory
        all_snippets = extract_all_snippets(code_dir, {fname: data})

        # Create component atoms (always, even without cc)
        for node in data.get("nodes", []):
            name = node.get("name", "?")
            start_line = node.get("start_line", 0)
            end_line = node.get("end_line", start_line + 5)

            # Extract source snippet
            snippet = extract_source_snippet(
                code_dir, fname, start_line, end_line
            )
            mechs = tag_mechanisms(snippet)

            atom_dict = {
                "type": "component",
                "title": f"{stem}.{name}",
                "content": json.dumps({
                    "kind": node.get("kind", ""),
                    "file": fname,
                    "line": start_line,
                    "end_line": end_line,
                    "qualified_name": node.get("qualified_name", ""),
                    "signature": node.get("signature", ""),
                    "source_snippet": snippet[:1500],
                    "mechanisms": mechs,
                }),
                "tags": ["codegraph", stem, node.get("kind", "function")]
                + [f"mech:{m}" for m in mechs],
            }
            atoms.append(atom_dict)

            # If CC instance provided, also add to CC
            if cc is not None:
                atom = cc.add_atom(
                    type=atom_dict["type"],
                    title=atom_dict["title"],
                    content=atom_dict["content"],
                    tags=atom_dict["tags"],
                )
                atoms[-1] = atom  # Replace dict with actual atom object

            # Create relation: algo → implements → each component
        if cc is not None:
            for atom in atoms:
                try:
                    cc.add_relation(stem, atom["id"], "implements")
                except Exception:
                    pass

            # Create dependency edges as CC relations
        if cc is not None:
            for edge in data.get("edges", []):
                try:
                    cc.add_relation(
                        edge.get("source", "?"),
                        edge.get("target", "?"),
                        edge.get("kind", edge.get("type", "depends_on")),
                    )
                except Exception:
                    pass

        result[stem] = atoms

    return result


def structure_summary(code_dir: Path) -> str:
    """Generate a text summary for RND KB embedding."""
    structure = extract_structure(code_dir)
    if not structure:
        return ""

    parts = []
    for fname, data in structure.items():
        nodes = data.get("nodes", [])
        classes = [n for n in nodes if n.get("kind") == "class"]
        funcs = [n for n in nodes if n.get("kind") in ("function", "method")]
        edges = data.get("edges", [])

        algo = Path(fname).stem
        summary = f"{algo}: "
        if classes:
            summary += f"{len(classes)} classes ({', '.join(c.get('name','?') for c in classes[:4])})"
        if funcs:
            summary += f", {len(funcs)} functions ({', '.join(f.get('name','?') for f in funcs[:4])})"
        if edges:
            summary += f", {len(edges)} deps"
        summary += "."
        parts.append(summary)

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Diff / conflict detection
# ---------------------------------------------------------------------------

def diff_structures(before_dir: Path, after_dir: Path) -> dict:
    """Compare CodeGraph structures between two code directories.

    Returns:
        {algo_name: {added_nodes: [...], removed_nodes: [...],
                      modified_nodes: [...], added_edges: [...], removed_edges: [...]}}
    """
    before = extract_structure(before_dir)
    after = extract_structure(after_dir)

    all_files = set(before.keys()) | set(after.keys())
    diffs = {}

    for fname in all_files:
        b_nodes = {n.get("name", n.get("id")): n for n in before.get(fname, {}).get("nodes", [])}
        a_nodes = {n.get("name", n.get("id")): n for n in after.get(fname, {}).get("nodes", [])}
        b_edges = {(e.get("source"), e.get("target"), e.get("kind")): e
                   for e in before.get(fname, {}).get("edges", [])}
        a_edges = {(e.get("source"), e.get("target"), e.get("kind")): e
                   for e in after.get(fname, {}).get("edges", [])}

        b_names = set(b_nodes.keys())
        a_names = set(a_nodes.keys())

        diffs[Path(fname).stem] = {
            "added_nodes": [a_nodes[n] for n in (a_names - b_names)],
            "removed_nodes": [b_nodes[n] for n in (b_names - a_names)],
            "modified_nodes": [
                {"name": n, "before": b_nodes[n], "after": a_nodes[n]}
                for n in (b_names & a_names)
                if b_nodes[n] != a_nodes[n]
            ],
            "added_edges": [a_edges[k] for k in (set(a_edges) - set(b_edges))],
            "removed_edges": [b_edges[k] for k in (set(b_edges) - set(a_edges))],
        }

    return diffs


def detect_conflicts(diff: dict) -> list[dict]:
    """Detect potential conflicts in a structure diff.

    Returns list of conflict descriptions:
      [{type: 'overwrite'|'duplicate'|'diverge', description: str, files: [...]}]
    """
    conflicts = []
    for algo, d in diff.items():
        # Check if nodes were both added and removed (may indicate overwrite)
        if d["added_nodes"] and d["removed_nodes"]:
            added_names = {n.get("name") for n in d["added_nodes"]}
            removed_names = {n.get("name") for n in d["removed_nodes"]}
            overlap = added_names & removed_names
            if overlap:
                conflicts.append({
                    "type": "overwrite",
                    "algo": algo,
                    "description": f"Functions both added and removed: {overlap}",
                    "overlapping_names": list(overlap),
                })

        # Check if same function modified in incompatible ways
        if len(d["modified_nodes"]) > 3:
            conflicts.append({
                "type": "large_change",
                "algo": algo,
                "description": f"Large change: {len(d['modified_nodes'])} modified nodes",
                "modified_count": len(d["modified_nodes"]),
            })

    return conflicts


# ---------------------------------------------------------------------------
# Source snippet extraction + mechanism tagging
# ---------------------------------------------------------------------------

# Key RL mechanisms to detect in actor-critic code
MECHANISM_PATTERNS: dict[str, list[str]] = {
    "gradient_clip": ["clip_grad_norm", "grad_clip", "clip_grad"],
    "twin_q": ["qf1", "qf2", "twin", "double_q"],
    "entropy_reg": ["entropy", "alpha", "temperature", "log_alpha"],
    "delayed_update": ["target_update", "tau", "polyak", "soft_update"],
    "deterministic_policy": ["deterministic", "ddpg"],
    "stochastic_policy": ["gaussian", "normal", "log_prob", "rsample"],
    "gae": ["gae", "generalized_advantage", "lambda"],
    "clip_ratio": ["clip_ratio", "clip_param", "clip_range", "clip_eps"],
    "replay_buffer": ["replay_buffer", "ReplayBuffer", "experience_replay"],
    "target_noise": ["target_noise", "policy_noise", "smoothing_noise"],
    "bc_pretrain": ["bc_pretrain", "behavior_clone", "imitation"],
}


def extract_source_snippet(code_dir: Path, file_path: str,
                          start_line: int, end_line: int,
                          max_chars: int = 5000) -> str:
    """Extract actual source code for a component from file."""
    fpath = code_dir / file_path
    if not fpath.exists():
        return ""
    try:
        lines = fpath.read_text(encoding="utf-8").split("\n")
        # Expand range to capture full function/class body
        s = max(0, start_line - 1)
        e = min(len(lines), max(end_line, start_line + 50))
        snippet = "\n".join(lines[s:e])
        return snippet[:max_chars]
    except Exception:
        return ""


def tag_mechanisms(code_text: str) -> list[str]:
    """Detect key RL mechanisms in source code."""
    text_lower = code_text.lower()
    found = []
    for mech, patterns in MECHANISM_PATTERNS.items():
        for pat in patterns:
            if pat.lower() in text_lower:
                found.append(mech)
                break
    return found


def compute_mechanism_diff(algo_a: str, mechs_a: list[str],
                           algo_b: str, mechs_b: list[str]) -> dict:
    """Compute key mechanism differences between two algorithms."""
    set_a = set(mechs_a)
    set_b = set(mechs_b)
    return {
        f"{algo_a}_only": sorted(set_a - set_b),
        f"{algo_b}_only": sorted(set_b - set_a),
        "shared": sorted(set_a & set_b),
    }


def extract_all_snippets(code_dir: Path, structure: dict) -> dict[str, dict]:
    """Extract source snippets + mechanism tags for all components.

    Returns: {component_name: {snippet, mechanisms, file, lines}}
    """
    result = {}
    for fname, data in structure.items():
        fpath = code_dir / fname
        if not fpath.exists():
            continue
        for node in data.get("nodes", []):
            name = node.get("name", node.get("id", "?"))
            start = node.get("start_line", 0)
            end = node.get("end_line", start + 5)
            snippet = extract_source_snippet(code_dir, fname, start, end)
            mechs = tag_mechanisms(snippet)
            result[name] = {
                "snippet": snippet,
                "mechanisms": mechs,
                "file": fname,
                "lines": f"{start}-{end}",
            }
    return result


async def llm_judge_component_diff(
    comp_a_name: str, comp_a_code: str,
    comp_b_name: str, comp_b_code: str,
    algo_a_mechs: list[str], algo_b_mechs: list[str],
) -> dict:
    """Use MiMo LLM to judge structural/mechanism differences between two components.

    Returns: {similarity: 1-10, is_mergeable: bool, key_diffs: [str],
              shared_patterns: [str], mechanism_analysis: str}
    """
    import os
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key="sk-cr1e299iw09nn2bt9a2vvu39sxwp18bfzf4vgzn25r1mldns",
        base_url="https://api.xiaomimimo.com/v1",
    )

    prompt = f"""You are an expert code analyst. Compare two code components and identify their structural and algorithmic differences.

## Component A: {comp_a_name}
Algorithm mechanisms: {algo_a_mechs}
```python
{comp_a_code[:1000]}
```

## Component B: {comp_b_name}
Algorithm mechanisms: {algo_b_mechs}
```python
{comp_b_code[:1000]}
```

## Instructions
1. Rate their STRUCTURAL similarity (1-10, 1=completely different, 10=essentially identical)
2. Determine if they can share a common base implementation (is_mergeable=true if similarity >= 6)
3. List KEY DIFFERENCES (what makes them distinct? focus on algorithm logic, not variable names)
4. List SHARED PATTERNS (what structural patterns do they share?)
5. Provide a brief mechanism-level analysis

Respond with ONLY a JSON object:
{{"similarity": <1-10>, "is_mergeable": <bool>, "key_diffs": ["diff1", "diff2"], "shared_patterns": ["pattern1"], "mechanism_analysis": "brief analysis"}}"""

    try:
        resp = await client.chat.completions.create(
            model="mimo-v2.5-pro",
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=2048,
            temperature=0.3,
            timeout=60,
        )
        text = resp.choices[0].message.content.strip()
        # Parse JSON
        import re
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                return json.loads(m.group(0))
    except Exception as e:
        logger.warning(f"MiMo judge failed: {e}")

    return {"similarity": 5, "is_mergeable": False, "key_diffs": ["LLM unavailable"],
            "shared_patterns": [], "mechanism_analysis": "Fallback"}


def algo_mechanism_summary(code_dir: Path, algo: str) -> dict:
    """Get aggregated mechanism summary for an algorithm."""
    struct = extract_structure(code_dir)
    if not struct:
        return {"mechanisms": [], "key_diffs": []}

    all_mechs = set()
    for fname, data in struct.items():
        if algo not in fname:
            continue
        for node in data.get("nodes", []):
            start = node.get("start_line", 0)
            end = node.get("end_line", start + 5)
            snippet = extract_source_snippet(code_dir, fname, start, end)
            all_mechs.update(tag_mechanisms(snippet))

    return {
        "algo": algo,
        "mechanisms": sorted(all_mechs),
    }
