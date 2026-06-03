"""Intern-Atlas Claim Chain v2 — SQLite-backed graph database.

Replaces claim_chain.py (JSONL append-only) with a proper relational store:
- Schema-enforced: CHECK constraints, foreign keys, UNIQUE on (src,dst,type)
- Transactional: BEGIN → insert → validate → COMMIT or ROLLBACK
- Post-validation: 4 deterministic rules run before each commit
- History-preserving: superseded_by for SGT-MCTS lineage

Usage:
    from claim_chain_v2 import ClaimChainV2
    cc = ClaimChainV2("claims.db")
    cc.add_node(Node(id="n1", title="FlashAttention", type="method"))
    cc.add_edge(Edge(src="n1", dst="n2", type=EdgeType.IMPROVES, rho=Rho(...)))
    cc.commit()  # triggers post-validation
"""

import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    from claim_chain.schemas.taxonomy import EdgeType, BottleneckCategory, STRONG_CAUSAL, BOTTLENECK_CATEGORIES
    from claim_chain.schemas.models import Rho, Edge, Node
except ImportError:
    from claim_chain.schemas.taxonomy import EdgeType, BottleneckCategory, STRONG_CAUSAL, BOTTLENECK_CATEGORIES
    from claim_chain.schemas.models import Rho, Edge, Node


SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    type        TEXT NOT NULL DEFAULT 'method'
                CHECK (type IN ('method', 'bottleneck', 'paper', 'fact', 'component', 'hypothesis', 'experiment', 'verification')),
    paper_id    TEXT,
    summary     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    -- EvoScientist extensions (v2 schema)
    content     TEXT NOT NULL DEFAULT '',
    tags        TEXT NOT NULL DEFAULT '[]',
    status      TEXT NOT NULL DEFAULT 'active',
    metadata    TEXT NOT NULL DEFAULT '{{}}',
    -- BGE-M3 embedding (1024-dim float array as JSON string)
    embedding   TEXT
);

CREATE TABLE IF NOT EXISTS bottlenecks (
    id          TEXT PRIMARY KEY,
    category    TEXT NOT NULL
                CHECK (category IN ({bottleneck_placeholders})),
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS node_addresses (
    node_id       TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    bottleneck_id TEXT NOT NULL REFERENCES bottlenecks(id) ON DELETE CASCADE,
    PRIMARY KEY (node_id, bottleneck_id)
);

CREATE TABLE IF NOT EXISTS edges (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    src             TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    dst             TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    type            TEXT NOT NULL
                    CHECK (type IN ({edge_placeholders})),
    -- ρ(e) inlined (avoids JOIN for performance)
    rho_bottleneck  TEXT REFERENCES bottlenecks(id),
    rho_mechanism   TEXT,
    rho_tradeoff    TEXT,
    rho_confidence  REAL CHECK (rho_confidence BETWEEN 0 AND 1),
    created_at      TEXT NOT NULL,
    -- SGT-MCTS pre-allocated fields
    superseded_by   INTEGER REFERENCES edges(id),
    visit_count     INTEGER NOT NULL DEFAULT 0,
    value_sum       REAL NOT NULL DEFAULT 0.0,
    UNIQUE(src, dst, type)
);

CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst);
CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(type);
CREATE INDEX IF NOT EXISTS idx_edges_superseded ON edges(superseded_by);
""".format(
    bottleneck_placeholders=", ".join(f"'{b}'" for b in sorted(BOTTLENECK_CATEGORIES)),
    edge_placeholders=", ".join(f"'{e.value}'" for e in EdgeType),
)

# Schema version stored in PRAGMA user_version
CURRENT_SCHEMA_VERSION = 2


def migrate_schema(db_path: str | Path) -> bool:
    """Migrate existing cc.db from v1 (BLOB embedding, no content/tags/status/metadata) to v2.

    Uses table-rename strategy since SQLite doesn't support ALTER COLUMN or CHECK modification.
    Handles both Schema A (8 node types) and Schema B (3 node types).
    Returns True if migration was performed, False if already at current version.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return False

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute("PRAGMA user_version")
        version = cur.fetchone()[0]
        if version >= CURRENT_SCHEMA_VERSION:
            return False

        # Check if migration is needed
        cur = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='nodes'")
        row = cur.fetchone()
        if row is None:
            return False
        old_ddl = row[0]
        needs_migration = "BLOB" in old_ddl or "content" not in old_ddl

        if not needs_migration:
            conn.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")
            conn.commit()
            return False

        # Detect old column names
        col_check = conn.execute("SELECT * FROM nodes LIMIT 0")
        old_cols = [d[0] for d in col_check.description]
        has_content = "content" in old_cols

        # 1. Disable FKs, rename old tables
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("ALTER TABLE nodes RENAME TO nodes_old")
        conn.execute("ALTER TABLE edges RENAME TO edges_old")

        # 2. Create new nodes and edges tables with v2 schema
        bottleneck_placeholders = ", ".join(f"'{b}'" for b in sorted(BOTTLENECK_CATEGORIES))
        edge_placeholders = ", ".join(f"'{e.value}'" for e in EdgeType)
        conn.execute(f"""
            CREATE TABLE nodes (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                type        TEXT NOT NULL DEFAULT 'method'
                            CHECK (type IN ('method','bottleneck','paper','fact','component','hypothesis','experiment','verification')),
                paper_id    TEXT,
                summary     TEXT NOT NULL DEFAULT '',
                created_at  TEXT NOT NULL,
                content     TEXT NOT NULL DEFAULT '',
                tags        TEXT NOT NULL DEFAULT '[]',
                status      TEXT NOT NULL DEFAULT 'active',
                metadata    TEXT NOT NULL DEFAULT '{{}}',
                embedding   TEXT
            )
        """)
        conn.execute(f"""
            CREATE TABLE edges (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                src             TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
                dst             TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
                type            TEXT NOT NULL CHECK (type IN ({edge_placeholders})),
                rho_bottleneck  TEXT REFERENCES bottlenecks(id),
                rho_mechanism   TEXT,
                rho_tradeoff    TEXT,
                rho_confidence  REAL CHECK (rho_confidence BETWEEN 0 AND 1),
                created_at      TEXT NOT NULL,
                superseded_by   INTEGER REFERENCES edges(id),
                visit_count     INTEGER NOT NULL DEFAULT 0,
                value_sum       REAL NOT NULL DEFAULT 0.0,
                UNIQUE(src, dst, type)
            )
        """)

        # 3. Copy nodes: map old columns → new columns
        if has_content:
            conn.execute("""
                INSERT INTO nodes (id, title, type, paper_id, summary, created_at,
                                   content, tags, status, metadata, embedding)
                SELECT id, title, type, paper_id, summary, created_at,
                       COALESCE(content, ''), COALESCE(tags, '[]'),
                       COALESCE(status, 'active'), COALESCE(metadata, '{}'),
                       NULL
                FROM nodes_old
            """)
        else:
            conn.execute("""
                INSERT INTO nodes (id, title, type, paper_id, summary, created_at)
                SELECT id, title, type, paper_id, summary, created_at
                FROM nodes_old
            """)
        conn.execute("DROP TABLE nodes_old")

        # 4. Copy edges
        conn.execute("""
            INSERT INTO edges (id, src, dst, type, rho_bottleneck, rho_mechanism,
                               rho_tradeoff, rho_confidence, created_at,
                               superseded_by, visit_count, value_sum)
            SELECT id, src, dst, type, rho_bottleneck, rho_mechanism,
                   rho_tradeoff, rho_confidence, created_at,
                   superseded_by, visit_count, value_sum
            FROM edges_old
        """)
        conn.execute("DROP TABLE edges_old")

        # 5. Recreate indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_superseded ON edges(superseded_by)")

        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")
        conn.commit()

        import logging
        logging.getLogger("claim_chain").info(
            f"Schema migrated to v{CURRENT_SCHEMA_VERSION}: {db_path}"
        )
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _row_to_node(row, addresses: list[str]) -> Node:
    """Convert a SQL row (10 columns) to a Node dataclass."""
    return Node(
        id=row[0], title=row[1], type=row[2], paper_id=row[3],
        summary=row[4],
        created_at=datetime.fromisoformat(row[5]),
        content=row[6] if len(row) > 6 else "",
        tags=json.loads(row[7]) if len(row) > 7 and row[7] else [],
        status=row[8] if len(row) > 8 else "active",
        metadata=json.loads(row[9]) if len(row) > 9 and row[9] else {},
        addresses=addresses,
    )


class ClaimChainV2:
    """SQLite-backed Intern-Atlas compliant Claim Chain."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        # Auto-migrate schema before first use (no-op if already current)
        migrate_schema(self.db_path)

    # ── Connection Management ──

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.executescript(SCHEMA)
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── CRUD: Nodes ──

    def add_node(self, node: Node) -> Node:
        """Insert a node. Returns the node (unchanged). embedding is set NULL for later batch fill."""
        tags_json = json.dumps(node.tags) if node.tags else "[]"
        metadata_json = json.dumps(node.metadata, ensure_ascii=False) if node.metadata else "{}"
        self.conn.execute(
            "INSERT OR IGNORE INTO nodes (id, title, type, paper_id, summary, created_at, "
            "content, tags, status, metadata, embedding) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            (node.id, node.title, node.type, node.paper_id,
             node.summary, node.created_at.isoformat(),
             node.content, tags_json, node.status, metadata_json),
        )
        # Insert bottleneck addresses
        for bid in node.addresses:
            self.conn.execute(
                "INSERT OR IGNORE INTO node_addresses (node_id, bottleneck_id) VALUES (?, ?)",
                (node.id, bid),
            )
        return node

    def get_node(self, node_id: str) -> Optional[Node]:
        row = self.conn.execute(
            "SELECT id, title, type, paper_id, summary, created_at, "
            "content, tags, status, metadata FROM nodes WHERE id = ?",
            (node_id,),
        ).fetchone()
        if row is None:
            return None
        addrs = self.conn.execute(
            "SELECT bottleneck_id FROM node_addresses WHERE node_id = ?", (node_id,)
        ).fetchall()
        return _row_to_node(row, [a[0] for a in addrs])

    def all_nodes(self) -> list[Node]:
        rows = self.conn.execute(
            "SELECT id, title, type, paper_id, summary, created_at, "
            "content, tags, status, metadata FROM nodes ORDER BY created_at"
        ).fetchall()
        nodes = []
        for r in rows:
            addrs = self.conn.execute(
                "SELECT bottleneck_id FROM node_addresses WHERE node_id = ?", (r[0],)
            ).fetchall()
            nodes.append(_row_to_node(r, [a[0] for a in addrs]))
        return nodes

    # ── CRUD: Bottlenecks ──

    def add_bottleneck(self, category: str, description: str = "") -> None:
        """Register a bottleneck. category is both the ID and FK target.

        Rho.bottleneck directly references bottlenecks.id (= category value).
        This ensures every ρ(e) record FK-resolves without indirection.
        """
        if category not in BOTTLENECK_CATEGORIES:
            raise ValueError(
                f"Unknown bottleneck category '{category}'. "
                f"Must be one of: {sorted(BOTTLENECK_CATEGORIES)}"
            )
        self.conn.execute(
            "INSERT OR IGNORE INTO bottlenecks (id, category, description) VALUES (?, ?, ?)",
            (category, category, description),
        )

    # ── CRUD: Edges ──

    def add_edge(self, edge: Edge) -> Edge:
        """Stage an edge for commit. Validation runs at commit() time."""
        errors = edge.validate()
        if errors:
            raise ValueError(f"Edge validation failed: {'; '.join(errors)}")

        rho_b = edge.rho.bottleneck if edge.rho else None
        rho_m = edge.rho.mechanism if edge.rho else None
        rho_t = edge.rho.tradeoff if edge.rho else None
        rho_c = edge.rho.confidence if edge.rho else None

        self.conn.execute(
            "INSERT OR IGNORE INTO edges "
            "(src, dst, type, rho_bottleneck, rho_mechanism, rho_tradeoff, "
            " rho_confidence, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (edge.src, edge.dst, edge.type.value,
             rho_b, rho_m, rho_t, rho_c,
             edge.created_at.isoformat()),
        )
        return edge

    def get_edge(self, edge_id: int) -> Optional[Edge]:
        row = self.conn.execute(
            "SELECT id, src, dst, type, rho_bottleneck, rho_mechanism, "
            "rho_tradeoff, rho_confidence, created_at FROM edges WHERE id = ?",
            (edge_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_edge(row)

    def outgoing(self, node_id: str, edge_type: Optional[EdgeType] = None) -> list[Edge]:
        if edge_type:
            rows = self.conn.execute(
                "SELECT id, src, dst, type, rho_bottleneck, rho_mechanism, "
                "rho_tradeoff, rho_confidence, created_at "
                "FROM edges WHERE src = ? AND type = ? AND superseded_by IS NULL "
                "ORDER BY created_at",
                (node_id, edge_type.value),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id, src, dst, type, rho_bottleneck, rho_mechanism, "
                "rho_tradeoff, rho_confidence, created_at "
                "FROM edges WHERE src = ? AND superseded_by IS NULL "
                "ORDER BY created_at",
                (node_id,),
            ).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def all_edges(self, include_superseded: bool = False) -> list[Edge]:
        if include_superseded:
            rows = self.conn.execute(
                "SELECT id, src, dst, type, rho_bottleneck, rho_mechanism, "
                "rho_tradeoff, rho_confidence, created_at FROM edges ORDER BY created_at"
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id, src, dst, type, rho_bottleneck, rho_mechanism, "
                "rho_tradeoff, rho_confidence, created_at "
                "FROM edges WHERE superseded_by IS NULL ORDER BY created_at"
            ).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def _row_to_edge(self, row) -> Edge:
        rho = None
        if row[4] is not None:  # rho_bottleneck
            rho = Rho(
                bottleneck=row[4],
                mechanism=row[5] or "",
                tradeoff=row[6] or "",
                confidence=row[7] or 0.0,
            )
        return Edge(
            src=row[1], dst=row[2],
            type=EdgeType(row[3]),
            rho=rho,
            created_at=datetime.fromisoformat(row[8]),
        )

    # ── Evolution Chain Query (§3.4) ──

    def get_evolution_chain(self, seed_node: str, max_depth: int = 5) -> list[Edge]:
        """BFS traversal over STRONG_CAUSAL edges, starting from seed_node."""
        strong_types = tuple(e.value for e in STRONG_CAUSAL)
        visited = {seed_node}
        chain = []
        queue = [(seed_node, 0)]

        while queue:
            current, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            rows = self.conn.execute(
                "SELECT id, src, dst, type, rho_bottleneck, rho_mechanism, "
                "rho_tradeoff, rho_confidence, created_at "
                "FROM edges WHERE src = ? AND type IN ({}) AND superseded_by IS NULL".format(
                    ",".join("?" * len(strong_types))
                ),
                (current, *strong_types),
            ).fetchall()
            for r in rows:
                edge = self._row_to_edge(r)
                if edge.dst not in visited:
                    chain.append(edge)
                    visited.add(edge.dst)
                    queue.append((edge.dst, depth + 1))
        return chain

    # ── Commit with Validation ──

    def commit(self):
        """Run post-validation, then commit. Rolls back on failure."""
        try:
            from claim_chain.schemas.validation import run_post_validation
        except ImportError:
            from claim_chain.schemas.validation import run_post_validation
        errors = run_post_validation(self.conn)
        if errors:
            self.conn.rollback()
            raise ValidationError(errors)
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    # ── Export ──

    def export_graph(self) -> dict:
        """Export full graph as JSON-serializable dict (for viewer/API)."""
        nodes = []
        for n in self.all_nodes():
            d = n.to_dict()
            # Load bottleneck details
            b_rows = self.conn.execute(
                "SELECT id, category, description FROM bottlenecks WHERE id IN ("
                + ",".join("?" * len(n.addresses)) + ")",
                n.addresses,
            ).fetchall() if n.addresses else []
            d["bottlenecks"] = [
                {"id": r[0], "category": r[1], "description": r[2]}
                for r in b_rows
            ]
            nodes.append(d)

        edges = [e.to_dict() for e in self.all_edges(include_superseded=False)]

        return {"nodes": nodes, "edges": edges}

    # ── Backward-compatible API (Phase 7: CC v1→v2 migration) ──

    def add_atom(self, type: str, title: str, content: str = "",
                 tags: list[str] | None = None, evidence_level: str = "experiment",
                 metadata: dict | None = None,
                 iteration: int | None = None, phase: str | None = None) -> dict:
        """Backward-compatible API mirroring claim_chain.py add_atom().

        Converts v1-style atom dict to v2 Node. Persists content, tags, metadata to SQL.
        embedding is set NULL for later batch fill via bge_socket_server.

        iteration/phase are injected into metadata for temporal tracking (Bug 3 fix).
        """
        import time, uuid

        meta = dict(metadata or {})
        meta.setdefault("created_at_iso", datetime.now(timezone.utc).isoformat())
        if iteration is not None:
            meta["iter"] = iteration
        if phase is not None:
            meta["phase"] = phase

        node_id = meta.get("id")
        if not node_id:
            node_id = f"node_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

        node = Node(
            id=str(node_id),
            title=title,
            type=type if type in ("method", "fact", "component", "hypothesis", "experiment", "bottleneck", "paper") else "method",
            summary=content[:500] if content else "",
            content=content,
            tags=tags or [],
            status="active",
            metadata=meta,
            addresses=meta.get("addresses", []),
            created_at=datetime.now(timezone.utc),
        )
        self.add_node(node)
        self.commit()
        return {
            "id": node.id,
            "type": node.type,
            "title": node.title,
            "content": content,
            "tags": tags or [],
            "evidence_level": evidence_level,
            "status": "active",
            "metadata": meta,
        }

    def add_relation(self, source_id: str, target_id: str, type: str,
                     evidence: str = "", metadata: dict | None = None) -> dict:
        """Backward-compatible API mirroring claim_chain.py add_relation()."""
        try:
            from claim_chain.schemas.taxonomy import EdgeType as ET
        except ImportError:
            from claim_chain.schemas.taxonomy import EdgeType as ET

        try:
            edge_type = ET(type)
        except ValueError:
            edge_type = ET.BACKGROUND

        rho = None
        if metadata:
            bottleneck_id = metadata.get("bottleneck", "")
            if bottleneck_id:
                # Auto-register bottleneck to satisfy FK constraint
                self.add_bottleneck(bottleneck_id, metadata.get("bottleneck_desc", ""))
                tradeoff = metadata.get("tradeoff", "")
                if not tradeoff:
                    tradeoff = f"Relation from {source_id} to {target_id}"
                rho = Rho(
                    bottleneck=bottleneck_id,
                    mechanism=metadata.get("mechanism", evidence or ""),
                    tradeoff=tradeoff,
                    confidence=min(1.0, max(0.0, metadata.get("confidence", 0.5))),
                )

        from datetime import datetime, timezone
        edge = Edge(
            src=str(source_id),
            dst=str(target_id),
            type=edge_type,
            rho=rho,
            created_at=datetime.now(timezone.utc),
        )
        self.add_edge(edge)
        self.commit()
        return edge.to_dict()

    def get_graph_summary(self) -> dict:
        """Backward-compatible API. Returns node/edge counts."""
        nodes = self.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edges = self.conn.execute(
            "SELECT COUNT(*) FROM edges WHERE superseded_by IS NULL"
        ).fetchone()[0]
        return {"total_nodes": nodes, "total_edges": edges}



    # ── Embedding methods ──

    def get_atoms_with_embeddings(self) -> list[dict]:
        """Return all atoms with embedding and text suitable for BGE-M3 encoding.

        Returns list of {id, title, type, content, tags, status, metadata, embedding, embed_text}.
        embed_text is formatted as '{title}: {summary} [tags: ...]' for embedding computation.
        """
        rows = self.conn.execute(
            "SELECT id, title, type, content, tags, status, metadata, summary, embedding "
            "FROM nodes ORDER BY created_at"
        ).fetchall()

        result = []
        for r in rows:
            tags_list = json.loads(r[4]) if r[4] else []
            embedding = json.loads(r[8]) if r[8] else None
            embed_text = f"{r[1]}: {r[7][:500]} [tags: {', '.join(tags_list)}]"
            result.append({
                "id": r[0], "title": r[1], "type": r[2],
                "content": r[3] or r[7] or "{}",
                "tags": tags_list,
                "status": r[5] or "active",
                "metadata": json.loads(r[6]) if r[6] else {},
                "embedding": embedding,
                "embed_text": embed_text,
            })
        return result

    def update_embedding(self, atom_id: str, embedding: list[float]) -> None:
        """Update the embedding for a single atom."""
        emb_json = json.dumps(embedding, ensure_ascii=False)
        self.conn.execute(
            "UPDATE nodes SET embedding = ? WHERE id = ?",
            (emb_json, atom_id),
        )

    def get_null_embedding_atoms(self) -> list[tuple[str, str]]:
        """Return (id, embed_text) for atoms with NULL embedding."""
        rows = self.conn.execute(
            "SELECT id, title, summary, tags FROM nodes WHERE embedding IS NULL"
        ).fetchall()
        result = []
        for r in rows:
            tags_list = json.loads(r[3]) if r[3] else []
            text = f"{r[1]}: {r[2][:500]} [tags: {', '.join(tags_list)}]"
            result.append((r[0], text))
        return result

    # ── Compatibility with old ClaimChain API ──

    @property
    def atoms_path(self):
        """Deprecated: use get_atoms() instead. Returns path for backward compat only."""
        return self.db_path.parent / "atoms.jsonl"

    @property
    def relations_path(self):
        """Deprecated: use get_relations() instead. Returns path for backward compat only."""
        return self.db_path.parent / "relations.jsonl"

    def get_atoms(self, limit: int = 0, type: str | None = None, tags: list[str] | None = None):
        """Compatibility wrapper for all_nodes(). Reads from cc.db nodes table."""
        nodes = self.all_nodes()
        result = []
        for n in nodes:
            if type and n.type != type:
                continue
            if tags and not any(t in (n.tags or []) for t in tags):
                continue
            d = {"id": n.id, "type": n.type if isinstance(n.type, str) else str(n.type),
                 "title": n.title,
                 "content": n.content or n.summary or "{}",
                 "tags": n.tags or [],
                 "status": n.status or "active",
                 "metadata": n.metadata or {}}
            result.append(d)
        return result[:limit] if limit > 0 else result

    def get_relations(self, limit: int = 0, source_id: str | None = None,
                      target_id: str | None = None, type: str | None = None):
        """Compatibility wrapper for all_edges(). Now supports filtering."""
        edges = self.all_edges()
        result = []
        for e in edges:
            if source_id and e.src != source_id:
                continue
            if target_id and e.dst != target_id:
                continue
            if type and e.type.value != type:
                continue
            d = {"source_id": e.src, "target_id": e.dst,
                 "type": e.type.value if hasattr(e.type, 'value') else str(e.type),
                 "evidence": json.dumps({"rho_mechanism": e.rho.mechanism if e.rho else ""}),
                 "id": str(hash((e.src, e.dst, e.type)))}
            result.append(d)
        return result[:limit] if limit > 0 else result

    def get_atom(self, atom_id):
        """Compatibility: lookup atom by id from cc.db."""
        nodes = self.all_nodes()
        for n in nodes:
            if str(n.id) == str(atom_id):
                return {"id": n.id, "type": str(n.type), "title": n.title,
                        "content": n.content or n.summary or "{}",
                        "tags": n.tags or [],
                        "status": n.status or "active",
                        "metadata": n.metadata or {}}
        return None

    def get_atoms_index(self) -> dict:
        """Return structure index of the CC graph (shape summary, no full data).

        Used for progressive discovery — agents see what types exist, what's
        missing, orphan counts, and tag vocabulary without reading all atoms.
        """
        atoms = self.get_atoms()
        relations = self.get_relations()

        type_counts: dict[str, int] = {}
        for a in atoms:
            t = a.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1

        related_ids: set[str] = set()
        for r in relations:
            related_ids.add(str(r.get("source_id", "")))
            related_ids.add(str(r.get("target_id", "")))

        all_ids: set[str] = {str(a.get("id", "")) for a in atoms}
        orphan_count = len(all_ids - related_ids)

        rel_type_counts: dict[str, int] = {}
        for r in relations:
            t = r.get("type", "unknown")
            rel_type_counts[t] = rel_type_counts.get(t, 0) + 1

        all_tags: set[str] = set()
        for a in atoms:
            for tag in a.get("tags", []):
                all_tags.add(str(tag))

        all_known_types = {"fact", "method", "theorem", "verification",
                           "hypothesis", "observation", "component", "experiment"}
        missing_types = sorted(all_known_types - set(type_counts.keys()))

        all_known_rels = {"validates", "contradicts", "derives", "boundary_of",
                          "motivates", "specializes", "compares_to", "causes",
                          "implements"}
        missing_rels = sorted(all_known_rels - set(rel_type_counts.keys()))

        return {
            "total_atoms": len(atoms),
            "type_counts": type_counts,
            "missing_atom_types": missing_types,
            "total_relations": len(relations),
            "relation_type_counts": rel_type_counts,
            "missing_relation_types": missing_rels,
            "orphan_atom_count": orphan_count,
            "tag_vocabulary": sorted(all_tags),
            "empty": len(atoms) == 0,
        }

    def update_atom_metadata(self, atom_id: str, updates: dict) -> bool:
        """Update metadata for a single atom. Merges updates into existing metadata JSON.

        Returns True if atom was found and updated.
        """
        row = self.conn.execute(
            "SELECT metadata FROM nodes WHERE id = ?", (str(atom_id),)
        ).fetchone()
        if row is None:
            return False
        meta = json.loads(row[0]) if row[0] else {}
        meta.update(updates)
        meta.setdefault("updated_at_iso", datetime.now(timezone.utc).isoformat())
        self.conn.execute(
            "UPDATE nodes SET metadata = ?, embedding = NULL WHERE id = ?",
            (json.dumps(meta, ensure_ascii=False), str(atom_id)),
        )
        return True

    def tag_atoms_by_phase(self, iteration: int, phase: str, updates: dict) -> int:
        """Bulk-update metadata on all atoms matching iteration and phase.

        Returns count of updated atoms.
        """
        atoms = self.get_atoms()
        count = 0
        for a in atoms:
            meta = a.get("metadata", {})
            if meta.get("iter") == iteration and meta.get("phase") == phase:
                if self.update_atom_metadata(a["id"], updates):
                    count += 1
        if count > 0:
            self.commit()
        return count

    def tag_atoms_by_iteration(self, iteration: int, updates: dict) -> int:
        """Bulk-update metadata on ALL atoms matching iteration (all phases).

        Used by jump_to_plan to mark an entire iteration as complete or rolled back.
        """
        atoms = self.get_atoms()
        count = 0
        for a in atoms:
            meta = a.get("metadata", {})
            if meta.get("iter") == iteration:
                if self.update_atom_metadata(a["id"], updates):
                    count += 1
        if count > 0:
            self.commit()
        return count

class ValidationError(Exception):
    """Raised when post-validation fails at commit time."""
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Validation failed ({len(errors)} errors): {'; '.join(errors[:5])}")

# Backward compatibility alias
ClaimChain = ClaimChainV2
