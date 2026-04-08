"""
EvoScientist Agent Manager — MCP Server.

Exposes 8 tools to Claude Code for controlling the multi-agent system:
  evo_create_session, evo_send, evo_discuss, evo_status,
  evo_list_sessions, evo_resume, evo_approve, evo_get_memory
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .manager import AgentManager

logger = logging.getLogger(__name__)

# Global manager instance (initialized on first use)
_manager: AgentManager | None = None


def get_manager(base_dir: str | None = None) -> AgentManager:
    global _manager
    if _manager is None:
        _manager = AgentManager(base_dir=base_dir)
    return _manager


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS = [
    Tool(
        name="evo_create_session",
        description=(
            "Create a new EvoScientist multi-agent session. "
            "Returns session_id for use with other evo_ tools. "
            "The agent has 6 sub-agents: planner, researcher, coder, debugger, analyst, writer."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_dir": {
                    "type": "string",
                    "description": "Absolute path to the project workspace directory",
                },
                "model": {
                    "type": "string",
                    "description": "LLM model name (default: claude-sonnet-4-5)",
                },
                "provider": {
                    "type": "string",
                    "description": "LLM provider: anthropic, openai, google (default: anthropic)",
                },
            },
            "required": ["workspace_dir"],
        },
    ),
    Tool(
        name="evo_send",
        description=(
            "Send a message to an EvoScientist agent session. "
            "The agent auto-delegates to sub-agents (planner/researcher/coder/debugger/analyst/writer) as needed. "
            "Returns the agent response and which sub-agents were used. "
            "Supports conda, GPU, and system commands (no sandbox restrictions)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID from evo_create_session"},
                "message": {"type": "string", "description": "Message to send to the agent"},
            },
            "required": ["session_id", "message"],
        },
    ),
    Tool(
        name="evo_discuss",
        description=(
            "Trigger a multi-agent discussion on a topic. "
            "Multiple sub-agents analyze the topic from their expertise (planning, research, code, analysis) "
            "and produce a discussion transcript with synthesized conclusion."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID"},
                "topic": {"type": "string", "description": "Topic for multi-agent discussion"},
                "agents": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific agents to involve (optional, default: all)",
                },
            },
            "required": ["session_id", "topic"],
        },
    ),
    Tool(
        name="evo_status",
        description="Get the current status of an agent session, including active agent, progress, and memory summary.",
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID"},
            },
            "required": ["session_id"],
        },
    ),
    Tool(
        name="evo_list_sessions",
        description="List all active EvoScientist agent sessions.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="evo_resume",
        description="Resume a previous agent session by ID. Loads conversation history from checkpoint.",
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID to resume"},
            },
            "required": ["session_id"],
        },
    ),
    Tool(
        name="evo_approve",
        description="Approve or reject a pending agent action (HITL gate). Used when agents request permission for risky operations.",
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID"},
                "action_id": {"type": "string", "description": "ID of the pending action"},
                "approved": {"type": "boolean", "description": "True to approve, false to reject"},
            },
            "required": ["session_id", "action_id", "approved"],
        },
    ),
    Tool(
        name="evo_get_memory",
        description="Read the agent's persistent memory (user profile, research preferences, experiment history, learned preferences).",
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID"},
            },
            "required": ["session_id"],
        },
    ),
]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

async def handle_tool(name: str, arguments: dict) -> str:
    """Route tool calls to the appropriate manager method."""
    mgr = get_manager()

    if name == "evo_create_session":
        result = await mgr.create_session(
            workspace_dir=arguments["workspace_dir"],
            model=arguments.get("model"),
            provider=arguments.get("provider"),
        )
    elif name == "evo_send":
        result = await mgr.send_message(
            session_id=arguments["session_id"],
            message=arguments["message"],
        )
    elif name == "evo_discuss":
        result = await mgr.discuss(
            session_id=arguments["session_id"],
            topic=arguments["topic"],
            agents=arguments.get("agents"),
        )
    elif name == "evo_status":
        result = await mgr.get_status(session_id=arguments["session_id"])
    elif name == "evo_list_sessions":
        result = mgr.list_sessions()
    elif name == "evo_resume":
        # Resume = get status (session is already in memory if created)
        result = await mgr.get_status(session_id=arguments["session_id"])
    elif name == "evo_approve":
        result = await mgr.approve(
            session_id=arguments["session_id"],
            action_id=arguments["action_id"],
            approved=arguments["approved"],
        )
    elif name == "evo_get_memory":
        result = await mgr.get_memory(session_id=arguments["session_id"])
    else:
        result = {"error": f"Unknown tool: {name}"}

    return json.dumps(result, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# MCP Server setup
# ---------------------------------------------------------------------------

def create_server(base_dir: str | None = None) -> Server:
    """Create and configure the MCP server."""
    server = Server("evo-agent-manager")

    # Initialize manager with base_dir
    get_manager(base_dir)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        result_text = await handle_tool(name, arguments)
        return [TextContent(type="text", text=result_text)]

    return server


async def run_server(base_dir: str | None = None):
    """Run the MCP server on stdio."""
    server = create_server(base_dir)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def run_test():
    """Print available tools for verification."""
    print("EvoScientist Agent Manager — MCP Server")
    print(f"Tools: {len(TOOLS)}")
    print()
    for tool in TOOLS:
        print(f"  {tool.name}")
        print(f"    {tool.description[:80]}...")
        print()
    print("Server ready. Add to Claude Code with:")
    print("  claude mcp add evo-agents -- conda run -n evo-agents python -m evo_agent_manager.server")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="EvoScientist Agent Manager MCP Server")
    parser.add_argument("--test", action="store_true", help="Print tool list and exit")
    parser.add_argument("--base-dir", type=str, default=None, help="Base directory for agent-manager")
    args = parser.parse_args()

    if args.test:
        run_test()
        return

    base_dir = args.base_dir or str(Path(__file__).parent.parent)

    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )

    asyncio.run(run_server(base_dir))


if __name__ == "__main__":
    main()
