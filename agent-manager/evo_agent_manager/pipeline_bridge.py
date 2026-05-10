"""PipelineBridge — Unix Socket server 对标 Ping Island HookSocketServer + ApprovalCoordinator.

接收 AgentManager HookEmitter 发来的生命周期事件:
- 更新 Pipeline 状态 (锁定/解锁步骤)
- 推送 SSE 事件到浏览器
- 对阻塞事件 (expects_response) 等待 Dashboard 决策后响应

通信协议 (对标 Ping Island BridgeEnvelope):
  Agent → Bridge: {"id":"uuid","event_type":"task_start|task_done|...","session_id":"...","data":{...},"expects_response":false}
  Bridge → Agent: {"request_id":"uuid","decision":"allow|deny","action":"..."}
"""

import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

# Socket 路径 (与 HookEmitter 默认值一致)
DEFAULT_SOCKET_PATH = "/tmp/evo-pipeline-bridge.sock"


class PipelineBridge:
    """Unix Socket server that bridges AgentManager events to Pipeline Monitor."""

    def __init__(self, socket_path: str = DEFAULT_SOCKET_PATH):
        self.socket_path = socket_path
        self._server = None
        self._event_bus = None
        self._mgr = None
        self._workspace_dir = ""
        # 对标 ApprovalCoordinator
        self._pending_decisions: dict[str, asyncio.Event] = {}
        self._decisions: dict[str, dict] = {}
        # 活跃任务追踪 (用于按钮锁定)
        self._active_tasks: dict[str, dict] = {}

    def set_event_bus(self, event_bus):
        self._event_bus = event_bus

    def set_manager(self, mgr):
        self._mgr = mgr

    def set_workspace(self, workspace_dir: str):
        self._workspace_dir = workspace_dir

    # ── Socket Server ──

    async def start(self):
        """启动 Unix Socket 监听 (对标 HookSocketServer.start())."""
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

        self._server = await asyncio.start_unix_server(
            self._handle_client, self.socket_path
        )
        os.chmod(self.socket_path, 0o600)
        logger.info(f"PipelineBridge listening on {self.socket_path}")

    async def stop(self):
        """停止监听。"""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """处理一个 AgentManager 连接 (对标 SocketServer.handle())."""
        try:
            data = await asyncio.wait_for(reader.read(), timeout=60)
            if not data:
                return

            envelope = json.loads(data.decode())
            response = await self._process_envelope(envelope)

            if response is not None:
                resp_data = (json.dumps(response, ensure_ascii=False) + "\n").encode()
                writer.write(resp_data)
                await writer.drain()
        except asyncio.TimeoutError:
            logger.debug("PipelineBridge client read timeout")
        except json.JSONDecodeError as e:
            logger.warning(f"PipelineBridge invalid JSON: {e}")
        except Exception as e:
            logger.error(f"PipelineBridge client error: {e}", exc_info=True)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    # ── Envelope Processing ──

    async def _process_envelope(self, envelope: dict) -> dict | None:
        """处理事件 envelope (对标 SessionStore.ingest() + ApprovalCoordinator)."""
        event_type = envelope.get("event_type", "")
        session_id = envelope.get("session_id", "")
        data = envelope.get("data", {})
        expects_response = envelope.get("expects_response", False)

        logger.debug(f"PipelineBridge received: {event_type} from {session_id}")

        # 根据事件类型更新状态
        if event_type == "session_start":
            self._on_session_start(session_id, data)
        elif event_type == "task_start":
            self._on_task_start(session_id, data)
        elif event_type == "task_done":
            self._on_task_done(session_id, data)
        elif event_type == "task_error":
            self._on_task_error(session_id, data)

        # 推送 SSE 事件到浏览器
        self._push_sse(session_id, event_type, data)

        # 阻塞事件: 等待 Dashboard 决策
        if expects_response:
            decision = await self._wait_for_decision(envelope["id"])
            return decision

        return None

    # ── 状态更新 ──

    def _on_session_start(self, session_id: str, data: dict):
        """session_start 事件处理。"""
        logger.info(f"PipelineBridge: session_start {session_id}")

    def _on_task_start(self, session_id: str, data: dict):
        """task_start 事件: 锁定 Pipeline 步骤。"""
        task_info = {
            "type": data.get("task_type", "unknown"),
            "started_at": time.time(),
            "session_id": session_id,
        }
        self._active_tasks[session_id] = task_info

        # 写入 PIPELINE_STATE.json 的 active_task 锁
        self._write_active_task_lock(session_id, task_info)

        logger.info(f"PipelineBridge: task_start {data.get('task_type', '')} for {session_id}")

    def _on_task_done(self, session_id: str, data: dict):
        """task_done 事件: 解锁 Pipeline 步骤。"""
        self._active_tasks.pop(session_id, None)

        # 清除 PIPELINE_STATE.json 的 active_task 锁
        self._clear_active_task_lock(session_id)

        logger.info(f"PipelineBridge: task_done {data.get('task_type', '')} for {session_id}")

    def _on_task_error(self, session_id: str, data: dict):
        """task_error 事件: 解锁并记录错误。"""
        self._active_tasks.pop(session_id, None)
        self._clear_active_task_lock(session_id)
        logger.error(f"PipelineBridge: task_error for {session_id}: {data.get('error', '')[:200]}")

    # ── active_task 锁 (PIPELINE_STATE.json) ──

    def _get_state_path(self) -> Path | None:
        """获取 PIPELINE_STATE.json 路径。"""
        if not self._workspace_dir:
            # 尝试从 mgr 获取
            if self._mgr:
                for sid, session in getattr(self._mgr, 'sessions', {}).items():
                    return Path(session.workspace_dir) / "PIPELINE_STATE.json"
            return None
        return Path(self._workspace_dir) / "PIPELINE_STATE.json"

    def _write_active_task_lock(self, session_id: str, task_info: dict):
        """在 PIPELINE_STATE.json 中写入 active_task 锁。"""
        state_path = self._get_state_path()
        if not state_path or not state_path.exists():
            return
        try:
            from pipeline_protocol import atomic_read, atomic_write
            state = atomic_read(state_path)
            state["active_task"] = task_info
            state["session_id"] = state.get("session_id") or session_id
            atomic_write(state_path, state)
        except Exception as e:
            logger.debug(f"PipelineBridge: write active_task lock failed: {e}")

    def _clear_active_task_lock(self, session_id: str):
        """清除 PIPELINE_STATE.json 中的 active_task 锁。"""
        state_path = self._get_state_path()
        if not state_path or not state_path.exists():
            return
        try:
            from pipeline_protocol import atomic_read, atomic_write
            state = atomic_read(state_path)
            if "active_task" in state:
                del state["active_task"]
                atomic_write(state_path, state)
        except Exception as e:
            logger.debug(f"PipelineBridge: clear active_task lock failed: {e}")

    # ── SSE 推送 ──

    def _push_sse(self, session_id: str, event_type: str, data: dict):
        """推送事件到 EventBus → SSE → 浏览器。"""
        if self._event_bus:
            try:
                self._event_bus.publish(session_id, {
                    "type": f"hook_{event_type}",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "data": {k: str(v)[:300] for k, v in data.items()},
                })
            except Exception as e:
                logger.debug(f"PipelineBridge SSE push failed: {e}")

    # ── 决策等待 (对标 ApprovalCoordinator) ──

    async def _wait_for_decision(self, request_id: str,
                                  timeout: float = 3600) -> dict:
        """阻塞等待 Dashboard 决策 (对标 ApprovalCoordinator.waitForDecision())."""
        event = asyncio.Event()
        self._pending_decisions[request_id] = event
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return self._decisions.pop(request_id, {"decision": "timeout"})
        except asyncio.TimeoutError:
            self._pending_decisions.pop(request_id, None)
            return {"decision": "timeout", "error": "Decision wait timed out"}

    def resolve_decision(self, request_id: str, decision: dict):
        """Dashboard 做出决策后调用 (对标 ApprovalCoordinator.resolve())."""
        self._decisions[request_id] = decision
        event = self._pending_decisions.pop(request_id, None)
        if event:
            event.set()

    # ── 查询接口 ──

    def is_task_running(self, session_id: str) -> bool:
        """检查是否有活跃任务在运行。"""
        if session_id in self._active_tasks:
            task = self._active_tasks[session_id]
            elapsed = time.time() - task.get("started_at", 0)
            if elapsed < 3600:  # 1小时内认为有效
                return True
            self._active_tasks.pop(session_id, None)  # 过期清理
        return False

    def get_active_task(self, session_id: str) -> dict | None:
        """获取活跃任务信息。"""
        if self.is_task_running(session_id):
            return self._active_tasks.get(session_id)
        return None
