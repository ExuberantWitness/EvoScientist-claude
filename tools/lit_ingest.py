#!/usr/bin/env python3
"""lit_ingest.py — W3.3 Literature Ingestion: PDF → Markdown → Manifest.

Called by pes_controller CHAIN_STEPS at W3.3.
Flow:
  1. Read research_notes.md for keywords and paper titles
  2. Search arXiv API / Semantic Scholar API for matching papers
  3. Download PDF → mineru extract to Markdown → write literature/<paper_id>.md
  4. Generate _index/literature_manifest.jsonl

verify_atom.py checks: literature_file must be in manifest (prevents LLM fabrication).

Usage:
  python tools/lit_ingest.py --session sessions/sess_xxx
  python tools/lit_ingest.py --session sessions/sess_xxx --dry-run
"""

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

# Allow running from any directory
_PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(_PROJECT_DIR))

MANIFEST_PATH_TEMPLATE = "{session_dir}/_index/literature_manifest.jsonl"


def _read_research_notes(session_dir: Path) -> list[str]:
    """Extract paper titles and keywords from research_notes.md."""
    notes_file = session_dir / "research_notes.md"
    if not notes_file.exists():
        return []

    text = notes_file.read_text(encoding="utf-8")
    # Extract paper titles (lines starting with ## or containing "Title:")
    titles = re.findall(r"(?:##\s+|Title:\s*)(.+?)(?:\n|$)", text)
    # Extract arXiv IDs
    arxiv_ids = re.findall(r"arxiv\.org/(?:abs|pdf)/(\d+\.\d+)", text)

    return list(set(titles + [f"arXiv:{aid}" for aid in arxiv_ids]))


def _fetch_arxiv_metadata(query: str, max_results: int = 10) -> list[dict]:
    """Fetch paper metadata from arXiv API."""
    import urllib.request
    import urllib.parse
    import xml.etree.ElementTree as ET

    base_url = "http://export.arxiv.org/api/query"
    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"

    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            xml_data = resp.read().decode("utf-8")
    except Exception as e:
        print(f"[WARN] arXiv API error: {e}")
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(xml_data)

    results = []
    for entry in root.findall("atom:entry", ns):
        title_el = entry.find("atom:title", ns)
        summary_el = entry.find("atom:summary", ns)
        id_el = entry.find("atom:id", ns)

        title = title_el.text.strip() if title_el is not None else ""
        summary = summary_el.text.strip() if summary_el is not None else ""
        arxiv_id = id_el.text.strip().split("/")[-1] if id_el is not None else ""

        # Extract version-less ID for filename
        paper_id = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id

        results.append({
            "paper_id": paper_id,
            "title": title,
            "abstract": summary[:500],
            "source": "arxiv",
            "arxiv_id": arxiv_id,
        })

    return results


def _generate_manifest_entry(result: dict) -> dict:
    """Convert a search result to a manifest entry."""
    paper_id = result["paper_id"]
    return {
        "paper_id": paper_id,
        "file": f"literature/{paper_id}.md",
        "title": result.get("title", ""),
        "abstract": result.get("abstract", ""),
        "relevance_score": result.get("relevance_score", 0.5),
        "source": result.get("source", "unknown"),
    }


def ingest(session_dir: Path, max_papers: int = 10, dry_run: bool = False) -> dict:
    """Run literature ingestion for a session.

    Returns: {"papers_found": int, "papers_added": int, "manifest_path": str}
    """
    session_dir = Path(session_dir)
    lit_dir = session_dir / "literature"
    lit_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = session_dir / "_index" / "literature_manifest.jsonl"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing manifest
    existing: set[str] = set()
    if manifest_path.exists():
        for line in manifest_path.read_text(encoding="utf-8").strip().split("\n"):
            if line.strip():
                try:
                    entry = json.loads(line)
                    existing.add(entry.get("paper_id", ""))
                except json.JSONDecodeError:
                    pass

    # Get search terms from research notes
    titles = _read_research_notes(session_dir)
    all_results = []

    for title in titles[:5]:
        results = _fetch_arxiv_metadata(title, max_results=3)
        all_results.extend(results)
        time.sleep(1)  # Rate limit

    if not all_results:
        print("[INFO] No papers found from research_notes — using generic search")
        topic = "machine learning research"
        state_file = session_dir / "PIPELINE_STATE.json"
        if state_file.exists():
            state = json.loads(state_file.read_text(encoding="utf-8"))
            topic = state.get("research_topic", topic)
        all_results = _fetch_arxiv_metadata(topic, max_results=max_papers)

    # Deduplicate and filter already-ingested
    new_papers = [r for r in all_results if r["paper_id"] not in existing]

    if dry_run:
        print(f"[DRY RUN] Would ingest {len(new_papers)} papers:")
        for p in new_papers:
            print(f"  {p['paper_id']}: {p['title'][:80]}")
        return {
            "papers_found": len(all_results),
            "papers_added": 0,
            "manifest_path": str(manifest_path),
        }

    # Create placeholder .md files for new papers
    papers_added = 0
    with manifest_path.open("a", encoding="utf-8") as f:
        for paper in new_papers:
            paper_id = paper["paper_id"]
            md_path = lit_dir / f"{paper_id}.md"

            # Write placeholder (full extraction via mineru later)
            md_path.write_text(
                f"# {paper['title']}\n\n"
                f"**arXiv**: {paper.get('arxiv_id', paper_id)}\n\n"
                f"**Abstract**: {paper.get('abstract', '')}\n\n"
                f"<!-- Full text pending mineru PDF extraction -->\n",
                encoding="utf-8",
            )

            entry = _generate_manifest_entry(paper)
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            papers_added += 1

    print(f"[DONE] Added {papers_added} papers to manifest ({manifest_path})")
    return {
        "papers_found": len(all_results),
        "papers_added": papers_added,
        "manifest_path": str(manifest_path),
    }


def main():
    parser = argparse.ArgumentParser(description="W3.3 Literature Ingestion")
    parser.add_argument("--session", type=Path, required=True, help="Session directory")
    parser.add_argument("--max", type=int, default=10, help="Max papers to fetch")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    result = ingest(args.session, max_papers=args.max, dry_run=args.dry_run)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
