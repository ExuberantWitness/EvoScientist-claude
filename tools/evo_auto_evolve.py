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
import shlex
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
                if v.get("claim_atom_id") == atom_id:
                    return island["id"]
        return None

    def set_claim_atom_id(self, island_id: str, variant_id: str, atom_id: int):
        """Store the Claim Chain method atom ID on the island variant for merge detection."""
        for island in self.islands:
            if island["id"] == island_id:
                for v in island.get("variants", []):
                    if v.get("id") == variant_id:
                        v["claim_atom_id"] = atom_id
                        island_dir = self.islands_dir / island_id
                        (island_dir / "island_meta.json").write_text(
                            json.dumps(island, indent=2, ensure_ascii=False))
                        return

    def export(self) -> list[dict]:
        return self.islands


# ── Rubric + LLM-as-Judge (L2) ──

class RubricJudge:
    """Multi-dimensional evaluation triggered when two algorithms have close L1 scores.

    Evaluates across INITIAL_RUBRIC_DIMENSIONS and proposes new dimensions when
    existing ones can't distinguish between algorithms.
    """

    INITIAL_DIMENSIONS = ["accuracy", "robustness", "efficiency", "completeness", "generalization"]
    SIMILARITY_THRESHOLD = 0.9
    TRIGGER_RATIO = 0.10  # Trigger when scores within 10% of each other
    MAX_DIMENSIONS = 10

    def __init__(self, max_score: float = 1000, solve_threshold: float | None = None):
        self.max_score = max_score
        self.solve_threshold = solve_threshold
        self.dimensions = list(self.INITIAL_DIMENSIONS)
        self.comparisons: list[dict] = []

    def should_trigger(self, score_a: float, score_b: float) -> bool:
        """Check if two scores are close enough to warrant rubric evaluation."""
        if score_a <= 0 or score_b <= 0:
            return abs(score_a - score_b) < max(abs(score_a), abs(score_b), 1) * 0.2
        ratio = abs(score_a - score_b) / max(abs(score_a), abs(score_b))
        return ratio < self.TRIGGER_RATIO

    def evaluate(self, variant_a: dict, variant_b: dict, claim_chain_dir: Path | None = None) -> dict:
        """Evaluate two variants across all current rubric dimensions.

        Args:
            variant_a, variant_b: dicts with {id, score, params, raw_output, ...}
            claim_chain_dir: optional Claim Chain dir for context

        Returns: {dimension_scores: {dim: {a: N, b: N}}, similarity: float, new_dimensions: [...]}
        """
        dim_scores = {}
        for dim in self.dimensions:
            score_a = self._score_dimension(dim, variant_a)
            score_b = self._score_dimension(dim, variant_b)
            dim_scores[dim] = {"a": score_a, "b": score_b}

        # Compute overall similarity (1 - normalized L1 distance)
        total_diff = 0
        max_possible = 0
        for dim in self.dimensions:
            sc = dim_scores[dim]
            total_diff += abs(sc["a"] - sc["b"])
            max_possible += 10  # each dim scored 0-10
        similarity = 1.0 - (total_diff / max_possible) if max_possible > 0 else 1.0

        new_dims = []
        if similarity > self.SIMILARITY_THRESHOLD and len(self.dimensions) < self.MAX_DIMENSIONS:
            new_dims = self._propose_dimensions(variant_a, variant_b, dim_scores)

        result = {
            "dimension_scores": dim_scores,
            "similarity": round(similarity, 3),
            "new_dimensions_proposed": new_dims,
            "dimensions_used": len(self.dimensions),
        }
        self.comparisons.append(result)
        return result

    def _score_dimension(self, dim: str, variant: dict) -> float:
        """Score a variant on a single rubric dimension (0-10 scale)."""
        score = variant.get("score", 0)
        params = variant.get("params", {})
        raw = variant.get("raw_output", {})

        if dim == "accuracy":
            return min(10.0, score / (self.max_score / 10.0)) if score > 0 else 0

        elif dim == "robustness":
            # Lower std is better. Normalize: 10 * (1 - std/max_score*0.4) capped [0,10]
            std = raw.get("last10_std", variant.get("last10_std", 50))
            return max(0, min(10.0, 10.0 * (1 - std / max(self.max_score * 0.4, 1))))

        elif dim == "efficiency":
            episodes = params.get("episodes", 500)
            elapsed = variant.get("elapsed", raw.get("elapsed_seconds", episodes / 50))
            eff = score / max(elapsed, 0.1)
            return min(10.0, eff / 10.0)

        elif dim == "completeness":
            best_avg = raw.get("best_avg_score", score)
            if self.solve_threshold and best_avg >= self.solve_threshold:
                return 10.0
            elif self.solve_threshold:
                ratio = best_avg / self.solve_threshold
                return min(10.0, ratio * 10.0)
            else:
                return min(10.0, max(0, score / (self.max_score / 10.0)))

        elif dim == "generalization":
            # Consistency: last10_std relative to mean. Lower = better generalization
            std = raw.get("last10_std", variant.get("last10_std", 50))
            avg = max(abs(score), 1)
            cv = std / avg  # coefficient of variation
            return max(0, min(10.0, 10.0 * (1 - cv)))

        else:
            # Custom dimension: try to extract from variant metadata
            return variant.get("dimension_scores", {}).get(dim, 5.0)

    def _propose_dimensions(self, variant_a: dict, variant_b: dict,
                            dim_scores: dict) -> list[str]:
        """Propose new rubric dimensions when existing ones can't distinguish.

        Heuristic: look for attributes where the two variants differ meaningfully
        that aren't captured by existing dimensions.
        """
        proposals = []
        params_a = variant_a.get("params", {})
        params_b = variant_b.get("params", {})
        raw_a = variant_a.get("raw_output", {})
        raw_b = variant_b.get("raw_output", {})

        # Check for parameter sensitivity differences
        lr_a, lr_b = params_a.get("lr", 0), params_b.get("lr", 0)
        if lr_a and lr_b and abs(lr_a - lr_b) / max(abs(lr_a), abs(lr_b), 1e-6) > 5:
            if "parameter_sensitivity" not in self.dimensions:
                proposals.append("parameter_sensitivity")

        # Check for convergence speed differences
        total_ep_a = raw_a.get("total_episodes", params_a.get("episodes", 500))
        total_ep_b = raw_b.get("total_episodes", params_b.get("episodes", 500))
        if total_ep_a and total_ep_b:
            ratio = max(total_ep_a, total_ep_b) / max(min(total_ep_a, total_ep_b), 1)
            if ratio > 2 and "convergence_speed" not in self.dimensions:
                proposals.append("convergence_speed")

        # Check network architecture complexity
        hidden_a, hidden_b = params_a.get("hidden", 0), params_b.get("hidden", 0)
        if hidden_a and hidden_b and abs(hidden_a - hidden_b) > 16:
            if "model_complexity" not in self.dimensions:
                proposals.append("model_complexity")

        return proposals[:2]  # Cap at 2 new dimensions per evaluation

    def add_dimension(self, name: str):
        """Add a new dimension to the rubric."""
        if name not in self.dimensions and len(self.dimensions) < self.MAX_DIMENSIONS:
            self.dimensions.append(name)
            _info(f"Rubric: added dimension '{name}' ({len(self.dimensions)}/{self.MAX_DIMENSIONS})")

    def format_report(self, evaluation: dict) -> str:
        """Format rubric evaluation as a readable string."""
        lines = ["## Rubric Evaluation (L2 LLM-as-Judge)"]
        lines.append(f"Similarity: {evaluation['similarity']:.1%} ({evaluation['dimensions_used']} dims)")
        lines.append("")
        lines.append("| Dimension | Algorithm A | Algorithm B | Δ |")
        lines.append("|-----------|------------|------------|---|")
        for dim, scores in evaluation["dimension_scores"].items():
            a, b = scores["a"], scores["b"]
            delta = abs(a - b)
            lines.append(f"| {dim} | {a:.1f} | {b:.1f} | {delta:.1f} |")
        if evaluation.get("new_dimensions_proposed"):
            lines.append("")
            lines.append(f"**New dimensions proposed:** {', '.join(evaluation['new_dimensions_proposed'])}")
        return "\n".join(lines)


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

        # Task config (replaces hardcoded CartPole/A2C values)
        self.task_config = config.get("task", {})
        self.task_name = self.task_config.get("name", "unknown")
        self.env_name = self.task_config.get("env", "unknown")

        self.tracker = FitnessTracker(window=stagnation_window)
        self.island_mgr = IslandManager(self.archive_dir)
        self.rubric = RubricJudge(
            max_score=self.task_config.get("max_score", 1000),
            solve_threshold=self.task_config.get("solve_threshold", None),
        )
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
            # Auto-init grid from config if no state file exists
            _info("No evolve_state.json found. Auto-initializing grid from config...")
            self._init_grid()
            if not state_path.exists():
                _err("Failed to auto-init grid. Check evolve_config.json.")
                sys.exit(1)
            self.state = json.loads(state_path.read_text(encoding="utf-8"))
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

    def _init_grid(self):
        """Auto-initialize grid from config if no state file exists."""
        from itertools import product as _itertools_product
        dims = self.config.get("behavior_dims", [])
        if not dims:
            _err("Cannot auto-init: behavior_dims missing from config")
            return

        dim_values = [d["values"] for d in dims]
        dim_names = [d["name"] for d in dims]
        cells = {}
        for combo in _itertools_product(*dim_values):
            key = "+".join(combo)
            cells[key] = {
                "dim_values": dict(zip(dim_names, combo)),
                "elite_id": None,
                "elite_score": None,
            }

        self.config["dim_names"] = dim_names
        state = {"cells": cells, "variant_history": [], "next_variant": 1}
        state_path = self.archive_dir / "evolve_state.json"
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
        _info(f"Auto-initialized {len(cells)} cells ({len(dim_names)}D: {' × '.join(str(len(v)) for v in dim_values)})")

    def _read_claim_chain_knowledge(self) -> dict:
        """Read Claim Chain to build a structured knowledge map.

        Returns:
            {
              "validated_params": [{param_name: value_range, ...}],  # what worked
              "contradicted_params": [{param_name: value_range, ...}],  # what failed
              "boundaries": [{param: [min, max], ...}],  # known constraints
              "score_by_param": {lr_level: {value: best_score}},  # param performance map
              "total_validates": N, "total_contradicts": N,
            }
        """
        atoms = _load_jsonl(self.claim_dir / "atoms.jsonl")
        relations = _load_jsonl(self.claim_dir / "relations.jsonl")
        atom_map = {a["id"]: a for a in atoms}

        knowledge = {
            "validated_params": [],
            "contradicted_params": [],
            "boundaries": [],
            "score_by_param": {},
            "total_validates": 0,
            "total_contradicts": 0,
        }

        for r in relations:
            rtype = r["type"]
            src = atom_map.get(r["source_id"])
            tgt = atom_map.get(r["target_id"])
            if not src or not tgt:
                continue

            tgt_meta = tgt.get("metadata", {})
            tgt_params = tgt_meta.get("params", {})

            if rtype == "validates":
                knowledge["total_validates"] += 1
                if tgt_params:
                    knowledge["validated_params"].append({
                        "params": tgt_params,
                        "score": tgt_meta.get("score", 0),
                        "method_title": src.get("title", ""),
                    })
            elif rtype == "contradicts":
                knowledge["total_contradicts"] += 1
                if tgt_params:
                    knowledge["contradicted_params"].append({
                        "params": tgt_params,
                        "score": tgt_meta.get("score", 0),
                        "method_title": src.get("title", ""),
                    })
            elif rtype == "boundary_of":
                evidence = r.get("evidence", "")
                knowledge["boundaries"].append({
                    "evidence": evidence,
                    "source": src.get("title", ""),
                })

        # Build score_by_param: aggregate scores by each parameter dimension value
        dim_names = self.config.get("dim_names", [])
        for name in dim_names:
            knowledge["score_by_param"][name] = {}

        for entry in self.state.get("variant_history", []):
            dims = entry.get("dims", {})
            score = entry.get("score", 0)
            params = entry.get("params", {})
            for name, val in dims.items():
                if name not in knowledge["score_by_param"]:
                    knowledge["score_by_param"][name] = {}
                dim_map = knowledge["score_by_param"][name]
                if val not in dim_map:
                    dim_map[val] = {"total": 0, "count": 0, "best": 0}
                d = dim_map[val]
                d["total"] += score
                d["count"] += 1
                d["best"] = max(d["best"], score)

        return knowledge

    def _apply_knowledge_to_params(self, base_params: dict, target_params: dict,
                                   knowledge: dict, cell_key: str) -> dict:
        """Apply Claim Chain knowledge to parameter selection.

        - Avoid parameter regions with contradicts
        - Bias toward validates regions
        - Respect boundaries
        """
        result = dict(target_params)

        # Merge base params for non-conflicting keys
        for k, v in base_params.items():
            if k not in result:
                result[k] = v

        # Find best-performing params for the target cell's dimensions
        dim_names = self.config.get("dim_names", [])
        cell_parts = cell_key.split("+")

        # Check if cell's dimension values have contradict history
        for name, val in zip(dim_names, cell_parts):
            param_map = knowledge["score_by_param"].get(name, {})
            if val in param_map:
                info = param_map[val]
                avg = info["total"] / max(info["count"], 1)
                _info(f"  [Knowledge] {name}={val}: avg={avg:.1f}, best={info['best']:.1f} "
                      f"({info['count']} trials)")

        # Apply contradicts avoidance: if params matching this cell have poor history,
        # mutate more aggressively
        has_contradicts = any(
            c["params"].get("lr") == result.get("lr")
            and c["params"].get("hidden") == result.get("hidden")
            for c in knowledge["contradicted_params"]
            if c["params"]
        )

        if has_contradicts and knowledge["total_validates"] > 0:
            _info("  [Knowledge] Cell params have contradicts history — increasing mutation rate")
            # Look for a validates example with similar cell dims and bias toward it
            best_validated = max(knowledge["validated_params"],
                                key=lambda x: x.get("score", 0),
                                default=None)
            if best_validated:
                vp = best_validated["params"]
                _info(f"  [Knowledge] Biasing toward best validated: lr={vp.get('lr')}, "
                      f"hidden={vp.get('hidden')}, score={best_validated['score']}")
                # Blend: 60% best validated params, 40% target params
                for key in ("lr", "hidden", "gamma"):
                    if key in vp and key in result:
                        result[key] = vp[key] * 0.6 + result[key] * 0.4
                        if isinstance(result[key], float):
                            result[key] = round(result[key], 6)
                        elif isinstance(result[key], int):
                            result[key] = int(round(result[key]))

        # Apply boundary constraints
        for b in knowledge["boundaries"]:
            evidence = b.get("evidence", "").lower()
            if "gamma" in evidence and "gamma" in result:
                if ">= 0.9" in evidence or "> 0.9" in evidence or ">= 0.99" in evidence:
                    result["gamma"] = max(result["gamma"], 0.99)
                    _info(f"  [Knowledge] Boundary constraint: gamma >= 0.99")

        # Random perturbation (reduced if knowledge is strong)
        if random.random() < (0.15 if knowledge["total_validates"] > 2 else 0.3):
            perturb_keys = ["lr", "gamma"]
            for key in perturb_keys:
                if key in result:
                    val = result[key]
                    factor = random.uniform(0.7, 1.4)  # narrower range when knowledge-guided
                    if isinstance(val, (int, float)):
                        result[key] = round(val * factor, 6)

        return result

    def run(self):
        """Run the autonomous PES loop."""
        _info(f"Starting auto-evolve: max {self.max_rounds} rounds, "
              f"exploit_ratio={self.exploit_ratio}, success_threshold={self.success_threshold}")
        _info(f"Archive: {self.archive_dir}, Claim Chain: {self.claim_dir}")
        _info(f"Existing variants: {len(self.state.get('variant_history', []))}")

        # Read initial Claim Chain knowledge
        self.claim_knowledge = self._read_claim_chain_knowledge()
        _info(f"Claim Chain knowledge: {self.claim_knowledge['total_validates']} validates, "
              f"{self.claim_knowledge['total_contradicts']} contradicts, "
              f"{len(self.claim_knowledge['boundaries'])} boundaries")

        trend = self.tracker.get_trend()
        mean_str = f"{trend['mean']:.1f}" if isinstance(trend.get('mean'), (int, float)) else "N/A"
        best_str = f"{trend['best']:.1f}" if isinstance(trend.get('best'), (int, float)) else "N/A"
        _info(f"Fitness trend: {trend['direction']} (mean={mean_str}, best={best_str})")

        for rnd in range(self.max_rounds):
            self.round = rnd + 1
            print(f"\n{'─'*60}", file=sys.stderr)
            _info(f"Round {self.round}/{self.max_rounds}", flush=True)

            # --- Plan Phase (Claim Chain informed) ---
            plan = self._plan()
            if plan is None:
                _warn("Cannot plan further. Stopping.")
                break

            # --- Execute Phase ---
            variant_id = f"v{self.state['next_variant']:03d}"
            result = self._execute(variant_id, plan)

            # --- Summary Phase ---
            self._summarize(variant_id, result, plan)

            # --- Rubric Phase (L2: check if scores close to any existing variant) ---
            self._check_rubric(variant_id, result, plan)

            # --- Island Migration Check ---
            self._check_island_migration(variant_id, plan)

            # --- Refresh Claim Chain knowledge after new data ---
            self.claim_knowledge = self._read_claim_chain_knowledge()

            # --- Check stopping conditions ---
            if self.success_threshold and result["score"] >= self.success_threshold:
                _success(f"Success threshold ({self.success_threshold}) reached! Evolution complete.")
                break

            if self.stagnation_count >= self.config.get("stagnation_window", 5):
                _warn(f"Stagnation detected ({self.stagnation_count} rounds). Applying meta-strategy...")
                self._apply_meta_strategy()
                self.stagnation_count = 0

            trend = self.tracker.get_trend()
            t_mean = f"{trend['mean']:.1f}" if 'mean' in trend else "N/A"
            t_best = f"{trend['best']:.1f}" if 'best' in trend else "N/A"
            _info(f"Trend: {trend['direction']} | mean={t_mean} best={t_best} | "
                  f"stagnation: {self.stagnation_count}/{self.config.get('stagnation_window', 5)}")

        self._finalize()

    def _plan(self) -> dict | None:
        """Plan the next evolution step, informed by Claim Chain knowledge."""
        strategy = "exploit" if random.random() < self.exploit_ratio else "explore"

        cells = self.state["cells"]
        filled = {k: v for k, v in cells.items() if v["elite_id"] is not None}
        cc = getattr(self, "claim_knowledge", {})

        if not filled:
            strategy = "explore"

        if strategy == "exploit":
            # Use Claim Chain knowledge to weight cell selection:
            # cells with validates history get higher weight, contradicts get lower
            keys = list(filled.keys())
            scores = np.array([filled[k]["elite_score"] for k in keys])
            scores = scores - scores.min() + 1e-6
            probs = scores / scores.sum()

            # Adjust probs by Claim Chain history per cell
            for i, k in enumerate(keys):
                cell_dims = cells[k].get("dim_values", {})
                # Check if this cell's param combo has validates
                has_validates = any(
                    vp.get("params", {}).get("lr") == cell_dims.get("lr_level")
                    for vp in cc.get("validated_params", []) if vp.get("params")
                )
                has_contradicts = any(
                    cp.get("params", {}).get("lr") == cell_dims.get("lr_level")
                    for cp in cc.get("contradicted_params", []) if cp.get("params")
                )
                if has_validates:
                    probs[i] *= 1.5
                    _info(f"  [Knowledge] {k} boosted (has validates)")
                if has_contradicts:
                    probs[i] *= 0.5
                    _info(f"  [Knowledge] {k} discounted (has contradicts)")
            probs = probs / probs.sum()

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

        # Get base params from parent or cell defaults
        if parent and parent.get("elite_params"):
            base_params = dict(parent["elite_params"])
        else:
            base_params = dict(cell_params)

        # Apply Claim Chain knowledge to guide mutation
        if cc:
            params = self._apply_knowledge_to_params(base_params, cell_params, cc, cell_key)
        else:
            params = base_params
            for k, v in cell_params.items():
                if k not in params:
                    params[k] = v

        # Add non-mapped params with defaults
        params.setdefault("gamma", 0.99)
        params.setdefault("episodes", 500)
        params.setdefault("seed", 42 + self.round)

        # Apply meta-strategy adjustments (set by _apply_meta_strategy during stagnation)
        if hasattr(self, '_forbidden_zones') and self._forbidden_zones:
            for _ in range(3):
                key = (params.get("lr"), params.get("hidden"), params.get("gamma"))
                if key not in self._forbidden_zones:
                    break
                params = mutate_params(params, params, mutate_rate=0.5)

        if hasattr(self, '_promising_zones') and self._promising_zones:
            best = max(self._promising_zones, key=lambda x: x.get("score", 0))
            for key in ("lr", "gamma"):
                if key in params and key in best and best[key] is not None:
                    params[key] = params[key] * 0.7 + best[key] * 0.3

        if hasattr(self, '_mutation_aggressiveness'):
            for key in ("lr", "gamma"):
                if key in params and isinstance(params[key], (int, float)):
                    factor = random.uniform(1.0 / self._mutation_aggressiveness,
                                            self._mutation_aggressiveness)
                    params[key] = type(params[key])(round(params[key] * factor, 6))

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

        # Safe parameter substitution with shlex.quote to prevent shell injection
        safe_params = {k: shlex.quote(str(v)) for k, v in params.items()}
        cmd = cmd_template.format(**safe_params)

        # Handle boolean/flag params
        for name, val in params.items():
            flag = f"--{name.replace('_', '-')}"
            if isinstance(val, bool) and val:
                cmd += f" {flag}"

        # Ensure seed is set
        if "--seed" not in cmd:
            cmd += f" --seed {shlex.quote(str(params.get('seed', 42)))}"

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

        # Update Claim Chain — returns method atom ID for island linking
        method_atom_id = self._update_claim_chain(variant_id, score, params, classification, parent_id, parent_score)

        # Assign to Island
        island_id = self.island_mgr.detect_and_assign(
            variant_id, cell_key, score, dim_entries,
            method_family=params.get("method_family", "default"))
        _info(f"  Island: {island_id}")

        # Link variant to its Claim Chain atom for merge detection
        if method_atom_id:
            self.island_mgr.set_claim_atom_id(island_id, variant_id, method_atom_id)

        # Update fitness tracker
        self.tracker.record(score)

        # Update stagnation counter
        if classification in ("STALE", "REGRESSION"):
            self.stagnation_count += 1
        else:
            self.stagnation_count = max(0, self.stagnation_count - 1)

    def _update_claim_chain(self, variant_id: str, score: float, params: dict,
                            classification: str, parent_id: str | None, parent_score: float | None) -> int:
        """Write atoms and relations to Claim Chain. Returns method atom ID."""
        from claim_chain import ClaimChain
        cc = ClaimChain(self.workspace)

        existing_atoms = cc.get_atoms(limit=500, status=None)

        # Create method atom
        params_safe = {k: v for k, v in params.items() if k != "seed"}
        method_atom = cc.add_atom(
            type="method",
            title=f"{variant_id} - {self.task_name} variant",
            content=f"{self.task_name} variant with {json.dumps(params_safe)}",
            tags=["variant", self.task_name, f"round_{self.round}"],
            evidence_level="experiment",
            metadata={"variant_id": variant_id, "round": self.round},
        )

        # Create verification atom
        verif_atom = cc.add_atom(
            type="verification",
            title=f"{variant_id} score: {score:.1f}",
            content=f"{variant_id} achieved score={score:.1f} on {self.env_name}. "
                     f"Parameters: {json.dumps(params_safe)}",
            tags=["score", self.task_name, f"round_{self.round}"],
            evidence_level="experiment",
            metadata={"score": score, "variant_id": variant_id, "params": params},
        )

        # Create relation using actual atom IDs from return values
        if classification == "IMPROVEMENT":
            cc.add_relation(source_id=method_atom["id"], target_id=verif_atom["id"], type="validates",
                           evidence=f"score={score}, improvement over parent ({parent_id} score={parent_score})")
        elif classification == "REGRESSION":
            cc.add_relation(source_id=method_atom["id"], target_id=verif_atom["id"], type="contradicts",
                           evidence=f"score={score}, worse than parent ({parent_id} score={parent_score})")
        elif classification == "BASELINE":
            cc.add_relation(source_id=method_atom["id"], target_id=verif_atom["id"], type="validates",
                           evidence=f"baseline score={score}")

        # If parent exists, link to parent
        if parent_id:
            parent_atoms = [a for a in existing_atoms if a.get("metadata", {}).get("variant_id") == parent_id]
            if parent_atoms:
                parent_method = [a for a in parent_atoms if a["type"] == "method"]
                if parent_method:
                    cc.add_relation(source_id=parent_method[0]["id"], target_id=method_atom["id"],
                                   type="derives", evidence=f"Mutation: {variant_id} derived from {parent_id}")

        return method_atom["id"]

    def _apply_meta_strategy(self):
        """Apply meta-strategy when stagnation is detected.

        Uses Claim Chain knowledge to:
        1. Identify and avoid parameter regions with consistent fails
        2. Shift toward parameter regions with consistent success
        3. Increase exploration of untouched cells
        4. Relax boundaries if all attempts within bounds are exhausted
        """
        _info("Meta-strategy: analyzing Claim Chain for strategy adjustment...")
        cc = self._read_claim_chain_knowledge()

        # 1. Build forbidden parameter zones from contradicts
        forbidden = set()
        for cp in cc["contradicted_params"]:
            p = cp.get("params", {})
            key = (p.get("lr"), p.get("hidden"), p.get("gamma"))
            forbidden.add(key)
        if forbidden:
            _info(f"  Forbidden zones: {len(forbidden)} param combinations to avoid")
            self._forbidden_zones = forbidden

        # 2. Build promising zones from validates
        self._promising_zones = []
        for vp in cc["validated_params"]:
            p = vp.get("params", {})
            if p:
                self._promising_zones.append({
                    "lr": p.get("lr"), "hidden": p.get("hidden"),
                    "gamma": p.get("gamma"), "score": vp.get("score", 0),
                })
        if self._promising_zones:
            best = max(self._promising_zones, key=lambda x: x["score"])
            _info(f"  Best promising zone: lr={best['lr']}, hidden={best['hidden']}, "
                  f"gamma={best['gamma']}, score={best['score']}")

        # 3. Check grid coverage - target empty cells more aggressively
        cells = self.state["cells"]
        empty = [k for k, v in cells.items() if v.get("elite_id") is None]
        if empty:
            _info(f"  Untouched cells: {len(empty)}/{len(cells)} — boosting exploration")
            self.exploit_ratio = max(0.2, self.exploit_ratio - 0.2)
        else:
            _info("  All cells touched — looking for weak spots")
            # Target cells with score below 50% of best
            filled = {k: v for k, v in cells.items() if v.get("elite_score")}
            best = max(v["elite_score"] for v in filled.values())
            weak = [k for k, v in filled.items() if v["elite_score"] < best * 0.3]
            if weak:
                _info(f"  Weak cells: {len(weak)} below 30% of best — targeting for improvement")

        # 4. Adjust exploration of hyperparameter ranges
        if cc["total_contradicts"] > cc["total_validates"]:
            _info("  More contradicts than validates — widening search space")
            self._mutation_aggressiveness = 1.5  # wider perturbations
        else:
            self._mutation_aggressiveness = 0.8  # tighter, exploit what works

        _info(f"  exploit_ratio={self.exploit_ratio:.1f}, "
              f"mutation_aggressiveness={getattr(self, '_mutation_aggressiveness', 1.0):.1f}")

    def _check_rubric(self, variant_id: str, result: dict, plan: dict):
        """L2 Rubric: check if current variant's score is close to any existing variant.

        When two algorithms have scores within TRIGGER_RATIO (10%), trigger
        multi-dimensional evaluation and write compares_to relation to Claim Chain.
        """
        history = self.state.get("variant_history", [])
        if len(history) < 2:
            return

        current_score = result["score"]
        if current_score <= 0:
            return

        # Find variants with close scores (within trigger ratio)
        close_variants = []
        for entry in history:
            if entry.get("id") == variant_id:
                continue
            entry_score = entry.get("score", 0)
            if entry_score <= 0:
                continue
            if self.rubric.should_trigger(current_score, entry_score):
                close_variants.append(entry)

        if not close_variants:
            return

        # Evaluate against the closest-score variant
        best_match = min(close_variants, key=lambda e: abs(e.get("score", 0) - current_score))
        variant_a = {
            "id": variant_id, "score": current_score,
            "params": result.get("params", {}),
            "raw_output": result.get("raw_output", {}),
            "elapsed": result.get("elapsed", 0),
            "last10_std": result.get("last10_std", 50),
        }
        variant_b = {
            "id": best_match.get("id", ""), "score": best_match.get("score", 0),
            "params": best_match.get("params", {}),
            "raw_output": best_match.get("raw_output", {}),
            "elapsed": best_match.get("elapsed", 0),
            "last10_std": best_match.get("last10_std", 50),
        }

        evaluation = self.rubric.evaluate(variant_a, variant_b, self.claim_dir)
        _info(f"  [Rubric L2] {variant_a['id']} vs {variant_b['id']}: "
              f"similarity={evaluation['similarity']:.1%} ({evaluation['dimensions_used']} dims)")

        # Write to Claim Chain: fact atom + compares_to relation
        self._write_rubric_to_cc(variant_a, variant_b, evaluation)

        # If new dimensions proposed, auto-accept in auto mode
        for new_dim in evaluation.get("new_dimensions_proposed", []):
            self.rubric.add_dimension(new_dim)

        # Display rubric table
        for dim, scores in evaluation["dimension_scores"].items():
            _info(f"    {dim:20s}: {variant_a['id']}={scores['a']:.1f}  {variant_b['id']}={scores['b']:.1f}  "
                  f"Δ={abs(scores['a']-scores['b']):.1f}")

    def _write_rubric_to_cc(self, variant_a: dict, variant_b: dict, evaluation: dict):
        """Write rubric comparison results to Claim Chain as fact atom + compares_to relation."""
        from claim_chain import ClaimChain
        cc = ClaimChain(self.workspace)
        existing = cc.get_atoms(limit=500, status=None)

        dim_summary = ", ".join(
            f"{dim}: A={s['a']:.1f} B={s['b']:.1f}"
            for dim, s in evaluation["dimension_scores"].items()
        )

        # Find method atoms for both variants
        atoms_a = [a for a in existing if a.get("metadata", {}).get("variant_id") == variant_a["id"]]
        atoms_b = [a for a in existing if a.get("metadata", {}).get("variant_id") == variant_b["id"]]
        method_a = next((a for a in atoms_a if a["type"] == "method"), None)
        method_b = next((a for a in atoms_b if a["type"] == "method"), None)

        # Create comparison fact atom — capture return value for correct ID
        fact_atom = cc.add_atom(
            type="fact",
            title=f"Rubric: {variant_a['id']} vs {variant_b['id']}",
            content=f"Multi-dimensional comparison: similarity={evaluation['similarity']:.1%}. "
                     f"Scores: {dim_summary}",
            tags=["comparison", "rubric", "l2"],
            evidence_level="experiment",
            metadata={"variant_a": variant_a["id"], "variant_b": variant_b["id"],
                      "evaluation": evaluation},
        )

        # Create compares_to relations using actual atom IDs
        if method_a and method_b:
            cc.add_relation(source_id=method_a["id"], target_id=method_b["id"],
                           type="compares_to",
                           evidence=f"similarity={evaluation['similarity']:.1%}: {dim_summary}")
            cc.add_relation(source_id=method_b["id"], target_id=method_a["id"],
                           type="compares_to",
                           evidence=f"similarity={evaluation['similarity']:.1%}: {dim_summary}")

    def _check_island_migration(self, variant_id: str, plan: dict):
        """L3 Island Migration: triple-check before moving variant between islands.

        Check 1: Claim Chain validation — target island's claims don't contradict the migrant
        Check 2: Score threshold — migrant score >= target island best * MIGRATION_SCORE_FLOOR_RATIO
        Check 3: Significant improvement over current island's average
        """
        history = self.state.get("variant_history", [])
        current_entry = next((h for h in history if h.get("id") == variant_id), None)
        if not current_entry:
            return

        current_score = current_entry.get("score", 0)
        current_cell = current_entry.get("cell", "")

        islands = self.island_mgr.export()
        if len(islands) < 2:
            return

        current_island_id = None
        for island in islands:
            for v in island.get("variants", []):
                if v.get("id") == variant_id:
                    current_island_id = island["id"]
                    break
            if current_island_id:
                break

        if not current_island_id:
            return

        current_island = next((i for i in islands if i["id"] == current_island_id), None)
        if not current_island:
            return

        # Check if another island would be a better fit
        for target_island in islands:
            if target_island["id"] == current_island_id:
                continue

            # Check 1: Claim Chain — do target island's atoms contradict our params?
            our_params = current_entry.get("params", {})
            cc_atoms = _load_jsonl(self.claim_dir / "atoms.jsonl")
            cc_relations = _load_jsonl(self.claim_dir / "relations.jsonl")

            target_variants = target_island.get("variants", [])
            target_atom_ids = set()
            for tv in target_variants:
                for a in cc_atoms:
                    if a.get("metadata", {}).get("variant_id") == tv.get("id"):
                        target_atom_ids.add(a["id"])

            contradicts_found = False
            for r in cc_relations:
                if r["type"] == "contradicts" and r["source_id"] in target_atom_ids:
                    target_atom = next((a for a in cc_atoms if a["id"] == r["source_id"]), None)
                    if target_atom:
                        tp = target_atom.get("metadata", {}).get("params", {})
                        # If our params are similar to a contradicted config, don't migrate
                        if (tp.get("lr") == our_params.get("lr") and
                                tp.get("hidden") == our_params.get("hidden")):
                            contradicts_found = True
                            break

            if contradicts_found:
                _info(f"  [Migration] Check 1 FAILED: {variant_id} contradicted in {target_island['id']}")
                continue

            # Check 2: Score threshold
            target_scores = [v.get("score", 0) for v in target_variants if v.get("score")]
            target_best = max(target_scores) if target_scores else 0
            floor = target_best * self.config.get("migration_score_floor_ratio", 0.8)
            if current_score < floor:
                _info(f"  [Migration] Check 2 FAILED: score {current_score:.1f} < floor {floor:.1f}")
                continue

            # Check 3: Migrant must improve upon target island's average
            target_island_scores = [v.get("score", 0) for v in target_variants if v.get("score")]
            target_avg = sum(target_island_scores) / max(len(target_island_scores), 1)
            if current_score <= target_avg:
                _info(f"  [Migration] Check 3 FAILED: score {current_score:.1f} not above "
                      f"target island avg {target_avg:.1f}")
                continue

            # All checks passed
            _success(f"  [Migration] PASSED: {variant_id} can migrate from {current_island_id} → {target_island['id']}")
            _info(f"    Score: {current_score:.1f} vs target best {target_best:.1f} (floor={floor:.1f})")
            self.island_mgr._add_to_island(target_island["id"], variant_id, current_cell, current_score)

            # Write migration to Claim Chain
            from claim_chain import ClaimChain
            cc = ClaimChain(self.workspace)
            cc.add_atom(
                type="fact",
                title=f"Migration: {variant_id} → {target_island['id']}",
                content=f"Variant {variant_id} (score={current_score}) migrated from "
                        f"{current_island_id} to {target_island['id']}. "
                        f"Triple check passed: no contradicts, score above floor, significant improvement.",
                tags=["migration", "island", "l3"],
                evidence_level="experiment",
                metadata={"variant_id": variant_id, "from_island": current_island_id,
                          "to_island": target_island["id"]},
            )
            break

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

    # init-config
    init_p = sub.add_parser("init-config", help="Generate evolve_config.json from workspace")
    init_p.add_argument("--workspace", required=True, help="Workspace directory")
    init_p.add_argument("--plan", default=None, help="Path to plan.md (optional)")
    init_p.add_argument("--training-command", default=None,
                        help="Training command template with {lr}, {hidden}, etc.")
    init_p.add_argument("--success-threshold", type=float, default=195.0,
                        help="Target score to stop evolution")

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

    elif args.command == "init-config":
        workspace = Path(args.workspace)
        archive_dir = workspace / "evolve_archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        config_path = archive_dir / "evolve_config.json"

        if config_path.exists():
            print(f"Config already exists: {config_path}")
            print(json.dumps(json.loads(config_path.read_text()), indent=2))
        else:
            # Detect training script from workspace
            training_cmd = args.training_command
            if not training_cmd:
                # Auto-detect common patterns
                for candidate in ["train.py", "train_a2c.py", "train_ppo.py", "run.py"]:
                    if (workspace / candidate).exists():
                        training_cmd = f"python {candidate} --lr {{lr}} --hidden {{hidden}} --gamma {{gamma}} --episodes {{episodes}} --seed {{seed}}"
                        break
                if not training_cmd:
                    training_cmd = "python train.py --lr {lr} --hidden {hidden} --gamma {gamma} --episodes {episodes} --seed {seed}"

            config = {
                "behavior_dims": [
                    {"name": "lr_level", "values": ["high", "medium", "low"]},
                    {"name": "network_size", "values": ["small", "medium", "large"]},
                ],
                "dim_names": ["lr_level", "network_size"],
                "param_mapping": {
                    "lr_level": {
                        "high": {"lr": 0.01},
                        "medium": {"lr": 0.003},
                        "low": {"lr": 0.001},
                    },
                    "network_size": {
                        "small": {"hidden": 8},
                        "medium": {"hidden": 32},
                        "large": {"hidden": 64},
                    },
                },
                "training_command": training_cmd,
                "max_rounds": 20,
                "exploit_ratio": 0.7,
                "stagnation_window": 5,
                "stagnation_threshold": 0.01,
                "success_threshold": args.success_threshold,
                "archive_dir": "evolve_archive",
            }

            config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False))
            print(f"Created config: {config_path}")
            print(json.dumps(config, indent=2))

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
