"""
AgentManager — Session management and multi-agent discussion coordination.
"""

import asyncio
import json
import logging
import os
import socket
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from session.event_bus import EventBus
from session.utils import generate_session_id, now_iso, truncate

logger = logging.getLogger(__name__)


# ── HookEmitter: 对标 Ping Island Bridge 的事件发射器 ──

class HookEmitter:
    """向 PipelineBridge (Unix Socket) 发送生命周期事件。

    对标 Ping Island 的 Hook 机制:
    - Agent 框架在关键切点发射事件
    - 非阻塞事件 (agent_message, tool_call): fire-and-forget
    - 阻塞事件 (permission_request): 发送后等待 Bridge 响应

    Socket 不可用时降级为 no-op，不影响 Agent 正常运行。
    """

    def __init__(self, socket_path: str = "/tmp/flux-pipeline-bridge.sock"):
        self.socket_path = socket_path
        self._connected = False
        self._try_connect()

    def _try_connect(self) -> bool:
        """尝试连接 socket。失败则降级为 no-op。"""
        if self._connected:
            return True
        if not os.path.exists(self.socket_path):
            return False
        try:
            self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._sock.settimeout(2.0)
            self._sock.connect(self.socket_path)
            self._sock.settimeout(None)
            self._connected = True
            logger.info(f"HookEmitter connected to {self.socket_path}")
            return True
        except Exception:
            return False

    def _send_envelope(self, envelope: dict) -> bool:
        """发送 envelope 到 socket。失败返回 False。"""
        if not self._connected and not self._try_connect():
            return False
        try:
            data = (json.dumps(envelope, ensure_ascii=False) + "\n").encode()
            self._sock.sendall(data)
            return True
        except Exception as e:
            logger.debug(f"HookEmitter send failed: {e}")
            self._connected = False
            return False

    def _recv_response(self, timeout: float = 300) -> dict | None:
        """阻塞读取 socket 响应。"""
        if not self._connected:
            return None
        try:
            self._sock.settimeout(timeout)
            data = b""
            while True:
                chunk = self._sock.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break
            self._sock.settimeout(None)
            if data:
                return json.loads(data.decode())
        except Exception as e:
            logger.debug(f"HookEmitter recv failed: {e}")
            self._connected = False
        return None

    def emit(self, event_type: str, session_id: str, data: dict | None = None,
             expects_response: bool = False):
        """发射非阻塞事件 (fire-and-forget)。"""
        envelope = {
            "id": str(uuid.uuid4()),
            "event_type": event_type,
            "session_id": session_id,
            "status": data.get("status", "") if data else "",
            "data": data or {},
            "expects_response": expects_response,
            "timestamp": time.time(),
        }
        self._send_envelope(envelope)

    def emit_and_wait(self, event_type: str, session_id: str,
                      data: dict | None = None, timeout: float = 3600) -> dict | None:
        """发射阻塞事件并等待 Bridge 响应。"""
        envelope = {
            "id": str(uuid.uuid4()),
            "event_type": event_type,
            "session_id": session_id,
            "status": data.get("status", "waiting_approval") if data else "waiting_approval",
            "data": data or {},
            "expects_response": True,
            "timestamp": time.time(),
        }
        if not self._send_envelope(envelope):
            return {"error": "HookEmitter not connected"}

        response = self._recv_response(timeout=timeout)
        if response is None:
            return {"error": "HookEmitter recv timeout"}
        return response


@dataclass
class AgentSession:
    """Represents an active agent session (OpenRath-style with lineage)."""
    session_id: str
    agent: Any
    thread_id: str
    workspace_dir: str
    created_at: str
    model: str = ""
    provider: str = ""
    status: str = "idle"
    events: list[dict] = field(default_factory=list)
    last_response: str = ""
    sub_agents_used: list[str] = field(default_factory=list)
    pending_approvals: list[dict] = field(default_factory=list)
    thread_count: int = 0
    thread_summaries: list[str] = field(default_factory=list)
    _task: Any = field(default=None)
    evolution_memory: Any = field(default=None)
    fitness_history: list[dict] = field(default_factory=list)
    # ── OpenRath-style lineage ──
    parent_session_ids: list[str] = field(default_factory=list)
    lineage_kind: str = "user"  # user | agent | fork | merge | compress


class AgentManager:
    """Manages EvoScientist agent sessions."""

    # Safety threshold: rotate thread before hitting model's context limit
    MAX_CONTEXT_CHARS = 2_400_000  # ~800K tokens (80% of DeepSeek's 1M)

    def __init__(self, base_dir: str | None = None,
                 hook_socket_path: str = "/tmp/flux-pipeline-bridge.sock",
                 use_persistent_checkpointer: bool = True):
        self.base_dir = base_dir or str(Path(__file__).parent.parent)
        self.sessions: dict[str, AgentSession] = {}
        self._checkpointer = None
        self._checkpoint_conn = None
        self._event_bus = EventBus()
        self._stream_states: dict[str, Any] = {}
        self._use_rich_streaming = True
        self._persistent_checkpointer = use_persistent_checkpointer
        # Pipeline pause gates: per-session asyncio.Event
        self._pipeline_gates: dict[str, asyncio.Event] = {}
        # HookEmitter: 对标 Ping Island Bridge 事件发射器
        self._hook = HookEmitter(hook_socket_path)
        # Recover sessions from disk on startup
        self._load_sessions_from_disk()

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    # ── Pipeline pause gate ──

    def _get_gate(self, session_id: str) -> asyncio.Event:
        """Get or create the pipeline gate for a session."""
        if session_id not in self._pipeline_gates:
            self._pipeline_gates[session_id] = asyncio.Event()
            self._pipeline_gates[session_id].set()  # default: not paused
        return self._pipeline_gates[session_id]

    async def _wait_if_paused(self, session_id: str):
        """Block if pipeline is paused. Returns immediately if not."""
        gate = self._get_gate(session_id)
        if not gate.is_set():
            logger.info(f"Pipeline paused for {session_id}, waiting...")
            await gate.wait()
            logger.info(f"Pipeline resumed for {session_id}")

    # ── Thread rotation for context overflow prevention ──

    def _rotate_thread(self, session: AgentSession, summary: str = "") -> str:
        """Create a new thread to avoid context accumulation.

        Each discuss()/send_message() call gets its own LangGraph thread
        so message history doesn't grow unboundedly. Previous context is
        passed via summaries injected into the first message.
        """
        if summary:
            if not isinstance(session.thread_summaries, list):
                session.thread_summaries = []
            session.thread_summaries.append(summary)
        session.thread_count += 1
        new_thread = f"{session.session_id}_t{session.thread_count}"
        session.thread_id = new_thread
        logger.info(f"Rotated to thread {new_thread} (total: {session.thread_count})")
        return new_thread

    def _summarize_response(self, response: str, max_len: int = 2000) -> str:
        """Extract a compact summary from an agent response."""
        if not response:
            return ""
        if len(response) <= max_len:
            return response
        # Take beginning + look for conclusion section
        parts = [response[:max_len // 2]]
        lower = response.lower()
        for marker in ["## synthesis", "## conclusion", "## summary", "## key findings", "## final"]:
            idx = lower.find(marker)
            if idx >= 0:
                tail = response[idx:idx + max_len // 2]
                parts.append(f"\n...[truncated]...\n{tail}")
                break
        return "\n".join(parts)

    def _build_context_prefix(self, session: AgentSession) -> str:
        """Build context from previous thread summaries."""
        if not session.thread_summaries:
            return ""
        parts = ["## Previous Discussion Summaries\n"]
        for i, s in enumerate(session.thread_summaries, 1):
            parts.append(f"### Discussion {i}\n{s}\n")
        parts.append("---\n\n")
        return "\n".join(parts)

    async def _get_checkpointer(self):
        """Get or create checkpointer.

        Uses InMemorySaver when use_persistent_checkpointer=False (Dashboard mode)
        or when langgraph/aiosqlite not installed.
        """
        if not self._persistent_checkpointer:
            return None  # force InMemorySaver in agent_factory
        if self._checkpointer is None:
            try:
                import aiosqlite
                from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
                from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
                db_path = Path(self.base_dir) / ".evo_checkpoints.db"
                db_path.parent.mkdir(parents=True, exist_ok=True)
                self._checkpoint_conn = await aiosqlite.connect(str(db_path))
                # Enable pickle_fallback to handle ToolMessage objects with
                # non-serializable artifacts from deepagents filesystem middleware.
                serde = JsonPlusSerializer(pickle_fallback=True)
                self._checkpointer = AsyncSqliteSaver(self._checkpoint_conn, serde=serde)
                logger.info(f"AsyncSqliteSaver initialized at {db_path}")
            except (ImportError, Exception) as e:
                logger.warning(f"Checkpointer unavailable ({e}), using InMemorySaver")
                self._checkpointer = None
        return self._checkpointer

    # ── Session persistence ──

    def _sessions_dir(self, workspace_dir: str) -> Path:
        return Path(workspace_dir) / ".evo_sessions"

    def _session_registry_path(self) -> Path:
        return Path(self.base_dir) / ".evo_session_registry.json"

    def _save_session_meta(self, session: AgentSession):
        """Persist session via JSONL WAL (OpenRath-style).

        Writes header + all chunks to {session_id}.jsonl.__partial__.
        The trailer + atomic rename → .jsonl happens on session completion.
        Also maintains backward-compatible .json metadata file.
        """
        try:
            sdir = self._sessions_dir(session.workspace_dir)
            sdir.mkdir(parents=True, exist_ok=True)

            # OpenRath-style JSONL WAL
            from session.persistence import SessionWriter
            wal_path = sdir / f"{session.session_id}.jsonl"
            writer = SessionWriter(wal_path)
            writer.write_header(
                session_id=session.session_id,
                workspace_dir=session.workspace_dir,
                parent_session_ids=session.parent_session_ids,
                model=session.model,
                provider=session.provider,
                metadata={"lineage_kind": session.lineage_kind},
            )
            # Write thread summaries as initial chunks
            for ts in session.thread_summaries:
                writer.write_chunk(kind="thread_summary", response=ts)
            writer.close(status=session.status)

            # Backward-compatible .json metadata
            data = {
                "session_id": session.session_id,
                "workspace_dir": session.workspace_dir,
                "thread_id": session.thread_id,
                "created_at": session.created_at,
                "model": session.model,
                "provider": session.provider,
                "status": session.status,
                "sub_agents_used": session.sub_agents_used,
                "thread_count": session.thread_count,
                "thread_summaries": session.thread_summaries,
                "last_response": session.last_response[:1000000] if session.last_response else "",
                "fitness_history": session.fitness_history[-50:],
            }
            (sdir / f"{session.session_id}.json").write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            # Update global registry
            registry = {}
            rpath = self._session_registry_path()
            if rpath.exists():
                try:
                    registry = json.loads(rpath.read_text(encoding="utf-8"))
                except Exception:
                    pass
            registry[session.session_id] = session.workspace_dir
            rpath.write_text(json.dumps(registry, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to save session meta: {e}")

    def _save_agent_context(self, session, agent_name: str, prompt: str,
                            response: str, parsed: dict) -> None:
        """Save per-agent independent context: full prompt + response + parsed output.

        Persistent, append-only storage in: {_index}/agents/{agent_name}/
        - conversation.jsonl: full prompt+response history
        - meta.json: agent metadata (call_count, last_title, last_call)
        """
        try:
            agent_dir = Path(session.workspace_dir) / "_index" / "agents" / agent_name
            agent_dir.mkdir(parents=True, exist_ok=True)

            conv_entry = {
                "timestamp": now_iso(),
                "session_id": session.session_id,
                "phase": self._current_phase(session.workspace_dir),
                "agent_name": agent_name,
                "prompt": prompt,
                "response": response[:1000000],
                "parsed": parsed,
            }
            conv_path = agent_dir / "conversation.jsonl"
            with conv_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(conv_entry, ensure_ascii=False) + "\n")

            existing_meta = {}
            meta_path = agent_dir / "meta.json"
            if meta_path.exists():
                try:
                    existing_meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            call_count = existing_meta.get("call_count", 0) + 1
            existing_meta.update({
                "agent_name": agent_name,
                "last_call": now_iso(),
                "last_title": parsed.get("title", ""),
                "call_count": call_count,
                "session_id": session.session_id,
            })
            meta_path.write_text(json.dumps(existing_meta, indent=2, ensure_ascii=False), encoding="utf-8")

            logger.info(f"Agent context saved: {agent_name} (call #{call_count})")
        except Exception as e:
            logger.warning(f"Failed to save agent context for {agent_name}: {e}")

    def _current_phase(self, workspace_dir: str) -> str:
        """Read current phase from PIPELINE_STATE.json."""
        try:
            sp = Path(workspace_dir) / "PIPELINE_STATE.json"
            if sp.exists():
                state = json.loads(sp.read_text(encoding="utf-8"))
                return state.get("phase", "unknown")
        except Exception:
            pass
        return "unknown"

    def _load_sessions_from_disk(self):
        """Scan workspace for saved sessions and rebuild AgentSession objects.
        Called on server startup to recover from crashes."""
        # First try global registry
        workspaces_to_check = set()
        rpath = self._session_registry_path()
        if rpath.exists():
            try:
                registry = json.loads(rpath.read_text(encoding="utf-8"))
                workspaces_to_check.update(registry.values())
            except Exception:
                pass
        # Also check default locations
        cwd = Path.cwd()
        if (cwd / ".evo_sessions").exists():
            workspaces_to_check.add(str(cwd))
        for p in [Path(self.base_dir).parent, Path(self.base_dir).parent.parent]:
            if (p / ".evo_sessions").exists():
                workspaces_to_check.add(str(p))

        recovered = 0
        for ws in workspaces_to_check:
            sdir = self._sessions_dir(ws)
            if not sdir.exists():
                continue
            for sf in sorted(sdir.glob("*.json")):
                try:
                    data = json.loads(sf.read_text(encoding="utf-8"))
                    sid = data["session_id"]
                    if sid in self.sessions:
                        continue  # already loaded
                    # Defensive: ensure list-typed fields are actually lists
                    sub_agents = data.get("sub_agents_used", [])
                    if not isinstance(sub_agents, list):
                        sub_agents = []
                    summaries = data.get("thread_summaries", [])
                    if not isinstance(summaries, list):
                        summaries = []
                    fitness = data.get("fitness_history", [])
                    if not isinstance(fitness, list):
                        fitness = []
                    thread_id = data.get("thread_id") or sid

                    session = AgentSession(
                        session_id=sid,
                        agent=None,  # will be rebuilt on first use
                        thread_id=thread_id,
                        workspace_dir=data["workspace_dir"],
                        created_at=data["created_at"],
                        model=data.get("model", ""),
                        provider=data.get("provider", ""),
                        status="recovered",
                        sub_agents_used=sub_agents,
                        thread_count=data.get("thread_count", 0),
                        thread_summaries=summaries,
                    )
                    session.fitness_history = fitness
                    session.last_response = data.get("last_response", "")
                    session.parent_session_ids = data.get("parent_session_ids", [])
                    session.lineage_kind = data.get("lineage_kind", "user")
                    self.sessions[sid] = session
                    recovered += 1
                except Exception as e:
                    logger.warning(f"Failed to load session {sf}: {e}")

    async def fork_session(self, parent_session_id: str,
                           lineage_kind: str = "fork") -> dict:
        """Fork a parent session to create a child with lineage tracking.

        The child inherits thread summaries and workspace from the parent
        but gets a fresh thread_id and agent. Parent's session_id is recorded
        in parent_session_ids for DAG traversal.
        """
        parent = self.sessions.get(parent_session_id)
        if not parent:
            self._load_sessions_from_disk()
            parent = self.sessions.get(parent_session_id)
        if not parent:
            return {"error": f"Parent session {parent_session_id} not found"}

        child_id = generate_session_id()
        now = now_iso()

        child = AgentSession(
            session_id=child_id,
            agent=None,
            thread_id=f"{child_id}_t0",
            workspace_dir=parent.workspace_dir,
            created_at=now,
            model=parent.model,
            provider=parent.provider,
            status="idle",
            thread_summaries=list(parent.thread_summaries),
            parent_session_ids=[parent_session_id],
            lineage_kind=lineage_kind,
        )
        self.sessions[child_id] = child
        self._save_session_meta(child)

        logger.info(f"Session forked: {parent_session_id} → {child_id} ({lineage_kind})")
        return {"session_id": child_id, "parent_session_id": parent_session_id,
                "lineage_kind": lineage_kind, "status": "idle"}

        if recovered:
            logger.info(f"Recovered {recovered} session(s) from disk")

    async def _ensure_agent(self, session: AgentSession):
        """Rebuild agent for a recovered session if needed."""
        if session.agent is not None:
            return
        from session.factory import create_agent
        checkpointer = await self._get_checkpointer()
        session.agent = create_agent(
            workspace_dir=session.workspace_dir,
            base_dir=self.base_dir,
            model=session.model or None,
            provider=session.provider or None,
            checkpointer=checkpointer,
        )
        logger.info(f"Agent rebuilt for recovered session {session.session_id} (model={session.model or 'default'}, provider={session.provider or 'default'})")

    async def create_session(
        self,
        workspace_dir: str,
        model: str | None = None,
        provider: str | None = None,
    ) -> dict:
        """Create a new agent session."""
        from session.factory import create_agent

        session_id = generate_session_id()
        checkpointer = await self._get_checkpointer()

        try:
            agent = create_agent(
                workspace_dir=workspace_dir,
                base_dir=self.base_dir,
                model=model,
                provider=provider,
                checkpointer=checkpointer,
            )
        except Exception as e:
            return {"error": f"Failed to create agent: {e}"}

        session = AgentSession(
            session_id=session_id,
            agent=agent,
            thread_id=session_id,
            workspace_dir=workspace_dir,
            created_at=now_iso(),
            model=model or "",
            provider=provider or "",
        )
        self.sessions[session_id] = session
        self._save_session_meta(session)

        # Hook: 发射 session_start 事件
        self._hook.emit("session_start", session_id, {
            "workspace_dir": workspace_dir,
            "created_at": session.created_at,
            "model": model or "",
            "provider": provider or "",
        })

        return {
            "session_id": session_id,
            "workspace_dir": workspace_dir,
            "status": "idle",
            "created_at": session.created_at,
        }

    async def send_message(self, session_id: str, message: str) -> dict:
        """Send a message to an agent session and collect the response."""
        session = self.sessions.get(session_id)
        if not session:
            return {"error": f"Session {session_id} not found"}

        # Pipeline pause gate
        await self._wait_if_paused(session_id)

        # Prevent overlapping tasks
        if session._task is not None and not session._task.done():
            return {"error": "Session is busy processing a previous request. Poll evo_status.", "status": "busy"}

        # Rotate thread: new thread for each call, carry summaries
        summary = self._summarize_response(session.last_response) if session.last_response else ""
        self._rotate_thread(session, summary)

        session.status = "running"
        session.sub_agents_used = []
        session.events = []

        # Rebuild agent for recovered sessions
        await self._ensure_agent(session)

        # Inject evolution memory priors
        mem = await self._get_evolution_memory(session)
        priors = await mem.inject_priors(message, max_chars=2000)

        # Inject previous context
        ctx_prefix = self._build_context_prefix(session)
        full_message = ctx_prefix + message if ctx_prefix else message
        if priors:
            full_message = priors + "\n\n---\n\n" + full_message

        # Launch background task
        session._task = asyncio.create_task(
            self._execute_discuss_background(session, full_message, set())
        )

        return {
            "status": "processing",
            "thread_id": session.thread_id,
            "message": "Message processing started in background. Poll evo_status for completion.",
        }

    async def discuss(
        self,
        session_id: str,
        topic: str,
        agents: list[str] | None = None,
        exclude_agents: list[str] | None = None,
    ) -> dict:
        """Trigger a multi-agent discussion on a topic.

        Args:
            exclude_agents: Sub-agents to exclude from delegation. If an
                implementation need arises, it is returned as a proposal
                instead of being executed. Default: ["code-agent", "debug-agent"].
        """
        session = self.sessions.get(session_id)
        if not session:
            return {"error": f"Session {session_id} not found"}

        # Pipeline pause gate
        await self._wait_if_paused(session_id)

        # Prevent overlapping tasks
        if session._task is not None and not session._task.done():
            return {"error": "Session is busy processing a previous request. Poll evo_status.", "status": "busy"}

        excluded = set(exclude_agents or ["code-agent", "debug-agent"])

        agent_list = ", ".join(agents) if agents else "planner, researcher, and analyst"
        discussion_prompt = (
            f"I need a multi-perspective discussion on this topic: {topic}\n\n"
            f"Please delegate to your sub-agents ({agent_list}) and have each one "
            f"contribute their perspective. For each sub-agent:\n"
            f"1. Ask them to analyze the topic from their expertise\n"
            f"2. Collect their responses\n"
            f"3. Synthesize a conclusion\n\n"
        )
        if excluded:
            names = ", ".join(sorted(excluded))
            discussion_prompt += (
                f"IMPORTANT: Do NOT delegate to {names}. "
                f"If implementation or debugging work is needed, describe it as a "
                f"proposal under a '## Code Proposals' section instead of executing it. "
                f"Each proposal should have a clear title and description.\n\n"
            )
        discussion_prompt += "Format the output as a discussion transcript showing each agent's contribution."

        session.status = "running"
        session.sub_agents_used = []
        session.events = []

        # Rotate thread: new thread for each discussion, carry summaries
        summary = self._summarize_response(session.last_response) if session.last_response else ""
        self._rotate_thread(session, summary)

        # Rebuild agent for recovered sessions
        await self._ensure_agent(session)

        # Inject evolution memory priors
        mem = await self._get_evolution_memory(session)
        priors = await mem.inject_priors(topic, max_chars=2000)

        # Inject previous context into the discussion prompt
        ctx_prefix = self._build_context_prefix(session)
        full_prompt = ctx_prefix + discussion_prompt if ctx_prefix else discussion_prompt
        if priors:
            full_prompt = priors + "\n\n---\n\n" + full_prompt

        # Launch background task to avoid MCP client timeout on long discussions
        session._task = asyncio.create_task(
            self._execute_discuss_background(session, full_prompt, excluded)
        )

        # Hook: 发射 task_start 事件
        self._hook.emit("task_start", session_id, {
            "task_type": "discuss",
            "topic": topic[:200],
            "agents": agents or ["planner", "researcher", "analyst"],
            "excluded": sorted(excluded),
        })

        return {
            "status": "processing",
            "thread_id": session.thread_id,
            "message": "Discussion started in background. Poll evo_status for completion.",
        }

    async def invoke_agent(
        self,
        session_id: str,
        agent_name: str,
        prompt: str,
    ) -> dict:
        """Invoke a SINGLE agent independently.\n    print("INVOKE_AGENT_CALLED: " + agent_name)

        Used for 4-persona independent proposal generation. The orchestrator
        delegates ONLY to the named agent and returns just that agent's raw output.
        """
        session = self.sessions.get(session_id)
        if not session:
            # Try recovering from disk (dashboard restart clears in-memory sessions)
            self._load_sessions_from_disk()
            session = self.sessions.get(session_id)
        if not session:
            return {"error": f"Session {session_id} not found"}

        await self._wait_if_paused(session_id)

        if session._task is not None and not session._task.done():
            return {"error": "Session is busy", "status": "busy"}

        # ── Phase 1: Tavily search (SSE-tracked, results baked into prompt) ──
        search_context = ""
        try:
            self._event_bus.publish(session_id, {
                "type": "persona_started",
                "data": {"persona": agent_name, "detail": f"{agent_name}: searching web..."}
            })
            from tavily import TavilyClient
            tc = TavilyClient()
            search_resp = tc.search(
                query=prompt[:1000000],
                max_results=3
            )
            results = search_resp.get("results", []) if isinstance(search_resp, dict) else []
            if results:
                search_context = "## Web Search Results\n"
                for i, r in enumerate(results[:3]):
                    search_context += f"{i+1}. {r.get('title','')}\n   {r.get('content','')[:1000000]}\n\n"
                self._event_bus.publish(session_id, {
                    "type": "tool_call",
                    "data": {"name": "tavily_search", "args_preview": f"{len(results)} results found"}
                })
                self._event_bus.publish(session_id, {
                    "type": "tool_result",
                    "data": {"name": "tavily_search", "content": f"{len(results)} papers found"}
                })
                logger.info(f"invoke_agent({agent_name}): Tavily returned {len(results)} results")

                # ── Sync search results to Claim Chain ──
                try:
                    from claim_chain.api import ClaimChainAPI
                    ws = Path(session.workspace_dir) if hasattr(session, 'workspace_dir') else Path(session.workspace_dir)
                    api = ClaimChainAPI(ws)
                    for r in results[:5]:
                        title = r.get('title', '')[:200]
                        content = r.get('content', '')[:1000000]
                        if title and content:
                            api.ingest_text(
                                f"{title}\n{content}",
                                source="web_search",
                                tags=["literature", "web_search", agent_name]
                            )
                    logger.info(f"invoke_agent({agent_name}): Synced {min(len(results),5)} search results to CC")
                except Exception as e:
                    logger.warning(f"invoke_agent({agent_name}): CC sync failed: {e}")
        except Exception as e:
            logger.warning(f"invoke_agent({agent_name}): Tavily search failed: {e}")

        # Build prompt with search results
        single_agent_prompt = (
            f"You are the {agent_name}. Respond DIRECTLY to the task below. "
            f"Answer in your own voice, from your unique perspective.\n\n"
            f"## Task\n{prompt}\n\n"
        )
        if search_context:
            single_agent_prompt += (
                f"{search_context}\n"
                f"Use the above search results to cite specific methods and papers.\n\n"
            )
        single_agent_prompt += (
            f"## CRITICAL: Output Format\n"
            f"Output ONLY a single JSON object. No other text.\n"
            f'{{"title": "concise title (under 80 chars)", '
            f'"hypothesis": "core hypothesis in 2-3 sentences", '
            f'"method_sketch": "detailed method with component-level specifics, cite references", '
            f'"search_results_summary": "key references found"}}\n'
        )

        # Rotate thread and prepare
        summary = self._summarize_response(session.last_response) if session.last_response else ""
        self._rotate_thread(session, summary)

        session.status = "running"
        session.sub_agents_used = []
        session.events = []

        await self._ensure_agent(session)

        # Inject evolution memory priors
        mem = await self._get_evolution_memory(session)
        priors = await mem.inject_priors(prompt, max_chars=1500)

        ctx_prefix = self._build_context_prefix(session)
        full_prompt = ctx_prefix + single_agent_prompt if ctx_prefix else single_agent_prompt
        if priors:
            full_prompt = priors + "\n\n---\n\n" + full_prompt

        # ── Phase 2: Direct LLM call (reliable JSON, search results baked in) ──
        try:
            response = await self._direct_llm_call(session, full_prompt)
            session.last_response = response
            session.status = "completed"
            self._save_session_meta(session)
            self._clear_pipeline_lock(session)

            # Try to parse JSON from response
            parsed = None
            try:
                import re
                # 1) Try ```json fence (greedy to capture nested braces)
                m = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", response)
                if m:
                    raw_json = m.group(1).strip()
                    # Fix common issues: trailing commas
                    raw_json = re.sub(r",\s*}", "}", raw_json)
                    raw_json = re.sub(r",\s*]", "]", raw_json)
                    try:
                        parsed = json.loads(raw_json)
                    except json.JSONDecodeError:
                        pass

                # 2) Try brace-matching extraction (handles nested JSON)
                if not parsed:
                    # Find all potential JSON start positions
                    for start_m in re.finditer(r'\{', response):
                        start = start_m.start()
                        # Count braces to find matching end
                        depth = 0
                        in_string = False
                        escape = False
                        for i in range(start, len(response)):
                            c = response[i]
                            if escape:
                                escape = False
                                continue
                            if c == '\\' and in_string:
                                escape = True
                                continue
                            if c == '"' and not escape:
                                in_string = not in_string
                                continue
                            if in_string:
                                continue
                            if c == '{':
                                depth += 1
                            elif c == '}':
                                depth -= 1
                                if depth == 0:
                                    candidate_str = response[start:i+1]
                                    if len(candidate_str) > 50:  # Skip tiny fragments
                                        # Fix trailing commas
                                        candidate_str = re.sub(r",\s*}", "}", candidate_str)
                                        candidate_str = re.sub(r",\s*]", "]", candidate_str)
                                        try:
                                            candidate = json.loads(candidate_str)
                                            if isinstance(candidate, dict) and any(k in candidate for k in ("title", "hypothesis", "method_sketch")):
                                                parsed = candidate
                                                break
                                        except (json.JSONDecodeError, ValueError):
                                            pass
                                    break  # depth==0, move to next start
                        if parsed:
                            break
            except Exception:
                pass

            if parsed and isinstance(parsed, dict):
                parsed.setdefault("title", agent_name)
                parsed.setdefault("hypothesis", "")
                parsed.setdefault("method_sketch", "")
                parsed.setdefault("source_agent", agent_name)
                # ── Save per-agent context ──
                self._save_agent_context(session, agent_name, full_prompt, response, parsed)
                return parsed

            # 3) Fallback: intelligent extraction from raw markdown text
            import re as _re
            title = ""
            hypothesis = ""
            method_sketch = ""

            # If response is extremely short, it's likely an error
            if len(response) < 80:
                logger.warning(f"invoke_agent({agent_name}): response too short ({len(response)} chars): {response[:100]}")
                return {
                    "title": f"{agent_name} proposal",
                    "hypothesis": f"[Agent produced insufficient output: {len(response)} chars]",
                    "method_sketch": f"[Agent produced insufficient output: {len(response)} chars]",
                    "search_results_summary": "",
                    "raw_response_length": len(response),
                }

            # ── Title extraction: prefer proposal-specific headings ──
            for pattern in [
                r"^#+\s*(?:proposal|方案|proposed\s*(?:method|approach)|核心创新|创新点|our\s*(?:approach|method))[:\s]*(.+)$",
                r"^#+\s*(.+)$",  # first heading as fallback
            ]:
                tm = _re.search(pattern, response, _re.MULTILINE | _re.IGNORECASE)
                if tm:
                    candidate = tm.group(1).strip()
                    # Skip generic analysis headings
                    if not _re.match(r"^(step|analysis|problem|literature|background|introduction|decomposition|问题|分析|文献|背景)", candidate, _re.IGNORECASE):
                        title = candidate[:120]
                        break

            if not title:
                title = f"{agent_name} proposal"

            # ── Hypothesis extraction ──
            for pattern in [
                r"(?:核心假设|hypothesis|core\s*(?:idea|thesis|contribution)|核心论点|主要创新)[:\s]*\n?([\s\S]{20,1000000}?)(?:\n##|\n\*\*\w|\Z)",
                r"(?:we\s+propose|our\s+approach|本方案|我们提出|核心思想)[:\s]*\n?([\s\S]{20,1000000}?)(?:\n##|\n\*\*\w|\Z)",
                r"(?:thesis|论点|主张|key\s+insight)[:\s]*\n?([\s\S]{20,1000000}?)(?:\n##|\n\*\*\w|\Z)",
            ]:
                hm = _re.search(pattern, response, _re.IGNORECASE | _re.MULTILINE)
                if hm:
                    hypothesis = hm.group(1).strip()[:1000000]
                    break

            # ── Method sketch extraction: prefer proposal/method sections ──
            for pattern in [
                r"(?:method[_\s]*sketch|具体方法|方案描述|proposed\s+method|our\s+method|approach)[:\s]*\n?([\s\S]{20,1000000}?)(?:\n##\s|\Z)",
                r"(?:architecture|架构|components|模块|implementation|实现)[:\s]*\n?([\s\S]{20,1000000}?)(?:\n##\s|\Z)",
            ]:
                mm = _re.search(pattern, response, _re.IGNORECASE | _re.MULTILINE)
                if mm:
                    method_sketch = mm.group(1).strip()[:1000000]
                    break

            # If no specific section found, use the latter half of the response
            # (proposals tend to be after analysis)
            if not method_sketch:
                if len(response) > 500:
                    # Take from midpoint onwards (skip analysis/reasoning)
                    mid = len(response) // 2
                    method_sketch = response[mid:mid+8000].strip()
                else:
                    method_sketch = response[:1000000]

            # If hypothesis still empty, use first substantive paragraph from method_sketch
            if not hypothesis and method_sketch:
                paras = [_l.strip() for _l in method_sketch.split('\n\n')
                         if _l.strip() and len(_l.strip()) > 30
                         and not _l.strip().startswith('#')
                         and not _l.strip().startswith('*')
                         and not _l.strip().startswith('-')]
                hypothesis = paras[0][:1000000] if paras else method_sketch[:1000000]

            # Extract search_results_summary if present in response
            search_summary = ""
            for sp in [
                r"(?:search[_\s]*results[_\s]*summary|检索结果|参考文献|references?|literature[_\s]*survey)[:\s]*\n?([\s\S]{20,1000000}?)(?:\n##\s|\Z)",
            ]:
                sm = _re.search(sp, response, _re.IGNORECASE | _re.MULTILINE)
                if sm:
                    search_summary = sm.group(1).strip()[:1000000]
                    break

            parsed = {
                "title": title,
                "hypothesis": hypothesis,
                "method_sketch": method_sketch,
                "search_results_summary": search_summary,
                "source_agent": agent_name,
                "raw_response_length": len(response),
            }
            self._save_agent_context(session, agent_name, full_prompt, response, parsed)
            return parsed
        except Exception as e:
            session.status = "error"
            session.last_response = f"Error: {e}"
            logger.error(f"invoke_agent({agent_name}) failed: {e}")
            return {"error": str(e)}

    async def _execute_discuss_background(
        self, session: AgentSession, full_prompt: str, excluded: set[str]
    ) -> None:
        """Execute discussion in background, storing results in session when done."""
        try:
            response = await self._run_agent(session, full_prompt)
            session.last_response = response
            session.status = "completed"
            self._save_session_meta(session)

            # Extract code proposals
            code_proposals = self._extract_code_proposals(response, excluded)
            session._task = None  # cleared when done

            # 直接清除 PIPELINE_STATE.json 中的 active_task 锁 (绕过 HookEmitter)
            self._clear_pipeline_lock(session)

            # Hook: 发射 task_done 事件
            self._hook.emit("task_done", session.session_id, {
                "task_type": "discuss",
                "status": "completed",
                "response_chars": len(response),
                "sub_agents_used": session.sub_agents_used,
                "proposals_count": len(code_proposals),
            })

            logger.info(
                f"Background discuss completed for {session.session_id}: "
                f"{len(response)} chars, {len(session.sub_agents_used)} agents, "
                f"{len(code_proposals)} proposals"
            )
        except Exception as e:
            session.status = "error"
            session.last_response = f"Error: {e}"
            session._task = None
            self._save_session_meta(session)

            # 直接清除 PIPELINE_STATE.json 中的 active_task 锁
            self._clear_pipeline_lock(session)

            # Hook: 发射 task_error 事件
            self._hook.emit("task_error", session.session_id, {
                "task_type": "discuss",
                "error": str(e)[:1000000],
            })

            logger.error(f"Background discuss failed for {session.session_id}: {e}", exc_info=True)

    def _clear_pipeline_lock(self, session: AgentSession) -> None:
        """直接清除 PIPELINE_STATE.json 中的 active_task 锁。
        HookEmitter socket 不可达时的可靠后备。
        """
        try:
            state_path = Path(session.workspace_dir) / "PIPELINE_STATE.json"
            if state_path.exists():
                state = json.loads(state_path.read_text(encoding="utf-8"))
                if "active_task" in state:
                    del state["active_task"]
                    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
        except Exception:
            pass

    def _extract_code_proposals(self, transcript: str, excluded: set[str]) -> list[str]:
        """Extract code/debug proposals from transcript text."""
        proposals = []
        no_code_markers = [
            "no code needed", "no implementation needed", "no code required",
            "none required", "no code change", "no coding", "nothing to implement",
        ]
        in_proposals_section = False
        for line in transcript.split("\n"):
            stripped = line.strip()
            # Match "## Code Proposals" or "### Code Proposals" (any heading level)
            is_proposal_heading = (
                "code proposal" in stripped.lower()
                and stripped.lstrip("#").strip().lower().startswith("code proposal")
            )
            if is_proposal_heading:
                in_proposals_section = True
                continue
            # End of proposals section: next heading (## or ###) that is not a proposals heading
            # Also end on horizontal rules (---) that start a new section
            if in_proposals_section and stripped.startswith("#") and not is_proposal_heading:
                in_proposals_section = False
                continue
            # Horizontal rule within proposals section = end of proposals
            if in_proposals_section and stripped == "---":
                in_proposals_section = False
                continue
            if in_proposals_section:
                # Capture numbered or bullet items
                if stripped and (stripped[0].isdigit() or stripped.startswith("-") or stripped.startswith("*")):
                    text = stripped.lstrip("-*0123456789. ")
                    if self._is_valid_proposal(text, no_code_markers):
                        proposals.append(text)
                elif stripped.startswith("**"):
                    # Bold-wrapped proposal title: **Proposal N: Title**
                    clean = stripped.strip("*").strip()
                    if clean and self._is_valid_proposal(clean, no_code_markers):
                        proposals.append(clean)
        return proposals[:20]  # Cap at 20 proposals

    @staticmethod
    def _is_valid_proposal(text: str, no_code_markers: list[str]) -> bool:
        """Filter out non-proposal text like 'No code needed'."""
        text_lower = text.lower()
        if any(marker in text_lower for marker in no_code_markers):
            return False
        if len(text) < 5:
            return False
        return True

    async def get_status(self, session_id: str) -> dict:
        """Get current session status."""
        session = self.sessions.get(session_id)
        if not session:
            return {"error": f"Session {session_id} not found"}

        memory_summary = ""
        memory_path = Path(session.workspace_dir) / "memory" / "MEMORY.md"
        if memory_path.exists():
            memory_summary = memory_path.read_text(encoding="utf-8")[:1000000]

        result = {
            "session_id": session_id,
            "status": session.status,
            "workspace_dir": session.workspace_dir,
            "created_at": session.created_at,
            "events_count": len(session.events),
            "sub_agents_used": session.sub_agents_used,
            "last_response_preview": truncate(session.last_response, 200),
            "memory_summary": memory_summary,
            "pending_approvals": len(session.pending_approvals),
        }

        # Add fitness stats if available
        try:
            from sdk.status.fitness import FitnessTracker
            fitness = FitnessTracker(session.workspace_dir)
            result["fitness"] = fitness.get_stats()
        except Exception:
            pass

        # Background task status for async discuss/send_message
        if session._task is not None:
            result["background_task"] = "running" if not session._task.done() else "completed"
            if session._task.done():
                exc = session._task.exception()
                if exc:
                    result["background_task"] = f"failed: {exc}"

        return result

    def get_stream_state(self, session_id: str) -> dict:
        """Get the rich stream state for dashboard."""
        session = self.sessions.get(session_id)
        if not session:
            return {"error": f"Session {session_id} not found"}
        state = self._stream_states.get(session_id)
        if state is None:
            return {"status": "no_stream_data"}
        return {
            "session_id": session_id,
            "agent_status": session.status,
            "thinking_text": getattr(state, "thinking_text", "")[:1000000],
            "response_text": getattr(state, "response_text", "")[:1000000],
            "is_thinking": getattr(state, "is_thinking", False),
            "is_responding": getattr(state, "is_responding", False),
            "tool_calls": [
                {"name": tc.get("name", ""), "id": tc.get("id", ""), "args_preview": str(tc.get("args", ""))[:100]}
                for tc in getattr(state, "tool_calls", [])[-20:]
            ],
            "subagents": [
                {"name": sa.name, "is_active": sa.is_active}
                for sa in getattr(state, "subagents", [])
            ],
            "total_input_tokens": getattr(state, "total_input_tokens", 0),
            "total_output_tokens": getattr(state, "total_output_tokens", 0),
        }

    def get_pipeline_state(self, session_id: str) -> dict:
        """Read PIPELINE_STATE.json from session workspace."""
        session = self.sessions.get(session_id)
        if not session:
            return {"error": f"Session {session_id} not found"}
        state_path = Path(session.workspace_dir) / "PIPELINE_STATE.json"
        if not state_path.exists():
            return {"status": "no_pipeline"}
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            return {"status": "parse_error"}

    def pipeline_control(self, session_id: str, action: str, **kwargs) -> dict:
        """Control pipeline state from dashboard or Claude Code.

        Actions: pause, resume, switch_to_claude, switch_to_agent, set_phase
        """
        session = self.sessions.get(session_id)
        if not session:
            return {"error": f"Session {session_id} not found"}

        state_path = Path(session.workspace_dir) / "PIPELINE_STATE.json"
        state = {}
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except Exception:
                state = {}

        action_map = {
            "pause": ("paused", "pipeline"),
            "resume": ("in_progress", "pipeline"),
            "switch_to_claude": ("awaiting_claude_code", "claude_code"),
            "switch_to_agent": ("in_progress", "pipeline"),
        }

        if action in action_map:
            status, control = action_map[action]
            state["status"] = status
            state["control"] = control
            state["timestamp"] = now_iso()

            # Operate the asyncio gate
            gate = self._get_gate(session_id)
            if action == "pause":
                gate.clear()  # block future calls
            else:
                gate.set()    # allow calls
        elif action == "set_phase":
            phase = kwargs.get("phase")
            if phase is not None:
                state["phase"] = phase
                state["timestamp"] = now_iso()

        # Write back
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

        # Publish SSE event
        self._event_bus.publish(session_id, {
            "type": "pipeline_control_changed",
            "timestamp": now_iso(),
            "data": {"action": action, "status": state.get("status"), "phase": state.get("phase")},
        })

        return {"action": action, "status": state.get("status"), "phase": state.get("phase")}

    def get_pipeline_control(self, session_id: str) -> dict:
        """Read current pipeline control state."""
        return self.get_pipeline_state(session_id)

    def refresh_sessions(self):
        """Re-scan disk for new sessions (called before list_sessions)."""
        self._load_sessions_from_disk()

    def list_sessions(self) -> list[dict]:
        """List all active sessions."""
        return [
            {
                "session_id": s.session_id,
                "workspace_dir": s.workspace_dir,
                "created_at": s.created_at,
                "status": s.status,
            }
            for s in self.sessions.values()
        ]

    async def approve(self, session_id: str, action_id: str, approved: bool) -> dict:
        """Approve or reject a pending agent action."""
        session = self.sessions.get(session_id)
        if not session:
            return {"error": f"Session {session_id} not found"}

        if not session.pending_approvals:
            return {"error": "No pending approvals"}

        for i, approval in enumerate(session.pending_approvals):
            if approval.get("id") == action_id:
                session.pending_approvals.pop(i)
                return {
                    "action_id": action_id,
                    "approved": approved,
                    "status": "processed",
                }

        return {"error": f"Action {action_id} not found in pending approvals"}

    async def get_memory(self, session_id: str) -> dict:
        """Read agent memory for a session."""
        session = self.sessions.get(session_id)
        if not session:
            return {"error": f"Session {session_id} not found"}

        memory_dir = Path(session.workspace_dir) / "memory"
        result = {}

        for name in ["MEMORY.md", "ideation-memory.md", "experiment-memory.md"]:
            path = memory_dir / name
            if path.exists():
                result[name] = truncate(path.read_text(encoding="utf-8"), 2000)

        if not result:
            result["status"] = "No memory files found."

        return result

    async def _get_evolution_memory(self, session: AgentSession):
        """Lazy-init evolution memory for a session."""
        if session.evolution_memory is None:
            from sdk.memory.memory import EvolutionMemory
            session.evolution_memory = EvolutionMemory(session.workspace_dir)
        return session.evolution_memory

    async def run_tournament(
        self, session_id: str, proposals: list[dict],
        judge_model: str = "deepseek-chat",
        phase: str = "W3 Research",
    ) -> dict:
        """Run Elo tournament on proposals with phase-specific dimensions."""
        session = self.sessions.get(session_id)
        if not session:
            return {"error": f"Session {session_id} not found"}

        from pes_controller.elo.tournament import EloTournament

        # Hook: 发射 task_start
        self._hook.emit("task_start", session_id, {
            "task_type": "tournament",
            "num_proposals": len(proposals),
            "judge_model": judge_model,
            "phase": phase,
        })

        tournament = EloTournament(judge_model=judge_model, phase=phase)
        ranked = await tournament.rank(proposals)
        dim_names = tournament.dimension_names

        # Hook: 发射 task_done
        self._hook.emit("task_done", session_id, {
            "task_type": "tournament",
            "status": "completed",
            "winner": ranked[0]["title"] if ranked else "",
            "num_ranked": len(ranked),
        })

        return {
            "status": "completed",
            "phase": phase,
            "num_proposals": len(ranked),
            "winner": ranked[0]["title"] if ranked else "",
            "winner_elo": ranked[0]["elo_rating"] if ranked else 0,
            "dimensions": dim_names,
            "ranked": [
                {
                    "id": p.get("id", ""),
                    "title": p.get("title", "")[:200],
                    "hypothesis": p.get("hypothesis", "")[:1000000],
                    "method_sketch": p.get("method_sketch", "")[:1000000],
                    "elo_rating": p.get("elo_rating", 1500),
                    "product_satisfaction": p.get("product_satisfaction", 0),
                    "source_agent": p.get("source_agent", ""),
                    "rubric_novelty": p.get("rubric_novelty", 0.5),
                    "rubric_novelty_scored": p.get("rubric_novelty_scored", 5.0),
                    "rnd_coarse": p.get("rnd_coarse", 0.5),
                    "rnd_fine": p.get("rnd_fine", 0.5),
                    "verified_novelty": p.get("verified_novelty"),
                    "rnd_details": p.get("rnd_details", {}),
                    # Phase-specific dimension scores
                    **{d: p.get(d, 0) for d in dim_names},
                }
                for p in ranked
            ],
        }

    async def distill(
        self, session_id: str, distill_type: str,
        proposals: list[dict] | None = None,
        failure_info: dict | None = None,
        strategy_info: dict | None = None,
        conversation_history: list[dict] | None = None,
    ) -> dict:
        """Manually trigger evolution memory distillation."""
        session = self.sessions.get(session_id)
        if not session:
            return {"error": f"Session {session_id} not found"}

        # Hook: 发射 task_start
        self._hook.emit("task_start", session_id, {
            "task_type": "distill",
            "distill_type": distill_type,
        })

        mem = await self._get_evolution_memory(session)
        result = {"status": "completed", "actions": []}

        if distill_type in ("llm", "all") and conversation_history:
            llm_result = await mem.llm_distill(
                conversation_history=conversation_history,
                task_id=session_id,
            )
            result["actions"].append({"type": "LLM_DISTILL", "result": llm_result})

        if distill_type in ("ide", "all") and proposals:
            ide_result = await mem.distill_ideation(proposals)
            result["actions"].append({"type": "IDE", "result": ide_result})

        if distill_type in ("ive", "all") and failure_info:
            await mem.record_failure(
                direction=failure_info.get("direction", ""),
                reason=failure_info.get("reason", ""),
                score=failure_info.get("score", 0.0),
            )
            result["actions"].append({"type": "IVE", "status": "recorded"})

        if distill_type in ("ese", "all") and strategy_info:
            await mem.distill_experiment(
                strategy=strategy_info.get("strategy", ""),
                outcome=strategy_info.get("outcome", "SUCCESS"),
                details=strategy_info.get("details", ""),
                score=strategy_info.get("score", 0.0),
            )
            result["actions"].append({"type": "ESE", "status": "recorded"})

        result["stats"] = mem.get_stats()

        # Hook: 发射 task_done
        self._hook.emit("task_done", session_id, {
            "task_type": "distill",
            "status": "completed",
            "actions": [a.get("type", "") for a in result.get("actions", [])],
        })

        return result

    async def get_evolution_memory(
        self, session_id: str, memory_type: str = "all", limit: int = 20,
    ) -> dict:
        """Read evolution memory entries."""
        session = self.sessions.get(session_id)
        if not session:
            return {"error": f"Session {session_id} not found"}

        mem = await self._get_evolution_memory(session)

        result = {"stats": mem.get_stats()}
        if memory_type in ("ideation", "all"):
            result["ideation"] = [
                {
                    "direction": e.get("direction", "")[:120],
                    "status": e.get("status", ""),
                    "score": e.get("score", 0),
                    "source_task": e.get("source_task", ""),
                }
                for e in mem._read_ideation(limit=limit)
            ]
        if memory_type in ("experiment", "all"):
            result["experiment"] = [
                {
                    "strategy": e.get("strategy", "")[:120],
                    "outcome": e.get("outcome", ""),
                    "score": e.get("score", 0),
                    "applicability": e.get("applicability", []),
                }
                for e in mem._read_experiments(limit=limit)
            ]

        return result

    async def _run_agent(self, session: AgentSession, message: str) -> str:
        """Run the agent with rich event streaming (fallback to simple)."""
        if self._use_rich_streaming:
            try:
                return await self._run_agent_rich(session, message)
            except Exception as e:
                logger.warning(f"Rich streaming failed ({e}), falling back to simple")
                self._use_rich_streaming = False
        return await self._run_agent_simple(session, message)

    async def _run_agent_rich(self, session: AgentSession, message: str) -> str:
        """Run agent with full event streaming for dashboard."""
        try:
            from session.stream.events import stream_agent_events
            from session.stream.state import StreamState
        except ImportError:
            raise RuntimeError("Rich streaming imports not available")

        stream_state = StreamState()
        self._stream_states[session.session_id] = stream_state

        metadata = {
            "agent_name": "EvoScientist",
            "updated_at": now_iso(),
            "workspace_dir": session.workspace_dir,
        }
        response_text = ""

        try:
            async for event in stream_agent_events(
                session.agent,
                message,
                session.thread_id,
                metadata=metadata,
            ):
                event_type = event.get("type", "unknown")

                # Update stream state
                if hasattr(stream_state, "handle_event"):
                    stream_state.handle_event(event)

                # Track sub-agents
                if event_type == "subagent_start":
                    name = event.get("name", "sub-agent")
                    if name not in session.sub_agents_used:
                        session.sub_agents_used.append(name)
                    # Hook: 发射 agent_message (子Agent启动)
                    self._hook.emit("agent_message", session.session_id, {
                        "agent": name, "message": "sub-agent started",
                    })
                elif event_type == "tool_call":
                    # Hook: 发射 tool_call
                    self._hook.emit("tool_call", session.session_id, {
                        "tool": str(event.get("tool_name", ""))[:100],
                        "args_preview": str(event.get("args", ""))[:200],
                    })
                elif event_type == "done":
                    response_text = event.get("response", "")
                    # Fix: done event's response is often just the main-agent's
                    # initial announcement. Use stream_state's accumulated text
                    # which includes all sub-agent output.
                    final_text = getattr(stream_state, "response_text", "")
                    if final_text and (not response_text or len(final_text) > len(response_text)):
                        event = {**event, "response": final_text}
                        response_text = final_text

                # Store event
                session.events.append({
                    "type": event_type,
                    "timestamp": now_iso(),
                    "data": {k: str(v)[:200] for k, v in event.items() if k != "type"},
                })

                # Publish to SSE event bus
                self._event_bus.publish(session.session_id, {
                    "type": event_type,
                    "timestamp": now_iso(),
                    "data": event,
                })
        except Exception as e:
            logger.error(f"Rich streaming error: {e}", exc_info=True)
            # Publish error event
            self._event_bus.publish(session.session_id, {
                "type": "error",
                "timestamp": now_iso(),
                "data": {"message": str(e)},
            })
            raise

        return response_text or stream_state.response_text or "(No response from agent)"

    async def _run_agent_simple(self, session: AgentSession, message: str) -> str:
        """Run the agent with simplified streaming (fallback)."""
        from langchain_core.messages import HumanMessage

        config = {
            "configurable": {"thread_id": session.thread_id},
            "metadata": {
                "agent_name": "EvoScientist",
                "updated_at": now_iso(),
                "workspace_dir": session.workspace_dir,
            },
        }

        human_msg = HumanMessage(content=message)
        response_text = ""

        try:
            async for chunk in session.agent.astream(
                {"messages": [human_msg]},
                config=config,
                stream_mode="values",
            ):
                messages = chunk.get("messages", [])
                if messages:
                    last_msg = messages[-1]
                    if hasattr(last_msg, "name") and last_msg.name:
                        if last_msg.name not in session.sub_agents_used:
                            session.sub_agents_used.append(last_msg.name)
                    if hasattr(last_msg, "content") and last_msg.type == "ai":
                        response_text = last_msg.content if isinstance(last_msg.content, str) else str(last_msg.content)

                    event = {
                        "type": last_msg.type,
                        "timestamp": now_iso(),
                        "data": {"content_preview": str(last_msg.content)[:200] if hasattr(last_msg, "content") else ""},
                    }
                    session.events.append(event)

                    # Still publish to event bus for dashboard
                    self._event_bus.publish(session.session_id, event)
        except Exception as e:
            logger.error(f"Agent streaming error: {e}", exc_info=True)
            raise

        return response_text or "(No response from agent)"

    async def _direct_llm_call(self, session: AgentSession, prompt: str) -> str:
        """Direct LLM call without tools — used for persona generation.

        Bypasses the agent framework to avoid tool-calling failures
        (Tavily rate limits, search errors, etc.) that produce empty outputs.
        """
        try:
            from session.config.settings import get_effective_config, apply_config_to_env
            from session.llm.models import get_chat_model
            from langchain_core.messages import HumanMessage, SystemMessage

            cfg = get_effective_config()
            apply_config_to_env(cfg)

            # Use session's model/provider if specified
            model_name = session.model or cfg.model
            provider_name = session.provider or cfg.provider

            llm = get_chat_model(model=model_name, provider=provider_name, max_tokens=16384)

            system_msg = SystemMessage(
                content="You are a research proposal generator. Output ONLY valid JSON. "
                        "No analysis, no reasoning outside the JSON, no markdown. "
                        "Your entire response must be a single JSON object."
            )
            human_msg = HumanMessage(content=prompt)

            response = await asyncio.to_thread(
                lambda: llm.invoke([system_msg, human_msg])
            )

            if hasattr(response, "content"):
                text = response.content if isinstance(response.content, str) else str(response.content)
            else:
                text = str(response)

            logger.info(f"Direct LLM call ({model_name}): {len(text)} chars")
            return text

        except Exception as e:
            logger.error(f"Direct LLM call failed: {e}", exc_info=True)
            # Fallback to agent-based execution
            logger.info("Falling back to agent-based execution")
            return await self._run_agent(session, prompt)
