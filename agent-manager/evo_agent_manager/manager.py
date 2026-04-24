"""
AgentManager — Session management and multi-agent discussion coordination.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .event_bus import EventBus
from .utils import generate_session_id, now_iso, truncate

logger = logging.getLogger(__name__)


@dataclass
class AgentSession:
    """Represents an active agent session."""
    session_id: str
    agent: Any
    thread_id: str
    workspace_dir: str
    created_at: str
    status: str = "idle"  # idle / running / waiting_approval / error
    events: list[dict] = field(default_factory=list)
    last_response: str = ""
    sub_agents_used: list[str] = field(default_factory=list)
    pending_approvals: list[dict] = field(default_factory=list)
    # Thread management for context overflow prevention
    thread_count: int = 0
    thread_summaries: list[str] = field(default_factory=list)


class AgentManager:
    """Manages EvoScientist agent sessions."""

    # Safety threshold: rotate thread before hitting model's context limit
    MAX_CONTEXT_CHARS = 2_400_000  # ~800K tokens (80% of DeepSeek's 1M)

    def __init__(self, base_dir: str | None = None):
        self.base_dir = base_dir or str(Path(__file__).parent.parent)
        self.sessions: dict[str, AgentSession] = {}
        self._checkpointer = None
        self._checkpoint_conn = None
        self._event_bus = EventBus()
        self._stream_states: dict[str, Any] = {}
        self._use_rich_streaming = True
        # Pipeline pause gates: per-session asyncio.Event
        self._pipeline_gates: dict[str, asyncio.Event] = {}
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
        """Get or create SqliteSaver (disk-persisted, survives restarts)."""
        if self._checkpointer is None:
            import sqlite3
            from langgraph.checkpoint.sqlite import SqliteSaver
            db_path = Path(self.base_dir) / ".evo_checkpoints.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._checkpoint_conn = sqlite3.connect(str(db_path), check_same_thread=False)
            self._checkpointer = SqliteSaver(self._checkpoint_conn)
            logger.info(f"SqliteSaver initialized at {db_path}")
        return self._checkpointer

    # ── Session persistence ──

    def _sessions_dir(self, workspace_dir: str) -> Path:
        return Path(workspace_dir) / ".evo_sessions"

    def _session_registry_path(self) -> Path:
        return Path(self.base_dir) / ".evo_session_registry.json"

    def _save_session_meta(self, session: AgentSession):
        """Persist session metadata to disk (not the agent object)."""
        try:
            sdir = self._sessions_dir(session.workspace_dir)
            sdir.mkdir(parents=True, exist_ok=True)
            data = {
                "session_id": session.session_id,
                "workspace_dir": session.workspace_dir,
                "thread_id": session.thread_id,
                "created_at": session.created_at,
                "status": session.status,
                "sub_agents_used": session.sub_agents_used,
                "thread_count": session.thread_count,
                "thread_summaries": session.thread_summaries,
                "last_response": session.last_response[:8000] if session.last_response else "",
            }
            (sdir / f"{session.session_id}.json").write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            # Update global registry: session_id → workspace_dir
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
                    session = AgentSession(
                        session_id=sid,
                        agent=None,  # will be rebuilt on first use
                        thread_id=data.get("thread_id", sid),
                        workspace_dir=data["workspace_dir"],
                        created_at=data["created_at"],
                        status="recovered",
                        sub_agents_used=data.get("sub_agents_used", []),
                        thread_count=data.get("thread_count", 0),
                        thread_summaries=data.get("thread_summaries", []),
                    )
                    session.last_response = data.get("last_response", "")
                    self.sessions[sid] = session
                    recovered += 1
                except Exception as e:
                    logger.warning(f"Failed to load session {sf}: {e}")

        if recovered:
            logger.info(f"Recovered {recovered} session(s) from disk")

    async def _ensure_agent(self, session: AgentSession):
        """Rebuild agent for a recovered session if needed."""
        if session.agent is not None:
            return
        from .agent_factory import create_agent
        checkpointer = await self._get_checkpointer()
        session.agent = create_agent(
            workspace_dir=session.workspace_dir,
            base_dir=self.base_dir,
            model=None,
            provider=None,
            checkpointer=checkpointer,
        )
        logger.info(f"Agent rebuilt for recovered session {session.session_id}")

    async def create_session(
        self,
        workspace_dir: str,
        model: str | None = None,
        provider: str | None = None,
    ) -> dict:
        """Create a new agent session."""
        from .agent_factory import create_agent

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
        )
        self.sessions[session_id] = session
        self._save_session_meta(session)

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

        # Rotate thread: new thread for each call, carry summaries
        summary = self._summarize_response(session.last_response) if session.last_response else ""
        self._rotate_thread(session, summary)

        session.status = "running"
        session.sub_agents_used = []
        session.events = []

        # Rebuild agent for recovered sessions
        await self._ensure_agent(session)

        try:
            # Inject previous context
            ctx_prefix = self._build_context_prefix(session)
            full_message = ctx_prefix + message if ctx_prefix else message

            response = await self._run_agent(session, full_message)
            session.last_response = response
            session.status = "idle"
            self._save_session_meta(session)

            return {
                "response": truncate(response, 4000),
                "sub_agents_used": session.sub_agents_used,
                "events_count": len(session.events),
                "status": "completed",
                "thread_id": session.thread_id,
            }
        except Exception as e:
            session.status = "error"
            logger.error(f"Agent error in session {session_id}: {e}")
            return {"error": str(e), "status": "error"}

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

        try:
            # Inject previous context into the discussion prompt
            ctx_prefix = self._build_context_prefix(session)
            full_prompt = ctx_prefix + discussion_prompt if ctx_prefix else discussion_prompt

            response = await self._run_agent(session, full_prompt)
            session.last_response = response
            session.status = "idle"
            self._save_session_meta(session)

            # Extract code proposals from transcript
            code_proposals = self._extract_code_proposals(response, excluded)

            has_proposals = len(code_proposals) > 0
            return {
                "transcript": truncate(response, 6000),
                "agents_participated": session.sub_agents_used,
                "events_count": len(session.events),
                "code_proposals": code_proposals,
                "has_code_proposals": has_proposals,
                "requires_claude_code": has_proposals,
                "status": "completed",
                "thread_id": session.thread_id,
            }
        except Exception as e:
            session.status = "error"
            return {"error": str(e)}

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
            memory_summary = memory_path.read_text(encoding="utf-8")[:500]

        return {
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
            "thinking_text": getattr(state, "thinking_text", "")[:500],
            "response_text": getattr(state, "response_text", "")[:2000],
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
            from EvoScientist.stream.events import stream_agent_events
            from EvoScientist.stream.state import StreamState
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
