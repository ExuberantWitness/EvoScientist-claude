"""Pipeline Watchdog — Rule-based anomaly detection for the EvoScientist pipeline.

Monitors PIPELINE_STATE.json and session metadata on a configurable interval,
applying time-based, event-based, heartbeat-based, and lock-based rules.
Pushes alerts via EventBus SSE and writes watchdog_alerts to state.

Design principle: purely rule-based, no LLM calls. Detects clear anomalies
(stalls, timeouts, missing events, inconsistent state) independent of AI judgment.
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ── Rule thresholds (seconds) ──

# How long a phase may run before flagged
PHASE_MAX_DURATION: dict[str, int] = {
    "W2 Plan":      1800,   # 30 min
    "W3 Research":  3600,   # 60 min (includes literature search)
    "W3.5 Ideate":  1800,   # 30 min
    "W4 Code":      3600,   # 60 min (agent subprocess)
    "W5 Analyze":   1800,   # 30 min
    "W6 Write":     3600,   # 60 min (agent subprocess)
    "W7 Review":    2700,   # 45 min (agent subprocess)
}

# How long a step type may run before flagged
STEP_MAX_DURATION: dict[str, int] = {
    "run_step_pipeline":     300,   # 5 min (CC query + indexing + embedding)
    "multi_agent_discuss":   900,   # 15 min (3+ DeepSeek LLM calls)
    "elo_tournament":        300,   # 5 min (LLM judge calls)
    "evolution_memory":      120,   # 2 min (LLM distillation)
    "invoke_skill_code":    1800,   # 30 min (Agent SDK subprocess)
    "invoke_skill_write":   1800,   # 30 min (Agent SDK subprocess)
    "invoke_skill_review":  1200,   # 20 min (Agent SDK subprocess)
    "invoke_skill_research": 900,   # 15 min (literature search)
    "scan_islands_rubrics":   60,   # 1 min (local computation)
    "write_claim_chain":     120,   # 2 min
    "island_assign":          60,   # 1 min
}

# Agent SDK phases — these should have agent_heartbeat
AGENT_SDK_PHASES = frozenset({"W4 Code", "W6 Write", "W7 Review"})

# How long without any event before "stalled"
NO_EVENTS_STALL_SEC = 300        # 5 min

# How long without agent heartbeat before "agent dead" (agent phases only)
NO_HEARTBEAT_DEAD_SEC = 180      # 3 min

# How long an active_task lock may exist before "stale lock"
ACTIVE_TASK_STALE_SEC = 1800     # 30 min

# How long "awaiting_decision" may persist before nagging
AWAITING_DECISION_NAG_SEC = 600  # 10 min

# Minimum events expected for a multi_agent_discuss step
MIN_DISCUSS_EVENTS = 10

# Minimum sub-agents expected in a successful discuss
MIN_DISCUSS_SUBAGENTS = 2

# ── Alert severity ──

class Severity:
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class Alert:
    """A watchdog alert."""
    id: str
    severity: str          # info / warning / error
    category: str          # stall / timeout / heartbeat / lock / state
    message: str
    suggestion: str        # recommended action
    session_id: str
    phase: str = ""
    step: str = ""
    elapsed: float = 0.0
    threshold: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class SessionWatch:
    """Per-session tracking state for the watchdog."""
    session_id: str
    workspace: str
    last_event_count: int = 0
    last_event_at: float = 0.0
    last_heartbeat_at: float = 0.0
    last_heartbeat_step: str = ""
    last_phase: str = ""
    phase_started_at: float = 0.0
    last_step: str = ""
    step_started_at: float = 0.0
    last_status: str = ""
    status_since: float = 0.0
    active_task_type: str = ""
    active_task_started_at: float = 0.0
    alert_history: list[str] = field(default_factory=list)  # alert IDs already seen


class PipelineWatchdog:
    """Rule-based pipeline health monitor.

    Usage:
        watchdog = PipelineWatchdog(workspace_dir, event_bus, agent_manager)
        await watchdog.start()          # begins background scanning
        alerts = watchdog.check_now()   # one-shot check, returns alerts
        await watchdog.stop()           # stops background task
    """

    def __init__(
        self,
        workspace_dir: str,
        event_bus=None,          # EventBus for SSE push
        agent_manager=None,      # AgentManager for session access
        poll_interval: int = 20, # seconds between scans
        config_overrides: dict | None = None,
    ):
        self.workspace_dir = Path(workspace_dir)
        self._event_bus = event_bus
        self._agent_manager = agent_manager
        self.poll_interval = poll_interval
        self._task: asyncio.Task | None = None
        self._running = False
        self._sessions: dict[str, SessionWatch] = {}
        self._alerts: list[Alert] = []
        self._alert_count = 0
        self._workspaces: set[str] = set()  # Discovered workspaces

        # Threshold overrides
        self.phase_timeout = dict(PHASE_MAX_DURATION)
        self.step_timeout = dict(STEP_MAX_DURATION)
        if config_overrides:
            if "phase_timeout" in config_overrides:
                self.phase_timeout.update(config_overrides["phase_timeout"])
            if "step_timeout" in config_overrides:
                self.step_timeout.update(config_overrides["step_timeout"])

    # ── Public API ──

    async def start(self):
        """Start background scanning task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._scan_loop())
        logger.info(f"Watchdog started (poll={self.poll_interval}s)")

    async def stop(self):
        """Stop background scanning."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Watchdog stopped")

    def check_now(self) -> list[Alert]:
        """Run all checks synchronously across all discovered workspaces.
        Returns list of new alerts."""
        self._discover_workspaces()
        new_alerts = []
        for ws in self._workspaces:
            state = self._read_state(ws)
            if not state:
                continue
            new_alerts.extend(self._check_stall(state))
            new_alerts.extend(self._check_heartbeat(state))
            new_alerts.extend(self._check_phase_timeout(state))
            new_alerts.extend(self._check_step_timeout(state))
            new_alerts.extend(self._check_active_task_lock(state))
            new_alerts.extend(self._check_inconsistent_state(state))
            new_alerts.extend(self._check_agent_phases(state))
            new_alerts.extend(self._check_awaiting_decision(state))
            new_alerts.extend(self._check_discuss_health(state))

        self._alerts = new_alerts
        self._update_state_alerts(new_alerts)
        return new_alerts

    def get_alerts(self, limit: int = 50) -> list[dict]:
        """Get recent alert dicts."""
        alerts = sorted(self._alerts, key=lambda a: a.timestamp, reverse=True)
        return [_alert_to_dict(a) for a in alerts[:limit]]

    def get_stats(self) -> dict:
        """Get watchdog statistics."""
        sessions_info = {}
        for sid, sw in self._sessions.items():
            sessions_info[sid] = {
                "last_phase": sw.last_phase,
                "phase_elapsed": time.time() - sw.phase_started_at if sw.phase_started_at else 0,
                "last_step": sw.last_step,
                "step_elapsed": time.time() - sw.step_started_at if sw.step_started_at else 0,
                "last_event_at": sw.last_event_at,
                "events_since": time.time() - sw.last_event_at if sw.last_event_at else -1,
                "last_heartbeat_at": sw.last_heartbeat_at,
                "heartbeat_age": time.time() - sw.last_heartbeat_at if sw.last_heartbeat_at else -1,
                "active_task": sw.active_task_type,
                "task_elapsed": time.time() - sw.active_task_started_at if sw.active_task_started_at else 0,
            }
        return {
            "running": self._running,
            "poll_interval": self.poll_interval,
            "sessions_tracked": len(self._sessions),
            "total_alerts": self._alert_count,
            "active_alerts": len(self._alerts),
            "sessions": sessions_info,
        }

    # ── Background loop ──

    async def _scan_loop(self):
        """Periodic scan loop."""
        while self._running:
            try:
                new_alerts = self.check_now()
                for alert in new_alerts:
                    self._push_alert(alert)
            except Exception as e:
                logger.error(f"Watchdog scan error: {e}", exc_info=True)
            await asyncio.sleep(self.poll_interval)

    # ── Checks ──

    def _check_stall(self, state: dict) -> list[Alert]:
        """Detect stalled progress: no new events for too long."""
        alerts = []
        sid = state.get("session_id", "")
        if not sid:
            return alerts
        sw = self._get_or_create_watch(sid, state)
        events = state.get("events", [])
        event_count = len(events)

        if event_count > sw.last_event_count:
            sw.last_event_count = event_count
            sw.last_event_at = time.time()
        elif sw.last_event_at > 0:
            elapsed = time.time() - sw.last_event_at
            # Only alert if pipeline is in_progress (not idle or awaiting)
            status = state.get("status", "")
            phase = state.get("phase", "")
            if status == "in_progress" and elapsed > NO_EVENTS_STALL_SEC:
                sid_short = sid[:12]
                alerts.append(Alert(
                    id=f"stall_{sid_short}_{int(elapsed)}",
                    severity=Severity.WARNING,
                    category="stall",
                    message=f"Phase '{phase}' 无新事件 {elapsed:.0f}s (阈值 {NO_EVENTS_STALL_SEC}s)",
                    suggestion="检查 agent 是否存活，可能需要重启讨论或重置 active_task",
                    session_id=sid, phase=phase,
                    elapsed=elapsed, threshold=NO_EVENTS_STALL_SEC,
                ))
        return alerts

    def _check_heartbeat(self, state: dict) -> list[Alert]:
        """Check agent heartbeat for Agent SDK phases."""
        alerts = []
        phase = state.get("phase", "")
        if phase not in AGENT_SDK_PHASES:
            return alerts
        status = state.get("status", "")
        if status != "in_progress":
            return alerts

        sid = state.get("session_id", "")
        if not sid:
            return alerts
        sw = self._get_or_create_watch(sid, state)

        hb = state.get("agent_heartbeat")
        if hb:
            sw.last_heartbeat_at = hb.get("timestamp", 0)
            sw.last_heartbeat_step = hb.get("last_step", "")
            return alerts  # heartbeat is fresh

        # No heartbeat at all in agent phase
        if sw.last_heartbeat_at > 0:
            elapsed = time.time() - sw.last_heartbeat_at
        else:
            elapsed = time.time() - sw.phase_started_at if sw.phase_started_at else 0

        if elapsed > NO_HEARTBEAT_DEAD_SEC:
            sid_short = sid[:12]
            alerts.append(Alert(
                id=f"heartbeat_{sid_short}_{int(elapsed)}",
                severity=Severity.ERROR,
                category="heartbeat",
                message=f"Agent SDK 心跳丢失 {elapsed:.0f}s (阈值 {NO_HEARTBEAT_DEAD_SEC}s), phase={phase}",
                suggestion="Agent 子进程可能已崩溃。建议终止当前 phase 并重新执行。",
                session_id=sid, phase=phase,
                elapsed=elapsed, threshold=NO_HEARTBEAT_DEAD_SEC,
            ))
        return alerts

    def _check_phase_timeout(self, state: dict) -> list[Alert]:
        """Detect phases running beyond expected duration."""
        alerts = []
        phase = state.get("phase", "")
        status = state.get("status", "")
        if status != "in_progress":
            return alerts
        sid = state.get("session_id", "")
        if not sid:
            return alerts
        sw = self._get_or_create_watch(sid, state)

        threshold = self.phase_timeout.get(phase)
        if not threshold:
            return alerts

        elapsed = time.time() - sw.phase_started_at if sw.phase_started_at else 0
        if elapsed > threshold:
            sid_short = sid[:12]
            alerts.append(Alert(
                id=f"phase_timeout_{sid_short}_{phase.replace(' ','_')}",
                severity=Severity.WARNING,
                category="timeout",
                message=f"Phase '{phase}' 已运行 {elapsed:.0f}s (阈值 {threshold}s)",
                suggestion=f"检查 phase 是否卡住。可尝试跳过当前步骤或终止重建。",
                session_id=sid, phase=phase,
                elapsed=elapsed, threshold=threshold,
            ))
        return alerts

    def _check_step_timeout(self, state: dict) -> list[Alert]:
        """Detect individual steps running beyond expected duration."""
        alerts = []
        sid = state.get("session_id", "")
        if not sid:
            return alerts
        sw = self._get_or_create_watch(sid, state)

        # Infer current step from state
        current_step = self._infer_current_step(state)
        if not current_step:
            return alerts

        threshold = self.step_timeout.get(current_step)
        if not threshold:
            return alerts

        elapsed = time.time() - sw.step_started_at if sw.step_started_at else 0
        if elapsed > threshold:
            sid_short = sid[:12]
            alerts.append(Alert(
                id=f"step_timeout_{sid_short}_{current_step}",
                severity=Severity.WARNING,
                category="timeout",
                message=f"Step '{current_step}' 已运行 {elapsed:.0f}s (阈值 {threshold}s)",
                suggestion=f"此步骤可能卡住。建议检查 API 连通性或强制跳过。",
                session_id=sid, phase=state.get("phase", ""), step=current_step,
                elapsed=elapsed, threshold=threshold,
            ))
        return alerts

    def _check_active_task_lock(self, state: dict) -> list[Alert]:
        """Detect stale active_task locks."""
        alerts = []
        active = state.get("active_task")
        if not active:
            return alerts
        sid = active.get("session_id") or state.get("session_id", "")
        if not sid:
            return alerts

        started = active.get("started_at", 0)
        elapsed = time.time() - started
        if elapsed > ACTIVE_TASK_STALE_SEC:
            task_type = active.get("type", "unknown")
            sid_short = sid[:12]
            alerts.append(Alert(
                id=f"stale_lock_{sid_short}_{task_type}",
                severity=Severity.ERROR,
                category="lock",
                message=f"Active task '{task_type}' 锁已过期 {elapsed:.0f}s (阈值 {ACTIVE_TASK_STALE_SEC}s)",
                suggestion="任务可能已崩溃但锁未释放。建议手动清除 active_task 字段。",
                session_id=sid, phase=active.get("phase", ""), step=task_type,
                elapsed=elapsed, threshold=ACTIVE_TASK_STALE_SEC,
            ))
        return alerts

    def _check_inconsistent_state(self, state: dict) -> list[Alert]:
        """Detect logically inconsistent state."""
        alerts = []
        sid = state.get("session_id", "")
        status = state.get("status", "")
        phase = state.get("phase", "")

        # Status "in_progress" but no active_task and no events in 10 min
        events = state.get("events", [])
        active = state.get("active_task")
        if status == "in_progress" and not active and phase:
            if events:
                last_ts = events[-1].get("ts", 0)
                elapsed = time.time() - last_ts
            else:
                elapsed = 0
            if elapsed > 600 and phase not in AGENT_SDK_PHASES:
                sid_short = sid[:12]
                alerts.append(Alert(
                    id=f"orphan_progress_{sid_short}",
                    severity=Severity.WARNING,
                    category="state",
                    message=f"Status='in_progress' 但无 active_task 且 {elapsed:.0f}s 无事件，phase='{phase}'",
                    suggestion="状态可能不同步。建议重置 status 或触发下一步。",
                    session_id=sid, phase=phase,
                    elapsed=elapsed, threshold=600,
                ))

        # Phase is "已终止" but status is "in_progress"
        if phase == "已终止" and status == "in_progress":
            sid_short = sid[:12]
            alerts.append(Alert(
                id=f"terminated_inconsist_{sid_short}",
                severity=Severity.WARNING,
                category="state",
                message="Phase='已终止' 但 status='in_progress'，状态不一致",
                suggestion="将 status 设为 'terminated' 以保持一致。",
                session_id=sid, phase=phase,
            ))

        return alerts

    def _check_agent_phases(self, state: dict) -> list[Alert]:
        """Check agent SDK subprocess phases for expected behavior."""
        alerts = []
        phase = state.get("phase", "")
        if phase not in AGENT_SDK_PHASES:
            return alerts
        status = state.get("status", "")
        if status != "in_progress":
            return alerts

        sid = state.get("session_id", "")
        if not sid:
            return alerts

        # Check session's discuss/agent health
        if self._agent_manager:
            session = self._agent_manager.sessions.get(sid)
            if session:
                # If session status is "error", flag it
                if session.status == "error":
                    sid_short = sid[:12]
                    alerts.append(Alert(
                        id=f"agent_error_{sid_short}",
                        severity=Severity.ERROR,
                        category="state",
                        message=f"Agent session status='error' 在 phase='{phase}'",
                        suggestion=f"查看 session last_response 了解错误详情。可能需要重启 Agent SDK 子进程。",
                        session_id=sid, phase=phase,
                    ))

        return alerts

    def _check_awaiting_decision(self, state: dict) -> list[Alert]:
        """Nag when pipeline is stuck waiting for user decision."""
        alerts = []
        status = state.get("status", "")
        if status != "awaiting_decision":
            return alerts
        sid = state.get("session_id", "")
        if not sid:
            return alerts
        sw = self._get_or_create_watch(sid, state)

        elapsed = time.time() - sw.status_since if sw.status_since else 0
        if elapsed > AWAITING_DECISION_NAG_SEC:
            phase = state.get("phase", "")
            sid_short = sid[:12]
            alerts.append(Alert(
                id=f"awaiting_nag_{sid_short}",
                severity=Severity.INFO,
                category="state",
                message=f"等待用户决策已 {elapsed:.0f}s (phase='{phase}')",
                suggestion="请在 Dashboard 选择: Satisfied (进入下一 phase) / Unsatisfied (重试) / Terminate",
                session_id=sid, phase=phase,
                elapsed=elapsed, threshold=AWAITING_DECISION_NAG_SEC,
            ))
        return alerts

    def _check_discuss_health(self, state: dict) -> list[Alert]:
        """Check multi-agent discussion health via session events."""
        alerts = []
        sid = state.get("session_id", "")
        if not sid:
            return alerts

        active = state.get("active_task")
        if not active or active.get("type") != "evo_discuss":
            return alerts

        if not self._agent_manager:
            return alerts

        session = self._agent_manager.sessions.get(sid)
        if not session:
            return alerts

        event_count = len(session.events)
        subagent_count = len(session.sub_agents_used)
        elapsed = time.time() - active.get("started_at", 0)

        # Discussion running but too few events
        if elapsed > 300 and event_count < MIN_DISCUSS_EVENTS:
            sid_short = sid[:12]
            alerts.append(Alert(
                id=f"discuss_low_events_{sid_short}",
                severity=Severity.WARNING,
                category="stall",
                message=f"讨论运行 {elapsed:.0f}s 但仅 {event_count} 事件 (最少期望 {MIN_DISCUSS_EVENTS})",
                suggestion="Agent 可能无法正常调用 API。检查 DeepSeek API 连通性和 API key。",
                session_id=sid, phase=active.get("phase", ""), step="multi_agent_discuss",
                elapsed=elapsed, threshold=MIN_DISCUSS_EVENTS,
            ))

        # Discussion running long but too few sub-agents
        if elapsed > 600 and subagent_count < MIN_DISCUSS_SUBAGENTS:
            sid_short = sid[:12]
            alerts.append(Alert(
                id=f"discuss_few_agents_{sid_short}",
                severity=Severity.WARNING,
                category="stall",
                message=f"讨论运行 {elapsed:.0f}s 但仅 {subagent_count} 个 sub-agent (最少期望 {MIN_DISCUSS_SUBAGENTS})",
                suggestion="主 agent 可能未能成功委托 sub-agent。检查 agent 配置和 multi-agent 模型设置。",
                session_id=sid, phase=active.get("phase", ""), step="multi_agent_discuss",
                elapsed=elapsed, threshold=MIN_DISCUSS_SUBAGENTS,
            ))

        return alerts

    # ── Helpers ──

    def _discover_workspaces(self):
        """Discover workspaces from session registry and agent_manager sessions."""
        # From agent_manager sessions
        if self._agent_manager:
            for sid, session in self._agent_manager.sessions.items():
                ws = getattr(session, "workspace_dir", "")
                if ws and Path(ws).exists():
                    self._workspaces.add(ws)

        # From session registry files
        for base in [self.workspace_dir, Path.cwd()]:
            for name in [".evo_session_registry.json", "agent-manager/.evo_session_registry.json"]:
                rpath = base / name
                if rpath.exists():
                    try:
                        registry = json.loads(rpath.read_text(encoding="utf-8"))
                        for ws in registry.values():
                            if isinstance(ws, str) and Path(ws).exists():
                                self._workspaces.add(ws)
                    except Exception:
                        pass

        # Fallback: monitor workspace_dir itself
        if not self._workspaces and (self.workspace_dir / "PIPELINE_STATE.json").exists():
            self._workspaces.add(str(self.workspace_dir))

    def _read_state(self, workspace: str) -> dict:
        """Read PIPELINE_STATE.json from a workspace."""
        state_path = Path(workspace) / "PIPELINE_STATE.json"
        if not state_path.exists():
            return {}
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Watchdog failed to read state from {workspace}: {e}")
            return {}

    def _get_or_create_watch(self, sid: str, state: dict) -> SessionWatch:
        """Get or create per-session tracking."""
        if sid not in self._sessions:
            sw = SessionWatch(
                session_id=sid,
                workspace=str(self.workspace_dir),
            )
            self._sessions[sid] = sw

        sw = self._sessions[sid]

        # Track phase transitions
        phase = state.get("phase", "")
        if phase and phase != sw.last_phase:
            sw.last_phase = phase
            sw.phase_started_at = time.time()

        # Track status transitions
        status = state.get("status", "")
        if status and status != sw.last_status:
            sw.last_status = status
            sw.status_since = time.time()

        # Track step changes
        current_step = self._infer_current_step(state)
        if current_step and current_step != sw.last_step:
            sw.last_step = current_step
            sw.step_started_at = time.time()

        # Track active task
        active = state.get("active_task")
        if active:
            sw.active_task_type = active.get("type", "")
            sw.active_task_started_at = active.get("started_at", 0)

        return sw

    def _infer_current_step(self, state: dict) -> str:
        """Infer which step is currently executing from state."""
        # Check active_task first
        active = state.get("active_task")
        if active:
            task_type = active.get("type", "")
            if task_type == "evo_discuss":
                return "multi_agent_discuss"
            if task_type == "evo_run_tournament":
                return "elo_tournament"

        # Check sub_loop_step + phase → step chain
        phase = state.get("phase", "")
        step_idx = state.get("sub_loop_step", 0)

        from pes_controller import CHAIN_STEPS
        steps = CHAIN_STEPS.get(phase, [])
        if steps and step_idx < len(steps):
            return steps[step_idx]

        # Check if there's a command pending (for skill invocation)
        cmd = state.get("command")
        if cmd and cmd.get("status") in ("pending", "executing"):
            action = cmd.get("action", "")
            if action:
                return f"invoke_skill_{action}"

        return ""

    def _update_state_alerts(self, alerts: list[Alert]):
        """Write current alerts to PIPELINE_STATE.json for each workspace."""
        for ws in self._workspaces:
            try:
                state_path = Path(ws) / "PIPELINE_STATE.json"
                if not state_path.exists():
                    continue
                state = json.loads(state_path.read_text(encoding="utf-8"))
                # Only include alerts for sessions in this workspace
                ws_alerts = [
                    _alert_to_dict(a) for a in alerts[:20]
                    if a.session_id in self._sessions
                ]
                state["watchdog_alerts"] = ws_alerts
                tmp = state_path.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
                os.replace(tmp, state_path)
            except Exception as e:
                logger.warning(f"Watchdog failed to write alerts to {ws}: {e}")

    def _push_alert(self, alert: Alert):
        """Push alert to EventBus for SSE delivery."""
        self._alert_count += 1
        if self._event_bus:
            try:
                self._event_bus.publish(alert.session_id, {
                    "type": "watchdog_alert",
                    "timestamp": time.time(),
                    "data": _alert_to_dict(alert),
                })
            except Exception as e:
                logger.warning(f"Watchdog failed to push alert to EventBus: {e}")

    def _dedup_and_filter(self, alert: Alert, sw: SessionWatch) -> bool:
        """Return True if this is a new alert (not already seen recently)."""
        if alert.id in sw.alert_history:
            return False
        sw.alert_history.append(alert.id)
        if len(sw.alert_history) > 100:
            sw.alert_history = sw.alert_history[-100:]
        return True


# ── Alert helpers ──

def _alert_to_dict(a: Alert) -> dict:
    return {
        "id": a.id,
        "severity": a.severity,
        "category": a.category,
        "message": a.message,
        "suggestion": a.suggestion,
        "session_id": a.session_id,
        "phase": a.phase,
        "step": a.step,
        "elapsed": round(a.elapsed, 1),
        "threshold": a.threshold,
        "timestamp": a.timestamp,
    }


# ── Standalone entry point (for testing / cron) ──

def standalone_check(workspace_dir: str) -> list[dict]:
    """Run a one-shot watchdog check without dashboard integration.
    Useful for CLI or cron-based monitoring.
    """
    watchdog = PipelineWatchdog(workspace_dir)
    alerts = watchdog.check_now()
    return [_alert_to_dict(a) for a in alerts]


if __name__ == "__main__":
    import sys
    ws = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    alerts = standalone_check(ws)
    if alerts:
        print(f"=== {len(alerts)} alert(s) ===")
        for a in alerts:
            sev_icon = {"info": "ℹ", "warning": "⚠", "error": "❌"}.get(a["severity"], "?")
            print(f"  {sev_icon} [{a['category']}] {a['message']}")
            print(f"    → {a['suggestion']}")
    else:
        print("No alerts — pipeline looks healthy.")
