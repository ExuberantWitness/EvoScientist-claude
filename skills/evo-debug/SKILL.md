---
name: evo-debug
description: "Debug runtime failures and fix bugs with minimal, verifiable patches. Reproduce -> root cause -> fix. 调试运行时错误。"
argument-hint: [error_description_or_log]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Agent
---

# EvoScientist Debug: Runtime Failure Diagnosis & Fix

Debug and fix: **$ARGUMENTS**

## Overview

This skill diagnoses runtime failures in experiment code. It follows a strict reproduce-diagnose-fix cycle, applying minimal patches with clear verification steps. It does not refactor or improve code beyond fixing the bug.

## Constants

- **MAX_FIX_ATTEMPTS = 3** — Maximum fix-and-rerun cycles before escalating to user
- **VERIFY = true** — Run verification command after fix

## Inputs

- `$ARGUMENTS`: Error description, traceback, or log file path
- Relevant source files in `artifacts/` or project root
- (Optional) `experiment_log.md`: Recent run commands and parameters

## Workflow

### Phase 0: Gather Context

1. Parse the error from $ARGUMENTS. If it's a file path, read the file.
2. Read `experiment_log.md` to find the most recent run command.
3. Identify the failing script and relevant source files.

### Phase 1: Reproduce

1. If a run command is available, attempt to reproduce the error:
   ```
   # Run with timeout to avoid hanging
   timeout 60 python artifacts/[script].py [args] 2>&1 | tail -50
   ```
2. Capture the full traceback. If reproduction fails (error is intermittent), note this.

### Phase 2: Diagnose Root Cause

1. Read the traceback carefully. Identify:
   - **File and line number** of the crash
   - **Error type** (TypeError, RuntimeError, OOM, CUDA error, data error, etc.)
   - **Immediate cause** (what variable/value is wrong)
2. Read the relevant source code around the error location
3. Trace the root cause — often the immediate crash is a symptom, not the cause:
   - Wrong shapes? Check data loading and preprocessing
   - OOM? Check batch size, model size, gradient accumulation
   - NaN/Inf? Check learning rate, loss function, data normalization
   - Import error? Check package versions and environment

Write a **one-paragraph root cause explanation**.

### Phase 3: Apply Minimal Fix

1. Apply the smallest possible fix. Do NOT:
   - Refactor surrounding code
   - Add unnecessary error handling
   - Change code unrelated to the bug
2. If multiple fix strategies exist, choose the least invasive one.

### Phase 4: Verify

If VERIFY = true:
1. Re-run the original command (or a smoke test variant)
2. Confirm the error is resolved
3. Check that no new errors were introduced

If verification fails and attempts < MAX_FIX_ATTEMPTS, return to Phase 2.
If verification fails and attempts >= MAX_FIX_ATTEMPTS, escalate to user.

### Phase 5: Report

Output summary:

```markdown
## Debug Report

### Root Cause
[One paragraph explaining why it failed]

### Fix Applied
- **File**: [path]
- **Change**: [brief description of the edit]

### Reproduction Steps
1. [Command that triggers the original error]

### Verification
- **Command**: [what was run to verify]
- **Result**: [pass/fail + brief output]
```

## Key Rules

- **Minimal fixes only**: Fix the bug, nothing else. No refactoring, no style changes.
- **Reproduce first**: Never guess at a fix without understanding the error.
- **One paragraph diagnosis**: Keep the root cause explanation concise.
- **Verify always**: A fix without verification is not a fix.
- **Escalate early**: After MAX_FIX_ATTEMPTS, ask the user rather than making increasingly speculative changes.

## Composing with Other Skills

```
/evo-code "stage N"      ← implements code (may introduce bugs)
/evo-debug "error msg"   ← you are here
/evo-run                 ← re-run after fix
```