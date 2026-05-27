"""IslandManager: 变体簇管理。

Island = 同 method_family 下的变体集合。
创建自动，合并需 agent 提议 + 用户确认。
"""

import json
from datetime import datetime
from pathlib import Path


def _load_jsonl(path: Path) -> list[dict]:
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


class IslandManager:
    """变体簇管理。Island = 同 method_family 下的变体集合。"""

    def __init__(self, archive_dir: Path):
        self.islands_dir = Path(archive_dir) / "islands"
        self.islands_dir.mkdir(parents=True, exist_ok=True)
        self._load_islands()

    def _load_islands(self):
        self.islands = []
        for d in sorted(self.islands_dir.iterdir()):
            if d.is_dir():
                meta_path = d / "island_meta.json"
                if meta_path.exists():
                    self.islands.append(json.loads(meta_path.read_text(encoding="utf-8")))

    # ── 分配 (自动创建) ──

    def detect_and_assign(self, variant_id: str, cell_key: str, score: float,
                          dims: dict, method_family: str = "default") -> str:
        """将变体分配到 Island，必要时自动创建新 Island。返回 island_id。"""
        matching = [i for i in self.islands if i.get("method_family") == method_family]

        if not matching:
            return self._create_island(variant_id, cell_key, score, dims, method_family)

        cell_parts = cell_key.split("+")
        dim0 = cell_parts[0] if cell_parts else ""
        for island in matching:
            island_cells = [v.get("cell", "") for v in island.get("variants", [])]
            if any(c.startswith(dim0) for c in island_cells):
                self._add_to_island(island["id"], variant_id, cell_key, score)
                return island["id"]

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
        (island_dir / "island_meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False))
        self.islands.append(meta)
        return island_id

    def _add_to_island(self, island_id: str, variant_id: str, cell_key: str, score: float):
        for island in self.islands:
            if island["id"] == island_id:
                island.setdefault("variants", []).append(
                    {"id": variant_id, "cell": cell_key, "score": score})
                island_dir = self.islands_dir / island_id
                (island_dir / "island_meta.json").write_text(
                    json.dumps(island, indent=2, ensure_ascii=False))
                return

    # ── 合并提议 (Agent 提议 + 用户确认) ──

    def propose_merges(self, claim_chain) -> list[dict]:
        """扫描 CC 中 specializes/derives 关系，发现应合并的 Island。
        ClaimChain 实例作为参数传入 (from tools.claim_chain)。
        """
        relations = claim_chain.get_relations()
        proposals = []
        merge_types = {"specializes", "derives"}
        for r in relations:
            if r["type"] in merge_types:
                src_island = self._find_island_for_atom(r["source_id"])
                tgt_island = self._find_island_for_atom(r["target_id"])
                if src_island and tgt_island and src_island != tgt_island:
                    proposals.append({
                        "island_a": src_island,
                        "island_b": tgt_island,
                        "relation_type": r["type"],
                        "evidence": r.get("evidence", ""),
                        "requires_confirmation": True,
                    })
        return proposals

    def _find_island_for_atom(self, atom_id: int) -> str | None:
        for island in self.islands:
            for v in island.get("variants", []):
                if v.get("claim_atom_id") == atom_id:
                    return island["id"]
        return None

    # ── CC 关联 ──

    def set_claim_atom_id(self, island_id: str, variant_id: str, atom_id: int) -> bool:
        """关联变体与 Claim Chain 方法原子。"""
        for island in self.islands:
            if island["id"] == island_id:
                for v in island.get("variants", []):
                    if v.get("id") == variant_id:
                        v["claim_atom_id"] = atom_id
                        island_dir = self.islands_dir / island_id
                        (island_dir / "island_meta.json").write_text(
                            json.dumps(island, indent=2, ensure_ascii=False))
                        return True
        return False

    # ── 迁移检查 (三重) ──

    def check_migration(self, variant_id: str, target_island_id: str,
                        claim_chain, variant_score: float = 0.0,
                        variant_params: dict | None = None,
                        score_floor_ratio: float = 0.8) -> dict:
        """三重检查变体是否可以从当前 Island 迁移到目标 Island。

        Check 1: CC 验证 — 目标 Island 的 claims 不与迁移者矛盾
        Check 2: 分数阈值 — 迁移者得分 >= 目标 Island 最佳 * score_floor_ratio
        Check 3: 显著改进 — 迁移者得分 > 目标 Island 平均分

        Returns: {approved: bool, checks: [{name, passed, reason}]}
        """
        checks = []
        target_island = next((i for i in self.islands if i["id"] == target_island_id), None)
        if not target_island:
            return {"approved": False, "checks": [{"name": "island_not_found", "passed": False,
                                                    "reason": f"Island {target_island_id} not found"}]}

        target_variants = target_island.get("variants", [])
        target_atom_ids = set()
        atoms = claim_chain.get_atoms()
        for tv in target_variants:
            for a in atoms:
                if a.get("metadata", {}).get("variant_id") == tv.get("id"):
                    target_atom_ids.add(a["id"])

        # Check 1: CC 矛盾检测
        contradicts_found = False
        relations = claim_chain.get_relations()
        params = variant_params or {}
        for r in relations:
            if r["type"] == "contradicts" and r["source_id"] in target_atom_ids:
                target_atom = claim_chain.get_atom(r["source_id"])
                if target_atom:
                    tp = target_atom.get("metadata", {}).get("params", {})
                    if (tp.get("lr") == params.get("lr") and
                            tp.get("hidden") == params.get("hidden")):
                        contradicts_found = True
                        break

        checks.append({
            "name": "claim_chain_validation",
            "passed": not contradicts_found,
            "reason": "目标 Island 的 claims 与迁移者参数不矛盾" if not contradicts_found
                      else "目标 Island 存在与迁移者参数相同的矛盾记录",
        })

        # Check 2: 分数阈值
        target_scores = [v.get("score", 0) for v in target_variants if v.get("score")]
        target_best = max(target_scores) if target_scores else 0
        floor = target_best * score_floor_ratio
        check2_passed = variant_score >= floor
        checks.append({
            "name": "score_threshold",
            "passed": check2_passed,
            "reason": f"score={variant_score:.1f} >= floor={floor:.1f}" if check2_passed
                      else f"score={variant_score:.1f} < floor={floor:.1f}",
        })

        # Check 3: 显著改进
        target_avg = sum(target_scores) / max(len(target_scores), 1)
        check3_passed = variant_score > target_avg
        checks.append({
            "name": "significant_improvement",
            "passed": check3_passed,
            "reason": f"score={variant_score:.1f} > target_avg={target_avg:.1f}" if check3_passed
                      else f"score={variant_score:.1f} <= target_avg={target_avg:.1f}",
        })

        all_passed = all(c["passed"] for c in checks)
        return {"approved": all_passed, "checks": checks}

    # ── 摘要 ──

    def get_island_summary(self) -> list[dict]:
        """返回所有 Island 的摘要。"""
        return [
            {
                "id": i["id"],
                "name": i.get("name", ""),
                "method_family": i.get("method_family", "default"),
                "variant_count": len(i.get("variants", [])),
                "best_score": max((v.get("score", 0) for v in i.get("variants", [])), default=0),
                "centroid_cell": i.get("centroid_cell", ""),
            }
            for i in self.islands
        ]
