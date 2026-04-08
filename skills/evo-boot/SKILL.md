---
name: evo-boot
description: "Bootloader for EvoScientist Agent Manager. Extracts core modules, creates conda env, installs deps, registers MCP. Run once to set up multi-agent system. 一键安装 EvoScientist 多 Agent 管理系统。"
argument-hint: [evoscientist_source_path]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Agent
---

# EvoScientist Boot: Agent Manager Setup

Set up the EvoScientist multi-agent system from source: **$ARGUMENTS**

## Overview

This is a one-time bootloader that sets up the EvoScientist Agent Manager as an MCP server for Claude Code. It extracts core multi-agent modules from EvoScientist source code, creates a conda environment with dependencies, and registers the MCP server.

After setup, Claude Code gains access to 8 MCP tools for controlling a real multi-agent system (6 specialized agents that auto-coordinate via LangGraph).

## Prerequisites

- conda installed and available in PATH
- EvoScientist source code (zip or extracted directory)
- ANTHROPIC_API_KEY set (for the agents to use Claude)

## Workflow

### Phase 0: Ask User — Installation Mode

Present two options to the user:

**Option A: Automatic (recommended)**
> I'll handle everything: extract core modules, create conda env, install dependencies, and register the MCP server with Claude Code.

**Option B: Manual**
> I'll generate the setup scripts and instructions. You run them yourself.

Ask the user which mode they prefer before proceeding.

### Phase 1: Locate Source

1. If $ARGUMENTS provided, use it as the source path
2. Otherwise, search common locations:
   - Current directory for `EvoScientist-main/` or `EvoScientist-main.zip`
   - Parent directory
   - `/tmp/evo_extracted/`
3. Verify the source contains `EvoScientist/EvoScientist.py` (core module)

If source not found, ask the user for the path.

### Phase 2: Extract Core Modules

Run `extract_core.sh` (or equivalent commands):

```bash
SOURCE="[located source]/EvoScientist"
TARGET="[agent-manager dir]/evoscientist_core/EvoScientist"

mkdir -p "$TARGET"

# Core files
cp "$SOURCE/__init__.py" "$TARGET/"
cp "$SOURCE/EvoScientist.py" "$TARGET/"
cp "$SOURCE/prompts.py" "$TARGET/"
cp "$SOURCE/subagent.yaml" "$TARGET/"
cp "$SOURCE/paths.py" "$TARGET/"
cp "$SOURCE/utils.py" "$TARGET/"
cp "$SOURCE/sessions.py" "$TARGET/"

# Subdirectories (full copy)
cp -r "$SOURCE/llm" "$TARGET/"
cp -r "$SOURCE/middleware" "$TARGET/"
cp -r "$SOURCE/tools" "$TARGET/"
cp -r "$SOURCE/stream" "$TARGET/"
cp -r "$SOURCE/mcp" "$TARGET/"
cp -r "$SOURCE/config" "$TARGET/"
cp -r "$SOURCE/skills" "$TARGET/"

# Skip: cli/, channels/, stt.py, ccproxy_manager.py, update_check.py
```

Verify extraction: `ls "$TARGET/EvoScientist.py"` should exist.

### Phase 3: Create Conda Environment

```bash
conda create -n evo-agents python=3.11 -y
```

### Phase 4: Install Dependencies

```bash
conda run -n evo-agents pip install \
  "deepagents>=0.4.11" \
  "langchain>=1.2.12" \
  "langchain-anthropic>=1.4.0" \
  "langchain-openai>=1.1" \
  "langgraph>=0.4" \
  "langgraph-checkpoint-sqlite>=3.0.0" \
  "langchain-mcp-adapters>=0.1" \
  "mcp>=1.0.0" \
  "httpx>=0.27" \
  "pyyaml>=6.0" \
  "python-dotenv>=1.0" \
  "rich>=14.0"
```

Optional (if user wants web search):
```bash
conda run -n evo-agents pip install tavily-python
```

### Phase 5: Register MCP Server

```bash
AGENT_MANAGER_DIR="[absolute path to agent-manager]"

claude mcp add evo-agents -- conda run --no-banner -n evo-agents python -m evo_agent_manager.server --base-dir "$AGENT_MANAGER_DIR"
```

### Phase 6: Verify

1. `conda run -n evo-agents python -c "from EvoScientist.EvoScientist import create_cli_agent; print('Core OK')"` — verify core imports
2. `conda run -n evo-agents python -m evo_agent_manager.server --test` — verify MCP server starts

### Phase 7: Report

Present setup summary:

```
EvoScientist Agent Manager — Setup Complete

Environment: conda env "evo-agents" (Python 3.11)
MCP Server: evo-agents (registered with Claude Code)
Core Modules: [N] files extracted from EvoScientist source

Available MCP Tools:
  evo_create_session  — Create a multi-agent session
  evo_send            — Send message, get agent response
  evo_discuss         — Trigger multi-agent discussion
  evo_status          — Check session status
  evo_list_sessions   — List all sessions
  evo_resume          — Resume a previous session
  evo_approve         — Approve/reject agent actions
  evo_get_memory      — Read agent memory

Usage: In Claude Code, the MCP tools are automatically available.
  Example: "Create an evo session and discuss DreamerV3 vs TD-MPC2"
```

## Key Rules

- **One-time setup**: This skill only needs to run once. After setup, the MCP tools are permanently available.
- **conda required**: If conda is not available, suggest installing miniconda first.
- **Source required**: Must have EvoScientist source code. Cannot download from GitHub (network may be restricted).
- **No EvoScientist CLI**: We deliberately skip the CLI — the MCP server replaces it.
- **ANTHROPIC_API_KEY**: Remind user to set this if not already configured.
