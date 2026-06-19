"""Base Phase Handler — 所有 Phase Handler 的抽象基类。

每个 Phase（W2, W3, ..., W8）实现一个 handler 子类。
Handler 的 build_step() 方法负责执行当前 step 并返回 StepResult。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pes_controller.types import StepResult

logger = logging.getLogger(__name__)


class BasePhaseHandler(ABC):
    """Phase Handler 基类。

    子类必须：
    1. 设置 chain_steps: list[str] — 该 phase 的 step 名称列表
    2. 实现 build_step(step_name) — 执行指定 step

    Handler 通过构造函数接收共享的 executor、llm_client、tavily_client。
    """

    chain_steps: list[str] = []
    phase_label: str = ""  # Set by subclasses (e.g., "W2 问题分析")

    def __init__(
        self,
        executor: Any,     # SkillExecutor
        llm_client: Any,    # LLMClient
        tavily_client: Any,  # TavilyClient | None
        state: dict,
    ):
        self.executor = executor
        self.llm_client = llm_client
        self.tavily_client = tavily_client
        self.state = state

    @abstractmethod
    def build_step(self, step_name: str) -> StepResult:
        """执行当前 step，返回 StepResult。"""
        ...

    def _ws(self) -> Path:
        """获取 workspace 目录。"""
        return Path(self.state.get("workspace_dir", "."))

    def _step_index(self) -> int:
        """获取当前 step 索引。"""
        return self.state.get("sub_loop_step", 0) - 1

    def _research_topic(self) -> str:
        return self.state.get("research_topic", "")

    def _venue(self) -> str:
        return self.state.get("venue", "ICLR")

    def _session_id(self) -> str:
        return self.state.get("session_id", "")

    def _feedback(self) -> str:
        return self.state.get("iteration_feedback", "")
