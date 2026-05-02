# Agent-to-Skill Mapping

This document explains how EvoScientist's original Python multi-agent system maps to Claude Code Skills.

## Architecture Comparison

| Aspect | EvoScientist (Python) | EvoScientist-claude (Skills) |
|--------|----------------------|------------------------------|
| Runtime | Python + LangChain + LangGraph | Claude Code native |
| Agents | 6 Python sub-agents | 13 composable Skills |
| Dependencies | ~30 Python packages | Zero (pure Markdown) |
| LLM Provider | Multi-provider via langchain | Claude Code + MCP bridges |
| Memory | SQLite + Pydantic extraction | Markdown files in /memory/ |
| Execution | `EvoSci` CLI / TUI | `/skill-name` in Claude Code |

## Agent Mapping

### planner-agent -> /evo-planner
- **Original**: LangGraph sub-agent with think_tool, two modes (PLAN/REFLECTION)
- **Skill**: Preserves both modes. PLAN MODE generates staged plans with success signals. REFLECTION MODE evaluates progress and suggests adjustments.
- **Key change**: Reads memory files directly instead of through middleware injection.

### research-agent -> /evo-research
- **Original**: Uses tavily_search for web research
- **Skill**: Uses Claude Code's WebSearch + WebFetch. Same one-topic-at-a-time constraint.
- **Key change**: No tavily dependency. Output format standardized.

### code-agent -> /evo-code
- **Original**: Implements code with think_tool, writes to /artifacts/
- **Skill**: Same /artifacts/ convention. Adds Lite vs Effort modes. Preflight checks preserved.
- **Key change**: Directly edits files instead of going through sandbox backend.

### debug-agent -> /evo-debug
- **Original**: Reproduce → root cause → minimal fix with think_tool
- **Skill**: Same diagnostic flow. Adds MAX_FIX_ATTEMPTS retry limit.
- **Key change**: Can directly run commands to reproduce and verify.

### data-analysis-agent -> /evo-analyze
- **Original**: Computes metrics, creates plots, saves to /artifacts/
- **Skill**: Same structure. Adds explicit statistical rigor requirements (significance, correction, CI).
- **Key change**: Can write and execute Python analysis scripts directly.

### writing-agent -> /evo-write
- **Original**: 7-section Markdown report, no fabrication
- **Skill**: Same 7-section structure. Adds citation verification step.
- **Key change**: Optional LaTeX output mode.

## New Skills (Not in Original)

| Skill | Why Added |
|-------|-----------|
| `/evo-intake` | Extracted from main workflow Step 1 (was inline) |
| `/evo-run` | Experiment execution was implicit in code-agent |
| `/evo-review` | Cross-model review via MCP (inspired by ARIS) |
| `/evo-ideation` | Combines research-ideation + idea-tournament |
| `/evo-iterate` | Extracted from main workflow Step 4 (evaluate & iterate) |
| `/evo-memory` | Replaces EvoMemoryMiddleware with explicit skill |
| `/evo-pipeline` | Replaces the LangGraph agent graph orchestration |

## Workflow Comparison

### Original (LangGraph)
```
User Input → Main Agent → [delegates to sub-agents via "task" tool]
  → planner-agent → research-agent → code-agent
  → debug-agent → data-analysis-agent → writing-agent
  → Memory middleware extracts learnings
```

### Claude Code Skills
```
User Input → /evo-pipeline orchestrates:
  /evo-intake → /evo-planner → /evo-research → /evo-ideation
  → /evo-code → /evo-debug → /evo-run
  → /evo-analyze → /evo-iterate (loop)
  → /evo-write → /evo-review → /evo-memory
```

Key difference: Skills are **independently invocable**. Users can run any skill standalone without the pipeline.
