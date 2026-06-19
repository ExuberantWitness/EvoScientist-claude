"""Phase Handler 注册表。

自动注册所有 handler 子类。controller.py 通过 get_handler(phase) 获取。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pes_controller.phases.base import BasePhaseHandler

_HANDLER_REGISTRY: dict[str, type[BasePhaseHandler]] = {}


def register_handler(phase: str):
    """装饰器：注册 Phase Handler 类。"""
    def decorator(cls):
        _HANDLER_REGISTRY[phase] = cls
        return cls
    return decorator


def get_handler(phase: str) -> type[BasePhaseHandler] | None:
    """获取 phase 对应的 handler 类。"""
    # 延迟导入所有 handler 模块（触发注册）
    _ensure_loaded()
    return _HANDLER_REGISTRY.get(phase)


def get_all_handlers() -> dict[str, type[BasePhaseHandler]]:
    """获取所有已注册的 handler。"""
    _ensure_loaded()
    return dict(_HANDLER_REGISTRY)


_loaded = False


def _ensure_loaded():
    """确保所有 handler 模块已导入（触发 @register_handler 装饰器）。"""
    global _loaded
    if _loaded:
        return
    _loaded = True

    # 导入所有 handler 模块
    from pes_controller.phases import (
        w1_handler,
        w2_handler,
        w3_handler,
        w4_handler,
        w5_handler,
        w6_handler,
        w7_1_handler,
        w7_2_handler,
        w7_3_handler,
        w7_4_handler,
        w7_5_handler,
        w8_handler,
    )
