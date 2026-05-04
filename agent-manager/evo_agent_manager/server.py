"""
EvoScientist Agent Manager — MCP Server.

Exposes 17 tools to Claude Code for controlling the multi-agent system:
  evo_create_session, evo_send, evo_discuss, evo_status,
  evo_list_sessions, evo_resume, evo_approve, evo_get_memory,
  evo_pipeline_control, evo_run_tournament, evo_distill, evo_get_evolution_memory,
  evo_get_fitness, evo_get_strategy, evo_patch_strategy, evo_rollback_strategy,
  evo_meta_evolve
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
                    "description": "LLM model name (default: deepseek-chat)",
                },
                "provider": {
                    "type": "string",
                    "description": "LLM provider: openai, anthropic, google (default: openai)",
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
            "Multiple sub-agents analyze the topic from their expertise (planning, research, analysis) "
            "and produce a discussion transcript with synthesized conclusion. "
            "Code and debug agents are excluded by default — implementation proposals "
            "are returned as 'code_proposals' for Claude Code to execute."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID"},
                "topic": {"type": "string", "description": "Topic for multi-agent discussion"},
                "agents": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific agents to involve (optional, default: planner, researcher, analyst)",
                },
                "exclude_agents": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Agents to exclude (default: ['code-agent', 'debug-agent']). Proposals returned instead of executed.",
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
    Tool(
        name="evo_pipeline_control",
        description=(
            "Control the pipeline state from Claude Code. Actions: pause, resume, "
            "switch_to_claude (mark phase as awaiting Claude Code), switch_to_agent "
            "(return control to multi-agent pipeline), set_phase (jump to a specific phase). "
            "Updates PIPELINE_STATE.json and notifies dashboard via SSE."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID"},
                "action": {
                    "type": "string",
                    "description": "Control action: pause, resume, switch_to_claude, switch_to_agent, set_phase",
                    "enum": ["pause", "resume", "switch_to_claude", "switch_to_agent", "set_phase"],
                },
                "phase": {
                    "type": "number",
                    "description": "Target phase number (only for set_phase action)",
                },
            },
            "required": ["session_id", "action"],
        },
    ),
    Tool(
        name="evo_run_tournament",
        description=(
            "Run an Elo-based tournament to rank research proposals via pairwise comparison. "
            "Uses an LLM judge to compare proposals on 4 dimensions: "
            "novelty, feasibility, relevance, and clarity. "
            "Full round-robin: N*(N-1)/2 comparisons. Returns proposals sorted by Elo rating."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID"},
                "proposals": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "title": {"type": "string"},
                            "hypothesis": {"type": "string"},
                            "method_sketch": {"type": "string"},
                        },
                    },
                    "description": "List of proposal dicts with id, title, hypothesis, method_sketch",
                },
                "judge_model": {
                    "type": "string",
                    "description": "LLM model for pairwise judging (default: deepseek-chat)",
                },
            },
            "required": ["session_id", "proposals"],
        },
    ),
    Tool(
        name="evo_distill",
        description=(
            "Manually trigger evolution memory distillation. "
            "IDE: distill ideation directions from ranked proposals. "
            "IVE: record a validation failure. "
            "ESE: record an effective experiment strategy. "
            "Use after ideation/research phases to persist learnings."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID"},
                "distill_type": {
                    "type": "string",
                    "description": "Type of distillation: ide, ive, ese, llm, all",
                    "enum": ["ide", "ive", "ese", "llm", "all"],
                },
                "proposals": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "For IDE: ranked proposal list [{title, hypothesis, elo_rating}, ...]",
                },
                "failure_info": {
                    "type": "object",
                    "properties": {
                        "direction": {"type": "string"},
                        "reason": {"type": "string"},
                        "score": {"type": "number"},
                    },
                    "description": "For IVE: {direction, reason, score}",
                },
                "strategy_info": {
                    "type": "object",
                    "properties": {
                        "strategy": {"type": "string"},
                        "outcome": {"type": "string"},
                        "details": {"type": "string"},
                        "score": {"type": "number"},
                    },
                    "description": "For ESE: {strategy, outcome, details, score}",
                },
                "conversation_history": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "For LLM: list of message dicts [{role, content}, ...]",
                },
            },
            "required": ["session_id", "distill_type"],
        },
    ),
    Tool(
        name="evo_get_evolution_memory",
        description=(
            "Read evolution memory entries (IDE/IVE/ESE). "
            "Returns ideation directions and experiment strategies from previous tasks."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID"},
                "memory_type": {
                    "type": "string",
                    "description": "Which memory to read: ideation, experiment, all",
                    "enum": ["ideation", "experiment", "all"],
                },
                "limit": {"type": "number", "description": "Max entries to return (default 20)"},
            },
            "required": ["session_id"],
        },
    ),
    Tool(
        name="evo_get_fitness",
        description=(
            "Get fitness history and trend for a session. "
            "Returns eval scores over time, trend direction (improving/declining/stable), and summary statistics."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID"},
                "limit": {"type": "number", "description": "Max history entries (default 50)"},
            },
            "required": ["session_id"],
        },
    ),
    Tool(
        name="evo_get_strategy",
        description=(
            "Read current strategy file content. "
            "Returns the markdown content, parsed key-value parameters, and version history."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID"},
                "filename": {
                    "type": "string",
                    "description": "Strategy file name (default: distillation_strategy.md). "
                    "Options: distillation_strategy.md, memory_retrieval.md, self_modification.md",
                },
            },
            "required": ["session_id"],
        },
    ),
    Tool(
        name="evo_patch_strategy",
        description=(
            "Apply a modification to a strategy file. "
            "Archives current version before applying. "
            "Used by meta-evolution to evolve the system's own learning parameters."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID"},
                "filename": {
                    "type": "string",
                    "description": "Target strategy file (default: distillation_strategy.md)",
                },
                "content": {"type": "string", "description": "New content for the strategy file"},
                "rationale": {"type": "string", "description": "Why this modification was proposed"},
            },
            "required": ["session_id", "content"],
        },
    ),
    Tool(
        name="evo_rollback_strategy",
        description=(
            "Rollback a strategy file to a previous version. "
            "Restores archived content if a strategy change caused regression."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID"},
                "version": {"type": "number", "description": "Version to rollback to (null = previous)"},
                "filename": {"type": "string", "description": "Target strategy file"},
            },
            "required": ["session_id"],
        },
    ),
    Tool(
        name="evo_meta_evolve",
        description=(
            "Trigger meta-evolution: check if self-modification should occur, "
            "propose strategy changes via MetaAgent LLM, apply with validation. "
            "Returns whether a modification was proposed, applied, or skipped."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID"},
                "force": {
                    "type": "boolean",
                    "description": "Force trigger even if conditions not met (default: false)",
                },
                "target_file": {
                    "type": "string",
                    "description": "Which strategy file to evolve (default: distillation_strategy.md)",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Propose but don't apply (default: false)",
                },
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
            model=arguments.get("model", "deepseek-chat"),
            provider=arguments.get("provider", "openai"),
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
            exclude_agents=arguments.get("exclude_agents"),
        )
    elif name == "evo_status":
        result = await mgr.get_status(session_id=arguments["session_id"])
    elif name == "evo_list_sessions":
        result = mgr.list_sessions()
    elif name == "evo_resume":
        # Resume: check if session exists, reload from disk if needed
        sid = arguments["session_id"]
        if sid not in mgr.sessions:
            mgr._load_sessions_from_disk()
        if sid in mgr.sessions:
            session = mgr.sessions[sid]
            agent_ok = True
            agent_error = ""
            if session.agent is None:
                try:
                    await mgr._ensure_agent(session)
                except Exception as exc:
                    agent_ok = False
                    agent_error = str(exc)[:500]
                    logger.warning(f"Agent rebuild failed for {sid}: {exc}")
            result = await mgr.get_status(session_id=sid)
            if not agent_ok:
                result["agent_status"] = "rebuild_failed"
                result["agent_error"] = agent_error
        else:
            result = {"error": f"Session {sid} not found (no disk backup available)"}
    elif name == "evo_approve":
        result = await mgr.approve(
            session_id=arguments["session_id"],
            action_id=arguments["action_id"],
            approved=arguments["approved"],
        )
    elif name == "evo_get_memory":
        result = await mgr.get_memory(session_id=arguments["session_id"])
    elif name == "evo_pipeline_control":
        result = mgr.pipeline_control(
            session_id=arguments["session_id"],
            action=arguments["action"],
            phase=arguments.get("phase"),
        )
    elif name == "evo_run_tournament":
        result = await mgr.run_tournament(
            session_id=arguments["session_id"],
            proposals=arguments["proposals"],
            judge_model=arguments.get("judge_model", "deepseek-chat"),
        )
    elif name == "evo_distill":
        result = await mgr.distill(
            session_id=arguments["session_id"],
            distill_type=arguments["distill_type"],
            proposals=arguments.get("proposals"),
            failure_info=arguments.get("failure_info"),
            strategy_info=arguments.get("strategy_info"),
            conversation_history=arguments.get("conversation_history"),
        )
    elif name == "evo_get_evolution_memory":
        result = await mgr.get_evolution_memory(
            session_id=arguments["session_id"],
            memory_type=arguments.get("memory_type", "all"),
            limit=arguments.get("limit", 20),
        )
    elif name == "evo_get_fitness":
        session = mgr.sessions.get(arguments["session_id"])
        if not session:
            result = {"error": f"Session {arguments['session_id']} not found"}
        else:
            from .evolution.fitness import FitnessTracker
            fitness = FitnessTracker(session.workspace_dir)
            result = {
                "stats": fitness.get_stats(),
                "history": fitness.get_history(limit=arguments.get("limit", 50)),
            }
    elif name == "evo_get_strategy":
        session = mgr.sessions.get(arguments["session_id"])
        if not session:
            result = {"error": f"Session {arguments['session_id']} not found"}
        else:
            from .evolution.strategy import StrategyManager
            sm = StrategyManager(session.workspace_dir)
            filename = arguments.get("filename", "distillation_strategy.md")
            content = sm.load_strategy(filename)
            kv = sm.parse_kv(content)
            result = {
                "filename": filename,
                "content": content,
                "parameters": kv,
                "version_history": sm.get_version_history(),
            }
    elif name == "evo_patch_strategy":
        session = mgr.sessions.get(arguments["session_id"])
        if not session:
            result = {"error": f"Session {arguments['session_id']} not found"}
        else:
            from .evolution.strategy import StrategyManager
            sm = StrategyManager(session.workspace_dir)
            filename = arguments.get("filename", "distillation_strategy.md")
            archive_path = sm.apply_patch(
                patch=arguments["content"],
                rationale=arguments.get("rationale", ""),
                target_file=filename,
            )
            result = {
                "status": "applied",
                "filename": filename,
                "archive_path": str(archive_path),
            }
    elif name == "evo_rollback_strategy":
        session = mgr.sessions.get(arguments["session_id"])
        if not session:
            result = {"error": f"Session {arguments['session_id']} not found"}
        else:
            from .evolution.strategy import StrategyManager
            sm = StrategyManager(session.workspace_dir)
            success = sm.rollback(
                version=arguments.get("version"),
                target_file=arguments.get("filename"),
            )
            result = {"status": "rolled_back" if success else "rollback_failed"}
    elif name == "evo_meta_evolve":
        session = mgr.sessions.get(arguments["session_id"])
        if not session:
            result = {"error": f"Session {arguments['session_id']} not found"}
        else:
            from .evolution.fitness import FitnessTracker
            from .evolution.meta_agent import MetaAgent
            from .evolution.strategy import StrategyManager
            from .evolution.trigger import MetaCognitionTrigger
            from .evolution.validator import EvolutionValidator

            fitness = FitnessTracker(session.workspace_dir)
            scores = fitness.get_recent_scores(n=10)

            trigger = MetaCognitionTrigger()
            agent_state = trigger.build_agent_state(
                scores, cycle_just_completed=arguments.get("force", False)
            )
            should = trigger.should_trigger(agent_state) or arguments.get("force", False)

            if not should:
                result = {
                    "triggered": False,
                    "reason": "No trigger condition met",
                    "scores": scores,
                }
            else:
                sm = StrategyManager(session.workspace_dir)
                target = arguments.get("target_file", "distillation_strategy.md")
                current = sm.load_strategy(target)
                fitness_stats = fitness.get_stats()
                mem = await mgr._get_evolution_memory(session)
                memory_stats = mem.get_stats()

                meta = MetaAgent()
                new_content, rationale = await meta.propose_modification(
                    target_file=target,
                    current_strategy=current,
                    fitness_history=fitness.get_history(limit=5),
                    evolution_log=[],
                    memory_stats=memory_stats,
                )

                if arguments.get("dry_run", False):
                    result = {
                        "triggered": True,
                        "applied": False,
                        "rationale": rationale,
                        "new_content_preview": new_content[:500],
                        "current_content_preview": current[:500],
                    }
                else:
                    validator = EvolutionValidator(session.workspace_dir)
                    strategy_path = sm.base_dir / target
                    validator.on_strategy_change(arguments["session_id"], strategy_path)
                    archive_path = sm.apply_patch(
                        new_content, rationale=rationale, target_file=target
                    )
                    result = {
                        "triggered": True,
                        "applied": True,
                        "rationale": rationale,
                        "archive_path": str(archive_path),
                        "observation_window": validator.OBSERVATION_WINDOW,
                    }
    else:
        result = {"error": f"Unknown tool: {name}"}

    return json.dumps(result, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# MCP Server setup
# ---------------------------------------------------------------------------

def create_server(base_dir: str | None = None, dashboard_port: int = 8420) -> Server:
    """Create and configure the MCP server."""
    server = Server("evo-agent-manager")

    # Initialize manager with base_dir
    mgr = get_manager(base_dir)

    # Wire manager to dashboard
    from .dashboard import set_manager
    set_manager(mgr)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        result_text = await handle_tool(name, arguments)
        return [TextContent(type="text", text=result_text)]

    return server


async def run_server(base_dir: str | None = None, dashboard_port: int = 8420):
    """Run the MCP server on stdio with optional dashboard."""
    # Ensure API keys are available (Claude Code may not inject -e vars at runtime)
    _defaults = {
        "OPENAI_API_KEY": "sk-d56c7dbcd28c44b689773a3f544486b2",
        "OPENAI_BASE_URL": "https://api.deepseek.com/v1",
        "OPENAI_API_BASE": "https://api.deepseek.com/v1",
        "DEEPSEEK_API_KEY": "sk-d56c7dbcd28c44b689773a3f544486b2",
        "TAVILY_API_KEY": "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",
    }
    for k, v in _defaults.items():
        os.environ.setdefault(k, v)

    server = create_server(base_dir)

    # Start dashboard web server in background thread (shares AgentManager)
    if dashboard_port and dashboard_port > 0:
        try:
            from .dashboard import start_dashboard
            start_dashboard(port=dashboard_port)
        except Exception as e:
            logger.warning(f"Dashboard failed to start: {e}")

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
    parser.add_argument("--dashboard-port", type=int, default=8420, help="Dashboard web server port (0 to disable)")
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

    asyncio.run(run_server(base_dir, dashboard_port=args.dashboard_port))


if __name__ == "__main__":
    main()
