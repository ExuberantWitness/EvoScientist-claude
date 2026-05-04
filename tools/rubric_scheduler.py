"""RubricScheduler: 多维评分 + ELO追踪。

评分维度与 Cell Grid 维度完全独立。
ELO 仅锦标赛内部一次性使用，用完废弃。
"""

import math
from pathlib import Path


class RubricScheduler:
    """多维 Rubric 评分调度器 + ELO 追踪。"""

    INITIAL_DIMENSIONS = ["accuracy", "robustness", "efficiency", "completeness", "generalization"]
    SIMILARITY_THRESHOLD = 0.9
    TRIGGER_RATIO = 0.10       # 得分接近触发: 差距 < 10%
    ANOMALY_RATIO = 0.30       # CC异常触发: 同条件差距 > 30%
    MAX_DIMENSIONS = 10
    ELO_K = 32

    def __init__(self, claim_chain, max_score: float = 1000, solve_threshold: float | None = None):
        """
        claim_chain: ClaimChain 实例 (from tools.claim_chain)
        """
        self.cc = claim_chain
        self.max_score = max_score
        self.solve_threshold = solve_threshold
        self.dimensions = list(self.INITIAL_DIMENSIONS)

    # ── 触发判断 ──

    def should_trigger(self, score_a: float, score_b: float) -> bool:
        """得分接近触发: 差距 < 10%"""
        if score_a <= 0 or score_b <= 0:
            return abs(score_a - score_b) < max(abs(score_a), abs(score_b), 1) * 0.2
        ratio = abs(score_a - score_b) / max(abs(score_a), abs(score_b))
        return ratio < self.TRIGGER_RATIO

    def is_anomaly(self, variant_a: dict, variant_b: dict) -> bool:
        """CC 异常触发: 同 CC 条件下得分差距 > 30%"""
        score_a = variant_a.get("score", 0)
        score_b = variant_b.get("score", 0)
        if score_a <= 0 or score_b <= 0:
            return False
        ratio = abs(score_a - score_b) / max(abs(score_a), abs(score_b))
        # 同 CC 条件: 同 method_family 或共享 CC 先验
        same_family = variant_a.get("method_family") == variant_b.get("method_family")
        same_cell = variant_a.get("cell") == variant_b.get("cell")
        return (same_family or same_cell) and ratio > self.ANOMALY_RATIO

    def scan_cells_for_triggers(self, cell_grid) -> list[dict]:
        """扫描 Cell Grid 中所有需要 Rubric 对比的变体对。
        返回: [{cell_key, variant_a, variant_b, trigger_type: "proximity"|"anomaly"}]
        """
        pairs = []
        cells = cell_grid.get_all_cells()
        for cell_key, cell in cells.items():
            variants = cell.get("variants", [])
            if len(variants) < 2:
                continue
            for i in range(len(variants)):
                for j in range(i + 1, len(variants)):
                    va, vb = variants[i], variants[j]
                    if self.should_trigger(va.get("score", 0), vb.get("score", 0)):
                        pairs.append({
                            "cell_key": cell_key,
                            "variant_a": va,
                            "variant_b": vb,
                            "trigger_type": "proximity",
                        })
                    elif self.is_anomaly(va, vb):
                        pairs.append({
                            "cell_key": cell_key,
                            "variant_a": va,
                            "variant_b": vb,
                            "trigger_type": "anomaly",
                        })
        return pairs

    # ── 评分 ──

    def evaluate(self, variant_a: dict, variant_b: dict) -> dict:
        """对两个变体进行多维评分。

        variant_a/b: {id, score, params, raw_output, method_family, cell, ...}

        返回: {dimension_scores: {dim: {a: N, b: N}}, similarity, winner,
               new_dimensions_proposed, dimensions_used}
        """
        dim_scores = {}
        for dim in self.dimensions:
            score_a = self._score_dimension(dim, variant_a)
            score_b = self._score_dimension(dim, variant_b)
            dim_scores[dim] = {"a": score_a, "b": score_b}

        total_diff = 0
        for dim in self.dimensions:
            sc = dim_scores[dim]
            total_diff += abs(sc["a"] - sc["b"])
        similarity = 1.0 - (total_diff / (len(self.dimensions) * 10)) if self.dimensions else 1.0

        new_dims = []
        if similarity > self.SIMILARITY_THRESHOLD and len(self.dimensions) < self.MAX_DIMENSIONS:
            new_dims = self._propose_dimensions(variant_a, variant_b, dim_scores)

        # 判定 winner
        score_a_total = sum(s["a"] for s in dim_scores.values())
        score_b_total = sum(s["b"] for s in dim_scores.values())
        if abs(score_a_total - score_b_total) < 2:
            winner = "draw"
        else:
            winner = "variant_a" if score_a_total > score_b_total else "variant_b"

        return {
            "dimension_scores": dim_scores,
            "similarity": round(similarity, 3),
            "winner": winner,
            "new_dimensions_proposed": new_dims,
            "dimensions_used": len(self.dimensions),
        }

    def _score_dimension(self, dim: str, variant: dict) -> float:
        """评分单个维度 (0-10)。缺失维度留空，返回 -1 表示待评估。"""
        score = variant.get("score", 0)
        params = variant.get("params", {})
        raw = variant.get("raw_output", {})

        if dim == "accuracy":
            return min(10.0, score / (self.max_score / 10.0)) if score > 0 else 0

        elif dim == "robustness":
            std = raw.get("last10_std", variant.get("last10_std", 50))
            return max(0, min(10.0, 10.0 * (1 - std / max(self.max_score * 0.4, 1))))

        elif dim == "efficiency":
            elapsed = variant.get("elapsed", raw.get("elapsed_seconds", 10))
            eff = score / max(elapsed, 0.1)
            return min(10.0, eff / 10.0)

        elif dim == "completeness":
            best_avg = raw.get("best_avg_score", score)
            if self.solve_threshold and best_avg >= self.solve_threshold:
                return 10.0
            elif self.solve_threshold:
                return min(10.0, (best_avg / self.solve_threshold) * 10.0)
            else:
                return min(10.0, max(0, score / (self.max_score / 10.0)))

        elif dim == "generalization":
            std = raw.get("last10_std", variant.get("last10_std", 50))
            avg = max(abs(score), 1)
            cv = std / avg
            return max(0, min(10.0, 10.0 * (1 - cv)))

        else:
            return variant.get("dimension_scores", {}).get(dim, -1.0)

    def _propose_dimensions(self, variant_a: dict, variant_b: dict,
                            dim_scores: dict) -> list[str]:
        """当现有维度无法区分两个变体时，提议新维度。"""
        proposals = []
        params_a = variant_a.get("params", {})
        params_b = variant_b.get("params", {})

        lr_a, lr_b = params_a.get("lr", 0), params_b.get("lr", 0)
        if lr_a and lr_b and abs(lr_a - lr_b) / max(abs(lr_a), abs(lr_b), 1e-6) > 5:
            if "parameter_sensitivity" not in self.dimensions:
                proposals.append("parameter_sensitivity")

        hidden_a, hidden_b = params_a.get("hidden", 0), params_b.get("hidden", 0)
        if hidden_a and hidden_b and abs(hidden_a - hidden_b) > 16:
            if "model_complexity" not in self.dimensions:
                proposals.append("model_complexity")

        return proposals[:2]

    # ── ELO (锦标赛内部一次性使用) ──

    def update_elo(self, method_atom_id: int, opponent_atom_id: int, outcome: str) -> dict:
        """K=32 标准 Elo。ELO 分数暂存内存，不写入 CC。锦标赛结束后废弃。

        outcome: "win" | "loss" | "draw"
        返回: {atom_id, old_elo, new_elo, delta}
        """
        if not hasattr(self, "_elo_cache"):
            self._elo_cache = {}

        ra = self._elo_cache.get(method_atom_id, 1500.0)
        rb = self._elo_cache.get(opponent_atom_id, 1500.0)

        ea = 1.0 / (1.0 + math.pow(10, (rb - ra) / 400.0))
        eb = 1.0 - ea

        if outcome == "win":
            sa, sb = 1.0, 0.0
        elif outcome == "loss":
            sa, sb = 0.0, 1.0
        else:
            sa, sb = 0.5, 0.5

        new_ra = ra + self.ELO_K * (sa - ea)
        new_rb = rb + self.ELO_K * (sb - eb)

        self._elo_cache[method_atom_id] = new_ra
        self._elo_cache[opponent_atom_id] = new_rb

        return {
            "atom_id": method_atom_id,
            "old_elo": round(ra, 1),
            "new_elo": round(new_ra, 1),
            "delta": round(new_ra - ra, 1),
        }

    def get_elo_ranking(self, limit: int = 10) -> list[dict]:
        """返回当前锦标赛的 ELO 排名 (内存缓存)。"""
        if not hasattr(self, "_elo_cache") or not self._elo_cache:
            return []
        ranked = sorted(self._elo_cache.items(), key=lambda x: x[1], reverse=True)
        return [{"atom_id": aid, "elo": round(elo, 1)} for aid, elo in ranked[:limit]]

    def reset_elo(self):
        """清空 ELO 缓存 (锦标赛结束后调用)。"""
        self._elo_cache = {}

    # ── 维度管理 ──

    def get_active_dimensions(self) -> list[dict]:
        return [{"name": d, "index": i} for i, d in enumerate(self.dimensions)]

    def add_dimension(self, name: str) -> bool:
        if name not in self.dimensions and len(self.dimensions) < self.MAX_DIMENSIONS:
            self.dimensions.append(name)
            return True
        return False

    # ── 辅助 ──

    def format_report(self, evaluation: dict) -> str:
        """格式化为 Markdown 表格。"""
        lines = ["## Rubric Evaluation (L2)"]
        lines.append(f"Similarity: {evaluation['similarity']:.1%} | "
                     f"Winner: {evaluation.get('winner', 'N/A')}")
        lines.append("")
        lines.append("| Dimension | A | B | Δ |")
        lines.append("|-----------|---|---|---|")
        for dim, scores in evaluation.get("dimension_scores", {}).items():
            a, b = scores["a"], scores["b"]
            lines.append(f"| {dim} | {a:.1f} | {b:.1f} | {abs(a-b):.1f} |")
        if evaluation.get("new_dimensions_proposed"):
            lines.append("")
            lines.append(f"**New dimensions proposed:** "
                         f"{', '.join(evaluation['new_dimensions_proposed'])}")
        return "\n".join(lines)
