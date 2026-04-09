"""
AgentFactory — Creates EvoScientist LangGraph agents without sandbox restrictions.

Replaces create_cli_agent() from EvoScientist.EvoScientist, using
UnrestrictedBackend instead of CustomSandboxBackend.
"""

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _add_core_to_path(base_dir: str):
    """Add evoscientist_core to Python path so EvoScientist modules can be imported."""
    core_path = str(Path(base_dir) / "evoscientist_core")
    if core_path not in sys.path:
        sys.path.insert(0, core_path)


def create_agent(
    workspace_dir: str,
    *,
    base_dir: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    checkpointer=None,
):
    """Create an EvoScientist agent with unrestricted backend.

    Args:
        workspace_dir: Project workspace directory (agent's working dir).
        base_dir: Path to agent-manager directory (contains evoscientist_core/).
        model: LLM model name (default from config).
        provider: LLM provider (default from config).
        checkpointer: LangGraph checkpointer for session persistence.

    Returns:
        Compiled LangGraph agent with full multi-agent capabilities.
    """
    if base_dir:
        _add_core_to_path(base_dir)

    # Lazy import after path is set up
    from EvoScientist.config.settings import get_effective_config
    from EvoScientist.llm.models import get_chat_model
    from EvoScientist.prompts import get_system_prompt
    from EvoScientist.utils import load_subagents
    # SKILLS_DIR is defined in EvoScientist.py, not paths.py
    SKILLS_DIR = str(Path(base_dir) / "evoscientist_core" / "EvoScientist" / "skills")

    # Load config
    cfg = get_effective_config()
    if model:
        cfg.model = model
    if provider:
        cfg.provider = provider

    # Create LLM
    chat_model = get_chat_model(model=cfg.model, provider=cfg.provider)

    # Build tool registry
    tools = []
    try:
        from EvoScientist.tools import think_tool
        tools.append(think_tool)
    except ImportError:
        pass

    if os.environ.get("TAVILY_API_KEY"):
        try:
            from EvoScientist.tools import tavily_search
            tools.append(tavily_search)
        except ImportError:
            pass

    try:
        from EvoScientist.tools import skill_manager
        tools.append(skill_manager)
    except ImportError:
        pass

    tool_registry = {t.name: t for t in tools}

    # Load sub-agents
    subagent_config = Path(__file__).parent / "evoscientist_core" / "EvoScientist" / "subagent.yaml"
    if base_dir:
        subagent_config = Path(base_dir) / "evoscientist_core" / "EvoScientist" / "subagent.yaml"

    prompt_refs = _build_prompt_refs()

    subagents = []
    if subagent_config.exists():
        subagents = load_subagents(
            subagent_config,  # Pass Path object, not str
            tool_registry=tool_registry,
            prompt_refs=prompt_refs,
        )
        # Inject middleware into sub-agents
        _inject_subagent_middleware(subagents, chat_model)

    # Build backend (UNRESTRICTED — no sandbox)
    from .backend import UnrestrictedBackend
    workspace_backend = UnrestrictedBackend(root_dir=workspace_dir, timeout=300)

    # Build middleware
    middleware = _build_middleware(cfg, chat_model, workspace_dir)

    # System prompt
    system_prompt = get_system_prompt()

    # Create agent via deepagents
    try:
        from deepagents import create_deep_agent
    except ImportError:
        logger.error("deepagents not installed. Run: pip install deepagents>=0.4.11")
        raise

    # Use InMemorySaver if no checkpointer provided
    if checkpointer is None:
        try:
            from langgraph.checkpoint.memory import InMemorySaver
            checkpointer = InMemorySaver()
        except ImportError:
            pass

    kwargs = {
        "name": "EvoScientist",
        "model": chat_model,
        "tools": tools,
        "backend": workspace_backend,
        "subagents": subagents,
        "middleware": middleware,
        "system_prompt": system_prompt,
        "skills": ["/skills/"],
    }

    agent = create_deep_agent(
        **kwargs,
        checkpointer=checkpointer,
    ).with_config({"recursion_limit": 1000})

    return agent


def _build_prompt_refs():
    """Build prompt references for sub-agent loading."""
    try:
        import datetime
        from EvoScientist.prompts import RESEARCHER_INSTRUCTIONS
        return {
            "RESEARCHER_INSTRUCTIONS": RESEARCHER_INSTRUCTIONS.format(
                date=datetime.date.today().isoformat()
            ),
        }
    except (ImportError, AttributeError):
        return {}


def _inject_subagent_middleware(subagents, model):
    """Inject standard middleware into each sub-agent."""
    try:
        from EvoScientist.middleware.context_editing import create_context_editing_middleware
        from EvoScientist.middleware.tool_error_handler import ToolErrorHandlerMiddleware
        from EvoScientist.middleware.context_overflow import ContextOverflowMapperMiddleware

        for sub in subagents:
            existing = sub.get("middleware", [])
            sub["middleware"] = [
                create_context_editing_middleware(model),
                ToolErrorHandlerMiddleware(),
                ContextOverflowMapperMiddleware(),
                *existing,
            ]
    except ImportError:
        logger.warning("Could not inject sub-agent middleware (missing modules)")


def _build_middleware(cfg, model, workspace_dir):
    """Build the main agent middleware chain."""
    middleware = []

    try:
        from EvoScientist.middleware.context_editing import create_context_editing_middleware
        middleware.append(create_context_editing_middleware(model))
    except ImportError:
        pass

    try:
        from EvoScientist.middleware.context_overflow import ContextOverflowMapperMiddleware
        middleware.append(ContextOverflowMapperMiddleware())
    except ImportError:
        pass

    try:
        from EvoScientist.middleware.tool_error_handler import ToolErrorHandlerMiddleware
        middleware.append(ToolErrorHandlerMiddleware())
    except ImportError:
        pass

    try:
        from EvoScientist.middleware.tool_selector import create_tool_selector_middleware
        middleware.extend(create_tool_selector_middleware())
    except ImportError:
        pass

    try:
        from EvoScientist.middleware.memory import create_memory_middleware
        memory_dir = str(Path(workspace_dir) / "memory")
        os.makedirs(memory_dir, exist_ok=True)
        middleware.append(create_memory_middleware(memory_dir, extraction_model=model))
    except ImportError:
        pass

    return middleware
