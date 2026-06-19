"""W4 具体方案生成 Handler — 复用 W2 流程，phase-specific 维度。"""
from __future__ import annotations

from pes_controller.phases import register_handler
from pes_controller.phases.w2_handler import W2Handler

PHASE = "W4 具体方案生成"


@register_handler(PHASE)
class W4Handler(W2Handler):
    """W4 inherits W2's full pipeline with W4-specific Elo dimensions."""
    phase_label = PHASE
