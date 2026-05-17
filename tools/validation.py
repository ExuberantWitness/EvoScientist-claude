"""Intern-Atlas (2604.28158) Deterministic Post-Validation — 4 Rules.

Runs before every ClaimChainV2.commit(). All rules are pure SQL queries
against the SQLite connection. Zero LLM involvement.

Rules:
  R1: Reference Integrity — all edge.src / edge.dst exist in nodes
  R2: Temporal Consistency — edge.created_at ≥ max(node.created_at)
  R3: No Contradictions — (A→replaces→B) and (A→extends→B) cannot coexist
  R4: Rho Completeness — strong causal edges MUST have full ρ(e) 4-tuple
"""

import sqlite3
from taxonomy import STRONG_CAUSAL


def run_post_validation(conn: sqlite3.Connection) -> list[str]:
    """Run all 4 rules. Returns list of violation messages (empty = pass)."""
    errors = []
    errors.extend(_check_temporal_consistency(conn))
    errors.extend(_check_no_contradictions(conn))
    errors.extend(_check_rho_completeness(conn))
    # R1 (reference integrity) is enforced by FK constraints;
    # this is a soft check for diagnostics
    errors.extend(_check_reference_integrity(conn))
    return errors


def _check_reference_integrity(conn: sqlite3.Connection) -> list[str]:
    """R1: All edge endpoints must reference existing nodes."""
    rows = conn.execute("""
        SELECT e.id, e.src, e.dst FROM edges e
        WHERE e.src NOT IN (SELECT id FROM nodes)
           OR e.dst NOT IN (SELECT id FROM nodes)
    """).fetchall()
    return [f"R1 (reference): edge {r[0]} has dangling endpoint ({r[1]}→{r[2]})"
            for r in rows]


def _check_temporal_consistency(conn: sqlite3.Connection) -> list[str]:
    """R2: edge.created_at >= max(src.created_at, dst.created_at)."""
    rows = conn.execute("""
        SELECT e.id, e.created_at, s.created_at AS src_ts, d.created_at AS dst_ts
        FROM edges e
        JOIN nodes s ON e.src = s.id
        JOIN nodes d ON e.dst = d.id
        WHERE e.created_at < s.created_at
           OR e.created_at < d.created_at
    """).fetchall()
    return [
        f"R2 (temporal): edge {r[0]} created {r[1]} before "
        f"src({r[2]})/dst({r[3]})" for r in rows
    ]


def _check_no_contradictions(conn: sqlite3.Connection) -> list[str]:
    """R3: Cannot have both (A→replaces→B) and (A→extends→B) simultaneously."""
    rows = conn.execute("""
        SELECT e1.src, e1.dst
        FROM edges e1
        JOIN edges e2 ON e1.src = e2.src AND e1.dst = e2.dst
        WHERE e1.type = 'replaces' AND e2.type = 'extends'
          AND e1.superseded_by IS NULL AND e2.superseded_by IS NULL
    """).fetchall()
    return [
        f"R3 (contradiction): {s} both replaces and extends {d}"
        for s, d in rows
    ]


def _check_rho_completeness(conn: sqlite3.Connection) -> list[str]:
    """R4: Strong causal edges MUST carry complete ρ(e) 4-tuple."""
    strong_types = tuple(e.value for e in STRONG_CAUSAL)
    placeholders = ",".join("?" * len(strong_types))
    rows = conn.execute(
        f"""SELECT id, type FROM edges
        WHERE type IN ({placeholders})
          AND superseded_by IS NULL
          AND (rho_bottleneck IS NULL
            OR rho_mechanism IS NULL
            OR rho_tradeoff IS NULL
            OR rho_confidence IS NULL)""",
        strong_types,
    ).fetchall()
    return [
        f"R4 (ρ missing): edge {r[0]} ({r[1]}) lacks complete ρ(e) evidence"
        for r in rows
    ]
