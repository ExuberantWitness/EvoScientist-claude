"""W3 方案方向 Handler — 复用 W2 的 4-Persona + Elo 流程，phase-specific 维度。"""
from __future__ import annotations

from pes_controller.phases import register_handler
from pes_controller.phases.w2_handler import W2Handler

PHASE = "W3 方案方向"


@register_handler(PHASE)
class W3Handler(W2Handler):
    """W3 inherits W2's full pipeline. Elo picks up W3 dimensions via phase_label."""
    phase_label = PHASE
