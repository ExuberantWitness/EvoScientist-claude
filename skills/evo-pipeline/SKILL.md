---
name: evo-pipeline
description: "Full end-to-end scientific experiment pipeline. Orchestrates all EvoScientist skills: intake → plan → research → ideation → code → run → analyze → iterate → write → review. 全流程编排器。"
argument-hint: [research_proposal_or_question]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, WebSearch, WebFetch, Agent, Skill, mcp__llm-review__chat, mcp__gemini-review__review
---

# EvoScientist Pipeline: End-to-End Scientific Discovery

Run full experiment pipeline for: **$ARGUMENTS**

## Overview

This is the master orchestrator that chains all EvoScientist skills into a complete scientific discovery workflow. It manages state across phases, handles checkpoints, and supports recovery from interruptions.

```
W1: Intake → W2: Plan → W3: Research → W3.5: Ideation
    ↓
W4: Code → W4.5: Debug → W4.7: Run
    ↓
W5: Analyze → W5.5: Iterate ←──────┐
    ↓                                │
    ├── criteria NOT met ────────────┘
    │
    ├── criteria MET
    ↓
W6: Write → W7: Review (optional) → W8: Memory
```

## Constants

- **AUTO_PROCEED = false** — Skip checkpoints and auto-advance (true = fully autonomous)
- **SKIP_RESEARCH = false** — Skip literature survey (if user already has context)
- **SKIP_IDEATION = false** — Skip idea generation (if user already has a specific idea)
- **SKIP_REVIEW = false** — Skip cross-model review at the end
- **MAX_PIPELINE_ITERATIONS = 3** — Maximum full iterate-loops before stopping
- **CODE_MODE = "lite"** — Code generation mode: `lite` or `effort`
- **REVIEWER = "llm-review"** — MCP for review: `llm-review`, `gemini-review`, or `none`
- **STATE_FILE = "PIPELINE_STATE.json"** — Pipeline state for recovery

> Override: `/evo-pipeline "proposal" — AUTO_PROCEED: true, SKIP_RESEARCH: true`

## Inputs

- `$ARGUMENTS`: Research proposal, question, or goal

## Workflow

### Phase 0: State Recovery & Initialization

1. Check `PIPELINE_STATE.json`. If exists with `status: in_progress` and timestamp < 24h:
   - Resume from the saved phase
   - Load all intermediate files
   - Print: "Resuming pipeline from Phase [N]..."
2. Otherwise, start fresh:
   - Initialize: `mkdir -p artifacts/figures artifacts/tables memory`
   - If `memory/MEMORY.md` doesn't exist, run `/evo-memory init`

Save state:
```json
{
  "phase": 0,
  "status": "in_progress",
  "iteration": 0,
  "timestamp": "2026-04-08T22:00:00",
  "skipped": []
}
```

### Phase 1 (W1): Intake & Scope

Invoke: `/evo-intake "$ARGUMENTS"`

Output: `research_proposal.md` with structured scope.

If AUTO_PROCEED = false:
**🚦 Checkpoint 1:** Present extracted scope. Ask user to confirm or refine.

Update state: `"phase": 1`

### Phase 2 (W2): Experiment Planning

Invoke: `/evo-planner "$ARGUMENTS"`

Reads: `research_proposal.md`
Output: `plan.md`, `success_criteria.md`

If AUTO_PROCEED = false:
**🚦 Checkpoint 2:** Present experiment plan. Ask user to approve or modify.

Update state: `"phase": 2`

### Phase 3 (W3): Literature Research

If SKIP_RESEARCH = true → skip to Phase 3.5

Extract key research topics from `plan.md`. For each topic:
Invoke: `/evo-research "[topic]"`

Output: `research_notes.md`

Update state: `"phase": 3`

### Phase 3.5 (W3.5): Ideation

If SKIP_IDEATION = true → skip to Phase 4

Invoke: `/evo-ideation "$ARGUMENTS"`

Output: `idea_report.md`

If AUTO_PROCEED = false:
**🚦 Checkpoint 3:** Present ranked ideas. Ask user to select one.

If user selects an idea different from the current plan:
- Re-invoke `/evo-planner` with the selected idea
- Update `plan.md` and `success_criteria.md`

Update state: `"phase": 3.5`

### Phase 4 (W4): Implementation

For each stage in `plan.md` (in dependency order):

1. **Code**: Invoke `/evo-code "Stage N: [description]" — CODE_MODE: [CODE_MODE]`
2. **Run sanity**: Invoke `/evo-run "Stage N" — SANITY_FIRST: true`
3. If sanity fails: Invoke `/evo-debug "[error]"`
   - After debug, retry run (max 2 retries per stage)
4. **Run full**: Invoke `/evo-run "Stage N" — SANITY_FIRST: false`
5. If full run fails: Invoke `/evo-debug "[error]"`, retry once

Update state: `"phase": 4, "current_stage": N`

### Phase 5 (W5): Analysis

Invoke: `/evo-analyze "artifacts/"`

Output: `analysis_report.md`, `artifacts/figures/`

Update state: `"phase": 5`

### Phase 5.5 (W5.5): Evaluate & Iterate

Invoke: `/evo-iterate`

Reads: `plan.md`, `success_criteria.md`, `analysis_report.md`

**Decision tree:**
- **All criteria met** → advance to Phase 6
- **Criteria not met, iteration < MAX_PIPELINE_ITERATIONS** →
  - Apply suggested adjustments
  - Return to Phase 4 (Code → Run → Analyze → Iterate)
  - Increment iteration counter
- **Criteria not met, iteration >= MAX_PIPELINE_ITERATIONS** →
  - If AUTO_PROCEED = true: advance with best results so far
  - If AUTO_PROCEED = false: 🚦 Checkpoint: present status, ask user

Update state: `"phase": 5.5, "iteration": N`

### Phase 6 (W6): Write Report

Invoke: `/evo-write "$ARGUMENTS"`

Output: `final_report.md`

If AUTO_PROCEED = false:
**🚦 Checkpoint 6:** Present report summary. Ask user to review before proceeding to external review.

Update state: `"phase": 6`

### Phase 7 (W7): Cross-Model Review (Optional)

If SKIP_REVIEW = true OR REVIEWER = "none" → skip to Phase 8

Invoke: `/evo-review "final report" — REVIEWER: [REVIEWER]`

Output: `AUTO_REVIEW.md`, updated `final_report.md`

Update state: `"phase": 7`

### Phase 8 (W8): Memory & Cleanup

1. Invoke: `/evo-memory update`
2. Update `PIPELINE_STATE.json` with `"status": "completed"`
3. Present final summary:

```markdown
## Pipeline Complete

### Research Question
[from research_proposal.md]

### Key Results
[from analysis_report.md — top metrics]

### Success Criteria
| Criterion | Target | Achieved | Status |
|-----------|--------|----------|--------|
| ... | ... | ... | PASS/FAIL |

### Iterations
- Total iterations: N
- Stages completed: N/M

### Output Files
- Report: final_report.md
- Analysis: analysis_report.md
- Plan: plan.md
- Figures: artifacts/figures/
- Review: AUTO_REVIEW.md (if reviewed)

### Learnings Extracted
- [N] new entries added to experiment memory
```

## Key Rules

- **State persistence**: Write PIPELINE_STATE.json after every phase transition. Recovery is critical for long pipelines.
- **Checkpoint discipline**: In non-auto mode, ALWAYS pause at checkpoints. The user must stay in control.
- **Fail forward**: If a non-critical skill fails (e.g., ideation, review), log the error and continue. Only stop for critical failures (code won't run, no data).
- **One iteration at a time**: Do not try to change multiple things between iterations. Follow plan adjustments from `/evo-iterate`.
- **Time awareness**: Log timestamps. The user should know how long each phase took.
- **Graceful MCP degradation**: If review MCP is unavailable, skip review with a warning (not an error).
- **24h staleness**: Pipeline state older than 24h is considered stale. Start fresh.

## Composing with Individual Skills

Each phase can be run independently:

```bash
# Run just the parts you need
/evo-intake "proposal"
/evo-planner "goal"
/evo-research "topic"
/evo-ideation "direction"
/evo-code "stage 1"
/evo-run "stage 1"
/evo-debug "error"
/evo-analyze "artifacts/"
/evo-iterate
/evo-write "report"
/evo-review "report"
/evo-memory update
```

Or run end-to-end:
```bash
/evo-pipeline "Your research proposal" — AUTO_PROCEED: true
```