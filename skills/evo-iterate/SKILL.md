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
- **CLAIM_CHAIN_INTEGRATION = true** — Write structured knowledge to Claim Chain (L4)
- **ITERATE_SCOPE = "interactive"** — Scope of loop-back: `interactive` (user chooses), `W4` (code only), `W3.5` (ideation), `W3` (research), `W2` (re-plan)

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
- Recommended loop-back: **W4** (code adjustments only)

**Case C: Criteria far from met (gap > 20%)**
- Invoke `/evo-planner "goal" — MODE: reflection` for strategic assessment
- Analyze gap magnitude and recommend loop-back scope:
  - Gap 20-50%: recommend **W3.5** (try different method/approach)
  - Gap > 50%: recommend **W2** (re-plan from scratch)
- 🚦 Checkpoint: present assessment and options to user

**Case D: Results are worse than baseline**
- Flag as critical issue
- Check for common problems:
  - Data leakage in evaluation?
  - Bug in metric computation?
  - Wrong baseline comparison?
- Always escalate to user
- Recommended loop-back: **W3** (research) or **W2** (re-plan)

**Interactive Scope Selection (ITERATE_SCOPE = "interactive"):**

For Cases B/C/D, after gap analysis, use AskUserQuestion to let the user choose loop-back scope:

```
AskUserQuestion:
  question: "指标未达标，建议回退到哪个阶段？"
  options:
    - label: "W4: 调参 (推荐)"   # default for Case B
      description: "调整超参数/代码，不改变方法"
    - label: "W3.5: 换方法"       # recommended for Case C (20-50%)
      description: "重新构思方法，保留问题定义"
    - label: "W3: 补充调研"       # for Case D
      description: "补充文献调研，寻找新思路"
    - label: "W2: 重新规划"       # recommended for Case C (>50%)
      description: "从头重新规划实验方案"
```

After user selects, write loop_target to experiment_log.md:
```
## Loop Target
- iteration: N
- loop_back_to: W3.5
- reason: [gap analysis summary]
- timestamp: [ISO datetime]
```

### Phase 3: Knowledge Evolution (Dual Path)

Two parallel paths ensure research knowledge goes to the Claim Chain (L4) and dev details go to experiment_log.md.

**Path 1 — Claim Chain (knowledge-level, L4 hub):**

Use `python tools/claim_chain.py` to write structured knowledge:

For IMPROVEMENT (score improves or criteria met):
```bash
python tools/claim_chain.py add-atom --type method --title "[method description]" \
  --content "[what worked and why]" --tags "[algorithm],[domain]" --evidence-level experiment
python tools/claim_chain.py add-relation --source [method_atom_id] --target [verification_atom_id] \
  --type validates --evidence "score=[N], improvement=[delta]"
```

For REGRESSION (score drops or worse than baseline):
```bash
python tools/claim_chain.py add-atom --type method --title "[failed approach]" \
  --content "[what failed and why]" --tags "[algorithm],[domain]" --evidence-level experiment
python tools/claim_chain.py add-relation --source [method_atom_id] --target [verification_atom_id] \
  --type contradicts --evidence "score=[N], regression=[delta]"
```

For boundary discovery (finds where a method works/fails):
```bash
python tools/claim_chain.py add-atom --type fact --title "[boundary condition]" \
  --content "[scope of applicability]" --tags "boundary,[domain]"
python tools/claim_chain.py add-relation --source [boundary_atom_id] --target [method_atom_id] \
  --type boundary_of --evidence "[observation]"
```

**Path 2 — Development Log (implementation-level):**

Append to `experiment_log.md` with parameter-level details:
```markdown
## Iteration N — [Date]
- Parameters: lr=[X], batch_size=[Y], epochs=[Z]
- Training time: [duration]
- GPU memory: [usage]
- Key observations: [technical notes]
- Error/log excerpts: [relevant snippets]
```

**Key rule**: Path 1 contains directional conclusions ("PPO+curriculum works on stairs"). Path 2 contains implementation details ("lr=3e-4, 500 epochs, 28GB VRAM"). No duplication.

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