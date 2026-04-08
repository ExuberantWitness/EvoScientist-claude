---
name: evo-iterate
description: "Evaluate experiment progress against success signals. Decide: iterate, pivot, or advance. 迭代评估循环。"
argument-hint: [stage_or_scope]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Agent, Skill
---

# EvoScientist Iterate: Evaluate & Decide Next Step

Evaluate progress on: **$ARGUMENTS**

## Overview

This skill compares current experiment results against the success criteria defined in the plan. It decides whether to iterate (re-run with adjustments), pivot (change approach), or advance to the next stage. It also triggers memory evolution — extracting learnings from each iteration.

## Constants

- **MAX_ITERATIONS = 5** — Maximum iterations per stage before escalating
- **AUTO_ADVANCE = false** — Automatically advance when criteria met (vs. asking user)
- **MEMORY_EVOLUTION = true** — Extract learnings after each evaluation

## Inputs

- `plan.md`: Experiment plan with success signals
- `success_criteria.md`: Measurable thresholds
- `experiment_log.md`: What has been run so far
- `analysis_report.md` or experiment outputs: Current results
- (Optional) `artifacts/`: Generated files to check

## Workflow

### Phase 0: Load State

1. Read `plan.md` and `success_criteria.md`
2. Read `experiment_log.md` for execution history
3. Read `analysis_report.md` if available
4. Determine current stage and iteration count

### Phase 1: Evaluate Against Criteria

For each success criterion in the current stage:

| Criterion | Target | Current | Gap | Status |
|-----------|--------|---------|-----|--------|
| accuracy | > 0.85 | 0.82 | -0.03 | NOT MET |
| loss | < 0.3 | 0.28 | +0.02 | MET |
| training_time | < 2h | 1.5h | +0.5h | MET |

### Phase 2: Decide Action

Based on evaluation:

**Case A: All criteria met**
- If AUTO_ADVANCE = true → advance to next stage
- Otherwise → 🚦 Checkpoint: present results, ask user to confirm advance

**Case B: Some criteria not met, gap is small (within 10%)**
- Suggest targeted adjustments:
  - Hyperparameter tuning (learning rate, batch size, epochs)
  - Data augmentation or preprocessing changes
  - Longer training
- If iteration_count < MAX_ITERATIONS → iterate with adjustments
- Otherwise → escalate to user

**Case C: Criteria far from met (gap > 20%)**
- Invoke `/evo-planner "goal" — MODE: reflection` for strategic assessment
- Suggest one of:
  1. **Iterate**: Try a different hyperparameter configuration
  2. **Pivot**: Change the method/approach entirely
  3. **Debug**: The implementation may have bugs → `/evo-debug`
  4. **Research**: Need better methods → `/evo-research`
- 🚦 Checkpoint: present assessment and options to user

**Case D: Results are worse than baseline**
- Flag as critical issue
- Check for common problems:
  - Data leakage in evaluation?
  - Bug in metric computation?
  - Wrong baseline comparison?
- Always escalate to user

### Phase 3: Memory Evolution

If MEMORY_EVOLUTION = true, extract learnings:

**Iteration-Driven Evolution (IDE)**: What did this iteration teach us?
```markdown
## Iteration Learnings
- [Parameter X at value Y caused Z — avoid/prefer in future]
```

**Insight-Value Evolution (IVE)**: Did we gain new insights about the problem?
```markdown
## Problem Insights
- [The data has property X that affects method Y]
```

**Experiment-Strategy Evolution (ESE)**: Should we change our strategy?
```markdown
## Strategy Updates
- [Method A is more promising than B for this type of data]
```

Append learnings to `memory/experiment-memory.md`.

### Phase 4: Update Tracking

Update `todos.md` with current status:
- Mark completed stages
- Add new tasks for decided actions
- Update iteration counter

Update `experiment_log.md` with evaluation results.

## Key Rules

- **Data-driven decisions**: Decide based on metrics, not intuition.
- **Escalate early**: Don't iterate endlessly. After MAX_ITERATIONS, ask the user.
- **Baseline comparison**: Always compare against baseline, not just absolute values.
- **Memory extraction**: Every iteration is a learning opportunity. Extract and save.
- **Honest assessment**: If the approach isn't working, say so.

## Composing with Other Skills

```
/evo-analyze "results"    ← produces metrics to evaluate
/evo-iterate              ← you are here
/evo-planner — MODE: reflection  ← strategic reassessment
/evo-code "adjustments"   ← implement iteration changes
/evo-run "re-run"         ← re-execute experiment
```