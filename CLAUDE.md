# Flux-Insight

Multi-agent scientific discovery system, built as composable Claude Code Skills.

## Quick Start

```bash
# Install skills into Claude Code
cp -r skills/* ~/.claude/skills/

# (Optional) Set up LLM review MCP (servers from ARIS repo)
pip install mcp httpx
# See docs/MCP_SETUP.md for full instructions

# Run full pipeline in Claude Code
claude
> /flux-pipeline "Your research proposal or question"
```

## Skill Map

| Skill | Phase | Purpose |
|---|---|---|
| `/flux-pipeline` | Orchestrator | Full W1-W8 end-to-end |
| `/flux-code-agent-pre` | W5 | Code implementation pre-check |
| `/flux-code-agent-check` | W5 | Code implementation mid-check |
| `/flux-code-agent-post` | W5 | Code implementation post-check |

## File Conventions

```
project/
├── plan.md                  # Experiment plan (planner output)
├── success_criteria.md      # Success signal definitions
├── todos.md                 # Task tracking
├── research_notes.md        # Literature survey notes
├── experiment_log.md        # Experiment execution log
├── final_report.md          # Final paper-ready report
├── REVIEW_STATE.json        # Review loop state
├── PIPELINE_STATE.json      # Pipeline checkpoint state
├── artifacts/               # Code, figures, tables, models
└── memory/                  # Persistent memory
    ├── MEMORY.md
    ├── ideation-memory.md
    └── experiment-memory.md
```

## Principles

1. **Baseline first** — always establish baseline before adding complexity
2. **One variable per iteration** — change one thing at a time
3. **Never fabricate** — compute from real data, never invent results
4. **Delegate aggressively** — use specialized skills for each phase
5. **Scientific rigor** — effect sizes, confidence intervals, negative results
