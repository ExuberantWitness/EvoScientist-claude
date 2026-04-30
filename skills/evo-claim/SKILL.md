---
name: evo-claim
description: "Use when experiments complete to judge what claims the results support, what they don't, and what evidence is still missing. External LLM evaluates results against intended claims and routes to next action (pivot, supplement, or confirm). Use after experiments finish — before writing the paper."
argument-hint: [experiment-description]
allowed-tools: Bash(*), Read, Grep, Glob, Write, Edit, mcp__llm-chat__chat
---

# Result-to-Claim Gate

Experiments produce numbers; this gate decides what those numbers *mean*. Collect results, get an external LLM judgment, then auto-route based on verdict.

## Context: $ARGUMENTS

## When to Use

- After experiments complete (main results, not just sanity checks)
- Before committing to claims in a paper or report
- When results are ambiguous and you need an objective second opinion

## Workflow

### Step 1: Collect Results

Gather experiment data from available sources:

1. **`experiment_log.md`**: results table with baselines and verdicts
2. **`artifacts/`**: metrics, plots, tables
3. **Log files**: training logs, evaluation outputs
4. **`success_criteria.md`**: intended claims and experiment design

Assemble:
- What experiments were run (method, dataset, config)
- Main metrics and baseline comparisons (deltas)
- The intended claim these experiments test
- Known confounds or caveats

### Step 2: External LLM Judgment

```
mcp__llm-chat__chat:
  model: "deepseek-reasoner"
  system: |
    You are an independent experiment evaluator. Judge whether experimental results support the intended claim. Be honest. Do not inflate claims beyond what the data supports. A single positive result on one dataset does not support a general claim.
  prompt: |
    RESULT-TO-CLAIM EVALUATION

    Intended claim: [the claim these experiments test]

    Experiments run:
    [list experiments with method, dataset, metrics]

    Results:
    [paste key numbers, comparison deltas]

    Baselines:
    [baseline numbers and sources]

    Known caveats:
    [confounding factors, limited datasets, missing comparisons]

    Evaluate:
    1. claim_supported: yes | partial | no
    2. what_results_support: what the data actually shows
    3. what_results_dont_support: where data falls short of claim
    4. missing_evidence: specific evidence gaps
    5. suggested_claim_revision: strengthen/weaken/reframe
    6. next_experiments_needed: specific experiments to fill gaps
    7. confidence: high | medium | low
```

### Step 3: Route Based on Verdict

**`no`** — Claim not supported:
- Record postmortem in `findings.md`: what was tested, what failed, hypotheses
- Update `memory/experiment-memory.md` with IVE failure record
- Decide: pivot to next idea or try alternative approach

**`partial`** — Claim partially supported:
- Update working claim to reflect what IS supported
- Record gap in `findings.md`
- Design and run supplementary experiments
- Re-run evo-claim after supplementary experiments

**`yes`** — Claim supported:
- Record confirmed claim
- Ready for `/evo-write` or `/paper-write`

### Step 4: Update Evolution Memory

If claim supported (yes/partial): call `evo_distill` with type "ese" to record effective strategy.

If claim not supported (no): call `evo_distill` with type "ive" to record failure.

### Step 5: Update Research Wiki (if active)

If `research-wiki/` exists:
- Create experiment page
- Update claim status (supported/partial/invalidated)
- Add edges (supports/invalidates)
- Rebuild query_pack

## Rules

- **External LLM is the judge.** Prevents post-hoc rationalization.
- Do not inflate claims. If the judge says "partial", do not round up.
- If `confidence` is low, add experiments rather than committing.
- If llm-chat MCP is unavailable, make your own judgment and mark `[pending external review]`.
- Always record verdict and reasoning, regardless of outcome.

## Pipeline Position

```
/evo-run → experiments complete
/evo-claim "[experiment]"  ← you are here
/evo-write  ← if claims supported
```
