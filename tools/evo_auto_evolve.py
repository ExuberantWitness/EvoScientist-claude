"""evo_auto_evolve.py: Autonomous PES evolution engine for Island GA + MAP-Elites.

Drives the full PES (Plan-Execute-Summary) loop without human intervention:
  Sample → Generate Config → Run Experiment → Parse Results → Update Grid + Claims → Loop

Usage:
  python evo_auto_evolve.py run --config evolve_archive/evolve_config.json --workspace /tmp/evo_cartpole
  python evo_auto_evolve.py run --max-rounds 10 --exploit-ratio 0.6
  python evo_auto_evolve.py dry-run --config evolve_archive/evolve_config.json  # Show plan without executing
  python evo_auto_evolve.py status  # Show current evolution state
"""

import argparse
import json
import random
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

# Project root for importing claim_chain and evolve_grid
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))


def _info(msg: str, flush: bool = True):
    print(f"[evo-auto] {msg}", file=sys.stderr, flush=flush)


def _success(msg: str, flush: bool = True):
    print(f"[evo-auto] \033[32m{msg}\033[0m", file=sys.stderr, flush=flush)


def _warn(msg: str, flush: bool = True):
    print(f"[evo-auto] \033[33m{msg}\033[0m", file=sys.stderr, flush=flush)


def _err(msg: str, flush: bool = True):
    print(f"[evo-auto] \033[31m{msg}\033[0m", file=sys.stderr, flush=flush)


def _load_jsonl(path: Path):
    if not path.exists():
        return []
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _append_jsonl(path: Path, entry: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ── Parameter Mapping ──

def map_cell_to_params(cell_key: str, config: dict) -> dict:
    """Map a cell key like 'low+medium' to hyperparameters via param_mapping."""
    param_map = config.get("param_mapping", {})
    dim_names = config.get("dim_names", [])
    cell_values = cell_key.split("+")

    params = {}
    for name, value in zip(dim_names, cell_values):
        dim_map = param_map.get(name, {})
        mapped = dim_map.get(value, {})
        params.update(mapped)
    return params


def mutate_params(base_params: dict, target_params: dict, mutate_rate: float = 0.3) -> dict:
    """Mutate base params toward target cell, with random perturbation.

    When exploiting: base_params is parent's params, target_params is the cell's standard params.
    We want to stay close to the parent but might nudge toward the cell's standard values.
    """
    result = {}
    # Merge: start with base, but override with target for categorical shifts
    result.update(target_params)

    for key in base_params:
        if key not in result:
            result[key] = base_params[key]

    # Apply random perturbation
    if random.random() < mutate_rate:
        perturb_keys = ["lr", "gamma", "hidden", "clip_grad"]
        for key in perturb_keys:
            if key in result:
                val = result[key]
                factor = random.uniform(0.5, 2.0)
                if isinstance(val, float):
                    result[key] = val * factor
                elif isinstance(val, int) and key == "hidden":
                    # Round to nearby power of 2 variant
                    result[key] = max(4, int(val * factor))
    return result


# ── Fitness Tracker ──

class FitnessTracker:
    """Track score trajectory and detect stagnation."""

    def __init__(self, window: int = 5, threshold: float = 0.01):
        self.scores: list[float] = []
        self.window = window
        self.threshold = threshold

    def record(self, score: float):
        self.scores.append(score)

    def get_trend(self) -> dict:
        if len(self.scores) < 2:
            return {"direction": "insufficient_data", "slope": 0.0}
        recent = self.scores[-self.window:]
        if len(recent) < 2:
            return {"direction": "insufficient_data", "slope": 0.0}
        x = np.arange(len(recent))
        slope = np.polyfit(x, recent, 1)[0]
        mean_score = np.mean(recent) if recent else 0
        normalized_slope = slope / max(abs(mean_score), 1e-6)
        if normalized_slope > self.threshold:
            direction = "improving"
        elif normalized_slope < -self.threshold:
            direction = "declining"
        else:
            direction = "stable"
        return {"direction": direction, "slope": slope, "normalized_slope": normalized_slope,
                "mean": np.mean(recent), "best": max(recent), "window_size": len(recent)}


# ── Island Manager ──

class IslandManager:
    """Detect and manage islands of related variants."""

    def __init__(self, archive_dir: Path):
        self.islands_dir = archive_dir / "islands"
        self.islands_dir.mkdir(parents=True, exist_ok=True)
        self._load_islands()

    def _load_islands(self):
        self.islands = []
        for d in sorted(self.islands_dir.iterdir()):
            if d.is_dir():
                meta_path = d / "island_meta.json"
                if meta_path.exists():
                    self.islands.append(json.loads(meta_path.read_text(encoding="utf-8")))

    def detect_and_assign(self, variant_id: str, cell_key: str, score: float,
                          dims: dict, method_family: str = "default") -> str:
        """Assign variant to an island, creating one if needed.

        Returns the island_id.
        """
        # Strategy 1: Match by method family
        matching = [i for i in self.islands if i.get("method_family") == method_family]

        if not matching:
            # Create new island
            return self._create_island(variant_id, cell_key, score, dims, method_family)

        # Strategy 2: Match by cell proximity (same first dimension)
        cell_parts = cell_key.split("+")
        dim0 = cell_parts[0] if cell_parts else ""
        for island in matching:
            island_cells = [v.get("cell", "") for v in island.get("variants", [])]
            if any(c.startswith(dim0) for c in island_cells):
                self._add_to_island(island["id"], variant_id, cell_key, score)
                return island["id"]

        # Strategy 3: Add to largest matching island
        largest = max(matching, key=lambda i: len(i.get("variants", [])))
        self._add_to_island(largest["id"], variant_id, cell_key, score)
        return largest["id"]

    def _create_island(self, variant_id: str, cell_key: str, score: float,
                       dims: dict, method_family: str) -> str:
        n = len(self.islands) + 1
        island_id = f"island_{n:03d}"
        meta = {
            "id": island_id,
            "name": f"{method_family.capitalize()} Island",
            "method_family": method_family,
            "centroid_cell": cell_key,
            "created_from": variant_id,
            "created_at": datetime.now().isoformat(),
            "variants": [{"id": variant_id, "cell": cell_key, "score": score}],
        }
        island_dir = self.islands_dir / island_id
        island_dir.mkdir(parents=True, exist_ok=True)
        (island_dir / "island_meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
        self.islands.append(meta)
        _success(f"Created new island: {island_id} ({method_family})")
        return island_id

    def _add_to_island(self, island_id: str, variant_id: str, cell_key: str, score: float):
        for island in self.islands:
            if island["id"] == island_id:
                island.setdefault("variants", []).append(
                    {"id": variant_id, "cell": cell_key, "score": score}
                )
                island_dir = self.islands_dir / island_id
                (island_dir / "island_meta.json").write_text(
                    json.dumps(island, indent=2, ensure_ascii=False))
                return

    def propose_merges(self, claim_chain_path: Path) -> list[dict]:
        """Check Claim Chain for specializes/derives relations between islands.
        Returns list of merge proposals."""
        relations = _load_jsonl(claim_chain_path / "relations.jsonl")
        proposals = []
        merge_types = {"specializes", "derives"}
        for r in relations:
            if r["type"] in merge_types:
                # Check if source and target are in different islands
                src_island = self._find_island_for_atom(r["source_id"])
                tgt_island = self._find_island_for_atom(r["target_id"])
                if src_island and tgt_island and src_island != tgt_island:
                    proposals.append({
                        "island_a": src_island,
                        "island_b": tgt_island,
                        "relation_type": r["type"],
                        "evidence": r.get("evidence", ""),
                        "proposed": True,
                    })
        return proposals

    def _find_island_for_atom(self, atom_id: int) -> str | None:
        for island in self.islands:
            for v in island.get("variants", []):
                # Check if the atom ID corresponds to this variant's claim
                if v.get("claim_atom_id") == atom_id:
                    return island["id"]
        return None

    def export(self) -> list[dict]:
        return self.islands


# ── Auto Evolve Engine ──

class AutoEvolveEngine:
    """Autonomous PES evolution engine."""

    def __init__(self, workspace: Path, config: dict, max_rounds: int = 20,
                 exploit_ratio: float = 0.7, dry_run: bool = False,
                 stagnation_window: int = 5, success_threshold: float | None = None):
        self.workspace = workspace
        self.config = config
        self.max_rounds = max_rounds
        self.exploit_ratio = exploit_ratio
        self.dry_run = dry_run
        self.success_threshold = success_threshold or self._read_success_threshold()

        self.archive_dir = workspace / config.get("archive_dir", "evolve_archive")
        self.claim_dir = workspace / "claim_chain"
        self.evolution_log = self.archive_dir / "evolution_log.jsonl"

        self.tracker = FitnessTracker(window=stagnation_window)
        self.island_mgr = IslandManager(self.archive_dir)
        self.stagnation_count = 0
        self.round = 0

        self._init_dirs()
        self._load_state()

    def _read_success_threshold(self) -> float:
        """Read success threshold from success_criteria.md or config."""
        sc_path = self.workspace / "success_criteria.md"
        if sc_path.exists():
            content = sc_path.read_text(encoding="utf-8")
            # Try to parse a target score like "> 195"
            import re
            m = re.search(r'>\s*(\d+(?:\.\d+)?)', content)
            if m:
                return float(m.group(1))
        # Fall back to config
        return self.config.get("success_threshold", None)

    def _init_dirs(self):
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.claim_dir.mkdir(parents=True, exist_ok=True)

    def _load_state(self):
        state_path = self.archive_dir / "evolve_state.json"
        if state_path.exists():
            self.state = json.loads(state_path.read_text(encoding="utf-8"))
        else:
            _err("No evolve_state.json found. Run 'evolve_grid.py init' first.")
            sys.exit(1)
        # Ensure next_variant is always ahead of all recorded IDs
        max_n = 0
        for h in self.state.get("variant_history", []):
            vid = h.get("id", "")
            if vid.startswith("v"):
                try:
                    n = int(vid[1:])
                    max_n = max(max_n, n)
                except ValueError:
                    pass
        self.state["next_variant"] = max_n + 1
        self._replay_fitness()

    def _replay_fitness(self):
        """Replay existing variant history into fitness tracker."""
        for entry in self.state.get("variant_history", []):
            self.tracker.record(entry["score"])

    def run(self):
        """Run the autonomous PES loop."""
        _info(f"Starting auto-evolve: max {self.max_rounds} rounds, "
              f"exploit_ratio={self.exploit_ratio}, success_threshold={self.success_threshold}")
        _info(f"Archive: {self.archive_dir}, Claim Chain: {self.claim_dir}")
        _info(f"Existing variants: {len(self.state.get('variant_history', []))}")

        trend = self.tracker.get_trend()
        _info(f"Fitness trend: {trend['direction']} (mean={trend.get('mean', 'N/A'):.1f}, "
              f"best={trend.get('best', 'N/A'):.1f})")

        for rnd in range(self.max_rounds):
            self.round = rnd + 1
            print(f"\n{'─'*60}", file=sys.stderr)
            _info(f"Round {self.round}/{self.max_rounds}", flush=True)

            # --- Plan Phase ---
            plan = self._plan()
            if plan is None:
                _warn("Cannot plan further. Stopping.")
                break

            # --- Execute Phase ---
            variant_id = f"v{self.state['next_variant']:03d}"
            result = self._execute(variant_id, plan)

            # --- Summary Phase ---
            self._summarize(variant_id, result, plan)

            # --- Check stopping conditions ---
            if self.success_threshold and result["score"] >= self.success_threshold:
                _success(f"Success threshold ({self.success_threshold}) reached! Evolution complete.")
                break

            if self.stagnation_count >= self.config.get("stagnation_window", 5):
                _warn(f"Stagnation detected ({self.stagnation_count} rounds). Applying meta-strategy...")
                self._apply_meta_strategy()
                self.stagnation_count = 0

            trend = self.tracker.get_trend()
            _info(f"Trend: {trend['direction']} | mean={trend['mean']:.1f} best={trend['best']:.1f} | "
                  f"stagnation: {self.stagnation_count}/{self.config.get('stagnation_window', 5)}")

        self._finalize()

    def _plan(self) -> dict | None:
        """Plan the next evolution step."""
        # Determine strategy
        strategy = "exploit" if random.random() < self.exploit_ratio else "explore"

        # Sample from grid
        cells = self.state["cells"]
        filled = {k: v for k, v in cells.items() if v["elite_id"] is not None}

        if not filled:
            strategy = "explore"

        if strategy == "exploit":
            keys = list(filled.keys())
            scores = np.array([filled[k]["elite_score"] for k in keys])
            scores = scores - scores.min() + 1e-6
            probs = scores / scores.sum()
            idx = np.random.choice(len(keys), p=probs)
            cell_key = keys[idx]
            parent = filled[cell_key]
            _info(f"Plan: [{strategy}] from {cell_key} (parent={parent['elite_id']}, score={parent['elite_score']})")
        else:
            empty = {k: v for k, v in cells.items() if v["elite_id"] is None}
            if empty:
                cell_key = random.choice(list(empty.keys()))
                parent = None
                _info(f"Plan: [{strategy}] targeting empty cell {cell_key}")
            elif filled:
                keys = list(filled.keys())
                scores_list = [filled[k]["elite_score"] for k in keys]
                idx = int(np.argmin(scores_list))
                cell_key = keys[idx]
                parent = filled[cell_key]
                _info(f"Plan: [{strategy}] improving weakest cell {cell_key}")
            else:
                return None

        # Map cell to parameters
        cell_params = map_cell_to_params(cell_key, self.config)

        # Mutate from parent if available
        if parent and parent.get("elite_params"):
            params = mutate_params(parent["elite_params"], cell_params)
        else:
            params = dict(cell_params)

        # Add non-mapped params with defaults
        params.setdefault("gamma", 0.99)
        params.setdefault("episodes", 500)
        params.setdefault("seed", 42 + self.round)

        plan = {
            "strategy": strategy,
            "cell_key": cell_key,
            "parent_id": parent["elite_id"] if parent else None,
            "parent_score": parent["elite_score"] if parent else None,
            "params": params,
        }
        _info(f"  Params: {params}")
        return plan

    def _execute(self, variant_id: str, plan: dict) -> dict:
        """Execute the training run."""
        params = plan["params"]
        cmd_template = self.config.get("training_command",
            "python train_a2c.py --lr {lr} --hidden {hidden} --gamma {gamma} --episodes {episodes} --seed {seed}")

        # Build command with parameter substitution
        cmd = cmd_template.format(**params, **{k: v for k, v in params.items() if k not in params})

        # Handle boolean/flag params
        for name, val in params.items():
            flag = f"--{name.replace('_', '-')}"
            if isinstance(val, bool) and val:
                cmd += f" {flag}"

        # Ensure seed is set
        if "--seed" not in cmd:
            cmd += f" --seed {params.get('seed', 42)}"

        _info(f"  Running: {cmd}")

        if self.dry_run:
            _info(f"  [DRY RUN] Would execute: {cmd}")
            return {"score": 0, "params": params, "dry_run": True}

        start = time.time()
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                cwd=str(self.workspace), timeout=300,
            )
            elapsed = time.time() - start

            if result.returncode != 0:
                _err(f"  Training failed (exit={result.returncode})")
                _err(f"  stderr: {result.stderr[-300:]}")
                return {"score": 0, "error": result.stderr, "params": params, "elapsed": elapsed}

            # Parse JSON from stdout (last line)
            stdout_lines = result.stdout.strip().split("\n")
            # Find the JSON line (starts with {)
            for line in reversed(stdout_lines):
                line = line.strip()
                if line.startswith("{"):
                    try:
                        data = json.loads(line)
                        _success(f"  Score: {data.get('final_avg_score', 'N/A')} "
                                 f"(best_avg: {data.get('best_avg_score', 'N/A')}) "
                                 f"in {elapsed:.1f}s")
                        return {
                            "score": data.get("final_avg_score", 0),
                            "best_avg_score": data.get("best_avg_score", 0),
                            "last10_std": data.get("last10_std", 0),
                            "elapsed": elapsed,
                            "params": params,
                            "raw_output": data,
                        }
                    except json.JSONDecodeError:
                        _err(f"  JSON parse failed from line: {line[:100]}")

            _err(f"  No valid JSON result in stdout. Last 200 chars: {result.stdout.strip()[-200:]}")
            return {"score": 0, "error": "no_json", "params": params, "elapsed": elapsed}

        except subprocess.TimeoutExpired:
            _err(f"  Training timed out (>300s)")
            return {"score": 0, "error": "timeout", "params": params, "elapsed": 300}

    def _summarize(self, variant_id: str, result: dict, plan: dict):
        """Record results, update grid and Claim Chain."""
        score = result["score"]
        cell_key = plan["cell_key"]
        params = result.get("params", plan["params"])
        parent_id = plan["parent_id"]
        parent_score = plan["parent_score"]

        if result.get("dry_run"):
            return

        # Determine classification
        if parent_score is not None:
            delta = score - parent_score
            if delta > 0:
                classification = "IMPROVEMENT"
            elif delta < 0 and abs(delta) / max(abs(parent_score), 1e-6) > 0.05:
                classification = "REGRESSION"
            else:
                classification = "STALE"
        else:
            classification = "BASELINE"

        _info(f"  Classification: {classification}")

        # Update grid archive
        dim_entries = {}
        dim_names = self.config.get("dim_names", [])
        cell_parts = cell_key.split("+")
        for name, value in zip(dim_names, cell_parts):
            dim_entries[name] = value

        cell = self.state["cells"].get(cell_key)
        if cell:
            prev_elite = cell["elite_score"]
            if prev_elite is None or score > prev_elite:
                cell["elite_id"] = variant_id
                cell["elite_score"] = score
                cell["elite_params"] = params
                _info(f"  Elite updated: {cell_key} ({prev_elite} → {score})")

        # Record in history
        self.state["variant_history"].append({
            "id": variant_id,
            "score": score,
            "cell": cell_key,
            "dims": dim_entries,
            "params": params,
            "classification": classification,
            "parent_id": parent_id,
            "round": self.round,
            "timestamp": datetime.now().isoformat(),
        })
        self.state["next_variant"] += 1

        # Persist state
        state_path = self.archive_dir / "evolve_state.json"
        state_path.write_text(json.dumps(self.state, indent=2, ensure_ascii=False))

        # Evolution log
        _append_jsonl(self.evolution_log, {
            "variant_id": variant_id,
            "round": self.round,
            "cell": cell_key,
            "score": score,
            "params": params,
            "classification": classification,
            "timestamp": datetime.now().isoformat(),
        })

        # Update Claim Chain
        self._update_claim_chain(variant_id, score, params, classification, parent_id, parent_score)

        # Assign to Island
        island_id = self.island_mgr.detect_and_assign(
            variant_id, cell_key, score, dim_entries,
            method_family=params.get("method_family", "default"))
        _info(f"  Island: {island_id}")

        # Update fitness tracker
        self.tracker.record(score)

        # Update stagnation counter
        if classification in ("STALE", "REGRESSION"):
            self.stagnation_count += 1
        else:
            self.stagnation_count = max(0, self.stagnation_count - 1)

    def _update_claim_chain(self, variant_id: str, score: float, params: dict,
                            classification: str, parent_id: str | None, parent_score: float | None):
        """Write atoms and relations to Claim Chain."""
        from claim_chain import ClaimChain
        cc = ClaimChain(self.claim_dir)

        # Generate atom IDs based on existing data
        existing_atoms = cc.get_atoms(limit=500, status=None)
        max_id = max((a["id"] for a in existing_atoms), default=0)

        # Create method atom
        method_id = max_id + 1
        cc.add_atom(
            type="method",
            title=f"{variant_id} - A2C variant",
            content=f"A2C with lr={params.get('lr', 'N/A')}, hidden={params.get('hidden', 'N/A')}, "
                    f"gamma={params.get('gamma', 'N/A')}, seed={params.get('seed', 'N/A')}",
            tags=["a2c", "variant", f"round_{self.round}"],
            evidence_level="experiment",
            metadata={"variant_id": variant_id, "round": self.round},
        )

        # Create verification atom
        verif_id = method_id + 1
        cc.add_atom(
            type="verification",
            title=f"{variant_id} score: {score:.1f}",
            content=f"{variant_id} achieved avg_score={score:.1f} on CartPole-v1. "
                     f"Parameters: {json.dumps({k: v for k, v in params.items() if k != 'seed'})}",
            tags=["score", "cartpole", f"round_{self.round}"],
            evidence_level="experiment",
            metadata={"score": score, "variant_id": variant_id, "params": params},
        )

        # Create relation
        if classification == "IMPROVEMENT":
            cc.add_relation(source_id=method_id, target_id=verif_id, type="validates",
                           evidence=f"score={score}, improvement over parent ({parent_id} score={parent_score})")
        elif classification == "REGRESSION":
            cc.add_relation(source_id=method_id, target_id=verif_id, type="contradicts",
                           evidence=f"score={score}, worse than parent ({parent_id} score={parent_score})")
        elif classification == "BASELINE":
            cc.add_relation(source_id=method_id, target_id=verif_id, type="validates",
                           evidence=f"baseline score={score}")

        # If parent exists, link to parent
        if parent_id:
            parent_atoms = [a for a in existing_atoms if a.get("metadata", {}).get("variant_id") == parent_id]
            if parent_atoms:
                parent_method = [a for a in parent_atoms if a["type"] == "method"]
                if parent_method:
                    cc.add_relation(source_id=parent_method[0]["id"], target_id=method_id,
                                   type="derives", evidence=f"Mutation: {variant_id} derived from {parent_id}")

    def _apply_meta_strategy(self):
        """Apply meta-strategy when stagnation is detected."""
        _info("Meta-strategy: trying more aggressive exploration...")
        # Shift toward more exploration
        self.exploit_ratio = max(0.3, self.exploit_ratio - 0.15)
        _info(f"  exploit_ratio adjusted to {self.exploit_ratio}")

        # Check Claim Chain for hints
        claim_relations = _load_jsonl(self.claim_dir / "relations.jsonl")
        contradict_relations = [r for r in claim_relations if r["type"] == "contradicts"]
        if contradict_relations:
            _info(f"  Claim Chain: {len(contradict_relations)} contradicts — avoiding those directions")

        validates = [r for r in claim_relations if r["type"] == "validates"]
        if validates:
            _info(f"  Claim Chain: {len(validates)} validates — reinforcing those directions")

    def _finalize(self):
        """Final summary and export."""
        filled = {k: v for k, v in self.state["cells"].items() if v["elite_id"] is not None}
        total = len(self.state["cells"])
        history = self.state.get("variant_history", [])

        print(f"\n{'='*60}", file=sys.stderr)
        _info(f"Evolution Complete: {self.round} rounds, {len(history)} variants")
        _info(f"Grid Coverage: {len(filled)}/{total} cells ({100*len(filled)/max(total,1):.0f}%)")
        if history:
            scores = [h["score"] for h in history]
            _info(f"Score Range: {min(scores):.1f} → {max(scores):.1f}")
            _info(f"Best: {max(scores):.1f}")

        # Export best
        export = []
        for k, v in sorted(filled.items(), key=lambda x: x[1].get("elite_score", 0), reverse=True):
            export.append({"cell": k, "variant_id": v["elite_id"], "score": v["elite_score"],
                           "dims": v["dim_values"]})
        export_path = self.archive_dir / "best_variants.json"
        export_path.write_text(json.dumps(export, indent=2, ensure_ascii=False))

        # Islands summary
        islands = self.island_mgr.export()
        _info(f"Islands: {len(islands)}")
        for island in islands:
            variants = island.get("variants", [])
            island_scores = [v["score"] for v in variants if v.get("score")]
            best_score = max(island_scores) if island_scores else 0
            _info(f"  {island['id']}: {len(variants)} variants, best={best_score:.1f}")

        # Output JSON summary to stdout for piping
        summary = {
            "rounds": self.round,
            "total_variants": len(history),
            "grid_coverage": f"{100*len(filled)/max(total,1):.0f}%",
            "score_range": [min(scores) for _ in range(1)] + [max(scores) for _ in range(1)] if history else [],
            "best_score": max(scores) if history else None,
            "islands": [{"id": i["id"], "name": i.get("name", ""), "variants": len(i.get("variants", []))}
                        for i in islands],
            "classification_dist": {
                c: sum(1 for h in history if h.get("classification") == c)
                for c in set(h.get("classification", "") for h in history)
            },
            "success_threshold_met": (
                max(scores) >= self.success_threshold if history and self.success_threshold else False
            ),
        }
        summary["score_range"] = [min(scores) if history else None, max(scores) if history else None]
        print(json.dumps(summary, indent=2))


# ── Performance Gate ──

def check_performance_gate(workspace: Path) -> dict:
    """Check if experiment results meet success criteria enough to proceed to Phase 5.

    Returns: {"pass": bool, "ratio": float, "recommendation": str, "loop_target": str}
    """
    sc_path = workspace / "success_criteria.md"
    if not sc_path.exists():
        return {"pass": True, "ratio": 1.0, "recommendation": "no_criteria", "loop_target": None}

    content = sc_path.read_text(encoding="utf-8")
    import re

    # Extract targets
    targets = []
    for m in re.finditer(r'>\s*(\d+(?:\.\d+)?)', content):
        targets.append(float(m.group(1)))

    # Try to get actual score from latest result
    actual_score = None
    # Check evolve_archive first
    result_files = sorted((workspace / "evolve_archive" / "results").glob("v*_result.json"),
                          reverse=True)
    if not result_files:
        # Try the best_variants.json
        best_path = workspace / "evolve_archive" / "best_variants.json"
        if best_path.exists():
            best = json.loads(best_path.read_text(encoding="utf-8"))
            if best:
                actual_score = best[0]["score"]
    else:
        result = json.loads(result_files[0].read_text(encoding="utf-8"))
        actual_score = result.get("score", result.get("final_avg_score", 0))

    if actual_score is None:
        # Try evolution_log
        log_path = workspace / "evolve_archive" / "evolution_log.jsonl"
        logs = _load_jsonl(log_path)
        if logs:
            scores = [l["score"] for l in logs]
            actual_score = max(scores)

    if actual_score is None or not targets:
        return {"pass": True, "ratio": 1.0, "recommendation": "no_data", "loop_target": None,
                "actual_score": actual_score, "target": targets[0] if targets else None}

    target = targets[0]
    ratio = actual_score / target if target > 0 else 1.0

    if ratio >= 1.0:
        return {"pass": True, "ratio": ratio, "actual_score": actual_score, "target": target,
                "recommendation": "proceed_to_phase5", "loop_target": None}
    elif ratio >= 0.8:
        return {"pass": False, "ratio": ratio, "actual_score": actual_score, "target": target,
                "recommendation": "iterate_w4", "loop_target": "W4",
                "reason": f"Score ({actual_score:.1f}) at {ratio*100:.0f}% of target ({target}). Close — re-implement with adjusted params."}
    elif ratio >= 0.5:
        return {"pass": False, "ratio": ratio, "actual_score": actual_score, "target": target,
                "recommendation": "iterate_w3_5", "loop_target": "W3.5",
                "reason": f"Score ({actual_score:.1f}) at {ratio*100:.0f}% of target ({target}). Medium gap — consider method change."}
    elif ratio >= 0.2:
        return {"pass": False, "ratio": ratio, "actual_score": actual_score, "target": target,
                "recommendation": "iterate_w3", "loop_target": "W3",
                "reason": f"Score ({actual_score:.1f}) at {ratio*100:.0f}% of target ({target}). Large gap — research better methods."}
    else:
        return {"pass": False, "ratio": ratio, "actual_score": actual_score, "target": target,
                "recommendation": "iterate_w2", "loop_target": "W2",
                "reason": f"Score ({actual_score:.1f}) at {ratio*100:.0f}% of target ({target}). Massive gap — re-plan from scratch."}


# ── CLI ──

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Evo Auto Evolve: Autonomous PES evolution engine")
    sub = parser.add_subparsers(dest="command")

    # run
    run_p = sub.add_parser("run", help="Run autonomous evolution")
    run_p.add_argument("--config", required=True, help="Path to evolve_config.json")
    run_p.add_argument("--workspace", default=".", help="Workspace directory")
    run_p.add_argument("--max-rounds", type=int, default=20)
    run_p.add_argument("--exploit-ratio", type=float, default=0.7)
    run_p.add_argument("--success-threshold", type=float, default=None,
                       help="Stop when score exceeds this")
    run_p.add_argument("--stagnation-window", type=int, default=5)

    # dry-run
    dry_p = sub.add_parser("dry-run", help="Show plan without executing")
    dry_p.add_argument("--config", required=True)
    dry_p.add_argument("--workspace", default=".")
    dry_p.add_argument("--max-rounds", type=int, default=5)

    # status
    status_p = sub.add_parser("status", help="Show evolution status")
    status_p.add_argument("--workspace", default=".")

    # performance-gate
    gate_p = sub.add_parser("performance-gate", help="Check performance gate")
    gate_p.add_argument("--workspace", required=True)

    # detect-islands
    island_p = sub.add_parser("detect-islands", help="Detect/create islands from results")
    island_p.add_argument("--workspace", required=True)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "run":
        config_path = Path(args.config)
        if not config_path.exists():
            _err(f"Config not found: {config_path}")
            sys.exit(1)
        config = json.loads(config_path.read_text(encoding="utf-8"))
        workspace = Path(args.workspace)
        engine = AutoEvolveEngine(
            workspace=workspace, config=config,
            max_rounds=args.max_rounds, exploit_ratio=args.exploit_ratio,
            dry_run=False, stagnation_window=args.stagnation_window,
            success_threshold=args.success_threshold,
        )
        engine.run()

    elif args.command == "dry-run":
        config_path = Path(args.config)
        config = json.loads(config_path.read_text(encoding="utf-8"))
        engine = AutoEvolveEngine(
            workspace=Path(args.workspace), config=config,
            max_rounds=args.max_rounds, dry_run=True,
        )
        engine.run()

    elif args.command == "status":
        workspace = Path(args.workspace)
        state_path = workspace / "evolve_archive" / "evolve_state.json"
        if not state_path.exists():
            print("No evolution state found.")
            sys.exit(0)
        state = json.loads(state_path.read_text(encoding="utf-8"))
        config_path = workspace / "evolve_archive" / "evolve_config.json"
        config = {}
        if config_path.exists():
            config = json.loads(config_path.read_text(encoding="utf-8"))

        tracker = FitnessTracker()
        for entry in state.get("variant_history", []):
            tracker.record(entry["score"])

        cells = state["cells"]
        filled = {k: v for k, v in cells.items() if v["elite_id"] is not None}
        trend = tracker.get_trend()

        print(f"Archive: {len(filled)}/{len(cells)} cells filled")
        print(f"Variants: {len(state.get('variant_history', []))}")
        print(f"Trend: {trend['direction']} (slope={trend.get('normalized_slope', 0):.4f})")
        print(f"Mean: {trend.get('mean', 0):.1f}, Best: {trend.get('best', 0):.1f}")
        print()
        print("Cells:")
        for k, v in sorted(cells.items()):
            score = f"{v['elite_score']:.1f}" if v["elite_score"] is not None else "---"
            vid = v.get("elite_id", "---")
            print(f"  {k:20s}  {vid:6s}  {score:>8s}")

        # Island summary
        islands_dir = workspace / "evolve_archive" / "islands"
        if islands_dir.exists():
            print("\nIslands:")
            for d in sorted(islands_dir.iterdir()):
                if d.is_dir():
                    meta_path = d / "island_meta.json"
                    if meta_path.exists():
                        meta = json.loads(meta_path.read_text(encoding="utf-8"))
                        print(f"  {meta['id']}: {meta.get('name', '')} "
                              f"({len(meta.get('variants', []))} variants)")

    elif args.command == "performance-gate":
        result = check_performance_gate(Path(args.workspace))
        print(json.dumps(result, indent=2))

    elif args.command == "detect-islands":
        workspace = Path(args.workspace)
        mgr = IslandManager(workspace / "evolve_archive")
        state_path = workspace / "evolve_archive" / "evolve_state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            for entry in state.get("variant_history", []):
                mgr.detect_and_assign(
                    entry["id"], entry["cell"], entry["score"],
                    entry.get("dims", {}), "default")

        # Check for merge proposals
        claim_dir = workspace / "claim_chain"
        if claim_dir.exists():
            proposals = mgr.propose_merges(claim_dir)
            if proposals:
                print("Merge proposals:")
                for p in proposals:
                    print(f"  {p['island_a']} ←[{p['relation_type']}]→ {p['island_b']}")
                    print(f"    Evidence: {p['evidence']}")
            else:
                print("No merge proposals found.")

        islands = mgr.export()
        print(f"\nTotal islands: {len(islands)}")
        for i in islands:
            print(json.dumps(i, indent=2))
