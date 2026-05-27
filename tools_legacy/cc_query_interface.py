"""CCQueryInterface — structured Claim Chain subgraph retrieval.

Provides cc_query_related/neighbors/gaps for persona agents.
Uses BGE-M3 for semantic search + JSON structured output.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class CCQueryInterface:
    """JSON-structured CC subgraph queries for persona-agent interaction."""

    def __init__(self, cc, rnd_evaluator=None):
        self._cc = cc
        self._rnd = rnd_evaluator  # RNDEvaluator with BGE-M3 model

    # ── Queries ──

    def query_related(self, topic: str, top_k: int = 10) -> dict:
        """Find CC atoms most semantically related to a topic.

        Returns JSON:
          {related_atoms: [{id, type, title, content_preview, tags}],
           summary: "N atoms found across types: ..."}
        """
        atoms = self._cc.get_atoms(limit=500)
        if not atoms or not self._rnd:
            return self._fallback_related(atoms, topic, top_k)

        # BGE-M3 semantic search
        topic_emb = self._rnd._encode([topic])[0]
        scored = []
        for a in atoms:
            text = f"{a.get('title','')}: {a.get('content','')[:300]}"
            try:
                a_emb = self._rnd._encode([text])[0]
                dist = float(1.0 - np.dot(
                    topic_emb / (np.linalg.norm(topic_emb) + 1e-8),
                    a_emb / (np.linalg.norm(a_emb) + 1e-8),
                ))
                scored.append((dist, a))
            except Exception:
                pass

        scored.sort(key=lambda x: x[0])
        top = scored[:top_k]

        related = []
        type_counts: dict[str, int] = {}
        for dist, a in top:
            a_type = a.get("type", "?")
            type_counts[a_type] = type_counts.get(a_type, 0) + 1
            content = a.get("content", "")
            if isinstance(content, str) and len(content) > 200:
                content = content[:200] + "..."
            related.append({
                "id": a.get("id", ""),
                "type": a_type,
                "title": a.get("title", "")[:120],
                "content_preview": str(content)[:200],
                "tags": a.get("tags", []),
                "distance": round(dist, 4),
            })

        return {
            "related_atoms": related,
            "summary": (
                f"Found {len(related)} related atoms: "
                + ", ".join(f"{v} {k}" for k, v in type_counts.items())
            ),
            "topic": topic,
        }

    def query_neighbors(self, atom_id: int | str, depth: int = 1) -> dict:
        """Get the neighborhood subgraph around an atom.

        Returns JSON:
          {center: {id, type, title},
           neighbors: [{id, type, title, relation_type, direction}],
           relations: [{source, target, type}]}
        """
        atoms = self._cc.get_atoms(limit=500)
        relations = self._cc.get_relations(limit=1000)

        atom_id_str = str(atom_id)
        center = None
        atom_map_by_id = {}
        atom_map_by_title = {}
        for a in atoms:
            aid = str(a.get("id", ""))
            title = str(a.get("title", ""))
            atom_map_by_id[aid] = a
            atom_map_by_title[title] = a
            if aid == atom_id_str or title == atom_id_str:
                center = {"id": aid, "type": a.get("type", ""), "title": title}

        if center is None:
            return {"error": f"Atom not found: {atom_id}", "center": None, "neighbors": []}

        center_title = center["title"]

        # Find direct neighbors (relations use titles as source/target keys)
        neighbors = []
        for r in relations:
            src = str(r.get("source_id", ""))
            tgt = str(r.get("target_id", ""))
            rtype = r.get("type", "")

            if src == center_title:
                tgt_atom = atom_map_by_title.get(tgt)
                if tgt_atom:
                    neighbors.append({
                        "id": str(tgt_atom.get("id", "")),
                        "type": tgt_atom.get("type", ""),
                        "title": tgt_atom.get("title", "")[:100],
                        "relation_type": rtype,
                        "direction": "outgoing",
                    })
            elif tgt == center_title:
                src_atom = atom_map_by_title.get(src)
                if src_atom:
                    neighbors.append({
                        "id": str(src_atom.get("id", "")),
                        "type": src_atom.get("type", ""),
                        "title": src_atom.get("title", "")[:100],
                        "relation_type": rtype,
                        "direction": "incoming",
                    })

        return {
            "center": center,
            "neighbors": neighbors,
            "neighbor_count": len(neighbors),
            "relations": [
                {"source": r.get("source_id"), "target": r.get("target_id"),
                 "type": r.get("type")}
                for r in relations
                if str(r.get("source_id")) == center_title
                or str(r.get("target_id")) == center_title
            ],
        }

    def query_gaps(self) -> dict:
        """Identify gaps in the CC graph (missing relation types, orphan atoms).

        Returns JSON:
          {orphan_atoms: [...], missing_relation_types: [...],
           weakly_connected: [...]}
        """
        atoms = self._cc.get_atoms(limit=500)
        relations = self._cc.get_relations(limit=1000)

        connected_ids: set[str] = set()
        for r in relations:
            connected_ids.add(str(r.get("source_id", "")))
            connected_ids.add(str(r.get("target_id", "")))

        # Orphan atoms: no relations
        orphans = []
        for a in atoms:
            aid = str(a.get("id", ""))
            if aid not in connected_ids:
                orphans.append({
                    "id": aid,
                    "type": a.get("type", ""),
                    "title": a.get("title", "")[:100],
                })

        # Missing relation types: types that exist in schema but not in graph
        from ontology_schema_alignment import LINK_TYPE_RULES
        used_types = set(r.get("type", "") for r in relations)
        missing_types = set(LINK_TYPE_RULES.keys()) - used_types

        # Weakly connected: atoms with only 1 relation
        degree: dict[str, int] = {}
        for r in relations:
            src = str(r.get("source_id", ""))
            tgt = str(r.get("target_id", ""))
            degree[src] = degree.get(src, 0) + 1
            degree[tgt] = degree.get(tgt, 0) + 1
        weakly = [
            {"id": aid, "degree": deg}
            for aid, deg in degree.items()
            if deg <= 1 and aid in connected_ids
        ][:20]

        return {
            "orphan_atoms": orphans,
            "orphan_count": len(orphans),
            "missing_relation_types": sorted(missing_types),
            "weakly_connected": weakly,
            "weakly_connected_count": len(weakly),
            "total_atoms": len(atoms),
            "total_relations": len(relations),
        }

    # ── Helpers ──

    def _fallback_related(self, atoms: list[dict], topic: str, top_k: int) -> dict:
        """Fallback without BGE-M3: keyword match."""
        keywords = set(topic.lower().split())
        scored = []
        for a in atoms:
            text = f"{a.get('title','')} {a.get('content','')}".lower()
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scored.append((score, a))
        scored.sort(key=lambda x: x[0], reverse=True)

        related = [
            {"id": a.get("id"), "type": a.get("type"), "title": a.get("title", "")[:100],
             "tags": a.get("tags", []), "match_score": s}
            for s, a in scored[:top_k]
        ]
        return {
            "related_atoms": related,
            "summary": f"Keyword match: {len(related)} atoms (no BGE-M3)",
            "topic": topic,
        }
