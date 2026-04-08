---
name: evo-code
description: "Implement experiment code and runnable scripts. Minimal changes, reproducible, outputs to /artifacts/. 实验代码实现。"
argument-hint: [task_description]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Agent
---

# EvoScientist Code: Experiment Implementation

Implement experiment code for: **$ARGUMENTS**

## Overview

This skill implements experiment code based on the experiment plan. It keeps changes minimal and reproducible, writes outputs under `/artifacts/`, and logs parameters to `experiment_log.md`. It checks memory for proven strategies before writing new code.

## Constants

- **CODE_MODE = "lite"** — `lite` (straightforward implementation) or `effort` (iterative refinement with self-review)
- **PREFLIGHT = true** — Run environment checks before coding
- **ARTIFACTS_DIR = "artifacts"** — Output directory for scripts, models, figures
- **LOG_FILE = "experiment_log.md"** — Experiment parameter log

## Inputs

- `$ARGUMENTS`: Task description (e.g., "implement baseline transformer for Stage 1")
- (Required) `plan.md`: Experiment plan with stage definitions
- (Optional) `research_notes.md`: Methods and baselines to implement
- (Optional) `memory/experiment-memory.md`: Proven strategies from past experiments

## Workflow

### Phase 0: Preflight & Context

If PREFLIGHT = true:
1. Run `nvidia-smi` to check GPU availability (note: not all experiments need GPU)
2. Check Python version: `python3 --version`
3. Check key packages: `python3 -c "import torch; print(torch.__version__, torch.cuda.is_available())"` (if applicable)
4. Report preflight results (do NOT fail if GPU unavailable — some experiments are CPU-only)

Read context files:
1. Read `plan.md` — identify which stage is being implemented
2. Read `research_notes.md` — find relevant methods and code references
3. If exists, read `memory/experiment-memory.md` — check for proven strategies and known pitfalls
4. Scan existing `artifacts/` directory — avoid overwriting prior work

### Phase 1: Implement (Lite Mode)

If CODE_MODE = lite:

1. **Scan before writing**: Check if relevant scripts already exist in `artifacts/`. Reuse and modify rather than rewrite.
2. **Write clean, runnable scripts** under `artifacts/`:
   - Clear entry points (e.g., `python artifacts/train.py --config config.yaml`)
   - Explicit random seeds for reproducibility
   - Configurable hyperparameters via argparse or config file
   - Logging of key metrics to stdout and/or log file
3. **Keep changes minimal**: Only write what is needed for this stage. Do not refactor unrelated code.
4. **Log parameters** to `experiment_log.md`:

```markdown
## [YYYY-MM-DD HH:MM] Stage N: [Description]
- **Script**: artifacts/train.py
- **Command**: `python artifacts/train.py --lr 1e-3 --epochs 50 --seed 42`
- **Key Params**: lr=1e-3, batch_size=32, model=bert-base, epochs=50
- **Expected Output**: artifacts/results/stage_n/
- **Status**: ready to run
```

### Phase 1.5: Implement (Effort Mode)

If CODE_MODE = effort:

1. Follow all steps from Lite Mode
2. After initial implementation, perform self-review:
   - Check for common bugs (off-by-one, data leakage, wrong metric computation)
   - Verify reproducibility (seeds set? deterministic mode?)
   - Check resource usage (memory-efficient data loading? gradient accumulation if needed?)
3. Iterate: fix issues found in self-review
4. Add a simple smoke test (e.g., run 1 epoch on tiny subset) to verify the code runs

### Phase 2: Output Summary

Present to the user:
- **Files changed/created**: List with brief description
- **Commands to run**: Exact commands to execute the experiment
- **Output paths**: Where results will be saved
- **Remaining issues**: Any known limitations or TODOs

## Key Rules

- **Minimal changes**: Only write what the current stage requires. No premature abstractions.
- **Reproducibility**: Always set random seeds. Log all hyperparameters.
- **No fabrication**: Never hardcode results or generate fake data.
- **Artifacts directory**: All generated scripts, models, and outputs go under `artifacts/`.
- **Reuse existing code**: Always scan project before writing new scripts. Extend, don't duplicate.
- **Read skills first**: If a relevant local skill SKILL.md exists, follow its workflow.
- **Memory-aware**: Check `memory/experiment-memory.md` for proven strategies before choosing an approach.
- **Large file handling**: If Write tool fails for large files, retry with Bash heredoc silently.

## Composing with Other Skills

```
/evo-planner "goal"      ← creates plan with stages
/evo-research "topic"    ← finds methods to implement
/evo-code "stage N"      ← you are here
/evo-debug               ← if code fails at runtime
/evo-run                 ← execute the experiment
```
