# EvoScientist Agent Manager

MCP Server that exposes EvoScientist's multi-agent system to Claude Code.

## What This Does

- Wraps EvoScientist's 6 specialized AI agents (planner, researcher, coder, debugger, analyst, writer)
- Agents auto-coordinate via LangGraph — real multi-agent discussion, not sequential scripts
- No sandbox restrictions — conda, GPU, system paths all work
- Persistent memory across sessions (auto-extracts user profile, experiment conclusions)
- Claude Code controls everything via 8 MCP tools

## Architecture

```
Claude Code ──MCP──> evo-agent-manager ──> LangGraph Multi-Agent System
                                               ├── planner-agent
                                               ├── research-agent
                                               ├── code-agent
                                               ├── debug-agent
                                               ├── data-analysis-agent
                                               └── writing-agent
```

## Setup

### Option A: Use the bootloader skill (recommended)

```
# In Claude Code:
/evo-boot /path/to/EvoScientist-main
```

### Option B: Manual setup

```bash
# 1. Extract core modules from EvoScientist source
./extract_core.sh /path/to/EvoScientist-main

# 2. Create conda environment + install deps
./setup_env.sh

# 3. Register MCP server with Claude Code
./register_mcp.sh
```

### Option C: Step by step

```bash
# Create conda env
conda create -n evo-agents python=3.11 -y

# Install deps
conda run -n evo-agents pip install deepagents langchain langchain-anthropic langgraph langgraph-checkpoint-sqlite mcp httpx pyyaml python-dotenv rich

# Extract core
./extract_core.sh /path/to/EvoScientist-main

# Set API key
export ANTHROPIC_API_KEY=sk-ant-...

# Test
conda run -n evo-agents python -m evo_agent_manager.server --test

# Register
claude mcp add evo-agents -- conda run --no-banner -n evo-agents python -m evo_agent_manager.server --base-dir "$(pwd)"
```

## Usage (in Claude Code)

Once registered, the MCP tools are automatically available:

```
User: Create an evo session for my project and discuss DreamerV3 vs TD-MPC2

Claude Code:
  → evo_create_session(workspace_dir="/path/to/project")
  → evo_discuss(session_id="abc123", topic="DreamerV3 vs TD-MPC2 for locomotion")
  → Returns multi-agent discussion transcript
```

## MCP Tools

| Tool | Purpose |
|------|---------|
| `evo_create_session` | Create a new multi-agent session |
| `evo_send` | Send message, get response with sub-agent delegation |
| `evo_discuss` | Multi-perspective discussion on a topic |
| `evo_status` | Session status, active agent, memory |
| `evo_list_sessions` | List all sessions |
| `evo_resume` | Resume a previous session |
| `evo_approve` | HITL approval for risky agent actions |
| `evo_get_memory` | Read auto-extracted agent memory |

## Environment Variables

```bash
ANTHROPIC_API_KEY=sk-ant-...     # Required (or set in ~/.config/evoscientist/config.yaml)
OPENAI_API_KEY=sk-...            # Optional (for multi-model review)
TAVILY_API_KEY=tvly-...          # Optional (for web search)
```
