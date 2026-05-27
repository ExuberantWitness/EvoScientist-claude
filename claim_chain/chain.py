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
                CHECK (type IN ('method', 'bottleneck', 'paper')),
    paper_id    TEXT,
    summary     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    -- SGT-MCTS pre-allocated fields
    embedding   BLOB
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


class ClaimChainV2:
    """SQLite-backed Intern-Atlas compliant Claim Chain."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    # ── Connection Management ──

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(SCHEMA)
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── CRUD: Nodes ──

    def add_node(self, node: Node) -> Node:
        """Insert a node. Returns the node (unchanged)."""
        self.conn.execute(
            "INSERT OR IGNORE INTO nodes (id, title, type, paper_id, summary, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (node.id, node.title, node.type, node.paper_id,
             node.summary, node.created_at.isoformat()),
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
            "SELECT id, title, type, paper_id, summary, created_at FROM nodes WHERE id = ?",
            (node_id,),
        ).fetchone()
        if row is None:
            return None
        # Load addresses
        addrs = self.conn.execute(
            "SELECT bottleneck_id FROM node_addresses WHERE node_id = ?", (node_id,)
        ).fetchall()
        return Node(
            id=row[0], title=row[1], type=row[2], paper_id=row[3],
            summary=row[4],
            addresses=[a[0] for a in addrs],
            created_at=datetime.fromisoformat(row[5]),
        )

    def all_nodes(self) -> list[Node]:
        rows = self.conn.execute(
            "SELECT id, title, type, paper_id, summary, created_at FROM nodes ORDER BY created_at"
        ).fetchall()
        nodes = []
        for r in rows:
            addrs = self.conn.execute(
                "SELECT bottleneck_id FROM node_addresses WHERE node_id = ?", (r[0],)
            ).fetchall()
            nodes.append(Node(
                id=r[0], title=r[1], type=r[2], paper_id=r[3],
                summary=r[4],
                addresses=[a[0] for a in addrs],
                created_at=datetime.fromisoformat(r[5]),
            ))
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
                 metadata: dict | None = None) -> dict:
        """Backward-compatible API mirroring claim_chain.py add_atom().

        Converts v1-style atom dict to v2 Node + optional bottleneck addresses.
        """
        import time
        from datetime import datetime, timezone

        node_id = metadata.get("id") if metadata else None
        if not node_id:
            node_id = f"node_{int(time.time() * 1000)}"

        node = Node(
            id=str(node_id),
            title=title,
            type=type if type in ("method", "bottleneck", "paper") else "method",
            summary=content[:500] if content else "",
            addresses=metadata.get("addresses", []) if metadata else [],
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
            "metadata": metadata or {},
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
            rho = Rho(
                bottleneck=bottleneck_id,
                mechanism=metadata.get("mechanism", evidence or ""),
                tradeoff=metadata.get("tradeoff", ""),
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


class ValidationError(Exception):
    """Raised when post-validation fails at commit time."""
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Validation failed ({len(errors)} errors): {'; '.join(errors[:5])}")

# Backward compatibility alias
ClaimChain = ClaimChainV2
