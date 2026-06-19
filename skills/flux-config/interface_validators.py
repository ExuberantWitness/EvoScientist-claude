"""Validators for flux-* skill interface contracts."""
import json
import re
from pathlib import Path


def validate_skill_frontmatter(skill_md_path: Path) -> dict:
    """Parse and validate SKILL.md YAML frontmatter."""
    text = skill_md_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {"valid": False, "error": "Missing YAML frontmatter"}

    end = text.find("---", 3)
    if end == -1:
        return {"valid": False, "error": "Unclosed frontmatter"}

    frontmatter = text[3:end].strip()
    result = {"valid": True}

    for line in frontmatter.split("\n"):
        if line.startswith("name:"):
            result["name"] = line.split(":", 1)[1].strip()
        elif line.startswith("description:"):
            result["description"] = line.split(":", 1)[1].strip().strip('"')
        elif line.startswith("argument-hint:"):
            result["argument_hint"] = line.split(":", 1)[1].strip()
        elif line.startswith("allowed-tools:"):
            result["allowed_tools"] = line.split(":", 1)[1].strip()

    for required in ["name", "description"]:
        if required not in result:
            result["valid"] = False
            result["error"] = f"Missing required field: {required}"

    return result


def validate_deliverables(workspace_dir: Path, deliverables: list) -> dict:
    """Check if deliverable files/dirs exist in workspace."""
    missing = []
    for d in deliverables:
        p = workspace_dir / d
        if d.endswith("/"):
            if not p.is_dir():
                missing.append(d)
        else:
            if not p.exists():
                missing.append(d)
    return {
        "verified": len(missing) == 0,
        "missing": missing,
        "checked": deliverables,
    }


def validate_no_banned_words(tex_dir: Path) -> list:
    """Check .tex files for banned academic phrases."""
    banned = ["delve", "pivotal", "landscape", "crucially", "importantly",
              "in this paper we", "note that"]
    violations = []
    for tex_file in tex_dir.rglob("*.tex"):
        text = tex_file.read_text(encoding="utf-8").lower()
        for word in banned:
            if word in text:
                violations.append({"file": str(tex_file), "word": word})
    return violations


def validate_sse_event(event_type: str, data: dict) -> dict:
    """Validate SSE event payload against expected schema."""
    schemas = {
        "paper_plan_ready": ["plan_path", "sections", "figures", "claims"],
        "paper_figures_ready": ["figures_dir", "auto_count", "manual_count"],
        "paper_sections_progress": ["section", "total", "completed"],
        "paper_compiled": ["pdf_path", "pages", "errors"],
        "paper_review_round": ["round", "score", "verdict", "fixes_applied"],
        "research_review_round": ["round", "score", "verdict", "action"],
        "deliverables_verified": ["phase", "verified", "missing"],
        "phase_feedback": ["phase", "feedback", "action"],
    }
    expected = schemas.get(event_type, [])
    missing = [k for k in expected if k not in data]
    return {"valid": len(missing) == 0, "missing_fields": missing}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        # Quick self-test
        print("Validators loaded OK")
        print(f"SSE event types: {list(validate_sse_event.__code__.co_consts if hasattr(validate_sse_event, '__code__') else [])}")
        test_event = {"plan_path": "PAPER_PLAN.md", "sections": 6, "figures": 4, "claims": 3}
        print(f"Test SSE validation: {validate_sse_event('paper_plan_ready', test_event)}")
