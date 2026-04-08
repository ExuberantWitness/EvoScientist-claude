---
name: evo-planner
description: "Plan experiments with stages, success signals, and dependencies. Supports PLAN MODE (create new plan) and REFLECTION MODE (evaluate progress). 实验规划：阶段、成功信号、依赖关系。"
argument-hint: [research_goal_or_proposal]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Agent
---

# EvoScientist Planner: Experiment Planning & Reflection

Create or evaluate an experiment plan for: **$ARGUMENTS**

## Overview

This skill translates a research goal into a structured, actionable experiment plan with clear success signals for each stage. It operates in two modes:

- **PLAN MODE** (default): Generate a new experiment plan from a research proposal
- **REFLECTION MODE**: Evaluate progress against an existing plan and suggest adjustments

## Constants

- **MODE = plan** — `plan` or `reflection`. Override: `/evo-planner "goal" — MODE: reflection`
- **MAX_STAGES = 7** — Maximum experiment stages
- **MODEL_DEFAULT = "7B-class"** — Default to lightweight models unless user specifies otherwise
- **MEMORY_CHECK = true** — Read memory files before planning

## Inputs

- `$ARGUMENTS`: Research goal, proposal text, or path to proposal file
- (Optional) `memory/ideation-memory.md`: Prior idea exploration results
- (Optional) `memory/experiment-memory.md`: Proven strategies from past experiments
- (Optional) `plan.md`: Existing plan (for REFLECTION MODE)

## Workflow

### Phase 0: Initialization

1. If MEMORY_CHECK = true, read `memory/ideation-memory.md` and `memory/experiment-memory.md` (if they exist). Note any relevant prior knowledge, proven strategies, or failed approaches.
2. If $ARGUMENTS points to a file path, read the file content as the proposal.
3. Determine MODE from constants.

### Phase 1: PLAN MODE — Generate Experiment Plan

If MODE = plan:

1. **Assumptions & Scope**: List what is assumed (hardware, data availability, compute budget, model scale). Default to ≤7B-class models and lightweight baselines unless the user explicitly specifies larger.

2. **Numbered Stages** (up to MAX_STAGES): For each stage, define:
   - **Goal**: One sentence describing what this stage achieves
   - **Success Signals**: Concrete, measurable criteria (e.g., "accuracy > 0.85 on val set", "training loss < 0.3 within 5 epochs")
   - **What to Run**: Specific commands, scripts, or steps
   - **Expected Artifacts**: Files produced (models, logs, figures)
   - **Estimated Compute**: Rough GPU-hours or wall-clock time

3. **Dependencies**: Which stages depend on which (DAG). Mark parallelizable stages.

4. **Iteration Triggers**: Conditions under which to revisit earlier stages (e.g., "if Stage 2 accuracy < baseline, revisit Stage 1 data preprocessing").

5. **Evaluation Protocol**: How final success is measured. Include:
   - Primary metric + threshold
   - Secondary metrics
   - Statistical requirements (significance level, number of runs)

6. **Environment Preflight**: List checks to run before starting:
   - `nvidia-smi` (GPU availability)
   - Python/package versions
   - Dataset accessibility
   - Disk space

Write the plan to `plan.md` and success criteria to `success_criteria.md`.

**🚦 Checkpoint:** Present the plan summary to the user.
- **User approves** → Skill complete
- **User requests changes** → Revise specific stages
- **User wants more detail** → Expand the requested stages

### Phase 2: REFLECTION MODE — Evaluate Progress

If MODE = reflection:

1. Read `plan.md` and `success_criteria.md`
2. Read `experiment_log.md` and `todos.md` (if they exist)
3. Read `artifacts/` directory listing to check what has been produced

Produce a JSON-structured assessment:

```json
{
  "completed": ["stage_1", "stage_3"],
  "in_progress": ["stage_2"],
  "unmet_success_signals": [
    {"stage": "stage_2", "signal": "accuracy > 0.85", "current": "0.78"}
  ],
  "skill_suggestions": [
    "/evo-debug — Stage 2 training script has convergence issues",
    "/evo-research — Need alternative optimizer for Stage 2"
  ],
  "stage_modifications": [
    {"stage": "stage_2", "change": "Reduce learning rate from 1e-3 to 5e-4"}
  ],
  "new_stages": [],
  "todo_updates": [
    {"task": "Run Stage 2 with reduced LR", "status": "pending"}
  ]
}
```

Write reflection to `plan_reflection.md`. Update `todos.md` if todo_updates is non-empty.

## Key Rules

- **No implementation**: This skill only plans. Delegate coding to `/evo-code`.
- **No web search**: Delegate literature review to `/evo-research`.
- **Lightweight defaults**: Default to ≤7B-class models. Never assume A100/H100 unless user says so.
- **Measurable signals**: Every success signal must be a number or boolean, never vague ("good performance").
- **Honest uncertainty**: If compute estimates are uncertain, give ranges, not single numbers.
- **Memory-aware**: If memory contains failed approaches, explicitly exclude them from the plan.

## Composing with Other Skills

```
/evo-intake "proposal"      ← parses raw proposal
/evo-planner "goal"         ← you are here
/evo-research "topic"       ← literature survey for the plan
/evo-code "stage N"         ← implement a plan stage
```

Or use `/evo-pipeline` for the full end-to-end flow.
