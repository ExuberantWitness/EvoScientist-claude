"""Middleware package for EvoScientist.

Re-exports middleware classes and factory functions so that existing
``from EvoScientist.middleware import X`` imports continue to work.
"""

from .memory import (
    EvoMemoryMiddleware,
    EvoMemoryState,
    ExtractedMemory,
    create_memory_middleware,
)
from .tool_error_handler import ToolErrorHandlerMiddleware

__all__ = [
    "EvoMemoryMiddleware",
    "EvoMemoryState",
    "ExtractedMemory",
    "ToolErrorHandlerMiddleware",
    "create_memory_middleware",
]
