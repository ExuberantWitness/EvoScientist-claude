"""Structure Mapping Engine — 跨域关系同构搜索。

核心差异: 比较**关系图结构**而非实体名称。
e.g., "mutation→selection→inheritance" 映射到 "generate→evaluate→retain"
因为它们共享 "3节点 cyclic precedes 循环"，而非因为名称相似。

用法:
    sme = StructureMappingEngine("tools/concept_primitives.json")
    isos = sme.find_isomorphisms("evolutionary_algorithms", "neural_architecture_search")
    isos = sme.find_isomorphisms_across_library(seed_concepts=["entropy", "exploration"])
"""

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


class StructureMappingEngine:
    """关系同构搜索引擎。比较概念域的关系图结构。"""

    def __init__(self, primitives_path: str | Path | None = None):
        """加载概念基元库。"""
        if primitives_path is None:
            primitives_path = Path(__file__).resolve().parent / "concept_primitives.json"
        self.primitives_path = Path(primitives_path)
        self.library: dict = {}
        self._domains: dict[str, dict] = {}
        self._signatures: dict[str, dict] = {}
        self._abstraction_index: dict[str, list[str]] = defaultdict(list)
        if self.primitives_path.exists():
            self._load()

    # ── 加载 ──

    def _load(self):
        self.library = json.loads(self.primitives_path.read_text(encoding="utf-8"))
        self._domains = self.library.get("domains", {})
        for domain_name, domain_data in self._domains.items():
            for concept in domain_data.get("concepts", []):
                abs_name = concept.get("abstraction", "")
                if abs_name:
                    self._abstraction_index[abs_name].append(f"{domain_name}:{concept['name']}")

        # Pre-compute relational signatures
        for domain_name in self._domains:
            self._signatures[domain_name] = self.compute_relational_signature(domain_name)

    # ── 关系签名计算 ──

    def compute_relational_signature(self, domain: str) -> dict[str, dict[str, list[str]]]:
        """计算域的关系图签名。

        对域中每个 concept，提取 {relation_type: [neighbor_concepts]} 映射。
        SME 比较这些签名而非概念名称。

        返回: {concept_name: {relation_type: [target_names]}}
        """
        concepts = self._domains.get(domain, {}).get("concepts", [])
        signature = {}
        for concept in concepts:
            name = concept["name"]
            rel_map: dict[str, list[str]] = defaultdict(list)
            for rel in concept.get("relations", []):
                rel_map[rel["type"]].append(rel["target"])
            signature[name] = dict(rel_map)
        return signature

    # ── 同构搜索 ──

    def find_isomorphisms(
        self, source_domain: str, target_domain: str,
        min_similarity: float = 0.5
    ) -> list[dict]:
        """在两个 domain 之间查找结构同构。

        比较 source 和 target 的概念关系签名，
        找到共享相同关系类型模式的概念对/组。

        返回: [{
            "source_pattern": ["mutation", "selection", "inheritance"],
            "target_pattern": ["architecture_generation", "performance_evaluation", "weight_inheritance"],
            "isomorphic_relation_chain": "precedes→precedes→precedes",
            "confidence": 0.85,
            "type": "cyclic_3node",
            "interpretation": "Both are 3-node cyclic precedes chains"
        }]
        """
        if source_domain not in self._signatures:
            return []
        if target_domain not in self._signatures:
            return []

        src_sig = self._signatures[source_domain]
        tgt_sig = self._signatures[target_domain]

        results = []

        # Strategy 1: Compare pre-computed signature_cycles
        src_domain_data = self._domains.get(source_domain, {})
        tgt_domain_data = self._domains.get(target_domain, {})
        src_cycles = src_domain_data.get("signature_cycles", [])
        tgt_cycles = tgt_domain_data.get("signature_cycles", [])

        for sc in src_cycles:
            for tc in tgt_cycles:
                # Match by cycle type and relation chain
                if sc.get("type") == tc.get("type") or sc.get("relation_chain") == tc.get("relation_chain"):
                    sim = self._cycle_structural_similarity(sc, tc)
                    if sim >= min_similarity:
                        results.append({
                            "source_pattern": sc["pattern"],
                            "target_pattern": tc["pattern"],
                            "isomorphic_relation_chain": sc.get("relation_chain", ""),
                            "confidence": round(sim, 4),
                            "type": sc.get("type", "structural"),
                            "source_cycle_name": sc.get("name", ""),
                            "target_cycle_name": tc.get("name", ""),
                            "interpretation": self._generate_interpretation(sc, tc, source_domain, target_domain),
                        })

        # Strategy 2: Cross-domain concept-level isomorphic pairs
        for src_name, src_rel_map in src_sig.items():
            for tgt_name, tgt_rel_map in tgt_sig.items():
                sim = self.jaccard_signature_similarity(src_rel_map, tgt_rel_map)
                if sim >= min_similarity:
                    # Check abstraction match
                    src_abstraction = self._get_concept_abstraction(source_domain, src_name)
                    tgt_abstraction = self._get_concept_abstraction(target_domain, tgt_name)
                    results.append({
                        "source_pattern": [src_name],
                        "target_pattern": [tgt_name],
                        "isomorphic_relation_chain": self._describe_shared_relations(src_rel_map, tgt_rel_map),
                        "confidence": round(sim, 4),
                        "type": "concept_pair",
                        "source_abstraction": src_abstraction,
                        "target_abstraction": tgt_abstraction,
                        "shared_abstraction": src_abstraction == tgt_abstraction and src_abstraction or "",
                        "interpretation": f"'{src_name}' and '{tgt_name}' share relational roles: {self._describe_shared_relations(src_rel_map, tgt_rel_map)}",
                    })

        # Deduplicate and sort by confidence
        seen = set()
        unique = []
        for r in sorted(results, key=lambda x: x["confidence"], reverse=True):
            key = (tuple(r["source_pattern"]), tuple(r["target_pattern"]))
            if key not in seen:
                seen.add(key)
                unique.append(r)

        return unique

    def find_isomorphisms_across_library(
        self, seed_concepts: list[str],
        min_similarity: float = 0.5
    ) -> list[dict]:
        """给定 seed concepts (来自 CC atoms 的 tags/标题),
        在整个基元库中搜索同构结构。

        对每个 seed concept:
        1. 匹配基元库中的 abstraction
        2. 找到该 abstraction 所在的所有 domain
        3. 在那些 domain 和其他 domain 之间运行 find_isomorphisms
        """
        all_results = []
        searched_pairs = set()

        # Find which abstractions match the seed concepts
        relevant_domains = set()

        for seed in seed_concepts:
            seed_lower = seed.lower().replace("-", "_").replace(" ", "_")
            for abs_name, concept_refs in self._abstraction_index.items():
                if seed_lower in abs_name or abs_name in seed_lower:
                    for ref in concept_refs:
                        domain = ref.split(":")[0]
                        relevant_domains.add(domain)

        # Also match by concept name directly
        for domain_name, domain_data in self._domains.items():
            for concept in domain_data.get("concepts", []):
                concept_name = concept["name"]
                for seed in seed_concepts:
                    if seed.lower() in concept_name.lower() or concept_name.lower() in seed.lower():
                        relevant_domains.add(domain_name)

        if not relevant_domains:
            relevant_domains = set(self._domains.keys())

        # Search all pairs
        domain_list = sorted(relevant_domains)
        for i, d1 in enumerate(domain_list):
            for d2 in list(self._domains.keys()):
                if d1 == d2:
                    continue
                pair = tuple(sorted([d1, d2]))
                if pair in searched_pairs:
                    continue
                searched_pairs.add(pair)
                isos = self.find_isomorphisms(d1, d2, min_similarity)
                for iso in isos:
                    iso["source_domain"] = d1
                    iso["target_domain"] = d2
                    all_results.append(iso)

        # Also check pre-computed cross_domain_isomorphisms
        for iso in self.library.get("cross_domain_isomorphisms", []):
            for pattern in iso.get("isomorphic_patterns", []):
                if pattern.get("confidence", 0) >= min_similarity:
                    # Check relevance to seeds
                    relevant = any(
                        seed.lower() in iso.get("name", "").lower()
                        for seed in seed_concepts
                    )
                    if relevant or len(seed_concepts) == 0:
                        all_results.append({
                            "source_pattern": pattern["source_pattern"],
                            "target_pattern": pattern["target_pattern"],
                            "isomorphic_relation_chain": pattern.get("relation_chain", ""),
                            "confidence": pattern.get("confidence", 0),
                            "type": pattern.get("type", "cross_domain"),
                            "cross_domain_name": iso.get("name", ""),
                            "source_domain": iso.get("source_domain", ""),
                            "target_domain": iso.get("target_domain", ""),
                            "interpretation": f"Pre-computed isomorphism: {iso.get('name', '')} — {pattern.get('type', '')}",
                        })

        return sorted(all_results, key=lambda x: x["confidence"], reverse=True)

    # ── 相似度计算 ──

    def jaccard_signature_similarity(
        self, sig_a: dict[str, list[str]], sig_b: dict[str, list[str]]
    ) -> float:
        """两个关系签名的 Jaccard 相似度。

        比较关系类型集合和邻居集合的结构重叠。
        """
        # Flatten signatures into relation-type:target pairs
        pairs_a = set()
        pairs_b = set()

        for rel_type, targets in sig_a.items():
            for t in targets:
                pairs_a.add((rel_type, t))
        for rel_type, targets in sig_b.items():
            for t in targets:
                pairs_b.add((rel_type, t))

        if not pairs_a and not pairs_b:
            return 1.0
        if not pairs_a or not pairs_b:
            return 0.0

        intersection = len(pairs_a & pairs_b)
        union = len(pairs_a | pairs_b)
        return intersection / max(union, 1)

    def _cycle_structural_similarity(self, cycle_a: dict, cycle_b: dict) -> float:
        """两个 signature cycle 的结构相似度。"""
        score = 0.0
        max_score = 3.0

        # Same type → +1
        if cycle_a.get("type") == cycle_b.get("type"):
            score += 1.0

        # Same relation chain → +1
        if cycle_a.get("relation_chain") == cycle_b.get("relation_chain"):
            score += 1.0

        # Same number of nodes → +0.5
        if len(cycle_a.get("pattern", [])) == len(cycle_b.get("pattern", [])):
            score += 0.5

        # Both cyclic or both non-cyclic → +0.5
        if ("cyclic" in str(cycle_a.get("type", ""))) == ("cyclic" in str(cycle_b.get("type", ""))):
            score += 0.5

        return score / max_score

    # ── 辅助 ──

    def _get_concept_abstraction(self, domain: str, concept_name: str) -> str:
        for concept in self._domains.get(domain, {}).get("concepts", []):
            if concept["name"] == concept_name:
                return concept.get("abstraction", "")
        return ""

    def _describe_shared_relations(
        self, sig_a: dict[str, list[str]], sig_b: dict[str, list[str]]
    ) -> str:
        shared = set(sig_a.keys()) & set(sig_b.keys())
        if shared:
            return "→".join(sorted(shared)[:3])
        return "no_shared_relations"

    def _generate_interpretation(
        self, sc: dict, tc: dict, src_domain: str, tgt_domain: str
    ) -> str:
        src_name = self._domains.get(src_domain, {}).get("name", src_domain)
        tgt_name = self._domains.get(tgt_domain, {}).get("name", tgt_domain)
        return (
            f"'{sc.get('name', '?')}' in {src_name} is structurally isomorphic to "
            f"'{tc.get('name', '?')}' in {tgt_name}: "
            f"both share a {sc.get('type', 'unknown')} pattern "
            f"({sc.get('relation_chain', '?')})"
        )

    def get_domain_names(self) -> list[str]:
        return sorted(self._domains.keys())

    def get_domain_info(self, domain: str) -> dict | None:
        return self._domains.get(domain)

    def get_abstraction_index(self) -> dict[str, list[str]]:
        return dict(self._abstraction_index)

    def search_concepts_by_abstraction(self, abstraction: str) -> list[str]:
        """通过 abstract role 查找 concepts。"""
        return self._abstraction_index.get(abstraction, [])

    def find_violating_concepts(
        self, boundary_constraint: str
    ) -> list[dict]:
        """找到可以违反给定边界约束的概念。

        例如: boundary_constraint = "requires stochastic_policy"
        找到有 "deterministic" 或 "bypasses" 或 "escapes" 关系的概念。
        """
        violating_concepts = []
        violation_keywords = ["bypasses", "escapes", "replaces", "violates",
                              "relaxes", "circumvents", "approximates",
                              "removes", "eliminates", "breaks"]

        for domain_name, domain_data in self._domains.items():
            for concept in domain_data.get("concepts", []):
                for rel in concept.get("relations", []):
                    if rel["type"] in violation_keywords:
                        if any(kw in boundary_constraint.lower()
                               for kw in [rel["type"], rel["target"].lower()]):
                            violating_concepts.append({
                                "concept": concept["name"],
                                "domain": domain_name,
                                "domain_label": domain_data.get("name", domain_name),
                                "abstraction": concept.get("abstraction", ""),
                                "violation_mechanism": f"{rel['type']} → {rel['target']}",
                            })

        return violating_concepts


# ── 快速测试 ──

if __name__ == "__main__":
    import sys

    sme = StructureMappingEngine()
    print(f"Loaded {len(sme._domains)} domains: {sme.get_domain_names()}")

    # Test: find isomorphisms between evolution and NAS
    isos = sme.find_isomorphisms("evolutionary_algorithms", "neural_architecture_search")
    print(f"\nEvolution ↔ NAS isomorphisms: {len(isos)}")
    for iso in isos[:3]:
        print(f"  {iso['confidence']:.2f} | {iso['source_pattern']} ↔ {iso['target_pattern']}")
        print(f"         {iso['interpretation']}")

    # Test: find across library with seed concepts
    seed = ["entropy", "exploration", "causal"]
    print(f"\nSearching for seeds: {seed}")
    results = sme.find_isomorphisms_across_library(seed)
    print(f"Results: {len(results)}")
    for r in results[:5]:
        print(f"  {r['confidence']:.2f} | {r.get('source_domain','')} ↔ {r.get('target_domain','')}")
        print(f"         {r['source_pattern']} ↔ {r['target_pattern']}")

    # Test: find violating concepts
    print(f"\nViolating concepts for 'requires stochastic_policy':")
    viols = sme.find_violating_concepts("requires stochastic_policy")
    for v in viols[:5]:
        print(f"  {v['domain_label']}: {v['concept']} ({v['violation_mechanism']})")
