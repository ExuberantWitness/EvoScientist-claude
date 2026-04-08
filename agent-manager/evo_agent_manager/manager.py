"""
AgentManager — Session management and multi-agent discussion coordination.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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


class AgentManager:
    """Manages EvoScientist agent sessions."""

    def __init__(self, base_dir: str | None = None):
        self.base_dir = base_dir or str(Path(__file__).parent.parent)
        self.sessions: dict[str, AgentSession] = {}
        self._checkpointer = None

    async def _get_checkpointer(self):
        """Get or create SQLite checkpointer."""
        if self._checkpointer is None:
            try:
                from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
                db_path = Path(self.base_dir) / "sessions.db"
                self._checkpointer = AsyncSqliteSaver.from_conn_string(str(db_path))
                await self._checkpointer.setup()
            except ImportError:
                from langgraph.checkpoint.memory import InMemorySaver
                self._checkpointer = InMemorySaver()
        return self._checkpointer

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

        session.status = "running"
        session.sub_agents_used = []
        session.events = []

        try:
            response = await self._run_agent(session, message)
            session.last_response = response
            session.status = "idle"

            return {
                "response": truncate(response, 4000),
                "sub_agents_used": session.sub_agents_used,
                "events_count": len(session.events),
                "status": "completed",
            }
        except Exception as e:
            session.status = "error"
            logger.error(f"Agent error in session {session_id}: {e}")
            return {"error": str(e), "status": "error"}

    async def discuss(
        self, session_id: str, topic: str, agents: list[str] | None = None
    ) -> dict:
        """Trigger a multi-agent discussion on a topic.

        The main agent orchestrates sub-agents to discuss the topic
        from multiple perspectives.
        """
        session = self.sessions.get(session_id)
        if not session:
            return {"error": f"Session {session_id} not found"}

        # Craft a discussion prompt that triggers multi-agent delegation
        agent_list = ", ".join(agents) if agents else "planner, researcher, code expert, and analyst"
        discussion_prompt = (
            f"I need a multi-perspective discussion on this topic: {topic}\n\n"
            f"Please delegate to your sub-agents ({agent_list}) and have each one "
            f"contribute their perspective. For each sub-agent:\n"
            f"1. Ask them to analyze the topic from their expertise\n"
            f"2. Collect their responses\n"
            f"3. Synthesize a conclusion\n\n"
            f"Format the output as a discussion transcript showing each agent's contribution."
        )

        session.status = "running"
        session.sub_agents_used = []
        session.events = []

        try:
            response = await self._run_agent(session, discussion_prompt)
            session.last_response = response
            session.status = "idle"

            return {
                "transcript": truncate(response, 6000),
                "agents_participated": session.sub_agents_used,
                "events_count": len(session.events),
                "status": "completed",
            }
        except Exception as e:
            session.status = "error"
            return {"error": str(e)}

    async def get_status(self, session_id: str) -> dict:
        """Get current session status."""
        session = self.sessions.get(session_id)
        if not session:
            return {"error": f"Session {session_id} not found"}

        # Read memory if exists
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

        # Find and process the approval
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
            result["status"] = "No memory files found. Run /evo-memory init first."

        return result

    async def _run_agent(self, session: AgentSession, message: str) -> str:
        """Run the agent and collect response."""
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
            # Try streaming with event processing
            async for chunk in session.agent.astream(
                {"messages": [human_msg]},
                config=config,
                stream_mode="values",
            ):
                messages = chunk.get("messages", [])
                if messages:
                    last_msg = messages[-1]
                    # Track sub-agent usage
                    if hasattr(last_msg, "name") and last_msg.name:
                        if last_msg.name not in session.sub_agents_used:
                            session.sub_agents_used.append(last_msg.name)
                    # Collect AI response
                    if hasattr(last_msg, "content") and last_msg.type == "ai":
                        response_text = last_msg.content if isinstance(last_msg.content, str) else str(last_msg.content)

                    session.events.append({
                        "type": last_msg.type,
                        "content_preview": str(last_msg.content)[:100] if hasattr(last_msg, "content") else "",
                    })
        except Exception as e:
            logger.error(f"Agent streaming error: {e}", exc_info=True)
            raise

        return response_text or "(No response from agent)"
