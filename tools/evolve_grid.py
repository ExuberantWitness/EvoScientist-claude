"""evolve_grid.py: Pyribs-based MAP-Elites grid for quality-diversity evolution.

Provides ask-tell interface for managing behavior-space archives:
  init          — Initialize grid with behavior dimensions
  record-result — Record a variant's score and behavior descriptor
  sample        — Sample a parent variant (exploit/explore)
  status        — Show archive coverage and best scores
  heatmap       — ASCII heatmap of the grid
  export-best   — Export best variant per cell

Usage:
  python evolve_grid.py init --config evolve_config.json
  python evolve_grid.py record-result --id v001 --score 18 --dims '{"terrain":"flat","method":"ppo"}'
  python evolve_grid.py sample --strategy exploit
  python evolve_grid.py status
  python evolve_grid.py heatmap
  python evolve_grid.py export-best
"""

import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np


def _info(msg: str):
    """Print human-readable info to stderr."""
    print(msg, file=sys.stderr)

import numpy as np


class EvolveGrid:
    """Simple grid archive backed by JSON files. No Pyribs dependency at init time."""

    def __init__(self, archive_dir: str | Path = "evolve_archive"):
        self.dir = Path(archive_dir)
        self.config_path = self.dir / "evolve_config.json"
        self.state_path = self.dir / "evolve_state.json"

    def init(self, config: dict) -> None:
        """Initialize archive directory and grid structure."""
        self.dir.mkdir(parents=True, exist_ok=True)

        # Build cell map from behavior dimensions
        dims = config.get("behavior_dims", [])
        if not dims:
            _info("Error: behavior_dims required in config")
            sys.exit(1)

        # Create all cell keys as cartesian product
        dim_values = [d["values"] for d in dims]
        dim_names = [d["name"] for d in dims]

        cells = {}
        for combo in _cartesian_product(dim_values):
            key = "+".join(combo)
            cells[key] = {
                "dim_values": dict(zip(dim_names, combo)),
                "elite_id": None,
                "elite_score": None,
            }

        config["dim_names"] = dim_names
        self.config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False))

        state = {
            "cells": cells,
            "variant_history": [],
            "next_variant": 1,
        }
        self.state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))

        total = len(cells)
        _info(f"Initialized {total} cells ({len(dim_names)}D: {' × '.join(str(len(v)) for v in dim_values)})")

    def record_result(self, variant_id: str, score: float, dims: dict) -> dict:
        """Record a result and update elite if improved."""
        if not self.state_path.exists():
            print("Error: archive not initialized. Run 'init' first.", file=sys.stderr)
            sys.exit(1)

        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        dim_names = config["dim_names"]

        # Find cell key from dims
        key_parts = []
        for name in dim_names:
            val = dims.get(name)
            if val is None:
                _info(f"Error: missing dimension '{name}' in dims")
                sys.exit(1)
            key_parts.append(str(val))
        cell_key = "+".join(key_parts)

        if cell_key not in state["cells"]:
            _info(f"Error: cell '{cell_key}' not found in grid")
            sys.exit(1)

        cell = state["cells"][cell_key]
        updated = False

        if cell["elite_score"] is None or score > cell["elite_score"]:
            cell["elite_id"] = variant_id
            cell["elite_score"] = score
            updated = True

        # Record in history
        state["variant_history"].append({
            "id": variant_id,
            "score": score,
            "cell": cell_key,
            "dims": dims,
        })

        self.state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))

        action = "UPDATED elite" if updated else "recorded (no elite change)"
        _info(f"{action}: {variant_id} → {cell_key} (score={score}, best={cell['elite_score']})")

        return {"cell": cell_key, "updated": updated, "best_score": cell["elite_score"]}

    def sample(self, strategy: str = "exploit") -> dict | None:
        """Sample a parent variant from the archive.

        Args:
            strategy: "exploit" (from high-score cells) or "explore" (from empty/low-score cells)
        """
        if not self.state_path.exists():
            _info("Error: archive not initialized.")
            sys.exit(1)

        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        cells = state["cells"]

        filled = {k: v for k, v in cells.items() if v["elite_id"] is not None}
        empty = {k: v for k, v in cells.items() if v["elite_id"] is None}

        if strategy == "exploit":
            if not filled:
                _info("No filled cells to exploit from. Try 'explore'.")
                return None
            # Weighted by score
            keys = list(filled.keys())
            scores = np.array([filled[k]["elite_score"] for k in keys])
            # Shift to positive for weighting
            scores = scores - scores.min() + 1e-6
            probs = scores / scores.sum()
            idx = np.random.choice(len(keys), p=probs)
            chosen_key = keys[idx]
            cell = filled[chosen_key]

        elif strategy == "explore":
            if empty:
                chosen_key = random.choice(list(empty.keys()))
                cell = empty[chosen_key]
                # For empty cells, suggest a random neighbor from filled cells as parent
                if filled:
                    parent_key = random.choice(list(filled.keys()))
                    parent_cell = filled[parent_key]
                    _info(f"Explore target: {chosen_key} (empty)")
                    _info(f"Suggested parent: {parent_cell['elite_id']} from {parent_key} (score={parent_cell['elite_score']})")
                    return {"cell": chosen_key, "parent_id": parent_cell["elite_id"],
                            "parent_cell": parent_key, "parent_score": parent_cell["elite_score"],
                            "target": "empty_cell"}
                else:
                    _info(f"Explore target: {chosen_key} (empty, no parents yet)")
                    return {"cell": chosen_key, "parent_id": None, "target": "empty_cell"}
            else:
                # All cells filled, pick lowest-score cell for improvement
                keys = list(filled.keys())
                scores = [filled[k]["elite_score"] for k in keys]
                idx = int(np.argmin(scores))
                chosen_key = keys[idx]
                cell = filled[chosen_key]
                _info(f"All cells filled. Weakest: {chosen_key} (score={cell['elite_score']})")
        else:
            _info(f"Unknown strategy: {strategy}. Use 'exploit' or 'explore'.")
            return None

        _info(f"Sampled: {cell['elite_id']} from {chosen_key} (score={cell['elite_score']})")
        return {"cell": chosen_key, "elite_id": cell["elite_id"],
                "elite_score": cell["elite_score"]}

    def status(self) -> None:
        """Print archive status."""
        if not self.state_path.exists():
            _info("Archive not initialized.")
            return

        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        cells = state["cells"]
        filled = {k: v for k, v in cells.items() if v["elite_id"] is not None}
        total = len(cells)
        n_filled = len(filled)

        _info(f"Archive: {n_filled}/{total} cells filled ({100*n_filled/max(total,1):.0f}%)")
        _info(f"Total variants: {len(state.get('variant_history', []))}")

        if filled:
            scores = [v["elite_score"] for v in filled.values()]
            _info(f"Score range: {min(scores):.1f} — {max(scores):.1f} (mean={np.mean(scores):.1f})")
            _info("\nTop cells:")
            for k, v in sorted(filled.items(), key=lambda x: x[1]["elite_score"], reverse=True)[:5]:
                _info(f"  {k}: {v['elite_id']} (score={v['elite_score']})")

    def heatmap(self) -> None:
        """Print ASCII heatmap of the grid."""
        if not self.state_path.exists():
            _info("Archive not initialized.")
            return

        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        cells = state["cells"]
        dim_names = config["dim_names"]

        if len(dim_names) < 2:
            # 1D: just list
            for k, v in cells.items():
                score = f"{v['elite_score']:.0f}" if v["elite_score"] is not None else "---"
                _info(f"  {k}: {score}")
            return

        # 2D heatmap (first 2 dims)
        dim_a_name = dim_names[0]
        dim_b_name = dim_names[1]
        dim_a_values = config["behavior_dims"][0]["values"]
        dim_b_values = config["behavior_dims"][1]["values"]

        # Header
        cell_w = max(max(len(str(v)) for v in dim_a_values), len(dim_a_name)) + 2
        header = " " * (len(dim_b_name) + 3)
        for bv in dim_b_values:
            header += str(bv).center(cell_w)
        _info(header)
        _info(" " * (len(dim_b_name) + 3) + "-" * (cell_w * len(dim_b_values)))

        for av in dim_a_values:
            row = f"{av:>12} |"
            for bv in dim_b_values:
                key = f"{av}+{bv}"
                if len(dim_names) > 2:
                    # For higher dims, aggregate
                    matching = {k: v for k, v in cells.items()
                                if k.startswith(f"{av}+{bv}")}
                    scores = [v["elite_score"] for v in matching.values()
                              if v["elite_score"] is not None]
                    if scores:
                        best = max(scores)
                        row += f"{best:.0f}".center(cell_w)
                    else:
                        row += "---".center(cell_w)
                else:
                    cell = cells.get(key, {})
                    score = cell.get("elite_score")
                    if score is not None:
                        row += f"{score:.0f}".center(cell_w)
                    else:
                        row += "---".center(cell_w)
            _info(row)

        filled = sum(1 for v in cells.values() if v.get("elite_id"))
        _info(f"\nCoverage: {filled}/{len(cells)} ({100*filled/len(cells):.0f}%)")

    def export_best(self) -> None:
        """Export best variant per cell."""
        if not self.state_path.exists():
            _info("Archive not initialized.")
            return

        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        cells = state["cells"]
        filled = {k: v for k, v in cells.items() if v["elite_id"] is not None}

        if not filled:
            _info("No results recorded yet.")
            return

        export_path = self.dir / "best_variants.json"
        export = []
        for k, v in sorted(filled.items(), key=lambda x: x[1]["elite_score"], reverse=True):
            export.append({
                "cell": k,
                "dims": v["dim_values"],
                "variant_id": v["elite_id"],
                "score": v["elite_score"],
            })

        export_path.write_text(json.dumps(export, indent=2, ensure_ascii=False))
        _info(f"Exported {len(export)} best variants to {export_path}")


def _cartesian_product(lists):
    """Generate cartesian product of lists as tuples."""
    if not lists:
        return [()]
    result = [[]]
    for lst in lists:
        result = [prefix + [item] for prefix in result for item in lst]
    return [tuple(r) for r in result]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evolve Grid: MAP-Elites archive manager")
    sub = parser.add_subparsers(dest="command")

    # init
    init_p = sub.add_parser("init", help="Initialize archive")
    init_p.add_argument("--config", required=True, help="JSON config file or inline JSON")

    # record-result
    rec = sub.add_parser("record-result", help="Record a variant result")
    rec.add_argument("--id", required=True, help="Variant ID (e.g., v001)")
    rec.add_argument("--score", type=float, required=True)
    rec.add_argument("--dims", required=True, help="JSON dict of behavior dimensions")

    # sample
    samp = sub.add_parser("sample", help="Sample a parent variant")
    samp.add_argument("--strategy", default="exploit", choices=["exploit", "explore"])

    # status / heatmap / export-best
    status_p = sub.add_parser("status", help="Show archive status")
    heatmap_p = sub.add_parser("heatmap", help="ASCII heatmap")
    export_p = sub.add_parser("export-best", help="Export best variants")

    # dir (all subcommands)
    for p in [init_p, rec, samp, status_p, heatmap_p, export_p]:
        p.add_argument("--dir", default="evolve_archive", help="Archive directory")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    grid = EvolveGrid(getattr(args, "dir", "evolve_archive"))

    if args.command == "init":
        config_path = Path(args.config)
        if config_path.exists():
            config = json.loads(config_path.read_text(encoding="utf-8"))
        else:
            config = json.loads(args.config)
        grid.init(config)

    elif args.command == "record-result":
        dims = json.loads(args.dims)
        grid.record_result(args.id, args.score, dims)

    elif args.command == "sample":
        result = grid.sample(args.strategy)
        if result:
            print(json.dumps(result, indent=2))

    elif args.command == "status":
        grid.status()

    elif args.command == "heatmap":
        grid.heatmap()

    elif args.command == "export-best":
        grid.export_best()
