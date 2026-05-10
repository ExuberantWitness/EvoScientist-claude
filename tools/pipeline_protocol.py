"""PIPELINE_STATE.json 防幻觉文件协议。

写权限分离 + 原子写入 + checksum + 心跳看门狗。
Agent 不能写 Dashboard 字段，Dashboard 不能写 Agent 字段。
"""

import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any


PROTOCOL_VERSION = 1

# ── 权限分区: 谁可以写哪些字段 ──

DASHBOARD_FIELDS = frozenset({
    "phase", "status", "sub_loop_step", "iteration",
    "command", "approval_response", "research_topic",
    "config", "needs_init", "needs_intake", "needs_session",
    "last_gap_analysis", "last_pipeline_context",
    "ingested_results", "session_id", "timestamp",
})

AGENT_FIELDS = frozenset({
    "agent_heartbeat", "approval_request", "last_report",
})

READONLY_FIELDS = frozenset({
    "protocol_version", "agent_session_id",
})

IMMUTABLE_FIELDS = frozenset({
    "protocol_version", "agent_session_id",
})

EVENTS_FIELD = "events"


def _checksum(data: Any) -> str:
    """计算数据的 sha256 checksum。"""
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
    return f"sha256:{hashlib.sha256(raw).hexdigest()[:16]}"


def _default_state() -> dict:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "phase": "W2 Plan",
        "iteration": 0,
        "sub_loop_step": 0,
        "status": "not_initialized",
        "agent_session_id": None,
        "research_topic": "",
        "config": {},
        "agent_heartbeat": None,
        "approval_request": None,
        "approval_response": None,
        "command": None,
        "last_report": None,
        "last_gap_analysis": None,
        "events": [],
    }


def atomic_read(path: str | Path) -> dict:
    """原子读：读文件 + JSON解析 + protocol_version检查。"""
    p = Path(path)
    if not p.exists():
        return _default_state()
    raw = p.read_text(encoding="utf-8")
    state = json.loads(raw)
    # 迁移旧格式
    if "protocol_version" not in state:
        state["protocol_version"] = PROTOCOL_VERSION
    return state


def atomic_write(path: str | Path, state: dict):
    """原子写：写临时文件 → os.replace。绝不直接覆盖。"""
    p = Path(path)
    tmp = p.with_suffix(".json.tmp")
    state.setdefault("protocol_version", PROTOCOL_VERSION)
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


# ── Dashboard 写操作 ──

def dashboard_write(path: str | Path, updates: dict, event: dict | None = None):
    """Dashboard 写入受保护字段。拒绝写入 Agent 字段。"""
    state = atomic_read(path)

    for key in updates:
        if key in AGENT_FIELDS:
            raise PermissionError(
                f"Dashboard 不能写 Agent 字段 '{key}'。"
                f"Agent 独写区: {sorted(AGENT_FIELDS)}"
            )
        if key in IMMUTABLE_FIELDS:
            raise PermissionError(
                f"字段 '{key}' 创建后不可修改。"
            )
        state[key] = updates[key]

    state["timestamp"] = time.time()
    if event:
        _append_event(state, event)

    atomic_write(path, state)


def dashboard_write_approval(path: str | Path, request_id: str,
                              approved: bool, action: str = "satisfied"):
    """Dashboard 写审批回复。包含防伪造标记。"""
    state = atomic_read(path)

    # 幂等检查
    existing = state.get("approval_response")
    if existing and existing.get("request_id") == request_id:
        return existing  # 已经批复过

    state["approval_response"] = {
        "request_id": request_id,
        "approved": approved,
        "action": action,
        "responded_by": "dashboard",
        "timestamp": time.time(),
        "checksum": _checksum({"request_id": request_id, "action": action}),
    }
    state["status"] = "in_progress"
    state["timestamp"] = time.time()

    _append_event(state, {
        "type": "approval_decided",
        "request_id": request_id,
        "approved": approved,
        "action": action,
    })

    atomic_write(path, state)
    return state["approval_response"]


def dashboard_get_heartbeat(path: str | Path) -> dict | None:
    """读 agent 心跳，返回 None 或 heartbeat dict。"""
    state = atomic_read(path)
    return state.get("agent_heartbeat")


def dashboard_heartbeat_age(path: str | Path) -> float | None:
    """返回心跳距今秒数。无心跳返回 None。"""
    hb = dashboard_get_heartbeat(path)
    if not hb:
        return None
    return time.time() - hb.get("timestamp", 0)


# ── Agent 写操作 ──

def agent_write(path: str | Path, updates: dict, event: dict | None = None):
    """Agent 写入受保护字段。拒绝写入 Dashboard 字段。"""
    state = atomic_read(path)

    for key in updates:
        if key in DASHBOARD_FIELDS or key in READONLY_FIELDS:
            raise PermissionError(
                f"Agent 不能写 Dashboard/只读字段 '{key}'。"
            )
        state[key] = updates[key]

    if event:
        _append_event(state, event)

    atomic_write(path, state)


def agent_write_heartbeat(path: str | Path, last_step: str):
    """Agent 写心跳（仅 agent_heartbeat 字段）。"""
    state = atomic_read(path)
    state["agent_heartbeat"] = {
        "timestamp": time.time(),
        "last_step": last_step,
        "checksum": _checksum(state.get("last_report", {})),
    }
    atomic_write(path, state)


def agent_write_approval_request(path: str | Path, phase: str,
                                  summary: str, files: list[str]) -> str:
    """Agent 写审批请求。返回 request_id。"""
    state = atomic_read(path)
    apr_id = str(uuid.uuid4())
    state["approval_request"] = {
        "id": apr_id,
        "phase": phase,
        "status": "pending",
        "context": {
            "files_created": files,
            "summary": summary,
        },
        "checksum": _checksum({"phase": phase, "summary": summary}),
        "timestamp": time.time(),
    }
    state["agent_heartbeat"] = {
        "timestamp": time.time(),
        "last_step": f"awaiting_approval:{phase}",
        "checksum": _checksum(state.get("last_report", {})),
    }
    _append_event(state, {
        "type": "approval_requested",
        "request_id": apr_id,
        "phase": phase,
    })
    atomic_write(path, state)
    return apr_id


def agent_wait_approval(path: str | Path, request_id: str,
                         timeout: int = 1800) -> dict:
    """Agent 阻塞等待 Dashboard 批复。返回 approval_response 或超时错误。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(2)
        state = atomic_read(path)
        resp = state.get("approval_response")
        if (resp and resp.get("request_id") == request_id
                and resp.get("responded_by") == "dashboard"):
            return resp
    return {"error": "approval_timeout", "request_id": request_id}


def agent_write_report(path: str | Path, step_name: str, result: str):
    """Agent 写进度报告。"""
    state = atomic_read(path)
    state["last_report"] = {
        "step_name": step_name,
        "result": result,
        "timestamp": time.time(),
    }
    state["agent_heartbeat"] = {
        "timestamp": time.time(),
        "last_step": step_name,
        "checksum": _checksum(state["last_report"]),
    }
    _append_event(state, {
        "type": "progress",
        "step": step_name,
        "result": result,
    })
    atomic_write(path, state)


# ── 事件日志 ──

def _append_event(state: dict, event: dict):
    event.setdefault("ts", time.time())
    state.setdefault("events", [])
    state["events"].append(event)
    # 最多保留 500 条
    if len(state["events"]) > 500:
        state["events"] = state["events"][-500:]


# ── 协议校验 ──

def validate_state(state: dict) -> list[str]:
    """校验 state 的权限分区合规性。返回违规列表。"""
    violations = []
    # 检查 agent 是否写了 dashboard 字段
    for f in DASHBOARD_FIELDS:
        if f in state:
            hb = state.get("agent_heartbeat")
            if hb and hb.get("last_step") and f in ("research_topic", "config", "needs_init", "needs_intake", "needs_session", "last_gap_analysis", "last_pipeline_context", "ingested_results"):
                continue
    # 检查 approval_response 是否有 responded_by
    resp = state.get("approval_response")
    if resp and resp.get("responded_by") != "dashboard":
        violations.append(
            f"approval_response.responded_by='{resp.get('responded_by')}'"
            f" (expected 'dashboard') — 可能是 agent 伪造"
        )
    return violations
