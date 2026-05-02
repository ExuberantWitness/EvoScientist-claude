---
name: evo-refine
description: "Turn a vague research direction into a problem-anchored, elegant, implementation-oriented method plan via iterative external LLM review. Use when user says \"refine my approach\", \"帮我细化方案\", \"打磨idea\", \"refine research plan\", or wants a concrete method from a vague direction."
argument-hint: [problem_description]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, WebSearch, WebFetch, Agent, mcp__llm-chat__chat, mcp__evo-agents__evo_discuss
---

# EvoScientist Refine: Problem-Anchored Method Refinement

Refine and concretize: **$ARGUMENTS**

## Overview

Turns a vague research direction into a **problem → focused method → minimal validation** document through iterative external review. The reviewer is an external LLM (DeepSeek-reasoner via `mcp__llm-chat__chat`) that stress-tests the proposal across 7 dimensions.

Four principles:
1. **Do not lose the original problem.** Freeze an immutable Problem Anchor.
2. **The smallest adequate mechanism wins.**
3. **One paper, one dominant contribution.**
4. **Modern leverage is a prior, not a decoration.**

```
User input → Phase 0: Freeze Problem Anchor
  → Phase 1: Build initial proposal
  → Phase 2: External review (7 dimensions)
  → Phase 3: Anchor check + revise
  → Phase 4: Re-review (same context)
  → Repeat until score ≥ 9 or max rounds (5)
  → Phase 5: Final report
```

Sits between `/evo-ideation` and `/evo-planner` in the pipeline.

## Constants

- **REVIEWER = "mcp__llm-chat__chat"** — External LLM for review (DeepSeek-reasoner)
- **MAX_ROUNDS = 5** — Maximum review-revise rounds
- **SCORE_THRESHOLD = 9** — Minimum overall score to stop
- **OUTPUT_DIR = "refine-logs/"**

## Workflow

### Phase 0: Freeze the Problem Anchor

Before proposing anything, extract the immutable bottom-line problem:

- **Bottom-line problem**: What technical problem must be solved?
- **Must-solve bottleneck**: What specific weakness in current methods is unacceptable?
- **Non-goals**: What is explicitly NOT the goal?
- **Constraints**: Compute, data, time, tooling limits.
- **Success condition**: What evidence proves the method works?

### Phase 1: Build the Initial Proposal

1. **Scan grounding material**: Read `research_notes.md` for literature context
2. **Identify the technical gap**: Where does baseline fail? Why naive fixes insufficient?
3. **Choose the sharpest route**: Compare Elegant Minimal vs Frontier-Native routes
4. **Concretize the method**: Method thesis, complexity budget, system graph, training recipe, inference path
5. **Design minimal validation**: 1-3 core experiment blocks, claim-driven

Save to `refine-logs/round-0-initial-proposal.md`.

### Phase 2: External Method Review (Round 1)

Send the full proposal to the external reviewer:

```
mcp__llm-chat__chat:
  model: "deepseek-reasoner"
  system: |
    You are a senior ML reviewer for a top venue (NeurIPS/ICML/ICLR).
    This is an early-stage, method-first research proposal.

    Review principles:
    - Prefer the smallest adequate mechanism over a larger system.
    - Penalize parallel contributions that make the paper feel unfocused.
    - Do not ask for extra experiments unless needed to prove core claims.

    Score these 7 dimensions from 1-10:

    1. Problem Fidelity (15%): Does the method still attack the original bottleneck?
    2. Method Specificity (25%): Are interfaces, representations, losses concrete?
    3. Contribution Quality (25%): Is there one dominant mechanism-level contribution?
    4. Frontier Leverage (15%): Does it use modern primitives appropriately?
    5. Feasibility (10%): Can this be built with stated resources?
    6. Validation Focus (5%): Are experiments minimal but sufficient?
    7. Venue Readiness (5%): Would the contribution feel sharp for a top venue?

    OVERALL SCORE (1-10): Weighted as above.

    For each dimension < 7, provide:
    - The specific weakness
    - A concrete fix at the method level
    - Priority: CRITICAL / IMPORTANT / MINOR

    Add:
    - Simplification Opportunities: 1-3 ways to delete/merge components
    - Drift Warning: "NONE" if anchor preserved
    - Verdict: READY (score ≥ 9) / REVISE / RETHINK
  prompt: |
    === PROPOSAL ===
    [Full proposal from Phase 1]
    === END PROPOSAL ===
```

Save review to `refine-logs/round-1-review.md`.

### Phase 3: Parse Feedback and Revise

1. Parse all 7 dimension scores and overall score
2. Write **Anchor Check**: does revised method still solve original bottleneck?
3. Write **Simplicity Check**: what can be removed, merged, or kept frozen?
4. Process reviewer feedback: valid → sharpen; debatable → revise with reasoning; wrong/drifting → push back with evidence
5. Write full revised proposal to `refine-logs/round-N-refinement.md`

**STOP if**: score ≥ 9, verdict READY, no drift.

### Phase 4: Re-evaluation (Round 2+)

Send revised proposal + review history back to reviewer:

```
mcp__llm-chat__chat:
  model: "deepseek-reasoner"
  system: [Same reviewer system prompt as Phase 2]
  prompt: |
    [Round N re-evaluation]
    
    Previous round feedback was addressed. Key changes:
    1. [Method change 1]
    2. [Method change 2]
    
    === REVISED PROPOSAL ===
    [Full revised proposal]
    === END ===
    
    Re-score 7 dimensions + overall. Same output format.
```

Return to Phase 3 until score ≥ 9 or MAX_ROUNDS reached.

### Phase 5: Final Report

Write `refine-logs/REVIEW_SUMMARY.md` with round-by-round score evolution, and `refine-logs/FINAL_PROPOSAL.md` with the clean final version.

## Key Rules

- **Anchor first, every round.** Same Problem Anchor in every revision.
- **One paper, one dominant contribution.**
- **The smallest adequate mechanism wins.**
- **Pushback is encouraged.** If reviewer causes drift, argue back.
- **Be specific about compute and data assumptions.**

## Pipeline Position

```
/evo-ideation "direction"  → ranked ideas
/evo-refine "PROBLEM: ... | APPROACH: ..."  ← you are here
/evo-planner "refined proposal"  → detailed experiment plan
```
