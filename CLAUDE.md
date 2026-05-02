# EvoScientist — Claude Code Edition

Multi-agent scientific discovery system, rebuilt as composable Claude Code Skills.

## Quick Start

```bash
# Install skills into Claude Code
cp -r skills/* ~/.claude/skills/

# (Optional) Set up LLM review MCP
pip install -r mcp-servers/llm-review/requirements.txt
claude mcp add llm-review -- python3 mcp-servers/llm-review/server.py

# Run full pipeline in Claude Code
claude
> /evo-pipeline "Your research proposal or question"
```

## Skill Map

| Skill | Phase | Purpose |
|---|---|---|
| `/evo-pipeline` | Orchestrator | Full W1-W8 end-to-end |
| `/evo-intake` | W1 | Parse proposal, extract scope |
| `/evo-planner` | W2 | Experiment plan + success signals |
| `/evo-research` | W3 | Literature survey via paper-navigator |
| `/evo-ideation` | W3.5 | Idea Tree Search + Elo tournament |
| `/evo-refine` | W3.6 | Iterative method refinement (external review) |
| `/evo-code` | W4 | Implement experiment code |
| `/evo-debug` | W4.5 | Debug runtime failures |
| `/evo-run` | W4.7 | Execute experiments |
| `/evo-analyze` | W5 | Metrics, plots, statistical analysis |
| `/evo-claim` | W5.6 | Result-to-claim judgment gate |
| `/evo-iterate` | W5.5 | Evaluate vs success signals, loop |
| `/evo-write` | W6 | Paper-ready report |
| `/evo-review` | W7 | Cross-model review via MCP |
| `/evo-memory` | Utility | Persistent memory management |
| `/research-wiki` | Utility | Persistent knowledge base (papers/ideas/claims)

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
