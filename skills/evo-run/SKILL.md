---
name: evo-run
description: "Execute experiments locally, via SSH, or on cloud GPU. Monitor progress and collect results. 运行实验。"
argument-hint: [command_or_stage]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob
---

# EvoScientist Run: Experiment Execution

Execute experiment: **$ARGUMENTS**

## Overview

This skill runs experiment scripts, monitors their progress, and collects results. It supports local execution, remote SSH, and provides guidance for cloud GPU platforms (Vast.ai, Modal, RunPod).

## Constants

- **TARGET = "local"** — Execution target: `local`, `ssh`, `cloud`
- **TIMEOUT = 3600** — Maximum execution time in seconds (1 hour default)
- **SANITY_FIRST = true** — Run a quick sanity check before full experiment
- **BACKGROUND = false** — Run in background (for long experiments)
- **LOG_FILE = "experiment_log.md"** — Log file path

## Inputs

- `$ARGUMENTS`: Command to run, or stage name from `plan.md`
- (Required) `experiment_log.md`: For logging execution details
- (Optional) `plan.md`: To look up stage-specific commands

## Workflow

### Phase 0: Resolve Command

1. If $ARGUMENTS is a direct command (e.g., `python artifacts/train.py`), use it
2. If $ARGUMENTS is a stage name (e.g., "Stage 2"), read `plan.md` and `experiment_log.md` to find the command
3. Verify the script exists: `ls -la [script_path]`

### Phase 1: Sanity Check

If SANITY_FIRST = true:

1. Run a quick sanity variant of the experiment:
   - Add `--max_steps 10` or `--epochs 1` or `--debug` flag
   - Or: run on a tiny data subset
2. Verify it completes without errors
3. Check output format is as expected

If sanity fails → invoke `/evo-debug` instead of proceeding.

### Phase 2: Execute

#### Local Execution (TARGET = local)

```bash
# Log start time
echo "[$(date)] Starting: [command]" >> experiment_log.md

# Run with timeout and output capture
timeout TIMEOUT [command] 2>&1 | tee artifacts/run_output.log

# Log completion
echo "[$(date)] Completed: exit code $?" >> experiment_log.md
```

If BACKGROUND = true:
```bash
nohup [command] > artifacts/run_output.log 2>&1 &
echo "PID: $!" >> experiment_log.md
echo "Background execution started. Check: tail -f artifacts/run_output.log"
```

#### SSH Execution (TARGET = ssh)

Provide the user with SSH commands:
```bash
# User must configure SSH_HOST
ssh $SSH_HOST "cd [project_dir] && [command]" 2>&1 | tee artifacts/run_output.log
```

#### Cloud Guidance (TARGET = cloud)

Provide instructions for cloud GPU platforms (do not execute — user must handle auth):
- **Vast.ai**: `vastai create instance` workflow
- **Modal**: `modal run` workflow
- **RunPod**: `runpodctl` workflow

### Phase 3: Collect Results

After execution completes:

1. Check exit code — if non-zero, suggest `/evo-debug`
2. Locate output files (models, metrics, logs)
3. Update `experiment_log.md` with:

```markdown
## [YYYY-MM-DD HH:MM] Run: [stage/description]
- **Command**: `[exact command]`
- **Duration**: [time elapsed]
- **Exit Code**: [0/non-zero]
- **Output Files**: [list of generated files]
- **Key Metrics** (if visible in output):
  - [metric]: [value]
- **Notes**: [any observations]
```

4. If output exceeds 100KB, save full log to `artifacts/run_output.log` and show only the tail

**🚦 Checkpoint:** Report execution results to the user.

## Key Rules

- **Timeout protection**: Always use timeout. Never let experiments run indefinitely.
- **Log everything**: Every run gets an entry in experiment_log.md.
- **Sanity first**: A 10-step sanity check catches most bugs before wasting GPU hours.
- **Output capture**: Always tee output to both terminal and log file.
- **No silent failures**: If exit code is non-zero, flag it immediately.
- **Background safety**: For background runs, always provide the PID and log file path.

## Composing with Other Skills

```
/evo-code "stage N"       ← implements the experiment
/evo-run "stage N"        ← you are here
/evo-debug "error"        ← if run fails
/evo-analyze "results"    ← analyze outputs
```