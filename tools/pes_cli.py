#!/usr/bin/env python3
"""PES CLI — Claim Chain + Cell Grid 统一查询接口。

可预测 JSON schema，同一接口人和 agent 共用。可审计、可复现。

用法:
    # 人类使用
    python tools/pes_cli.py atoms --workspace /path/to/ws --type method --limit 20
    python tools/pes_cli.py cells --workspace /path/to/ws --status empty
    python tools/pes_cli.py summary --workspace /path/to/ws

    # Agent 使用 (相同接口)
    import subprocess, json
    result = json.loads(subprocess.check_output([
        "python", "tools/pes_cli.py", "atoms", "--type", "method", "--limit", "20"
    ]))

输出 schema (所有命令统一):
    { "status": "ok"|"error",
      "data": [...],
      "meta": {"count": N, "query": {...}, "timestamp": "<ISO8601>", "workspace": "<path>"} }
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


def _ok(data: list | dict, meta: dict) -> dict:
    return {"status": "ok", "data": data, "meta": meta}


def _err(message: str, meta: dict | None = None) -> dict:
    return {"status": "error", "data": [], "meta": {**(meta or {}), "error": message}}


def _meta(workspace: str, query: dict, count: int) -> dict:
    return {
        "count": count,
        "query": query,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "workspace": str(Path(workspace).resolve()),
    }


def cmd_atoms(workspace: str, atom_type: str | None = None,
              tags: list[str] | None = None, limit: int = 100) -> dict:
    """查询 Claim Chain atoms。"""
    from claim_chain import ClaimChain
    cc = ClaimChain(workspace)
    query = {}
    if atom_type:
        query["type"] = atom_type
    if tags:
        query["tags"] = tags
    query["limit"] = limit
    try:
        atoms = cc.get_atoms(type=atom_type, tags=tags, limit=limit)
        return _ok(atoms, _meta(workspace, query, len(atoms)))
    except Exception as e:
        return _err(str(e), _meta(workspace, query, 0))


def cmd_relations(workspace: str, rel_type: str | None = None,
                  limit: int = 100) -> dict:
    """查询 Claim Chain relations。"""
    from claim_chain import ClaimChain
    cc = ClaimChain(workspace)
    query = {"limit": limit}
    if rel_type:
        query["type"] = rel_type
    try:
        rels = cc.get_relations(type=rel_type, limit=limit)
        return _ok(rels, _meta(workspace, query, len(rels)))
    except Exception as e:
        return _err(str(e), _meta(workspace, query, 0))


def cmd_cells(workspace: str, status_filter: str | None = None) -> dict:
    """查询 Evolve Grid cells。status_filter: empty|filled|all"""
    from cell_grid import CellGrid
    grid = CellGrid(workspace)
    query = {"status_filter": status_filter or "all"}
    try:
        cells = grid.get_heatmap_data()
        all_cells = cells.get("cells", {})
        if status_filter == "empty":
            filtered = {k: v for k, v in all_cells.items() if not v.get("elite_id")}
        elif status_filter == "filled":
            filtered = {k: v for k, v in all_cells.items() if v.get("elite_id")}
        else:
            filtered = all_cells

        cell_list = [{"key": k, **v} for k, v in filtered.items()]
        return _ok(cell_list, _meta(workspace, query, len(cell_list)))
    except Exception as e:
        return _err(str(e), _meta(workspace, query, 0))


def cmd_variants(workspace: str, cell_key: str | None = None,
                 island_id: str | None = None) -> dict:
    """查询 variants。可按 cell_key 或 island_id 过滤。"""
    from cell_grid import CellGrid
    grid = CellGrid(workspace)
    query = {}
    if cell_key:
        query["cell_key"] = cell_key
    if island_id:
        query["island_id"] = island_id
    try:
        state = grid._read_state()
        history = state.get("variant_history", [])
        if cell_key:
            history = [v for v in history if v.get("cell") == cell_key]
        if island_id:
            history = [v for v in history if v.get("island_id") == island_id]
        return _ok(history, _meta(workspace, query, len(history)))
    except Exception as e:
        return _err(str(e), _meta(workspace, query, 0))


def cmd_islands(workspace: str) -> dict:
    """查询所有 islands 元信息。"""
    from island_manager import IslandManager
    mgr = IslandManager(workspace)
    query = {}
    try:
        islands = []
        islands_dir = Path(workspace) / "evolve_archive" / "islands"
        if islands_dir.exists():
            for island_dir in sorted(islands_dir.iterdir()):
                if island_dir.is_dir():
                    meta_path = island_dir / "island_meta.json"
                    if meta_path.exists():
                        islands.append(json.loads(meta_path.read_text()))
        return _ok(islands, _meta(workspace, query, len(islands)))
    except Exception as e:
        return _err(str(e), _meta(workspace, query, 0))


def cmd_milestones(workspace: str) -> dict:
    """查询 Grid milestones。"""
    from cell_grid import CellGrid
    grid = CellGrid(workspace)
    query = {}
    try:
        milestones = grid.detect_milestones()
        return _ok(milestones, _meta(workspace, query, len(milestones)))
    except Exception as e:
        return _err(str(e), _meta(workspace, query, 0))


def cmd_anomalies(workspace: str) -> dict:
    """查询异常 cells (score gap >30%)。"""
    from cell_grid import CellGrid
    grid = CellGrid(workspace)
    query = {}
    try:
        state = grid._read_state()
        cells = state.get("cells", {})
        anomalies = []
        for cell_key, cell_data in cells.items():
            for anomaly in cell_data.get("anomalies", []):
                anomalies.append({"cell": cell_key, **anomaly})
        return _ok(anomalies, _meta(workspace, query, len(anomalies)))
    except Exception as e:
        return _err(str(e), _meta(workspace, query, 0))


def cmd_summary(workspace: str) -> dict:
    """综合摘要: CC + Grid + Islands + Anomalies。"""
    from claim_chain import ClaimChain
    from cell_grid import CellGrid
    cc = ClaimChain(workspace)
    grid = CellGrid(workspace)
    query = {}
    try:
        cc_summary = cc.get_graph_summary()
        heatmap = grid.get_heatmap_data()
        cells = heatmap.get("cells", {})
        filled = sum(1 for c in cells.values() if c.get("elite_id"))
        empty = len(cells) - filled
        anomaly_count = sum(len(c.get("anomalies", [])) for c in cells.values())

        islands_dir = Path(workspace) / "evolve_archive" / "islands"
        island_count = 0
        island_families = []
        if islands_dir.exists():
            for d in islands_dir.iterdir():
                if d.is_dir():
                    meta_path = d / "island_meta.json"
                    if meta_path.exists():
                        island_count += 1
                        meta = json.loads(meta_path.read_text())
                        island_families.append(meta.get("method_family", "unknown"))

        data = {
            "claim_chain": cc_summary,
            "grid": {
                "dim_names": heatmap.get("dim_names", []),
                "total_cells": len(cells),
                "filled_cells": filled,
                "empty_cells": empty,
                "coverage": heatmap.get("coverage", "0%"),
                "best_score": heatmap.get("best_score"),
                "milestone_count": len(grid.detect_milestones()),
                "anomaly_count": anomaly_count,
            },
            "islands": {
                "count": island_count,
                "families": sorted(set(island_families)),
                "all_wildcard": all(
                    "centroid_cell" in (json.loads((islands_dir / d / "island_meta.json").read_text())
                     if (islands_dir / d / "island_meta.json").exists() else {})
                    and (json.loads((islands_dir / d / "island_meta.json").read_text())
                         .get("centroid_cell", "*") == "*+*+*+*")
                    for d in islands_dir.iterdir() if d.is_dir()
                ) if island_count > 0 else False,
            },
        }
        return _ok(data, _meta(workspace, query, 1))
    except Exception as e:
        return _err(str(e), _meta(workspace, query, 0))


def cmd_export(workspace: str, fmt: str = "json") -> dict:
    """导出所有数据 (atoms + relations + cells + islands)。"""
    from claim_chain import ClaimChain
    from cell_grid import CellGrid
    cc = ClaimChain(workspace)
    grid = CellGrid(workspace)
    query = {"format": fmt}
    try:
        atoms = cc.get_atoms(limit=1000)
        rels = cc.get_relations(limit=1000)
        heatmap = grid.get_heatmap_data()

        islands_data = []
        islands_dir = Path(workspace) / "evolve_archive" / "islands"
        if islands_dir.exists():
            for d in sorted(islands_dir.iterdir()):
                if d.is_dir():
                    meta_path = d / "island_meta.json"
                    if meta_path.exists():
                        islands_data.append(json.loads(meta_path.read_text()))

        data = {
            "atoms": atoms,
            "relations": rels,
            "grid_cells": heatmap.get("cells", {}),
            "dim_names": heatmap.get("dim_names", []),
            "islands": islands_data,
        }
        return _ok(data, _meta(workspace, query, 1))
    except Exception as e:
        return _err(str(e), _meta(workspace, query, 0))


# ── CLI entry point ──

SUBCOMMANDS = {
    "atoms":      (cmd_atoms,      [("--type", str, None), ("--tags", str, None), ("--limit", int, 100)]),
    "relations":  (cmd_relations,  [("--type", str, None), ("--limit", int, 100)]),
    "cells":      (cmd_cells,      [("--status", str, None)]),
    "variants":   (cmd_variants,   [("--cell", str, None), ("--island", str, None)]),
    "islands":    (cmd_islands,    []),
    "milestones": (cmd_milestones, []),
    "anomalies":  (cmd_anomalies,  []),
    "summary":    (cmd_summary,    []),
    "export":     (cmd_export,     [("--format", str, "json")]),
}


def main():
    parser = argparse.ArgumentParser(
        description="PES CLI — Claim Chain + Cell Grid 统一查询接口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="所有命令输出统一 JSON schema: {status, data[], meta}",
    )
    parser.add_argument("--workspace", "-w", type=str, required=True,
                        help="Workspace directory path")

    sub = parser.add_subparsers(dest="command", required=True)
    for cmd_name, (_, extra_args) in SUBCOMMANDS.items():
        p = sub.add_parser(cmd_name)
        for arg_name, arg_type, default in extra_args:
            arg_flag = arg_name.replace("_", "-")
            p.add_argument(arg_flag, type=arg_type, default=default)

    args = parser.parse_args()
    cmd_name = args.command
    handler, extra_args = SUBCOMMANDS[cmd_name]

    # Build kwargs
    kwargs = {"workspace": args.workspace}
    for arg_name, arg_type, default in extra_args:
        attr = arg_name.lstrip("-").replace("-", "_")
        val = getattr(args, attr, default)
        if val is not None:
            kwargs[attr] = val

    # Fix type→atom_type for atoms command
    if cmd_name == "atoms" and "type" in kwargs:
        kwargs["atom_type"] = kwargs.pop("type")
    if cmd_name == "relations" and "type" in kwargs:
        kwargs["rel_type"] = kwargs.pop("type")
    if cmd_name == "cells" and "status" in kwargs:
        kwargs["status_filter"] = kwargs.pop("status")
    if cmd_name == "variants":
        if "cell" in kwargs:
            kwargs["cell_key"] = kwargs.pop("cell")
        if "island" in kwargs:
            kwargs["island_id"] = kwargs.pop("island")
    if cmd_name == "export" and "format" in kwargs:
        kwargs["fmt"] = kwargs.pop("format")

    result = handler(**kwargs)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
