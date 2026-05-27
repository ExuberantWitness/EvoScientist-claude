"""Intern-Atlas (2604.28158) Taxonomy: 7 edge types + 14 bottleneck categories.

This is the SINGLE SOURCE OF TRUTH for edge types and bottleneck categories.
All other modules (claim_chain_v2, vault_manager, validation) import from here.
"""

from enum import Enum


# ── §3.2: Seven Core Edge Types ──

class EdgeType(str, Enum):
    """Seven core edge types per Intern-Atlas §3.2."""
    EXTENDS       = "extends"        # Strong causal: method B builds on method A
    IMPROVES      = "improves"       # Strong causal: addresses a bottleneck
    REPLACES      = "replaces"       # Strong causal: supersedes an older method
    ADAPTS        = "adapts"         # Strong causal: cross-domain adaptation
    USES_COMPONENT = "uses_component"  # Weak: uses a sub-component
    COMPARES      = "compares"       # Weak: empirical comparison
    BACKGROUND    = "background"     # None: contextual reference


# §3.2: Strong causal subset — used for evolution chain BFS
STRONG_CAUSAL = frozenset({
    EdgeType.EXTENDS,
    EdgeType.IMPROVES,
    EdgeType.REPLACES,
    EdgeType.ADAPTS,
})


# ── §3.1: 14 Bottleneck Categories ──

class BottleneckCategory(str, Enum):
    """14 bottleneck categories per Intern-Atlas §3.1."""
    OVERESTIMATION_BIAS      = "overestimation_bias"
    TRAINING_INSTABILITY     = "training_instability"
    SAMPLE_INEFFICIENCY      = "sample_inefficiency"
    EXPLORATION_INSUFFICIENT = "exploration_insufficient"
    CONVERGENCE_SLOW         = "convergence_slow"
    HYPERPARAMETER_SENSITIVITY = "hyperparameter_sensitivity"
    GENERALIZATION_GAP       = "generalization_gap"
    COMPUTATIONAL_COST       = "computational_cost"
    REWARD_SPARSITY          = "reward_sparsity"
    MULTI_OBJECTIVE_CONFLICT = "multi_objective_conflict"
    DISTRIBUTIONAL_SHIFT     = "distributional_shift"
    GRADIENT_INTERFERENCE    = "gradient_interference"
    REPRESENTATION_COLLAPSE  = "representation_collapse"
    CREDIT_ASSIGNMENT_LONG   = "credit_assignment_long"


# Set for fast membership checks (backward compat with vault_manager)
BOTTLENECK_CATEGORIES = frozenset(b.value for b in BottleneckCategory)


# ── Confidence Tiers (Graphify pattern) ──

class Confidence(str, Enum):
    """3-tier confidence per Intern-Atlas + Graphify."""
    EXTRACTED   = "EXTRACTED"    # From experiment data / code / paper excerpt
    INFERRED    = "INFERRED"     # LLM inference backed by data
    SPECULATIVE = "SPECULATIVE"  # LLM conjecture, no data — does NOT enter CC


# ── Edge Type Mapping (old 9 → new 7) ──
# Used by migration script. "DROP" means the old type has no paper-compliant equivalent.

OLD_TO_NEW_EDGE = {
    "motivates":     "DROP",           # No paper equivalent — discard or log
    "derives":       EdgeType.EXTENDS,  # "A derives from B" ≈ "A extends B"
    "validates":     "DROP",           # Empirical result → store in ρ(e).confidence
    "contradicts":   "DROP",           # Negative result → store as ρ(e).tradeoff note
    "implements":    EdgeType.USES_COMPONENT,  # "A implements B" ≈ uses B's component
    "compares_to":   EdgeType.COMPARES,
    "causes":        EdgeType.IMPROVES,  # "A causes improvement" ≈ improves
    "boundary_of":   "DROP",           # Meta-relation → store in node.summary
    "specializes":   EdgeType.EXTENDS,  # "A specializes B" ≈ extends
}
