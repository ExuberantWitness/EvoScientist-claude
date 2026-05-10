"""CellGrid: 轻量多维行为索引 + 异常检测 + 里程碑触发器。

纯 Python 实现，不依赖 numpy/Pyribs。
Cell Grid 维度来自 Claim Chain (索引)，与 Rubric 评分维度完全独立。

特性:
  - Part1+Part2 初始化 cell，Part3 通配符预留扩展槽
  - 5% 容错匹配 + 超范围自动建 cell
  - 同 CC 条件下巨大性能差异 → 标记 anomaly → 触发 W5 调查
  - 6 种里程碑事件

用法:
  python cell_grid.py init --config '{"behavior_dims": [...]}' --dir evolve_archive
  python cell_grid.py record-result --id v001 --score 18 --descriptor '{"method_family":"ppo"}'
  python cell_grid.py status --dir evolve_archive
  python cell_grid.py heatmap --dir evolve_archive
"""

import json
import sys
from itertools import product as _itertools_product
from pathlib import Path


# ── Dimension defaults (Part1: 通用标准) ──

PART1_DEFAULTS = [
    {"name": "accuracy",   "source": "rubric_standard", "values": ["low", "medium", "high"]},
    {"name": "robustness", "source": "rubric_standard", "values": ["low", "medium", "high"]},
    {"name": "efficiency", "source": "rubric_standard", "values": ["low", "medium", "high"]},
    {"name": "completeness", "source": "rubric_standard", "values": ["low", "medium", "high"]},
]

PART3_MAX = 3  # Part3 维度上限
TOLERANCE = 0.05  # 5% 容错匹配
ANOMALY_RATIO = 0.30  # 同 CC 条件下得分差异 >30% → 异常


def _info(msg: str):
    print(msg, file=sys.stderr)


class CellGrid:
    """轻量多维索引 + 异常检测 + 里程碑触发器。"""

    def __init__(self, archive_dir: str | Path = "evolve_archive"):
        self.dir = Path(archive_dir)
        self.config_path = self.dir / "evolve_config.json"
        self.state_path = self.dir / "evolve_state.json"
        self.audit_path = self.dir / "audit_log.jsonl"

    # ── 初始化 ──

    def init(self, dimensions: list[dict]) -> dict:
        """初始化网格。Part1 自动注入，Part2 来自参数，Part3 预留槽位。

        dimensions: Part2 任务相关维度
          [{"name": "method_family", "source": "task_specific", "values": ["baseline", "ppo"]}]
        """
        self.dir.mkdir(parents=True, exist_ok=True)

        merged_dims = list(PART1_DEFAULTS) + list(dimensions)
        dim_names = [d["name"] for d in merged_dims]

        cells = {}
        dim_values = [d["values"] for d in merged_dims]
        for combo in _itertools_product(*dim_values):
            key = "+".join(combo)
            cells[key] = {
                "dim_values": dict(zip(dim_names, combo)),
                "elite_id": None,
                "elite_score": None,
                "variants": [],  # [{id, score, claim_conditions}]
                "anomalies": [],
            }

        config = {
            "dim_names": dim_names,
            "behavior_dims": merged_dims,
            "part3_slots_remaining": PART3_MAX,
        }
        self.config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False))

        state = {
            "cells": cells,
            "variant_history": [],
            "milestone_log": [],
            "next_variant": 1,
        }
        self.state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))

        total = len(cells)
        _info(f"Initialized {total} cells ({len(dim_names)}D: "
              f"{' x '.join(str(len(v)) for v in dim_values)})")
        return {"total_cells": total, "dimension_names": dim_names}

    # ── 分配: 5% 容错匹配 ──

    def assign(self, variant_id: str, descriptor: dict) -> str:
        """将变体分配到 cell。5% 容错 + 超出范围自动创建 cell。"""
        state = self._read_state()
        config = self._read_config()
        dim_names = config["dim_names"]

        key_parts = []
        for name in dim_names:
            val = descriptor.get(name)
            if val is None:
                key_parts.append("*")
                continue

            str_val = str(val)
            # 尝试容错匹配
            dim_def = next((d for d in config.get("behavior_dims", [])
                           if d["name"] == name), None)
            if dim_def:
                matched = self._fuzzy_match(str_val, dim_def["values"])
                key_parts.append(matched if matched else str_val)
                if matched is None:
                    # 超出范围 → 自动扩展维度值
                    self._extend_dim_values(name, str_val)
            else:
                key_parts.append(str_val)

        cell_key = "+".join(key_parts)

        # 如果 cell 不存在，自动创建
        if cell_key not in state["cells"]:
            state["cells"][cell_key] = {
                "dim_values": dict(zip(dim_names, key_parts)),
                "elite_id": None,
                "elite_score": None,
                "variants": [],
                "anomalies": [],
            }
            self._write_state(state)

        return cell_key

    def _fuzzy_match(self, value: str, candidates: list[str]) -> str | None:
        """数字值的 5% 容错匹配。非数字值精确匹配。"""
        try:
            num_val = float(value)
        except ValueError:
            return value if value in candidates else None

        for c in candidates:
            try:
                num_c = float(c)
            except ValueError:
                continue
            if num_c == 0:
                if abs(num_val) < TOLERANCE:
                    return c
            elif abs(num_val - num_c) / abs(num_c) <= TOLERANCE:
                return c
        return None

    def _extend_dim_values(self, dim_name: str, new_value: str):
        """扩展维度的取值列表 (运行时自动发现新值)。"""
        config = self._read_config()
        for d in config.get("behavior_dims", []):
            if d["name"] == dim_name and new_value not in d["values"]:
                d["values"].append(new_value)
                self.config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False))
                _info(f"Extended dimension '{dim_name}' with new value '{new_value}'")
                # 审计日志
                self._audit("dimension_value_extended",
                           {"dimension": dim_name, "new_value": new_value})
                return

    # ── 记录结果 ──

    def record_result(self, variant_id: str, score: float,
                      descriptor: dict, claim_conditions: dict | None = None) -> dict:
        """记录变体得分，更新精英，检测异常和里程碑。

        claim_conditions: 该变体依赖的 CC 条件 {method_atom_ids, relation_chain, ...}
        """
        state = self._read_state()
        config = self._read_config()

        cell_key = self.assign(variant_id, descriptor)
        cell = state["cells"].get(cell_key)
        if not cell:
            return {"cell_key": cell_key, "error": "cell_not_found"}

        is_new_cell = cell["elite_id"] is None
        is_new_record = False
        is_anomaly = False
        anomaly_reason = ""

        variant_entry = {
            "id": variant_id,
            "score": score,
            "descriptor": descriptor,
            "claim_conditions": claim_conditions or {},
        }
        cell["variants"].append(variant_entry)

        # 更新精英
        if cell["elite_score"] is None or score > cell["elite_score"]:
            old_score = cell["elite_score"]
            cell["elite_id"] = variant_id
            cell["elite_score"] = score
            if not is_new_cell and old_score is not None:
                is_new_record = True
                _info(f"NEW RECORD: {variant_id} in {cell_key}: {old_score:.1f} → {score:.1f}")

        # 异常检测：同 CC 条件下巨大性能差异
        if cell["elite_score"] and score < cell["elite_score"]:
            ratio = (cell["elite_score"] - score) / max(cell["elite_score"], 1)
            if ratio > ANOMALY_RATIO and claim_conditions:
                # 检查是否共享 CC 条件
                for v in cell["variants"]:
                    if v["id"] == cell["elite_id"]:
                        continue
                    if self._same_cc_conditions(v.get("claim_conditions", {}),
                                                claim_conditions):
                        is_anomaly = True
                        anomaly_reason = (
                            f"Same CC conditions but score gap {ratio:.0%}: "
                            f"{cell['elite_id']}={cell['elite_score']:.1f} vs "
                            f"{variant_id}={score:.1f}"
                        )
                        cell["anomalies"].append({
                            "elite_id": cell["elite_id"],
                            "anomaly_id": variant_id,
                            "score_gap": ratio,
                            "reason": anomaly_reason,
                        })
                        _info(f"ANOMALY: {anomaly_reason}")
                        break

        # 历史
        state["variant_history"].append({
            "id": variant_id, "score": score, "cell": cell_key, "descriptor": descriptor,
        })

        self._write_state(state)

        # 里程碑检测
        milestones = self.detect_milestones()

        return {
            "cell_key": cell_key,
            "is_new_cell": is_new_cell,
            "is_new_record": is_new_record,
            "is_anomaly": is_anomaly,
            "anomaly_reason": anomaly_reason,
            "elite_score": cell["elite_score"],
            "milestones_triggered": milestones,
        }

    def _same_cc_conditions(self, cc_a: dict, cc_b: dict) -> bool:
        """判断两个变体是否共享 CC 条件 (同方法家族或共享 CC 先验链)。"""
        if not cc_a or not cc_b:
            return False
        family_a = cc_a.get("method_family") or cc_a.get("method_atom_ids", [])
        family_b = cc_b.get("method_family") or cc_b.get("method_atom_ids", [])
        if isinstance(family_a, list) and isinstance(family_b, list):
            return bool(set(family_a) & set(family_b))
        return family_a == family_b

    # ── 里程碑检测 (6 种事件) ──

    def detect_milestones(self) -> list[dict]:
        """扫描全 Grid，检测 6 种里程碑事件。"""
        state = self._read_state()
        cells = state["cells"]
        milestones = []

        filled = {k: v for k, v in cells.items() if v["elite_id"] is not None}
        empty = {k: v for k, v in cells.items() if v["elite_id"] is None}

        # cell_first_filled: 最新被填充的 cell
        recent = state.get("variant_history", [])[-10:]
        seen_new = set()
        for entry in reversed(recent):
            ck = entry.get("cell", "")
            if ck in filled and ck not in seen_new:
                cell = filled[ck]
                if len(cell.get("variants", [])) == 1:
                    milestones.append({
                        "type": "cell_first_filled",
                        "cell_key": ck,
                        "variant_id": cell["elite_id"],
                        "score": cell["elite_score"],
                    })
                    seen_new.add(ck)

        # cell_record_broken: 最近的记录刷新
        for ck, cell in filled.items():
            variants = cell.get("variants", [])
            if len(variants) >= 2 and variants[-1].get("id") == cell.get("elite_id"):
                scores = [v["score"] for v in variants]
                if len(scores) >= 2 and scores[-1] > max(scores[:-1]):
                    milestones.append({
                        "type": "cell_record_broken",
                        "cell_key": ck,
                        "variant_id": cell["elite_id"],
                        "old_score": max(scores[:-1]),
                        "new_score": scores[-1],
                    })

        # region_empty: 连续 3+ 空 cell
        empty_keys = sorted(empty.keys())
        for i in range(len(empty_keys) - 2):
            if (self._adjacent(empty_keys[i], empty_keys[i+1]) and
                    self._adjacent(empty_keys[i+1], empty_keys[i+2])):
                milestones.append({
                    "type": "region_empty",
                    "cells": empty_keys[i:i+3],
                    "count": 3,
                })
                break

        # region_saturated: 连续 5+ cell 被填充且分数标准差 < 5%
        filled_keys = sorted(filled.keys())
        for i in range(len(filled_keys) - 4):
            window = filled_keys[i:i+5]
            scores = [filled[k]["elite_score"] for k in window if filled[k]["elite_score"]]
            if len(scores) == 5:
                mean_s = sum(scores) / 5
                if mean_s > 0:
                    std_s = (sum((s - mean_s)**2 for s in scores) / 5) ** 0.5
                    if std_s / mean_s < 0.05:
                        milestones.append({
                            "type": "region_saturated",
                            "cells": window,
                            "mean_score": round(mean_s, 1),
                        })
                        break

        # dimension_correlated: 某维度值与高分强相关
        config = self._read_config()
        dim_names = config.get("dim_names", [])
        for dim_name in dim_names:
            by_value: dict[str, list[float]] = {}
            for ck, cell in filled.items():
                dv = cell.get("dim_values", {}).get(dim_name)
                if dv and cell["elite_score"]:
                    by_value.setdefault(str(dv), []).append(cell["elite_score"])
            if len(by_value) >= 2:
                means = {v: sum(s)/len(s) for v, s in by_value.items() if s}
                if len(means) >= 2:
                    best_val = max(means, key=means.get)
                    worst_val = min(means, key=means.get)
                    if means[best_val] > 0 and (means[best_val] - means[worst_val]) / means[best_val] > 0.3:
                        milestones.append({
                            "type": "dimension_correlated",
                            "dimension": dim_name,
                            "best_value": best_val,
                            "best_mean": round(means[best_val], 1),
                            "worst_value": worst_val,
                            "worst_mean": round(means[worst_val], 1),
                        })

        # anomaly_detected: 任何 cell 有未解决的异常
        for ck, cell in filled.items():
            for anomaly in cell.get("anomalies", []):
                milestones.append({
                    "type": "anomaly_detected",
                    "cell_key": ck,
                    "elite_id": anomaly["elite_id"],
                    "anomaly_id": anomaly["anomaly_id"],
                    "score_gap": anomaly["score_gap"],
                    "reason": anomaly["reason"],
                })

        return milestones

    def _adjacent(self, key_a: str, key_b: str) -> bool:
        """判断两个 cell key 是否在维度空间中相邻 (仅一个维度值不同)。"""
        parts_a = key_a.split("+")
        parts_b = key_b.split("+")
        if len(parts_a) != len(parts_b):
            return False
        diffs = sum(1 for a, b in zip(parts_a, parts_b) if a != b)
        return diffs == 1

    # ── 查询 ──

    def get_cell(self, cell_key: str) -> dict | None:
        state = self._read_state()
        return state["cells"].get(cell_key)

    def get_all_cells(self) -> dict[str, dict]:
        return self._read_state()["cells"]

    def get_empty_cells(self) -> list[str]:
        state = self._read_state()
        return [k for k, v in state["cells"].items() if v["elite_id"] is None]

    def get_anomaly_cells(self) -> list[dict]:
        """返回有异常标记的 cell。"""
        state = self._read_state()
        results = []
        for ck, cell in state["cells"].items():
            if cell.get("anomalies"):
                results.append({
                    "cell_key": ck,
                    "elite_id": cell["elite_id"],
                    "elite_score": cell["elite_score"],
                    "anomalies": cell["anomalies"],
                })
        return results

    def get_elites(self) -> list[dict]:
        state = self._read_state()
        results = []
        for ck, cell in state["cells"].items():
            if cell["elite_id"] is not None:
                results.append({
                    "cell_key": ck,
                    "dim_values": cell["dim_values"],
                    "variant_id": cell["elite_id"],
                    "score": cell["elite_score"],
                    "variant_count": len(cell.get("variants", [])),
                })
        return sorted(results, key=lambda x: x["score"], reverse=True)

    def get_heatmap_data(self) -> dict:
        state = self._read_state()
        config = self._read_config()
        return {
            "dim_names": config.get("dim_names", []),
            "behavior_dims": config.get("behavior_dims", []),
            "cells": {k: {"elite_score": v["elite_score"], "elite_id": v["elite_id"],
                          "variant_count": len(v.get("variants", [])),
                          "dim_values": v["dim_values"]}
                      for k, v in state["cells"].items()},
            "coverage": {
                "total": len(state["cells"]),
                "filled": sum(1 for v in state["cells"].values() if v["elite_id"] is not None),
            },
        }

    # ── 维度扩展 (Part3) ──

    def propose_dimension(self, name: str, values: list[str], source: str = "auto") -> dict:
        """提议新维度。需用户确认。"""
        config = self._read_config()
        remaining = config.get("part3_slots_remaining", 0)
        if remaining <= 0:
            return {"proposed": False, "reason": "part3_slots_exhausted",
                    "slots_remaining": 0}
        existing = any(d["name"] == name for d in config.get("behavior_dims", []))
        if existing:
            return {"proposed": False, "reason": "dimension_already_exists"}
        return {
            "proposed": True,
            "dimension": {"name": name, "values": values, "source": source},
            "requires_confirmation": True,
            "slots_remaining": remaining,
        }

    def add_dimension(self, name: str, values: list[str]) -> bool:
        """确认新增维度，重新计算所有已有变体的 cell 分配。"""
        config = self._read_config()
        remaining = config.get("part3_slots_remaining", 0)
        if remaining <= 0:
            return False

        existing = any(d["name"] == name for d in config.get("behavior_dims", []))
        if existing:
            return False

        config["behavior_dims"].append({
            "name": name, "values": values, "source": "auto",
        })
        config["dim_names"].append(name)
        config["part3_slots_remaining"] = remaining - 1

        # 重建所有 cell
        state = self._read_state()
        old_cells = state["cells"]
        dim_names = config["dim_names"]
        dim_values = [d["values"] for d in config["behavior_dims"]]

        new_cells = {}
        for combo in _itertools_product(*dim_values):
            key = "+".join(combo)
            new_cells[key] = {
                "dim_values": dict(zip(dim_names, combo)),
                "elite_id": None,
                "elite_score": None,
                "variants": [],
                "anomalies": [],
            }

        # 重新分配已有变体
        for old_key, old_cell in old_cells.items():
            for v in old_cell.get("variants", []):
                desc = v.get("descriptor", {})
                desc[name] = "*"  # 旧变体在新维度上标记为通配
                # 找到最佳匹配 cell
                best_key = self._best_match_key(desc, new_cells, config)
                if best_key and best_key in new_cells:
                    nc = new_cells[best_key]
                    nc["variants"].append(v)
                    if nc["elite_score"] is None or v["score"] > nc["elite_score"]:
                        nc["elite_id"] = v["id"]
                        nc["elite_score"] = v["score"]

        state["cells"] = new_cells

        self.config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False))
        self._write_state(state)
        self._audit("dimension_added", {"name": name, "values": values,
                                         "slots_remaining": remaining - 1})
        _info(f"Added Part3 dimension '{name}'. Cells rebuilt. "
              f"{remaining - 1} slots remaining.")
        return True

    def _best_match_key(self, descriptor: dict, cells: dict, config: dict) -> str | None:
        """在 cell 字典中寻找最佳匹配 key。"""
        dim_names = config.get("dim_names", [])
        key_parts = []
        for name in dim_names:
            val = descriptor.get(name, "*")
            if val == "*":
                # 通配符：匹配该维度第一个值
                dim_def = next((d for d in config.get("behavior_dims", [])
                               if d["name"] == name), None)
                key_parts.append(dim_def["values"][0] if dim_def else "*")
            else:
                key_parts.append(str(val))
        candidate = "+".join(key_parts)
        return candidate if candidate in cells else None

    # ── 内部读写 ──

    def get_discovery_index(self) -> dict:
        """返回 Grid 结构索引，供渐进式发现用。

        Agent 看到：哪些维度存在、空cell区域模式、饱和区域、异常计数。
        不直接看到完整 cell 数据，必须通过 pes_cli 查询。
        """
        state = self._read_state()
        config = self._read_config()
        cells = state.get("cells", {})

        filled = {k: v for k, v in cells.items() if v.get("elite_id") is not None}
        empty = {k: v for k, v in cells.items() if not v.get("elite_id")}

        dim_names = config.get("dim_names", [])
        behavior_dims = config.get("behavior_dims", [])
        dim_values = {d["name"]: d.get("values", []) for d in behavior_dims} if behavior_dims else {}

        empty_regions = self._find_empty_regions(empty, dim_names)
        saturated_regions = self._find_saturated_regions(filled)
        anomaly_count = sum(len(c.get("anomalies", [])) for c in cells.values())

        return {
            "dimension_names": dim_names,
            "dimension_values": dim_values,
            "total_cells": len(cells),
            "filled_cells": len(filled),
            "empty_cells": len(empty),
            "empty_regions": empty_regions,
            "saturated_regions": saturated_regions,
            "anomaly_count": anomaly_count,
            "part3_slots_remaining": config.get("part3_slots_remaining", 3),
            "milestone_count": len(state.get("milestone_log", [])),
            "next_variant": state.get("next_variant", 1),
        }

    def _find_empty_regions(self, empty: dict, dim_names: list[str]) -> list[dict]:
        """找相邻空cell区域（>=3个连续空cell共享某维度值）。"""
        if len(empty) < 3:
            return []

        # 按维度值分组空cell
        dim_value_counts: dict[str, dict[str, int]] = {}
        for dim in dim_names:
            dim_value_counts[dim] = {}
        for cell_key in empty:
            if cell_key.count("+") != len(dim_names) - 1:
                continue
            parts = cell_key.split("+")
            for i, dim in enumerate(dim_names):
                if i < len(parts):
                    val = parts[i]
                    dim_value_counts[dim][val] = dim_value_counts[dim].get(val, 0) + 1

        regions = []
        for dim in dim_names:
            for val, count in dim_value_counts[dim].items():
                if count >= 3:
                    # 找到具有此 dim=val 的 cell keys
                    matching_cells = [k for k in empty
                                     if k.count("+") == len(dim_names) - 1
                                     and k.split("+")[dim_names.index(dim)] == val]
                    regions.append({
                        "dimension": dim,
                        "value": val,
                        "empty_count": count,
                        "cell_keys_sample": matching_cells[:5],
                        "description": f"{count} empty cells share {dim}={val} — an unexplored behavioral region",
                    })
        return sorted(regions, key=lambda r: r["empty_count"], reverse=True)

    def _find_saturated_regions(self, filled: dict) -> list[dict]:
        """找饱和区域（>=3个filled cells共享某维度值，分数方差低）。"""
        if len(filled) < 3:
            return []

        state = self._read_state()
        cells = state.get("cells", {})
        config = self._read_config()
        dim_names = config.get("dim_names", [])

        dim_value_filled: dict[str, dict[str, list[float]]] = {}
        for dim in dim_names:
            dim_value_filled[dim] = {}
        for cell_key, cell_data in filled.items():
            parts = cell_key.split("+")
            for i, dim in enumerate(dim_names):
                if i < len(parts):
                    val = parts[i]
                    if val not in dim_value_filled[dim]:
                        dim_value_filled[dim][val] = []
                    score = cell_data.get("elite_score")
                    if score is not None:
                        dim_value_filled[dim][val].append(score)

        regions = []
        for dim in dim_names:
            for val, scores in dim_value_filled[dim].items():
                if len(scores) >= 3:
                    mean_score = sum(scores) / len(scores)
                    variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)
                    if variance < 0.1 * abs(mean_score) + 1e-6:  # Low variance → saturated
                        regions.append({
                            "dimension": dim,
                            "value": val,
                            "filled_count": len(scores),
                            "mean_score": round(mean_score, 2),
                            "score_variance": round(variance, 4),
                            "description": f"{len(scores)} filled cells share {dim}={val} with low score variance — saturated region",
                        })
        return sorted(regions, key=lambda r: r["filled_count"], reverse=True)

    def _read_state(self) -> dict:
        if not self.state_path.exists():
            return {"cells": {}, "variant_history": [], "milestone_log": [], "next_variant": 1}
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _write_state(self, state: dict):
        self.state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))

    def _read_config(self) -> dict:
        if not self.config_path.exists():
            return {"dim_names": [], "behavior_dims": [], "part3_slots_remaining": PART3_MAX}
        return json.loads(self.config_path.read_text(encoding="utf-8"))

    def _audit(self, event: str, data: dict):
        """记录审计日志。"""
        entry = {"timestamp": __import__("time").time(), "event": event, "data": data}
        with open(self.audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ── 状态展示 ──

    def status(self):
        """打印 Grid 状态。"""
        state = self._read_state()
        cells = state["cells"]
        filled = {k: v for k, v in cells.items() if v["elite_id"] is not None}
        total = len(cells)
        n_filled = len(filled)

        _info(f"Archive: {n_filled}/{total} cells filled "
              f"({100*n_filled/max(total,1):.0f}%)")
        _info(f"Total variants: {len(state.get('variant_history', []))}")
        _info(f"Anomalies: {sum(len(c.get('anomalies', [])) for c in cells.values())}")

        if filled:
            scores = [v["elite_score"] for v in filled.values()]
            _info(f"Score range: {min(scores):.1f} — {max(scores):.1f} "
                  f"(mean={sum(scores)/len(scores):.1f})")
            _info("\nTop cells:")
            for k, v in sorted(filled.items(), key=lambda x: x[1]["elite_score"],
                               reverse=True)[:5]:
                _info(f"  {k}: {v['elite_id']} (score={v['elite_score']})")

    def heatmap(self):
        """ASCII 热力图。"""
        state = self._read_state()
        config = self._read_config()
        cells = state["cells"]
        dim_names = config.get("dim_names", [])

        if len(dim_names) < 2:
            for k, v in cells.items():
                score = f"{v['elite_score']:.0f}" if v["elite_score"] is not None else "---"
                _info(f"  {k}: {score}")
            return

        dim_a_name = dim_names[0]
        dim_b_name = dim_names[1]
        dim_a_values = config["behavior_dims"][0]["values"]
        dim_b_values = config["behavior_dims"][1]["values"]

        cell_w = max(max(len(str(v)) for v in dim_a_values), len(dim_a_name)) + 2
        header = " " * (len(dim_b_name) + 3)
        for bv in dim_b_values:
            header += str(bv).center(cell_w)
        _info(header)

        for av in dim_a_values:
            row = f"{av:>12} |"
            for bv in dim_b_values:
                key = f"{av}+{bv}"
                if len(dim_names) > 2:
                    matching = {k: v for k, v in cells.items() if k.startswith(f"{av}+{bv}")}
                    scores = [v["elite_score"] for v in matching.values()
                             if v["elite_score"] is not None]
                    row += f"{max(scores):.0f}".center(cell_w) if scores else "---".center(cell_w)
                else:
                    cell = cells.get(key, {})
                    score = cell.get("elite_score")
                    row += f"{score:.0f}".center(cell_w) if score is not None else "---".center(cell_w)
            _info(row)

        filled = sum(1 for v in cells.values() if v.get("elite_id"))
        _info(f"\nCoverage: {filled}/{len(cells)} ({100*filled/max(len(cells),1):.0f}%)")

    def export_best(self):
        """导出最佳变体。"""
        state = self._read_state()
        cells = state["cells"]
        filled = {k: v for k, v in cells.items() if v["elite_id"] is not None}
        if not filled:
            _info("No results recorded.")
            return

        export_path = self.dir / "best_variants.json"
        export = []
        for k, v in sorted(filled.items(), key=lambda x: x[1]["elite_score"], reverse=True):
            export.append({
                "cell": k,
                "dims": v["dim_values"],
                "variant_id": v["elite_id"],
                "score": v["elite_score"],
                "variant_count": len(v.get("variants", [])),
                "anomaly_count": len(v.get("anomalies", [])),
            })
        export_path.write_text(json.dumps(export, indent=2, ensure_ascii=False))
        _info(f"Exported {len(export)} best variants to {export_path}")


# ── CLI ──

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Cell Grid: 多维索引 + 异常检测")
    sub = parser.add_subparsers(dest="command")

    init_p = sub.add_parser("init", help="初始化 Grid")
    init_p.add_argument("--config", required=True, help="JSON config 或 inline JSON")

    rec = sub.add_parser("record-result", help="记录变体结果")
    rec.add_argument("--id", required=True)
    rec.add_argument("--score", type=float, required=True)
    rec.add_argument("--descriptor", required=True, help="JSON descriptor dict")

    sub.add_parser("status", help="Grid 状态")
    sub.add_parser("heatmap", help="ASCII 热力图")
    sub.add_parser("export-best", help="导出精英变体")

    anomalies_p = sub.add_parser("anomalies", help="列出异常 cell")

    for p in [init_p, rec, anomalies_p]:
        p.add_argument("--dir", default="evolve_archive")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    grid = CellGrid(getattr(args, "dir", "evolve_archive"))

    if args.command == "init":
        config_path = Path(args.config)
        if config_path.exists():
            config = json.loads(config_path.read_text(encoding="utf-8"))
        else:
            config = json.loads(args.config)
        dims = config.get("behavior_dims", config.get("dimensions", []))
        grid.init(dims)

    elif args.command == "record-result":
        descriptor = json.loads(args.descriptor)
        result = grid.record_result(args.id, args.score, descriptor)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == "status":
        grid.status()

    elif args.command == "heatmap":
        grid.heatmap()

    elif args.command == "export-best":
        grid.export_best()

    elif args.command == "anomalies":
        for a in grid.get_anomaly_cells():
            print(json.dumps(a, indent=2, ensure_ascii=False))
