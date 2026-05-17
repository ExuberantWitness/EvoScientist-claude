"""Intern-Atlas (2604.28158) Data Models: Rho, Edge, Node.

Rho is frozen (immutable) — modifications create new revisions.
Edge validates that strong causal edges carry Rho evidence.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from taxonomy import EdgeType, BottleneckCategory, STRONG_CAUSAL


# ── ρ(e) Evidence Record (§3.3) ──

@dataclass(frozen=True)
class Rho:
    """Immutable 4-tuple evidence record per edge.

    Frozen by design: to "modify", create a new Rho and supersede the old edge.
    This preserves history for SGT-MCTS lineage reconstruction.
    """
    bottleneck: str          # FK to BottleneckCategory (14 values)
    mechanism: str           # Free text, must be ≥10 chars
    tradeoff: str            # Free text, must be non-empty
    confidence: float        # [0.0, 1.0]

    def __post_init__(self):
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0,1], got {self.confidence}")
        if len(self.mechanism.strip()) < 10:
            raise ValueError(
                f"mechanism too short (<10 chars): '{self.mechanism[:50]}...'"
            )
        if not self.tradeoff.strip():
            raise ValueError("tradeoff must be non-empty")

    def to_dict(self) -> dict:
        return {
            "bottleneck": self.bottleneck,
            "mechanism": self.mechanism,
            "tradeoff": self.tradeoff,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Rho":
        return cls(
            bottleneck=d["bottleneck"],
            mechanism=d["mechanism"],
            tradeoff=d["tradeoff"],
            confidence=float(d["confidence"]),
        )


# ── Edge (§3.2) ──

@dataclass(frozen=True)
class Edge:
    """Immutable typed relation between two nodes.

    Strong causal edges (extends, improves, replaces, adapts) MUST carry Rho.
    Weak/reference edges MAY carry Rho.
    """
    src: str
    dst: str
    type: EdgeType
    rho: Optional[Rho] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def validate(self) -> list[str]:
        """Return list of violations (empty = valid)."""
        errors = []
        if self.type in STRONG_CAUSAL and self.rho is None:
            errors.append(
                f"Strong causal edge '{self.type.value}' requires ρ(e) evidence"
            )
        if self.src == self.dst:
            errors.append("Self-loops are not allowed")
        return errors

    def to_dict(self) -> dict:
        d = {
            "src": self.src,
            "dst": self.dst,
            "type": self.type.value,
            "created_at": self.created_at.isoformat(),
        }
        if self.rho:
            d["rho"] = self.rho.to_dict()
        return d


# ── Node (§3.1) ──

@dataclass
class Node:
    """A node in the claim graph: method, bottleneck, or paper."""
    id: str
    title: str
    type: str = "method"         # "method" | "bottleneck" | "paper"
    paper_id: Optional[str] = None
    summary: str = ""
    addresses: list[str] = field(default_factory=list)  # bottleneck IDs
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "type": self.type,
            "paper_id": self.paper_id,
            "summary": self.summary,
            "addresses": self.addresses,
            "created_at": self.created_at.isoformat(),
        }
