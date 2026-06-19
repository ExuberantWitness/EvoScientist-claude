"""Flux-Insight PES Controller — 类型定义。

所有模块间数据契约的 dataclass 定义。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StepResult:
    """sub_loop() / PhaseHandler.build_step() 返回值。"""
    done: bool
    phase: str
    step: str
    step_index: int
    action: str
    data: dict = field(default_factory=dict)


@dataclass
class SkillResult:
    """SkillExecutor.execute() 返回值。"""
    success: bool
    files_written: list[str] = field(default_factory=list)
    actions_executed: list[dict] = field(default_factory=list)
    llm_response: str = ""
    raw_content: str = ""


@dataclass
class ActionResult:
    """命令执行结果。"""
    command: str
    returncode: int
    stdout: str
    stderr: str


@dataclass
class TransitionResult:
    """transition_phase() 返回值。"""
    transitioned: bool
    from_phase: str = ""
    to_phase: str = ""
    error: str = ""
    valid_targets: list[str] = field(default_factory=list)
    message: str = ""


@dataclass
class SSEEvent:
    """Dashboard SSE 事件。"""
    type: str
    data: dict
    phase: str = ""
    step: str = ""


@dataclass
class SkillConfig:
    """SKILL.md frontmatter 解析结果。"""
    name: str
    execution: str = "llm"       # "llm" | "python"
    handler: str = ""            # Python 函数路径 (execution=python 时)
    description: str = ""
    variables: list[dict] = field(default_factory=list)
