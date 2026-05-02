---
name: evo-review
description: "Cross-model review loop via MCP. External LLM (GPT/Gemini/MiniMax) reviews experiment and report, iterates until quality threshold. 跨模型审稿循环。"
argument-hint: [what_to_review]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, WebSearch, WebFetch, Agent, mcp__llm-review__chat, mcp__gemini-review__review
---

# EvoScientist Review: Cross-Model Quality Review Loop

Review and improve: **$ARGUMENTS**

## Overview

This skill implements an autonomous review loop where an external LLM (via MCP) acts as an independent reviewer of your experiment and report. Inspired by ARIS's auto-review-loop, it iterates until the review score meets the quality threshold or max rounds are reached.

The key insight: **self-review is weaker than cross-model review**. Using a different LLM as reviewer breaks the blindspots of the executor model.

## Constants

- **MAX_ROUNDS = 3** — Maximum review-fix cycles
- **THRESHOLD = 7** — Minimum score (out of 10) to pass review
- **REVIEWER = "llm-review"** — MCP to use: `llm-review` (GPT/OpenAI-compatible) or `gemini-review`
- **DIFFICULTY = "medium"** — Review difficulty: `medium`, `hard`
- **HUMAN_CHECKPOINT = false** — Pause after each round for user feedback
- **STATE_FILE = "REVIEW_STATE.json"** — State persistence for recovery

## Inputs

- `$ARGUMENTS`: What to review (e.g., "final report", "experiment code", "Stage 2 results")
- Files to review: `final_report.md`, `analysis_report.md`, relevant code in `artifacts/`
- (Optional) `plan.md`: Original goals for context
- (Optional) `success_criteria.md`: What constitutes success

## Workflow

### Phase 0: State Recovery

1. Check for `REVIEW_STATE.json`. If exists and `status: in_progress` and timestamp < 24h:
   - Resume from saved round number
   - Load previous review feedback
2. Otherwise, start fresh

### Phase 1: Prepare Review Package

Gather all relevant files into a review context:
- `final_report.md` or `analysis_report.md` (main content)
- `plan.md` (original goals)
- `success_criteria.md` (thresholds)
- Key code files from `artifacts/`

Compile into a single review prompt (keep under context limit).

### Phase 2: Review Round (repeat up to MAX_ROUNDS)

#### Step A: Send to External Reviewer

If REVIEWER = "llm-review":
```
mcp__llm-review__chat:
  prompt: |
    You are a senior scientific reviewer (NeurIPS/ICML level).
    
    [Round N/MAX_ROUNDS]
    
    Review the following research work:
    
    ---
    [compiled review package]
    ---
    
    Please evaluate on these dimensions:
    1. **Correctness** (1-10): Are the methods and results sound?
    2. **Completeness** (1-10): Are all necessary experiments done?
    3. **Clarity** (1-10): Is the writing clear and well-structured?
    4. **Rigor** (1-10): Statistical validity, reproducibility, limitations?
    5. **Novelty** (1-10): How significant is the contribution?
    
    Overall Score: X/10
    Verdict: [accept / revise / reject]
    
    Specific Issues (ordered by severity):
    1. [Most critical issue]
    2. [Second issue]
    ...
    
    Be brutally honest. Do not be polite at the expense of accuracy.
```

If REVIEWER = "gemini-review":
```
mcp__gemini-review__review:
  prompt: [same format as above]
```

#### Step B: Parse Review

Extract from the reviewer's response:
- Overall score (number)
- Verdict (accept/revise/reject)
- List of specific issues

#### Step C: Check Stop Condition

- If score >= THRESHOLD AND verdict contains "accept": **STOP** — review passes
- If round >= MAX_ROUNDS: **STOP** — max rounds reached
- Otherwise: continue to Step D

#### Step D: Implement Fixes

For each issue identified by the reviewer:
1. Assess severity and feasibility
2. Implement fixes (edit report, re-run analysis, update code)
3. Document what was changed

If changes require re-running experiments: invoke `/evo-run` then `/evo-analyze`.

#### Step E: Persist State

Write to STATE_FILE:
```json
{
  "round": N,
  "status": "in_progress",
  "last_score": 6.5,
  "last_verdict": "revise",
  "issues_fixed": ["issue_1", "issue_2"],
  "issues_deferred": ["issue_3"],
  "timestamp": "2026-04-08T22:00:00"
}
```

If HUMAN_CHECKPOINT = true:
**🚦 Checkpoint:** Present review score and issues to user. Ask if they want to continue, adjust, or stop.

Return to Step A for next round.

### Phase 3: Final Report

Write `AUTO_REVIEW.md`:

```markdown
# Review Log

## Summary
- **Rounds**: N/MAX_ROUNDS
- **Final Score**: X/10
- **Final Verdict**: [accept/revise/reject]
- **Reviewer**: [model name via MCP]

## Round History

### Round 1
- **Score**: X/10
- **Key Issues**: [list]
- **Fixes Applied**: [list]

### Round 2
...

## Remaining Issues
- [Issues not fixed, with explanation]

## Reviewer Feedback (Final Round)
[Full text of final review]
```

Update STATE_FILE with `"status": "completed"`.

## Difficulty Levels

### Medium (default)
Standard MCP-based review. Claude curates what context the reviewer sees.

### Hard
Everything in Medium, plus:
- **Reviewer Memory**: Maintain a `REVIEWER_MEMORY.md` that tracks suspicions across rounds. Include in subsequent review prompts:
  ```
  Previous suspicions (verify if these were addressed):
  [contents of REVIEWER_MEMORY.md]
  ```
- **Debate Protocol**: After reviewer flags an issue, Claude must provide a defense. Only fix issues that survive the debate.

## Key Rules

- **MCP required**: This skill requires at least one review MCP configured. If unavailable, warn user and skip gracefully.
- **No self-play**: The whole point is using a DIFFERENT model. Do not fall back to Claude reviewing itself.
- **State persistence**: Always write state after each round. Context can be compacted at any time.
- **Honest response**: Do not cherry-pick reviewer feedback. Address all issues or explain why they were deferred.
- **24h staleness**: If REVIEW_STATE.json is older than 24h, start fresh.
- **Graceful degradation**: If MCP fails mid-round, save state and inform user.

## Composing with Other Skills

```
/evo-write "report"       ← produces final_report.md
/evo-review "report"      ← you are here
/evo-memory update        ← extract learnings after review
```