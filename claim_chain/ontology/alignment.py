"""Ontology Schema Alignment — independent gatekeeper for Claim Chain.

Palantir-inspired 4-element ontology model:
  Object Type: entity class definitions with strict property schemas
  Link Type: explicit relations with cardinality constraints
  Action Type: operations on the graph (add/modify/merge/deprecate/...)
  Function/Interface: derived properties + cross-type query contracts

All CC writes MUST pass through this gatekeeper. CC itself does no deep validation.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


# ============================================================================
# Object Type Definitions
# ============================================================================

class AtomType(Enum):
    FACT = "fact"
    METHOD = "method"
    THEOREM = "theorem"
    VERIFICATION = "verification"
    COMPONENT = "component"


# Required and optional fields per Object Type
OBJECT_TYPE_SCHEMAS: dict[str, dict] = {
    "fact": {
        "required": ["title", "content"],
        "optional": ["tags", "evidence_level", "metadata", "status"],
    },
    "method": {
        "required": ["title", "content"],
        "optional": ["tags", "evidence_level", "metadata", "status",
                      "hypothesis", "method_sketch"],
    },
    "theorem": {
        "required": ["title", "content"],
        "optional": ["tags", "evidence_level", "metadata", "status"],
    },
    "verification": {
        "required": ["title", "content"],
        "optional": ["tags", "evidence_level", "metadata", "status"],
    },
    "component": {
        "required": ["title", "content"],
        "optional": ["tags", "evidence_level", "metadata", "status",
                      "signature", "file", "line", "kind", "qualified_name"],
    },
}

# Evidence levels
VALID_EVIDENCE_LEVELS = frozenset({"experiment", "literature", "llm_analysis"})


# ============================================================================
# Link Type Definitions
# ============================================================================

class RelationType(Enum):
    MOTIVATES = "motivates"
    DERIVES = "derives"
    VALIDATES = "validates"
    CONTRADICTS = "contradicts"
    IMPLEMENTS = "implements"
    COMPARES_TO = "compares_to"
    CAUSES = "causes"
    BOUNDARY_OF = "boundary_of"
    SPECIALIZES = "specializes"
    DEPENDS_ON = "depends_on"
    BASELINE_FOR = "baseline_for"


# Cardinality: (min_source, max_source), (min_target, max_target)
# None = unlimited
LINK_TYPE_CARDINALITY: dict[str, dict] = {
    "implements":    {"source": (0, None), "target": (1, None)},    # method → M:N components
    "depends_on":    {"source": (0, None), "target": (0, None)},    # M:N
    "motivates":     {"source": (0, None), "target": (0, None)},    # M:N
    "baseline_for":  {"source": (1, 1),    "target": (0, None)},    # 1 fact → N methods
    "validates":     {"source": (0, None), "target": (0, None)},
    "contradicts":   {"source": (0, None), "target": (0, None)},
    "derives":       {"source": (0, None), "target": (0, None)},
    "compares_to":   {"source": (0, None), "target": (0, None)},
    "causes":        {"source": (0, None), "target": (0, None)},
    "boundary_of":   {"source": (0, None), "target": (0, None)},
    "specializes":   {"source": (0, None), "target": (0, None)},
}

# Allowed source→target type pairs for each relation
LINK_TYPE_RULES: dict[str, list[tuple[str, str]]] = {
    "implements":    [("method", "component"), ("fact", "component")],
    "depends_on":    [("component", "component"), ("method", "method"),
                      ("component", "method"), ("method", "component")],
    "motivates":     [("fact", "method"), ("fact", "fact"), ("method", "method")],
    "baseline_for":  [("fact", "method")],
    "validates":     [("fact", "method"), ("method", "method"), ("fact", "fact")],
    "contradicts":   [("fact", "method"), ("method", "method")],
    "derives":       [("method", "method"), ("fact", "method")],
    "compares_to":   [("method", "method"), ("method", "fact")],
    "causes":        [("fact", "fact"), ("method", "method"), ("component", "component")],
    "boundary_of":   [("fact", "method")],
    "specializes":   [("method", "method"), ("component", "component")],
}


# ============================================================================
# Action Type Definitions
# ============================================================================

class ActionType(Enum):
    ADD_ATOM = "add_atom"
    ADD_RELATION = "add_relation"
    MODIFY_ATOM = "modify_atom"
    MERGE_ATOMS = "merge_atoms"
    DEPRECATE_ATOM = "deprecate_atom"
    VALIDATE = "validate"
    LINK = "link"
    UNLINK = "unlink"


# ============================================================================
# Validation Results
# ============================================================================

@dataclass
class ValidationResult:
    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def merge(self, other: "ValidationResult") -> "ValidationResult":
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        if other.errors:
            self.valid = False
        return self


# ============================================================================
# Gatekeeper
# ============================================================================

class OntologyGatekeeper:
    """Independent gatekeeper: all CC writes must pass through validation."""

    def __init__(self):
        self._atom_type_index: dict[str, str] = {}  # atom_id → atom_type

    def register_atoms(self, atoms: list[dict]) -> None:
        """Pre-register existing atoms for type lookup during relation validation."""
        for a in atoms:
            self._atom_type_index[str(a.get("id", a.get("title", "")))] = a.get("type", "?")

    # ── Object Type validation ──

    def validate_atom(self, atom: dict) -> ValidationResult:
        """Validate an atom against its Object Type schema."""
        result = ValidationResult()
        atom_type = atom.get("type", "")

        if atom_type not in OBJECT_TYPE_SCHEMAS:
            result.errors.append(f"Unknown atom type: {atom_type}")
            result.valid = False
            return result

        schema = OBJECT_TYPE_SCHEMAS[atom_type]

        # Check required fields
        for field in schema["required"]:
            if field not in atom or atom[field] is None:
                result.errors.append(
                    f"[{atom_type}] missing required field: {field}"
                )
                result.valid = False

        # Validate evidence_level if present
        evidence = atom.get("evidence_level", "")
        if evidence and evidence not in VALID_EVIDENCE_LEVELS:
            result.errors.append(
                f"[{atom_type}] invalid evidence_level: {evidence}"
            )
            result.valid = False

        # Validate title is non-empty string
        title = atom.get("title", "")
        if not isinstance(title, str) or not title.strip():
            result.errors.append(f"[{atom_type}] title must be non-empty string")
            result.valid = False

        return result

    def suggest_fields(self, atom_type: str) -> dict:
        """Return the schema for a given atom type (for autocomplete/suggestions)."""
        return OBJECT_TYPE_SCHEMAS.get(atom_type, {})

    # ── Link Type validation ──

    def validate_relation(
        self, source_id: str, target_id: str, rel_type: str
    ) -> ValidationResult:
        """Validate a relation against Link Type rules."""
        result = ValidationResult()

        # Check relation type is valid
        valid_types = {r.value for r in RelationType}
        if rel_type not in valid_types:
            result.errors.append(f"Unknown relation type: {rel_type}")
            result.valid = False
            return result

        # Check source→target type compatibility
        source_type = self._atom_type_index.get(source_id, "?")
        target_type = self._atom_type_index.get(target_id, "?")

        if source_type == "?" or target_type == "?":
            result.warnings.append(
                f"Unknown atom type for {source_id}({source_type})→{target_id}({target_type})"
            )
            # Don't reject — allow forward references
        else:
            rules = LINK_TYPE_RULES.get(rel_type, [])
            if rules and (source_type, target_type) not in rules:
                result.errors.append(
                    f"Relation {rel_type} not allowed: "
                    f"{source_type}→{target_type}. Allowed: {rules}"
                )
                result.valid = False

        return result

    def validate_cardinality(
        self, rel_type: str, existing_relations: list[dict], source_id: str = "",
        target_id: str = "",
    ) -> ValidationResult:
        """Check cardinality constraints after adding a relation."""
        result = ValidationResult()
        cardinality = LINK_TYPE_CARDINALITY.get(rel_type)
        if not cardinality:
            return result

        src_card = cardinality["source"]
        tgt_card = cardinality["target"]

        # Count existing relations of this type for source and target
        src_count = sum(
            1 for r in existing_relations
            if r.get("type") == rel_type and r.get("source_id") == source_id
        )
        tgt_count = sum(
            1 for r in existing_relations
            if r.get("type") == rel_type and r.get("target_id") == target_id
        )

        # Check max source cardinality
        max_src = src_card[1]
        if max_src is not None and src_count > max_src:
            result.errors.append(
                f"Cardinality violation: {rel_type} source '{source_id}' "
                f"has {src_count} relations (max {max_src})"
            )
            result.valid = False

        # Check max target cardinality
        max_tgt = tgt_card[1]
        if max_tgt is not None and tgt_count > max_tgt:
            result.errors.append(
                f"Cardinality violation: {rel_type} target '{target_id}' "
                f"has {tgt_count} relations (max {max_tgt})"
            )
            result.valid = False

        return result

    # ── De-duplication ──

    def find_duplicates(
        self, new_atom: dict, existing_atoms: list[dict],
        embeddings: dict[str, np.ndarray] | None = None,
        threshold: float = 0.95,
    ) -> list[dict]:
        """Find near-duplicate atoms using BGE-M3 cosine similarity.

        Args:
            new_atom: proposed atom
            existing_atoms: existing CC atoms to compare against
            embeddings: {atom_id: embedding_vector} if pre-computed
            threshold: cosine similarity above which atoms are considered duplicates

        Returns:
            List of existing atoms that are near-duplicates
        """
        if embeddings is None:
            # Compute BGE-M3 embeddings on-demand
            try:
                from pes_controller.elo.neighborhood import RNDEvaluator
                rnd = RNDEvaluator()
                texts = [json.dumps(new_atom, ensure_ascii=False)] + [
                    json.dumps(a, ensure_ascii=False) for a in existing_atoms
                ]
                embs = rnd._encode(texts)
                embeddings = {str(new_atom.get("title", "")): embs[0]}
                for i, a in enumerate(existing_atoms):
                    embeddings[str(a.get("title", ""))] = embs[i + 1]
            except Exception:
                return []  # BGE-M3 not available, skip dedup

        new_id = str(new_atom.get("id", new_atom.get("title", "")))
        new_emb = embeddings.get(new_id)
        if new_emb is None:
            return []

        duplicates = []
        new_norm = new_emb / (np.linalg.norm(new_emb) + 1e-8)

        for existing in existing_atoms:
            existing_id = str(existing.get("id", ""))
            if existing_id == new_id:
                continue
            existing_emb = embeddings.get(existing_id)
            if existing_emb is None:
                continue

            existing_norm = existing_emb / (np.linalg.norm(existing_emb) + 1e-8)
            similarity = float(np.dot(new_norm, existing_norm))

            if similarity >= threshold:
                duplicates.append({
                    "atom": existing,
                    "similarity": round(similarity, 4),
                })

        return duplicates

    # ── Three-layer alignment (code↔theory↔argument) ──

    def check_three_layer_alignment(
        self, component_atoms: list[dict], literature_atoms: list[dict],
        proposal_atoms: list[dict], relations: list[dict],
    ) -> ValidationResult:
        """Check code↔theory↔argument alignment via component atoms.

        A component atom is "aligned" if:
        - It has a depends_on/implements chain reaching a fact or method atom
        - That atom has a relation from a literature atom (or IS a literature atom)
        """
        result = ValidationResult()

        # Build adjacency
        forward: dict[str, set[str]] = {}
        reverse: dict[str, set[str]] = {}
        for r in relations:
            s, t = str(r.get("source_id", "")), str(r.get("target_id", ""))
            forward.setdefault(s, set()).add(t)
            reverse.setdefault(t, set()).add(s)

        # Relations use titles as keys, not numerical IDs
        comp_ids = {str(c.get("title", c.get("id", ""))) for c in component_atoms}
        anchor_ids = {str(p.get("title", p.get("id", "")))
                      for p in list(proposal_atoms) + list(literature_atoms)}

        for comp_id in comp_ids:
            reachable = self._bfs_reachable(
                comp_id, forward, target_types=anchor_ids, max_depth=3
            )
            if not reachable:
                # Also try reverse direction (component may be target of implements)
                reachable = self._bfs_reachable(
                    comp_id, reverse, target_types=anchor_ids, max_depth=3
                )
            if not reachable:
                result.warnings.append(
                    f"Component '{comp_id}' not connected to any proposal/fact atom"
                )

        return result

    @staticmethod
    def _bfs_reachable(
        start: str, adjacency: dict[str, set[str]],
        target_types: set[str], max_depth: int,
    ) -> set[str]:
        """BFS to find reachable nodes in target_types."""
        from collections import deque
        visited = {start}
        queue = deque([(start, 0)])
        found = set()

        while queue:
            node, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for neighbor in adjacency.get(node, set()):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                if neighbor in target_types:
                    found.add(neighbor)
                queue.append((neighbor, depth + 1))

        return found


# ============================================================================
# Module-level convenience
# ============================================================================

_gatekeeper: OntologyGatekeeper | None = None


def get_gatekeeper() -> OntologyGatekeeper:
    global _gatekeeper
    if _gatekeeper is None:
        _gatekeeper = OntologyGatekeeper()
    return _gatekeeper


def reset_gatekeeper() -> None:
    global _gatekeeper
    _gatekeeper = None


# ============================================================================
# Atom-level merge / dedup engine
# ============================================================================

@dataclass
class MergeGroup:
    """A group of similar atoms that can be merged."""
    base_atom: dict          # the most representative atom (kept)
    members: list[dict]       # other atoms (to be specialized)
    base_name: str            # normalized group name
    avg_similarity: float     # average pairwise similarity
    mechanism_union: list[str]  # all mechanisms in the group
    mechanism_diff: dict      # per-member mechanism differences


def build_merge_groups(
    atoms: list[dict],
    embeddings: dict[str, np.ndarray],
    threshold: float = 0.85,
) -> list[MergeGroup]:
    """Build merge groups from similar atoms across algorithms.

    Groups atoms by normalized name, then by BGE-M3 cosine similarity.
    Returns MergeGroup with base + members + mechanism diffs.
    """
    import re
    from collections import defaultdict

    def norm_name(title: str) -> str:
        """Normalize component name for grouping."""
        name = title.split(".")[-1] if "." in title else title
        return re.sub(r"^(target_|actor_|critic_)", "", name.lower())

    def get_mechs(atom: dict) -> set:
        content = atom.get("content", "{}")
        if isinstance(content, str):
            try: content = json.loads(content)
            except Exception: pass
        mechs = content.get("mechanisms", []) if isinstance(content, dict) else []
        return set(mechs)

    # Step 1: Group by normalized name
    name_groups: dict[str, list[dict]] = defaultdict(list)
    for a in atoms:
        if a.get("type") != "component":
            continue
        name_groups[norm_name(a.get("title", ""))].append(a)

    # Step 2: Within each name group, find cross-algo clusters by BGE-M3
    merge_groups: list[MergeGroup] = []
    for base_name, members in name_groups.items():
        algos = {a["title"].split(".")[0] for a in members}
        if len(algos) < 2:
            continue  # single algo, no merge needed

        if len(members) < 2:
            continue

        # Compute pairwise similarities
        member_ids = [str(a.get("id", a.get("title", ""))) for a in members]
        sims = []
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                e_i = embeddings.get(member_ids[i])
                e_j = embeddings.get(member_ids[j])
                if e_i is None or e_j is None:
                    continue
                sim = float(np.dot(
                    e_i / (np.linalg.norm(e_i) + 1e-8),
                    e_j / (np.linalg.norm(e_j) + 1e-8),
                ))
                sims.append((i, j, sim))

        if not sims:
            continue

        avg_sim = sum(s[2] for s in sims) / len(sims)
        if avg_sim < threshold:
            continue

        # Select base: the member with most shared mechanisms (most "general")
        all_mechs = set()
        for m in members:
            all_mechs |= get_mechs(m)

        best_idx = 0
        best_shared = -1
        for i, m in enumerate(members):
            mechs = get_mechs(m)
            # Prefer members with fewer unique mechanisms (more general)
            unique = len(mechs - all_mechs) + 1
            shared = len(mechs & all_mechs)
            score = shared / unique
            if score > best_shared:
                best_shared = score
                best_idx = i

        # Build mechanism diff per member
        base_mechs = get_mechs(members[best_idx])
        mech_diff = {}
        for i, m in enumerate(members):
            if i == best_idx:
                continue
            m_mechs = get_mechs(m)
            mech_diff[m.get("title", "")] = {
                "added": sorted(m_mechs - base_mechs),
                "removed": sorted(base_mechs - m_mechs),
                "shared": sorted(m_mechs & base_mechs),
            }

        merge_groups.append(MergeGroup(
            base_atom=members[best_idx],
            members=[m for i, m in enumerate(members) if i != best_idx],
            base_name=base_name,
            avg_similarity=round(avg_sim, 4),
            mechanism_union=sorted(all_mechs),
            mechanism_diff=mech_diff,
        ))

    return merge_groups


def apply_merges(
    merge_groups: list[MergeGroup],
    cc,  # ClaimChain instance
) -> dict:
    """Apply merge groups to CC: specialize relations with diff manifests.

    Does NOT delete atoms. Each non-base member gets a `specializes` relation
    to the base atom, with the mechanism diff stored in the relation metadata.

    Returns: {merged_groups: N, relations_created: N, atoms_merged: N}
    """
    created = 0
    for mg in merge_groups:
        base_title = mg.base_atom.get("title", "")
        for member in mg.members:
            member_title = member.get("title", "")
            if member_title == base_title:
                continue
            diff = mg.mechanism_diff.get(member_title, {})
            try:
                cc.add_relation(
                    member_title,
                    base_title,
                    "specializes",
                    evidence=json.dumps({
                        "merge_group": mg.base_name,
                        "avg_similarity": mg.avg_similarity,
                        "mechanism_diff": diff,
                        "base_is_generalized": True,
                    }),
                )
                created += 1
            except Exception:
                pass

    return {
        "merged_groups": len(merge_groups),
        "relations_created": created,
        "atoms_merged": sum(len(mg.members) for mg in merge_groups),
    }
