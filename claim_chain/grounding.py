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

        # Stage 2: EvidenceCard extraction (LLM → fallback chain)
        entities_created = 0
        relations_created = 0

        for paper in relevant[:10]:  # process top 10 per call
            try:
                extracted = None
                # Tier 1: LLM EvidenceCard extraction
                if self._llm_call:
                    try:
                        extracted = await self._llm_extract_entities(paper)
                    except Exception:
                        logger.warning(f"LLM extraction failed for {paper.get('title','')[:50]}, using fallback")
                        extracted = {}
                # Tier 2: check if LLM returned valid data
                if not extracted or not isinstance(extracted, dict):
                    extracted = self._fallback_evidence(paper)
                elif not extracted.get("method") and not extracted.get("claims"):
                    # LLM returned empty fields → fallback
                    extracted = self._fallback_evidence(paper)

                # Align to CC schema and write
                if extracted and isinstance(extracted, dict):
                    e_count, r_count = self._write_extracted_to_cc(extracted, paper)
                    entities_created += e_count
                    relations_created += r_count

                # Embed into RND KB
                if self._rnd:
                    text = f"{paper.get('title','')}: {paper.get('abstract','')[:500]}"
                    self._rnd.add(text, source_type="literature")

            except Exception as e:
                logger.warning(f"Literature enrichment failed for {paper.get('title','')[:50]}: {e}")
                # Final fallback: still try rule-based extraction
                try:
                    extracted = self._fallback_evidence(paper)
                    e_count, r_count = self._write_extracted_to_cc(extracted, paper)
                    entities_created += e_count
                    relations_created += r_count
                except Exception:
                    pass

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
    # Enrichment: Persona Proposals
    # ═══════════════════════════════════════════════════════════════

    def enrich_from_proposals(self, proposals: list[dict], phase: str = "") -> dict:
        """Persona proposals → ontology-aligned CC method atoms + relations.

        Each proposal dict: {title, hypothesis, method_sketch, source_agent, tags, ...}
        Each proposal MUST go through OntologyGatekeeper before CC write.
        Creates method atoms with "proposal" tag + evidence edges to supporting CC atoms.
        """
        from claim_chain.ontology.alignment import get_gatekeeper
        gatekeeper = get_gatekeeper()

        created_atoms = 0
        created_relations = 0

        for prop in proposals:
            if not isinstance(prop, dict):
                continue
            title = prop.get("title", "")
            if not title:
                continue

            # BGE-M3 dedup: check if this proposal already exists in CC
            atom = {
                "type": "method",
                "title": title[:120],
                "content": json.dumps({
                    "hypothesis": prop.get("hypothesis", ""),
                    "method_sketch": prop.get("method_sketch", ""),
                    "source_agent": prop.get("source_agent", ""),
                    "search_results_summary": prop.get("search_results_summary", ""),
                    "phase": phase,
                }),
                "tags": ["proposal", phase.replace(" ", "_")] + (prop.get("tags", []) or []),
                "evidence_level": "llm_analysis",
            }

            # Validate through gatekeeper
            vr = gatekeeper.validate_atom(atom)
            if not vr.valid:
                logger.warning(f"Proposal '{title[:60]}' failed ontology validation: {vr.errors}")
                continue

            # BGE-M3 dedup: check if similar proposal already in CC
            existing_atoms = self._cc.get_atoms(limit=200)
            existing_dicts = [a if isinstance(a, dict) else (a.to_dict() if hasattr(a, 'to_dict') else {'title': str(a)}) for a in existing_atoms]
            dupes = gatekeeper.find_duplicates(atom, existing_dicts, threshold=0.85)
            if dupes:
                logger.info(f"Proposal '{title[:60]}' dedup: {len(dupes)} similar existing atom(s), skipping")
                continue

            try:
                created = self._cc.add_atom(
                    type=atom["type"], title=atom["title"],
                    content=atom["content"], tags=atom["tags"],
                    evidence_level=atom["evidence_level"],
                )
                proposal_id = created.get("id") if isinstance(created, dict) else getattr(created, "id", None)
                created_atoms += 1

                # Find supporting evidence from existing CC atoms (BGE-M3 or keyword match)
                supporting_ids = prop.get("supporting_evidence_ids", [])
                if not supporting_ids and self._rnd:
                    # Keyword search for related atoms
                    sketch = prop.get("method_sketch", "")[:300]
                    existing = self._cc.get_atoms(limit=100)
                    for a in existing:
                        a_title = str(a.get("title", ""))
                        a_tags = a.get("tags", []) if isinstance(a, list) else []
                        if any(kw.lower() in a_title.lower() for kw in title.lower().split()[:3]):
                            supporting_ids.append(str(a.get("id", "")))

                # Create motivates/inspired_by relations to supporting evidence
                for sid in supporting_ids[:5]:
                    if sid and proposal_id:
                        try:
                            self._cc.add_relation(str(proposal_id), str(sid), "motivates")
                            created_relations += 1
                        except Exception:
                            pass

            except Exception as e:
                logger.warning(f"Add proposal atom '{title[:60]}': {e}")

        # Embed proposals into RND KB
        if self._rnd:
            for prop in proposals[:10]:
                if isinstance(prop, dict) and prop.get("title"):
                    text = f"{prop.get('title','')}: {prop.get('hypothesis','')[:200]} {prop.get('method_sketch','')[:300]}"
                    self._rnd.add(text, source_type="proposal")

        return {
            "atoms_added": created_atoms,
            "relations_added": created_relations,
        }

    def enrich_from_web_search(self, search_results: list[dict]) -> dict:
        """Web search results → CC fact atoms via ontology gatekeeper.

        Each result: {title, content, url, source}
        Uses BGE-M3 dedup against existing CC before writing.
        """
        from claim_chain.ontology.alignment import get_gatekeeper
        gatekeeper = get_gatekeeper()

        created_atoms = 0
        for r in search_results:
            title = r.get("title", "")[:200]
            content = r.get("content", "")[:1000]
            if not title and not content:
                continue
            text = f"{title}\n{content}"
            atom = {
                "type": "fact",
                "title": title if title else content[:120],
                "content": text[:2000],
                "tags": ["literature", "web_search"],
                "evidence_level": "literature",
            }
            vr = gatekeeper.validate_atom(atom)
            if not vr.valid:
                continue
            # BGE-M3 dedup
            existing = self._cc.get_atoms(limit=200)
            existing_dicts = [n if isinstance(n, dict) else (n.to_dict() if hasattr(n, "to_dict") else {"title": str(n)}) for n in existing]
            dupes = gatekeeper.find_duplicates(atom, existing_dicts, threshold=0.85)
            if dupes:
                continue
            try:
                self._cc.add_atom(
                    type=atom["type"], title=atom["title"],
                    content=atom["content"], tags=atom["tags"],
                    evidence_level=atom["evidence_level"],
                )
                created_atoms += 1
            except Exception:
                pass

        return {"atoms_added": created_atoms, "relations_added": 0}

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
        """LLM extracts structured EvidenceCard from a paper.

        EvidenceCard schema (8 fields) maps directly to CC node types:
          task → fact atom    method → method atom    claims → fact atoms + validates edges
          limitations → bottleneck atoms    transferable_ideas → method atoms (tags: proposal,seed)
          metrics/setting → fact atoms (tags: benchmark,protocol)
        """
        prompt = f"""You are extracting structured evidence from a research paper for a Claim Chain knowledge graph.

## Paper
Title: {paper.get('title', '')}
Abstract: {paper.get('abstract', '')[:1500]}

Return exactly one JSON object:
{{
  "task": "specific RL task or problem addressed",
  "method": "main method, algorithm, or training strategy",
  "setting": "datasets, baselines, evaluation protocol",
  "claims": [
    {{"claim": "claim text", "evidence_type": "theoretical|empirical|both", "confidence": "high|medium|low"}}
  ],
  "metrics": ["metric names"],
  "limitations": ["limitations, assumptions, or failure modes"],
  "transferable_ideas": [
    {{"idea": "reusable component or strategy", "type": "module|loss|training|architecture|evaluation"}}
  ],
  "relations_to_known": [
    {{"target": "known method name", "relation": "improves|uses|compares_to|contradicts|generalizes"}}
  ]
}}

## Field → CC Node Mapping
- task → fact atom (tags: ["task"])
- method → method atom (core contribution)
- claims → fact atoms (each claim) + validates edges to method
- limitations → bottleneck atoms
- transferable_ideas → method atoms (tags: ["proposal","seed"])
- metrics/setting → fact atoms (tags: ["benchmark","protocol"])
- relations_to_known → CC edges to existing atoms

Extract only what is explicitly stated. Do not fabricate. Use empty lists for fields with no evidence."""
        response = await self._llm_call(prompt)
        return self._parse_llm_response(response)

    def _fallback_evidence(self, paper: dict) -> dict:
        """Rule-based fallback when LLM extraction fails.

        Produces a valid EvidenceCard-like dict from paper metadata alone,
        using regex patterns for metrics and section heuristics for claims.
        """
        import re
        title = paper.get("title", "")
        abstract = paper.get("abstract", "")

        # Extract ALL-CAPS acronyms as method candidates
        acronyms = re.findall(r'\b[A-Z]{2,8}\b', abstract)
        method_name = acronyms[0] if acronyms else title[:80]

        # Extract metric terms from text
        metric_patterns = [
            r'\baccuracy\b', r'\breward\b', r'\breturn\b', r'\bsuccess rate\b',
            r'\bf1\b', r'\bprecision\b', r'\brecall\b', r'\bsample efficiency\b',
            r'\bregret\b', r'\bcost\b', r'\bwall time\b',
        ]
        text_lower = abstract.lower()
        metrics = sorted(set(
            m.group(0) for pat in metric_patterns
            for m in re.finditer(pat, text_lower)
        ))

        # Sentence-split for claims
        sentences = re.split(r'(?<=[.!?])\s+', abstract)
        claims = [s.strip()[:240] for s in sentences[:3] if len(s) > 30]

        # Extract limitation keywords
        limitation_keywords = ['limitation', 'however', 'future work', 'remains',
                               'challenge', 'drawback', 'does not', 'fail']
        limitations = []
        for s in sentences:
            if any(kw in s.lower() for kw in limitation_keywords):
                limitations.append(s.strip()[:200])
        if not limitations:
            limitations = ["No explicit limitations extracted from available text."]

        return {
            "task": abstract[:200] if abstract else title,
            "method": method_name,
            "setting": paper.get("venue", paper.get("source", "")),
            "claims": [{"claim": c, "evidence_type": "empirical", "confidence": "medium"}
                       for c in claims] if claims else [
                {"claim": f"{title} is relevant to the research domain.",
                 "evidence_type": "empirical", "confidence": "low"}
            ],
            "metrics": metrics,
            "limitations": limitations[:3],
            "transferable_ideas": [
                {"idea": f"Adapt method component from {title}: {method_name}",
                 "type": "module"}
            ],
            "relations_to_known": [],
        }

    def _write_extracted_to_cc(self, extracted: dict, paper: dict) -> tuple[int, int]:
        """Write EvidenceCard fields to CC through gatekeeper.

        Maps EvidenceCard 8-field schema to CC node types + edges:
          task → fact atom    method → method atom    claims → fact atoms + validates
          limitations → bottleneck    transferable_ideas → method atoms (seed)
          metrics/setting → fact atoms (benchmark)    relations_to_known → edges
        """
        from claim_chain.ontology.alignment import get_gatekeeper
        gatekeeper = get_gatekeeper()

        e_count = 0
        r_count = 0
        paper_title = paper.get("title", "")

        # ── 1. Method atom (core contribution) ──
        method_name = extracted.get("method", "")
        method_id = None
        if method_name:
            atom = {
                "type": "method",
                "title": method_name[:120],
                "content": json.dumps({
                    "task": extracted.get("task", ""),
                    "setting": extracted.get("setting", ""),
                    "source_paper": paper_title,
                }),
                "tags": ["literature", "grounding", "method"],
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
                    method_id = created.get("id") if isinstance(created, dict) else getattr(created, "id", None)
                    e_count += 1
                except Exception:
                    pass

        # ── 2. Task atom ──
        task_text = extracted.get("task", "")
        if task_text:
            atom = {
                "type": "fact",
                "title": task_text[:120],
                "content": json.dumps({"task": task_text, "source_paper": paper_title}),
                "tags": ["literature", "task"],
                "evidence_level": "literature",
            }
            vr = gatekeeper.validate_atom(atom)
            if vr.valid:
                try:
                    self._cc.add_atom(type=atom["type"], title=atom["title"],
                                      content=atom["content"], tags=atom["tags"],
                                      evidence_level=atom["evidence_level"])
                    e_count += 1
                except Exception:
                    pass

        # ── 3. Setting/metrics atoms ──
        setting = extracted.get("setting", "")
        if setting:
            atom = {
                "type": "fact",
                "title": f"Setting: {setting[:100]}",
                "content": json.dumps({"setting": setting, "metrics": extracted.get("metrics", []),
                                       "source_paper": paper_title}),
                "tags": ["literature", "benchmark", "protocol"],
                "evidence_level": "literature",
            }
            vr = gatekeeper.validate_atom(atom)
            if vr.valid:
                try:
                    self._cc.add_atom(type=atom["type"], title=atom["title"],
                                      content=atom["content"], tags=atom["tags"],
                                      evidence_level=atom["evidence_level"])
                    e_count += 1
                except Exception:
                    pass

        # ── 4. Claim atoms + validates edges to method ──
        for claim_entry in extracted.get("claims", []):
            claim_text = claim_entry.get("claim", "") if isinstance(claim_entry, dict) else str(claim_entry)
            if not claim_text:
                continue
            atom = {
                "type": "fact",
                "title": claim_text[:120],
                "content": json.dumps({
                    "claim": claim_text,
                    "evidence_type": claim_entry.get("evidence_type", "") if isinstance(claim_entry, dict) else "",
                    "confidence": claim_entry.get("confidence", "") if isinstance(claim_entry, dict) else "",
                    "source_paper": paper_title,
                }),
                "tags": ["literature", "claim"],
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
                    claim_id = created.get("id") if isinstance(created, dict) else getattr(created, "id", None)
                    e_count += 1
                    # validates edge: claim → method
                    if method_id and claim_id:
                        vr2 = gatekeeper.validate_relation(str(claim_id), str(method_id), "validates")
                        if vr2.valid:
                            try:
                                self._cc.add_relation(str(claim_id), str(method_id), "validates")
                                r_count += 1
                            except Exception:
                                pass
                except Exception:
                    pass

        # ── 5. Limitation → bottleneck atoms ──
        for lim in extracted.get("limitations", []):
            if not lim or "no explicit limitations" in lim.lower():
                continue
            atom = {
                "type": "bottleneck",
                "title": lim[:120],
                "content": json.dumps({"limitation": lim, "source_paper": paper_title}),
                "tags": ["literature", "limitation"],
                "evidence_level": "literature",
            }
            vr = gatekeeper.validate_atom(atom)
            if vr.valid:
                try:
                    self._cc.add_atom(type=atom["type"], title=atom["title"],
                                      content=atom["content"], tags=atom["tags"],
                                      evidence_level=atom["evidence_level"])
                    e_count += 1
                except Exception:
                    pass

        # ── 6. Transferable ideas → method atoms (proposal seeds) ──
        for idea_entry in extracted.get("transferable_ideas", []):
            idea_text = idea_entry.get("idea", "") if isinstance(idea_entry, dict) else str(idea_entry)
            idea_type = idea_entry.get("type", "module") if isinstance(idea_entry, dict) else "module"
            if not idea_text:
                continue
            atom = {
                "type": "method",
                "title": idea_text[:120],
                "content": json.dumps({
                    "idea": idea_text, "idea_type": idea_type,
                    "source_paper": paper_title,
                }),
                "tags": ["proposal", "seed", "literature", idea_type],
                "evidence_level": "literature",
            }
            vr = gatekeeper.validate_atom(atom)
            if vr.valid:
                try:
                    self._cc.add_atom(type=atom["type"], title=atom["title"],
                                      content=atom["content"], tags=atom["tags"],
                                      evidence_level=atom["evidence_level"])
                    e_count += 1
                except Exception:
                    pass

        # ── 7. Relations to known methods ──
        for rel_entry in extracted.get("relations_to_known", []):
            if isinstance(rel_entry, dict):
                target = rel_entry.get("target", "")
                rel_type = rel_entry.get("relation", "compares_to")
            else:
                target = str(rel_entry)
                rel_type = "compares_to"
            if target and method_id:
                # Try to find existing atom for the target
                existing = self._cc.get_atoms(limit=200)
                target_id = None
                for a in existing:
                    if target.lower() in str(a.get("title", "")).lower():
                        target_id = a.get("id")
                        break
                if target_id:
                    vr = gatekeeper.validate_relation(str(method_id), str(target_id), rel_type)
                    if vr.valid:
                        try:
                            self._cc.add_relation(str(method_id), str(target_id), rel_type)
                            r_count += 1
                        except Exception:
                            pass

        return e_count, r_count

    @staticmethod
    def _parse_llm_response(response: str) -> dict:
        """Parse LLM JSON response with fallbacks. Returns EvidenceCard-like dict."""
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
        return {}
