#!/usr/bin/env python3
"""CC Query Tool — unified CLI for Claim Chain operations.

The single entry point for agents to query and write the Claim Chain (cc.db).
Communicates with bge_socket_server for embeddings; works in degraded mode without it.

Usage:
  # Query
  python tools/cc_query_tool.py related --topic "Hopper entropy" --workspace /path/to/session
  python tools/cc_query_tool.py neighbors --atom-id 5 --depth 2 --workspace /path/to/session
  python tools/cc_query_tool.py summary --workspace /path/to/session

  # Write
  python tools/cc_query_tool.py upsert --title "CriticNetwork" --content '{"layer":"Linear"}' \\
      --tags "rl,critic" --type "component" --workspace /path/to/session
  python tools/cc_query_tool.py link --source "atom_id_1" --target "atom_id_2" \\
      --type implements --workspace /path/to/session

Socket path: <workspace>/_index/bge_socket.sock (auto-detected from --workspace)
"""

import argparse
import json
import logging
import socket
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [CC-TOOL] %(message)s")
logger = logging.getLogger("cc_tool")

UPSERT_SIMILARITY_THRESHOLD = 0.85


# ── Socket helpers ──

def _socket_path_from_workspace(workspace: str) -> Path:
    return Path(workspace) / "_index" / "bge_socket.sock"


def _send_to_socket(socket_path: str, request: dict, timeout: float = 30.0) -> dict:
    """Send a JSON-line request to the BGE socket, return parsed response."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(socket_path)
        payload = (json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8")
        sock.sendall(payload)

        buf = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
            if b"\n" in buf:
                break

        return json.loads(buf.decode("utf-8").strip())
    finally:
        sock.close()


def _socket_embed(socket_path: str, texts: list[str]) -> list[list[float]]:
    """Get BGE-M3 embeddings for texts via socket."""
    resp = _send_to_socket(socket_path, {"action": "embed", "texts": texts})
    if "error" in resp:
        raise RuntimeError(f"Socket embed error: {resp['error']}")
    return resp.get("embeddings", [])


def _ensure_embeddings(cc_db_path: str, socket_path: str) -> int:
    """Fill all NULL embeddings via socket embed. Returns count embedded.

    Opens its own short-lived DB connection AFTER the caller has closed theirs,
    so there is no lock contention."""
    import sqlite3

    if not Path(socket_path).exists():
        return 0

    # Read atoms with NULL embeddings
    conn = sqlite3.connect(cc_db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    rows = conn.execute(
        "SELECT id, title, summary FROM nodes WHERE embedding IS NULL"
    ).fetchall()

    if not rows:
        conn.close()
        return 0

    texts = [f"{r[1]}: {r[2][:500]}" for r in rows]
    try:
        embeddings = _socket_embed(socket_path, texts)
    except Exception as e:
        logger.error(f"Socket embed failed: {e}")
        conn.close()
        return 0

    for i, row in enumerate(rows):
        emb_json = json.dumps(embeddings[i], ensure_ascii=False)
        conn.execute("UPDATE nodes SET embedding = ? WHERE id = ?", (emb_json, row[0]))

    conn.commit()
    conn.close()
    logger.info(f"Embedded {len(rows)} atoms → {cc_db_path}")
    return len(rows)


# ── SQL backend ──

def _get_cc(workspace: str):
    """Instantiate ClaimChainV2 for the given workspace."""
    from claim_chain.chain import ClaimChainV2
    db_path = Path(workspace) / "_index" / "cc.db"
    if not db_path.exists():
        logger.warning(f"cc.db not found at {db_path}, creating new")
    return ClaimChainV2(db_path)


def _get_qi(cc, socket_path: str | None = None):
    """Instantiate CCQueryInterface, optionally with RNDEvaluator for semantic search."""
    from claim_chain.query import CCQueryInterface

    rnd = None
    if socket_path and Path(socket_path).exists():
        try:
            from pes_controller.elo.neighborhood import RNDEvaluator
            rnd = RNDEvaluator()
        except ImportError:
            logger.warning("Cannot import RNDEvaluator, using keyword fallback")
    return CCQueryInterface(cc, rnd_evaluator=rnd)


# ── Commands ──

def cmd_related(workspace: str, topic: str, top_k: int = 10):
    """Semantic search: find atoms related to a topic."""
    cc = _get_cc(workspace)
    socket_path = str(_socket_path_from_workspace(workspace))
    qi = _get_qi(cc, socket_path)
    result = qi.query_related(topic, top_k=top_k)
    cc.close()
    return result


def cmd_neighbors(workspace: str, atom_id: str, depth: int = 1):
    """Graph traversal: get neighborhood around an atom."""
    cc = _get_cc(workspace)
    qi = _get_qi(cc)
    result = qi.query_neighbors(atom_id, depth=depth)
    cc.close()
    return result


def cmd_summary(workspace: str):
    """Overview: atom/edge counts and type distribution."""
    cc = _get_cc(workspace)
    summary = cc.get_graph_summary()

    # Add type distribution
    rows = cc.conn.execute(
        "SELECT type, COUNT(*) FROM nodes GROUP BY type ORDER BY COUNT(*) DESC"
    ).fetchall()
    summary["type_distribution"] = {r[0]: r[1] for r in rows}

    # Count edges by type
    edge_rows = cc.conn.execute(
        "SELECT type, COUNT(*) FROM edges WHERE superseded_by IS NULL GROUP BY type"
    ).fetchall()
    summary["edge_types"] = {r[0]: r[1] for r in edge_rows} if edge_rows else {}

    # Embedding status
    emb_count = cc.conn.execute(
        "SELECT COUNT(*) FROM nodes WHERE embedding IS NOT NULL"
    ).fetchone()[0]
    summary["atoms_with_embeddings"] = emb_count
    summary["atoms_without_embeddings"] = summary["total_nodes"] - emb_count

    cc.close()
    return summary


def cmd_upsert(workspace: str, title: str, content: str = "",
               tags: str = "", atom_type: str = "component",
               status: str = "active", metadata: str = "{}",
               file_path: str = "", source_code: str = ""):
    """Insert or update an atom, using fuzzy title matching via BGE-M3 if socket available."""
    cc = _get_cc(workspace)
    socket_path = str(_socket_path_from_workspace(workspace))

    tags_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    try:
        metadata_dict = json.loads(metadata) if metadata else {}
    except json.JSONDecodeError:
        metadata_dict = {}
    if file_path:
        metadata_dict["file_path"] = file_path
    if source_code:
        metadata_dict["source_code"] = source_code[:2000]

    # Try fuzzy matching via socket
    existing_atoms = cc.get_atoms_with_embeddings()

    matched_atom = None
    if existing_atoms and Path(socket_path).exists():
        try:
            # Embed the input title
            query_emb = _socket_embed(socket_path, [title])[0]
            query_emb = np.array(query_emb, dtype=np.float32)
            query_norm = query_emb / (np.linalg.norm(query_emb) + 1e-8)

            # Compute cosine similarity against all existing atom title embeddings
            emb_list = []
            valid_indices = []
            for i, a in enumerate(existing_atoms):
                if a.get("embedding"):
                    emb_list.append(a["embedding"])
                    valid_indices.append(i)

            if emb_list:
                emb_matrix = np.array(emb_list, dtype=np.float32)
                emb_norm = emb_matrix / (np.linalg.norm(emb_matrix, axis=1, keepdims=True) + 1e-8)
                sims = np.dot(emb_norm, query_norm)
                best_local = int(np.argmax(sims))
                best_score = float(sims[best_local])
                best_idx = valid_indices[best_local]

                if best_score >= UPSERT_SIMILARITY_THRESHOLD:
                    matched_atom = existing_atoms[best_idx]
                    logger.info(f"Fuzzy match: '{title}' -> '{matched_atom['title']}' (score={best_score:.3f})")
                else:
                    logger.info(f"No fuzzy match above threshold (best={best_score:.3f} < {UPSERT_SIMILARITY_THRESHOLD})")
        except Exception as e:
            logger.warning(f"Fuzzy matching failed: {e}")

    # Also try exact title match as fallback
    if not matched_atom:
        for a in existing_atoms:
            if a.get("title", "").strip().lower() == title.strip().lower():
                matched_atom = a
                logger.info(f"Exact title match: '{title}' -> '{a['title']}'")
                break

    if matched_atom:
        # Update existing atom — compare content, set embedding=NULL if changed
        atom_id = matched_atom["id"]
        old_embed_text = matched_atom.get("embed_text", "")
        new_embed_text = f"{title}: {content[:500]} [tags: {', '.join(tags_list)}]"

        cc.conn.execute(
            "UPDATE nodes SET title=?, content=?, tags=?, status=?, metadata=?, summary=?"
            " WHERE id=?",
            (title, content, json.dumps(tags_list), status, json.dumps(metadata_dict, ensure_ascii=False),
             content[:500], atom_id),
        )
        if old_embed_text != new_embed_text:
            cc.conn.execute("UPDATE nodes SET embedding=NULL WHERE id=?", (atom_id,))
        cc.commit()

        result = {"action": "updated", "id": atom_id, "title": title,
                  "matched_title": matched_atom["title"]}
    else:
        # Insert new atom
        node_id = f"node_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()
        cc.conn.execute(
            "INSERT INTO nodes (id, title, type, summary, created_at, content, tags, status, metadata, embedding) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            (node_id, title, atom_type, content[:500], now, content,
             json.dumps(tags_list), status, json.dumps(metadata_dict, ensure_ascii=False)),
        )
        cc.commit()

        result = {"action": "created", "id": node_id, "title": title}

    # Close cc BEFORE embedding so socket server doesn't contend for DB lock
    cc.close()

    # Fill embedding via socket (pure compute — opens its own short-lived connection)
    if Path(socket_path).exists():
        embedded_count = _ensure_embeddings(str(Path(workspace) / "_index" / "cc.db"), socket_path)
        if embedded_count > 0:
            result["embedded"] = embedded_count

    return result


def cmd_link(workspace: str, source: str, target: str, edge_type: str = "implements",
             evidence: str = "", metadata: str = "{}"):
    """Create an edge between two atoms."""
    cc = _get_cc(workspace)

    try:
        metadata_dict = json.loads(metadata) if metadata else {}
    except json.JSONDecodeError:
        metadata_dict = {}

    r = cc.add_relation(source, target, edge_type, evidence=evidence, metadata=metadata_dict)
    cc.close()

    return {"action": "linked", "source": source, "target": target,
            "type": edge_type, "edge": r}


# ── CLI ──

def main():
    parser = argparse.ArgumentParser(description="CC Query Tool — Claim Chain operations")
    sub = parser.add_subparsers(dest="command")

    # Query: related
    p_related = sub.add_parser("related", help="Semantic search for atoms related to a topic")
    p_related.add_argument("--topic", required=True, help="Search topic")
    p_related.add_argument("--top-k", type=int, default=10, help="Max results")
    p_related.add_argument("--workspace", required=True, help="Session workspace path")

    # Query: neighbors
    p_neighbors = sub.add_parser("neighbors", help="Get neighborhood subgraph around an atom")
    p_neighbors.add_argument("--atom-id", required=True, help="Atom ID or title")
    p_neighbors.add_argument("--depth", type=int, default=1, help="Traversal depth")
    p_neighbors.add_argument("--workspace", required=True, help="Session workspace path")

    # Query: summary
    p_summary = sub.add_parser("summary", help="Overview of CC state")
    p_summary.add_argument("--workspace", required=True, help="Session workspace path")

    # Write: upsert
    p_upsert = sub.add_parser("upsert", help="Insert or update an atom")
    p_upsert.add_argument("--title", required=True, help="Atom title")
    p_upsert.add_argument("--content", default="", help="Atom content (JSON string)")
    p_upsert.add_argument("--tags", default="", help="Comma-separated tags")
    p_upsert.add_argument("--type", default="component", dest="atom_type",
                           help="Atom type (method/fact/component/hypothesis/experiment)")
    p_upsert.add_argument("--status", default="active", help="Atom status")
    p_upsert.add_argument("--metadata", default="{}", help="JSON metadata")
    p_upsert.add_argument("--file-path", default="", help="File path (e.g. artifacts/critic.py)")
    p_upsert.add_argument("--source-code", default="", help="Source code snippet")
    p_upsert.add_argument("--workspace", required=True, help="Session workspace path")

    # Write: link
    p_link = sub.add_parser("link", help="Create an edge between two atoms")
    p_link.add_argument("--source", required=True, help="Source atom ID")
    p_link.add_argument("--target", required=True, help="Target atom ID")
    p_link.add_argument("--type", default="implements", dest="edge_type",
                         help="Edge type (extends/improves/replaces/adapts/uses_component/compares/background/implements)")
    p_link.add_argument("--evidence", default="", help="Evidence text")
    p_link.add_argument("--metadata", default="{}", help="JSON metadata for Rho")
    p_link.add_argument("--workspace", required=True, help="Session workspace path")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        if args.command == "related":
            result = cmd_related(args.workspace, args.topic, args.top_k)
        elif args.command == "neighbors":
            result = cmd_neighbors(args.workspace, args.atom_id, args.depth)
        elif args.command == "summary":
            result = cmd_summary(args.workspace)
        elif args.command == "upsert":
            result = cmd_upsert(args.workspace, args.title, args.content,
                               args.tags, args.atom_type, args.status, args.metadata,
                               args.file_path, args.source_code)
        elif args.command == "link":
            result = cmd_link(args.workspace, args.source, args.target,
                             args.edge_type, args.evidence, args.metadata)
        else:
            parser.print_help()
            sys.exit(1)

        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        logger.error(f"Command failed: {e}")
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
