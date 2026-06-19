"""PES Controller - Pipeline Evolution System controller layer.

Default PESController is now the v5 lightweight dispatcher.
Legacy controller available as PESControllerLegacy if needed.
"""

# v5 lightweight dispatcher (default)
from pes_controller.controller_v5 import (
    PESController,
    PHASE_INTAKE,
    PHASE_PLAN_1, PHASE_PLAN_2, PHASE_IDEATE, PHASE_CODE,
    PHASE_ANALYZE,
    PHASE_WRITE_PLAN, PHASE_WRITE_FIGURE, PHASE_WRITE_LATEX,
    PHASE_WRITE_COMPILE, PHASE_WRITE_IMPROVE,
    PHASE_REVIEW, PHASE_TERMINATED,
    AUTO_ADVANCE_PHASES, PHASES,
    TRANSITIONS, CHAIN_STEPS, FOUR_PERSONA_AGENTS,
    AGENT_ROLES, PRODUCT_SPECS,
)

# Backward compat aliases
PHASE_WRITE = PHASE_WRITE_PLAN

# Legacy controller (4000-line) — only import on demand
def __getattr__(name):
    if name == "PESControllerLegacy":
        from pes_controller.controller import PESController as _Legacy
        return _Legacy
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
