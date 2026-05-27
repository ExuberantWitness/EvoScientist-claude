"""CC Grounding Pipeline — raw data → discrete form → ontology alignment → CC.

Called at 3 specific write points:
  1. Intake: after baseline CodeGraph parsing
  2. After literature survey (W3 Research)
  3. After experiment results (W5 Analyze)

Reads are free; writes go through ontology_schema_alignment gatekeeper.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Awaitable

import numpy as np

logger = logging.getLogger(__name__)


class CCGrounding:
    """Grounding pipeline: decompose → align → write to CC + RND KB."""

    def __init__(self, cc, rnd_evaluator=None, llm_call=None):
        self._cc = cc
        self._rnd = rnd_evaluator
        self._llm_call = llm_call  # async fn(prompt) -> str

    # ═══════════════════════════════════════════════════════════════
    # Enrichment: CodeGraph
    # ═══════════════════════════════════════════════════════════════

    def enrich_from_codegraph(
        self, code_dir: Path, algo_names: list[str] | None = None,
    ) -> dict:
        """CodeGraph → discrete entities → ontology alignment → CC atoms.

        Returns: {algo_name: atom_count}
        """
        from claim_chain.codegraph import extract_structure, structure_to_cc_atoms, structure_summary
        from claim_chain.ontology.alignment import get_gatekeeper

        gatekeeper = get_gatekeeper()

        result = structure_to_cc_atoms(code_dir, algo_names=algo_names, cc=self._cc)
        summary = structure_summary(code_dir)

        # Validate all new atoms through gatekeeper
        atoms = self._cc.get_atoms()
        gatekeeper.register_atoms(atoms)
        errors = []
        for a in atoms:
            vr = gatekeeper.validate_atom(a)
            if vr.errors:
                errors.extend(vr.errors)

        if errors:
            logger.warning(f"Ontology validation errors: {errors[:5]}")

        # Embed into RND KB
        if self._rnd and summary:
            self._rnd.add(summary, source_type="code")

        counts = {algo: len(comps) for algo, comps in result.items()}
        logger.info(f"CodeGraph enrichment: {counts}")
        return counts

    # ═══════════════════════════════════════════════════════════════
    # Enrichment: Literature
    # ═══════════════════════════════════════════════════════════════

    async def enrich_from_literature(
        self, papers: list[dict],
    ) -> dict:
        """Literature → BGE-M3 coarse filter → LLM fine entity/relation extraction → CC.

        Each paper dict: {title, abstract, url, source}

        Two-stage extraction:
          Stage 1: BGE-M3 embed papers, filter relevant ones vs existing CC
          Stage 2: LLM extracts entities + relations → align to CC schema → write

        Returns: {papers_processed, entities_extracted, relations_created}
        """
        if not papers:
            return {"papers_processed": 0, "entities_extracted": 0, "relations_created": 0}

        # Stage 1: BGE-M3 coarse filter
        relevant = papers
        if self._rnd and len(papers) > 20:
            relevant = self._coarse_filter_papers(papers)

        # Stage 2: LLM fine extraction
        entities_created = 0
        relations_created = 0

        for paper in relevant[:10]:  # process top 10 per call
            try:
                if self._llm_call:
                    extracted = await self._llm_extract_entities(paper)
                else:
                    extracted = self._rule_based_extract(paper)

                # Align to CC schema and write
                e_count, r_count = self._write_extracted_to_cc(extracted, paper)
                entities_created += e_count
                relations_created += r_count

                # Embed into RND KB
                if self._rnd:
                    text = f"{paper.get('title','')}: {paper.get('abstract','')[:500]}"
                    self._rnd.add(text, source_type="literature")

            except Exception as e:
                logger.warning(f"Literature enrichment failed for {paper.get('title','')[:50]}: {e}")

        return {
            "papers_processed": len(relevant[:10]),
            "entities_extracted": entities_created,
            "relations_created": relations_created,
        }

    # ═══════════════════════════════════════════════════════════════
    # Enrichment: Experiment Results
    # ═══════════════════════════════════════════════════════════════

    def enrich_from_experiments(self, results: dict) -> dict:
        """Experiment results → CC atoms + relations.

        Args:
            results: {algo_name: {score_mean, score_std, status, seeds, ...}}

        Creates verification atoms + validates/contradicts relations.
        """
        from claim_chain.ontology.alignment import get_gatekeeper
        gatekeeper = get_gatekeeper()

        created_atoms = 0
        created_relations = 0

        for algo, info in results.items():
            status = info.get("status", "tested")
            score = info.get("score_mean", 0)

            # Create verification atom
            atom = {
                "type": "verification",
                "title": f"Experiment: {algo}",
                "content": json.dumps(info),
                "tags": ["experiment", algo, status],
                "evidence_level": "experiment",
                "status": "active",
            }
            vr = gatekeeper.validate_atom(atom)
            if vr.valid:
                try:
                    self._cc.add_atom(**{k: v for k, v in atom.items()
                                        if k != "status"})
                    created_atoms += 1
                except Exception as e:
                    logger.warning(f"Add experiment atom {algo}: {e}")

        # Embed into RND KB
        if self._rnd:
            for algo, info in results.items():
                text = f"{algo}: score={info.get('score_mean',0)}±{info.get('score_std',0)}, status={info.get('status','?')}"
                self._rnd.add(text, source_type="experiment")

        return {
            "experiments_processed": len(results),
            "atoms_created": created_atoms,
            "relations_created": created_relations,
        }

    # ═══════════════════════════════════════════════════════════════
    # CC Maintenance
    # ═══════════════════════════════════════════════════════════════

    def maintain(self) -> dict:
        """Pre-read CC maintenance: dedup, validate, align.

        Returns maintenance report.
        """
        from claim_chain.ontology.alignment import get_gatekeeper
        gatekeeper = get_gatekeeper()

        atoms = self._cc.get_atoms(limit=500)
        relations = self._cc.get_relations(limit=1000)

        # Register atoms for type lookup
        gatekeeper.register_atoms(atoms)

        # Validate all atoms
        atom_errors = []
        for a in atoms:
            vr = gatekeeper.validate_atom(a)
            if vr.errors:
                atom_errors.append({"atom_id": a.get("id"), "errors": vr.errors})

        # Validate all relations
        rel_errors = []
        for r in relations:
            vr = gatekeeper.validate_relation(
                str(r.get("source_id", "")),
                str(r.get("target_id", "")),
                r.get("type", ""),
            )
            if vr.errors:
                rel_errors.append({"relation_id": r.get("id"), "errors": vr.errors})

        # Find orphan atoms
        connected = set()
        for r in relations:
            connected.add(str(r.get("source_id", "")))
            connected.add(str(r.get("target_id", "")))
        orphans = [a.get("id") for a in atoms if str(a.get("id")) not in connected]

        # Three-layer alignment check
        comp_atoms = [a for a in atoms if a.get("type") == "component"]
        lit_atoms = [a for a in atoms if a.get("type") == "fact"]
        method_atoms = [a for a in atoms if a.get("type") == "method"]
        alignment = gatekeeper.check_three_layer_alignment(
            comp_atoms, lit_atoms, method_atoms, relations,
        )

        report = {
            "total_atoms": len(atoms),
            "total_relations": len(relations),
            "atom_validation_errors": len(atom_errors),
            "relation_validation_errors": len(rel_errors),
            "orphan_atoms": len(orphans),
            "alignment_warnings": len(alignment.warnings),
            "alignment_errors": len(alignment.errors),
        }

        if atom_errors:
            logger.warning(f"Atom validation: {len(atom_errors)} errors")
        if alignment.warnings:
            logger.info(f"Alignment: {len(alignment.warnings)} warnings")

        return report

    # ═══════════════════════════════════════════════════════════════
    # Internal helpers
    # ═══════════════════════════════════════════════════════════════

    def _coarse_filter_papers(self, papers: list[dict]) -> list[dict]:
        """BGE-M3 coarse filter: keep papers semantically relevant to existing CC."""
        # Get existing CC text
        atoms = self._cc.get_atoms(limit=100)
        cc_texts = [
            f"{a.get('title','')}: {a.get('content','')[:300]}"
            for a in atoms if a.get("title")
        ]
        if not cc_texts:
            return papers

        try:
            cc_embs = self._rnd._encode(cc_texts)
            cc_centroid = np.mean(cc_embs, axis=0)
            cc_norm = cc_centroid / (np.linalg.norm(cc_centroid) + 1e-8)
        except Exception:
            return papers

        scored = []
        for p in papers:
            text = f"{p.get('title','')} {p.get('abstract','')[:500]}"
            try:
                emb = self._rnd._encode([text])[0]
                emb_norm = emb / (np.linalg.norm(emb) + 1e-8)
                sim = float(np.dot(cc_norm, emb_norm))
                scored.append((sim, p))
            except Exception:
                scored.append((0.5, p))

        scored.sort(key=lambda x: x[0], reverse=True)
        # Keep top 50% most relevant
        cutoff = max(5, len(scored) // 2)
        return [p for _, p in scored[:cutoff]]

    async def _llm_extract_entities(self, paper: dict) -> dict:
        """LLM extracts entities + relations from a paper."""
        prompt = f"""Extract key scientific entities and their relations from this paper.

## Paper
Title: {paper.get('title', '')}
Abstract: {paper.get('abstract', '')[:1000]}

## Instructions
1. Extract entities: methods, algorithms, components, concepts, datasets
2. Extract relations between entities: uses, improves, compares_to, motivates, validates, contradicts
3. For each entity, classify its type: method, component, or concept

Respond with ONLY a JSON object:
{{
  "entities": [
    {{"name": "...", "type": "method|component|concept", "description": "..."}}
  ],
  "relations": [
    {{"source": "entity_name", "target": "entity_name", "type": "uses|improves|compares_to|motivates|validates|contradicts"}}
  ]
}}"""
        response = await self._llm_call(prompt)
        return self._parse_llm_response(response)

    def _rule_based_extract(self, paper: dict) -> dict:
        """Rule-based fallback: extract capitalized acronyms as entities."""
        import re
        abstract = paper.get("abstract", "")
        # Find ALL-CAPS acronyms (2-8 chars)
        acronyms = re.findall(r'\b[A-Z]{2,8}\b', abstract)
        entities = [
            {"name": a, "type": "method", "description": f"Acronym from {paper.get('title','')}"}
            for a in set(acronyms)[:10]
        ]
        return {"entities": entities, "relations": []}

    def _write_extracted_to_cc(self, extracted: dict, paper: dict) -> tuple[int, int]:
        """Write extracted entities + relations to CC through gatekeeper."""
        from claim_chain.ontology.alignment import get_gatekeeper
        gatekeeper = get_gatekeeper()

        e_count = 0
        r_count = 0

        # Create entity atoms
        entity_id_map = {}
        for ent in extracted.get("entities", []):
            atom_type = ent.get("type", "fact")
            if atom_type == "concept":
                atom_type = "fact"
            elif atom_type not in ("fact", "method", "component"):
                atom_type = "fact"

            atom = {
                "type": atom_type,
                "title": ent.get("name", "Unknown")[:120],
                "content": json.dumps({
                    "description": ent.get("description", ""),
                    "source_paper": paper.get("title", ""),
                }),
                "tags": ["literature", "grounding", atom_type],
                "evidence_level": "literature",
            }

            vr = gatekeeper.validate_atom(atom)
            if vr.valid:
                try:
                    created = self._cc.add_atom(
                        type=atom["type"], title=atom["title"],
                        content=atom["content"], tags=atom["tags"],
                        evidence_level=atom["evidence_level"],
                    )
                    entity_id_map[ent.get("name", "")] = created.get("title", "")
                    e_count += 1
                except Exception:
                    pass

        # Create relations
        for rel in extracted.get("relations", []):
            src = entity_id_map.get(rel.get("source", ""), rel.get("source", ""))
            tgt = entity_id_map.get(rel.get("target", ""), rel.get("target", ""))
            rtype = rel.get("type", "motivates")

            vr = gatekeeper.validate_relation(src, tgt, rtype)
            if vr.valid:
                try:
                    self._cc.add_relation(src, tgt, rtype)
                    r_count += 1
                except Exception:
                    pass

        return e_count, r_count

    @staticmethod
    def _parse_llm_response(response: str) -> dict:
        """Parse LLM JSON response with fallbacks."""
        text = response.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        import re
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        return {"entities": [], "relations": []}
