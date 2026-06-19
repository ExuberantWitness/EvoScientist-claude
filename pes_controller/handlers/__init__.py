"""W6 Python handler functions — pure Python logic for SkillExecutor execution:python mode."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pes_controller.types import SkillResult

logger = logging.getLogger(__name__)


def scan_islands(variables: dict[str, Any]) -> SkillResult:
    """W6 scan_islands_rubrics — scan evolve_archive islands and compute rubric scores."""
    ws = Path(variables.get("workspace_dir", "."))
    archive_dir = ws / "evolve_archive"

    islands = []
    if archive_dir.exists():
        for island_dir in sorted(archive_dir.glob("island_*")):
            entries = []
            for entry_file in sorted(island_dir.glob("*.json")):
                try:
                    data = json.loads(entry_file.read_text(encoding="utf-8"))
                    entries.append({"file": entry_file.name, "score": data.get("score", 0)})
                except Exception:
                    pass
            islands.append({"id": island_dir.name, "entries": len(entries)})

    result_data = {"islands": islands, "total": len(islands)}
    output = ws / "island_scan.json"
    output.write_text(json.dumps(result_data, ensure_ascii=False, indent=2), encoding="utf-8")

    return SkillResult(
        success=True,
        files_written=[str(output)],
        llm_response=json.dumps(result_data, ensure_ascii=False),
    )


def island_assign(variables: dict[str, Any]) -> SkillResult:
    """W6 island_assign — assign proposals to evolution islands."""
    ws = Path(variables.get("workspace_dir", "."))
    proposals_dir = ws / "proposals"
    archive_dir = ws / "evolve_archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    assignments = {}
    if proposals_dir.exists():
        proposals = sorted(proposals_dir.glob("proposal_*.json"))
        for i, pf in enumerate(proposals):
            island_id = f"island_{i % 4}"
            island_dir = archive_dir / island_id
            island_dir.mkdir(parents=True, exist_ok=True)
            target = island_dir / pf.name
            if not target.exists():
                import shutil
                shutil.copy2(str(pf), str(target))
            assignments[pf.stem] = island_id

    return SkillResult(
        success=True,
        llm_response=json.dumps({"assignments": assignments}, ensure_ascii=False),
    )


def write_claim_chain(variables: dict[str, Any]) -> SkillResult:
    """W6 write_claim_chain — update claim chain database from analysis results."""
    ws = Path(variables.get("workspace_dir", "."))
    cc_db = ws / "_index" / "cc.db"

    if not cc_db.exists():
        return SkillResult(
            success=False,
            llm_response="cc.db not found — claim chain not available",
        )

    # Read proposals for claim extraction
    proposals_dir = ws / "proposals"
    claims = []
    if proposals_dir.exists():
        for pf in sorted(proposals_dir.glob("proposal_*.json")):
            try:
                data = json.loads(pf.read_text(encoding="utf-8"))
                llm_raw = data.get("llm_response", "")
                claims.append({
                    "source": pf.stem,
                    "hypothesis": _extract_field(llm_raw, "hypothesis"),
                    "title": _extract_field(llm_raw, "title"),
                })
            except Exception:
                pass

    output = ws / "claim_chain_update.json"
    output.write_text(
        json.dumps({"claims": claims, "count": len(claims)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return SkillResult(
        success=True,
        files_written=[str(output)],
        llm_response=f"Extracted {len(claims)} claims from proposals",
    )


def _extract_field(llm_response: str, field: str) -> str:
    """Extract a field from LLM JSON response."""
    try:
        parsed = json.loads(llm_response)
        return parsed.get(field, "")[:200]
    except (json.JSONDecodeError, TypeError):
        return ""
