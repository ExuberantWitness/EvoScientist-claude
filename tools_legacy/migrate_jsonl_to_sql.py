#!/usr/bin/env python3
"""Migrate all session atoms.jsonl + relations.jsonl to cc.db (ClaimChainV2 SQLite).

Usage:
    python tools/migrate_jsonl_to_sql.py --workspace /path/to/AUTORESEARCH
    python tools/migrate_jsonl_to_sql.py --workspace /path/to/AUTORESEARCH --dry-run
    python tools/migrate_jsonl_to_sql.py --workspace /path/to/AUTORESEARCH --session sess_a4c11c87
    python tools/migrate_jsonl_to_sql.py --workspace /path/to/AUTORESEARCH --delete-jsonl
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent dir for ClaimChainV2 import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from claim_chain.chain import ClaimChainV2

# Edge types found in relations.jsonl that don't map to EdgeType enum
_FALLBACK_EDGE_TYPE = "background"
_VALID_EDGE_TYPES = {
    "extends", "improves", "replaces", "adapts", "uses_component",
    "compares", "background", "implements",
    "validates", "boundary_of", "related_to",
}


def _normalize_edge_type(raw_type: str) -> str:
    """Map arbitrary edge type strings to valid EdgeType values."""
    t = raw_type.strip().lower()
    if t in _VALID_EDGE_TYPES:
        return t
    return _FALLBACK_EDGE_TYPE


def _find_session_indexes(workspace: Path) -> list[Path]:
    """Find all _index directories with atoms.jsonl across all sessions."""
    indexes = []
    sessions_dir = workspace / "EvoScientist-claude" / "sessions"
    if not sessions_dir.exists():
        print(f"No sessions directory found at {sessions_dir}")
        return indexes

    for session_dir in sorted(sessions_dir.iterdir()):
        if not session_dir.is_dir():
            continue
        for loc in [session_dir / "_index", session_dir / "vault" / "_index"]:
            atoms_path = loc / "atoms.jsonl"
            if atoms_path.exists():
                indexes.append(loc)
                break
    return indexes


def _read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file, returning list of parsed dicts. Skips empty/malformed lines."""
    if not path.exists():
        return []
    items = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  WARNING: skipping malformed line in {path.name}: {e}")
    return items


def migrate_atoms(cc: ClaimChainV2, atoms: list[dict], dry_run: bool) -> int:
    """Migrate atoms from JSONL format to cc.db via ClaimChainV2.add_atom()."""
    count = 0
    for atom in atoms:
        atom_id = atom.get("id")
        if atom_id is None:
            continue
        atom_type = atom.get("type", "method")
        title = atom.get("title", str(atom_id))
        content = atom.get("content", "")
        tags = atom.get("tags", [])
        status = atom.get("status", "active")
        metadata = atom.get("metadata", {})
        evidence_level = atom.get("evidence_level", "experiment")

        if not dry_run:
            cc.add_atom(
                type=atom_type,
                title=title,
                content=content,
                tags=tags,
                evidence_level=evidence_level,
                metadata={"id": atom_id, "status": status, **(metadata or {})},
            )
        count += 1
    return count


def migrate_relations(cc: ClaimChainV2, relations: list[dict], dry_run: bool) -> tuple[int, dict]:
    """Migrate relations from JSONL format to cc.db via ClaimChainV2.add_relation().

    Returns (count, type_map) where type_map shows original→normalized type counts.
    """
    count = 0
    type_map = {}
    for rel in relations:
        source_id = rel.get("source_id") or rel.get("src")
        target_id = rel.get("target_id") or rel.get("dst")
        if not source_id or not target_id:
            continue
        raw_type = rel.get("type", "background")
        if str(source_id) == str(target_id):
            print(f"    SKIP self-loop: {source_id} --[{raw_type}]--> {target_id}")
            continue

        normalized = _normalize_edge_type(raw_type)
        type_map[raw_type] = type_map.get(raw_type, 0) + 1

        evidence = rel.get("evidence", "")
        rel_metadata = rel.get("metadata", {})
        confidence = rel.get("confidence", 0.5)
        if isinstance(confidence, str):
            confidence = 0.5

        if not dry_run:
            cc.add_relation(
                source_id=str(source_id),
                target_id=str(target_id),
                type=normalized,
                evidence=evidence,
                metadata={
                    **(rel_metadata or {}),
                    "confidence": min(1.0, max(0.0, float(confidence))),
                    "original_type": raw_type,
                },
            )
        count += 1
    return count, type_map


def migrate_one_index(index_dir: Path, dry_run: bool, delete_jsonl: bool) -> dict:
    """Migrate a single _index directory's JSONL files to cc.db."""
    atoms_path = index_dir / "atoms.jsonl"
    relations_path = index_dir / "relations.jsonl"
    db_path = index_dir / "cc.db"

    atoms = _read_jsonl(atoms_path)
    relations = _read_jsonl(relations_path)

    if not atoms and not relations:
        return {"atoms": 0, "relations": 0, "type_map": {}, "skipped": True}

    print(f"  {index_dir}")
    print(f"    atoms: {len(atoms)}, relations: {len(relations)}")

    if dry_run:
        atom_count = len(atoms)
        type_map = {}
        for rel in relations:
            raw = rel.get("type", "background")
            type_map[raw] = type_map.get(raw, 0) + 1
        return {"atoms": atom_count, "relations": len(relations), "type_map": type_map, "skipped": False}

    # Phase 1: migrate atoms
    index_dir.mkdir(parents=True, exist_ok=True)
    cc = ClaimChainV2(db_path)
    atom_count = migrate_atoms(cc, atoms, dry_run=False)

    # Phase 2: find and create placeholder atoms for dangling relation references
    existing_ids = {n.id for n in cc.all_nodes()}
    missing_ids = set()
    for rel in relations:
        src = str(rel.get("source_id") or rel.get("src") or "")
        dst = str(rel.get("target_id") or rel.get("dst") or "")
        if not src or not dst:
            continue
        if src == dst:
            continue
        if src not in existing_ids:
            missing_ids.add(src)
        if dst not in existing_ids:
            missing_ids.add(dst)

    placeholder_count = 0
    for mid in sorted(missing_ids):
        cc.add_atom(
            type="concept",
            title=mid[:200],
            content="{}",
            tags=["dangling-reference"],
            evidence_level="speculative",
            metadata={"id": mid, "status": "dangling"},
        )
        placeholder_count += 1
        existing_ids.add(mid)

    if placeholder_count > 0:
        print(f"    → created {placeholder_count} placeholder atoms for dangling relation references")

    # Phase 3: migrate relations
    rel_count, type_map = migrate_relations(cc, relations, dry_run=False)
    cc.commit()
    cc.close()

    print(f"    → {atom_count} atoms (+{placeholder_count} placeholder), {rel_count} relations migrated")

    if delete_jsonl and atom_count + rel_count > 0:
        for path in [atoms_path, relations_path]:
            if path.exists():
                path.unlink()
                print(f"    → deleted {path.name}")

    return {
        "atoms": atom_count + placeholder_count,
        "relations": rel_count,
        "type_map": type_map,
        "skipped": False,
    }


def main():
    parser = argparse.ArgumentParser(description="Migrate JSONL to SQL for EvoScientist sessions")
    parser.add_argument("--workspace", required=True,
                        help="Path to AUTORESEARCH workspace directory")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without making changes")
    parser.add_argument("--delete-jsonl", action="store_true",
                        help="Delete atoms.jsonl and relations.jsonl after successful migration")
    parser.add_argument("--session", default=None,
                        help="Migrate only a specific session (e.g., sess_a4c11c87)")
    args = parser.parse_args()

    workspace = Path(args.workspace)
    if not workspace.exists():
        print(f"ERROR: workspace {workspace} does not exist")
        sys.exit(1)

    if args.dry_run:
        print("=== DRY RUN (no changes will be made) ===\n")

    indexes = _find_session_indexes(workspace)

    if args.session:
        indexes = [idx for idx in indexes if args.session in str(idx)]
        if not indexes:
            print(f"Session '{args.session}' not found or has no atoms.jsonl")
            sys.exit(1)

    if not indexes:
        print("No sessions with atoms.jsonl found.")
        sys.exit(0)

    print(f"Found {len(indexes)} session(s) to migrate\n")

    total_atoms = 0
    total_relations = 0
    all_type_maps = {}

    for idx in indexes:
        result = migrate_one_index(idx, args.dry_run, args.delete_jsonl)
        total_atoms += result["atoms"]
        total_relations += result["relations"]
        for k, v in result["type_map"].items():
            all_type_maps[k] = all_type_maps.get(k, 0) + v

    print(f"\n=== {'Would migrate' if args.dry_run else 'Migrated'} {total_atoms} atoms, {total_relations} relations across {len(indexes)} session(s) ===")
    if all_type_maps:
        print("Edge types used:")
        for t, c in sorted(all_type_maps.items(), key=lambda x: -x[1]):
            normalized = _normalize_edge_type(t)
            note = f" → {normalized}" if normalized != t else ""
            print(f"  {t}: {c}{note}")


if __name__ == "__main__":
    main()
