---
name: evo-ideation
description: "Generate, rank, and validate research ideas. Uses Idea Tree Search (K-way explore → branch → Elo prune → expand) with literature grounding from research_notes.md. 创意发现与排名。"
argument-hint: [research_direction]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, WebSearch, WebFetch, Agent, mcp__llm-review__chat, mcp__evo-agents__evo_run_tournament, mcp__evo-agents__evo_distill, mcp__evo-agents__evo_get_evolution_memory
---

# EvoScientist Ideation: Idea Tree Search + Elo Tournament

Explore ideas for: **$ARGUMENTS**

## Overview

This skill implements the **Idea Tree Search** algorithm (paper §3.2): K parallel directions → branch into variants → Elo tournament prune → expand winner into full proposal. All ideas must be grounded in literature from `research_notes.md`.

```
EXPLORE (K directions) → BRANCH (N variants each) → PRUNE (Elo top-K) → EXPAND (top-1 full proposal)
```

## Constants

- **K_DIRECTIONS = 3** — Number of distinct research directions to explore
- **N_BRANCHES = 3** — Number of refined variants per direction
- **TOP_K = 3** — Number of ideas to keep after Elo pruning
- **CROSS_MODEL = false** — Use external LLM for independent idea scoring
- **OUTPUT_FILE = "idea_report.md"**

## Prerequisites

**MANDATORY**: `research_notes.md` must exist with academic paper findings. If missing, run `/evo-research "$ARGUMENTS"` first. Ideas without literature grounding are not accepted.

## Workflow

### Phase 0: Load Context & Memory

1. **Load literature**: Read `research_notes.md`. Extract:
   - The **Challenge-Insight Tree** (challenges → insights → papers mapping)
   - **Unsolved challenges** (challenges with few insights → highest potential)
   - **Key papers** with their findings
   
2. **Load evolution memory**: Call `evo_get_evolution_memory(session_id, "all", limit=10)` to retrieve:
   - IDE PROMISING directions — use as seeds for explore
   - IVE FAILED directions — actively avoid these
   - ESE SUCCESS strategies — incorporate into method sketches

3. **Identify gaps**: From the challenge-insight tree, find challenges with few or no insights. These are the primary targets for idea generation.

### Phase 1: EXPLORE — K Parallel Directions

Generate **K_DIRECTIONS** distinct research directions. Each direction must be fundamentally different in approach, methodology, or problem framing.

For each direction, specify:
- **Title**: concise, descriptive
- **Hypothesis**: one-paragraph core claim
- **Method Sketch**: datasets, baselines, evaluation approach
- **Literature Gap**: which unsolved challenge from the tree does this address? **Cite specific papers** from research_notes.md (use the numbered references)

**Diversity rules**:
- At least 1 direction should target an "unsolved challenge" from the tree
- At least 1 direction should be a "cross-domain transfer" (apply insight from field A to challenge in field B)
- No direction should match a known IVE FAILED pattern from evolution memory

### Phase 2: BRANCH — N Variants Per Direction

For each direction from Phase 1, generate **N_BRANCHES** refined variants using different evolution strategies:

| Strategy | What it does |
|-----------------------|
| **Enhancement** | Strengthen with additional literature citations and technical detail |
| **Simplification** | Strip to the cleanest, most testable hypothesis |
| **Cross-domain** | Import an insight from a different field to solve the problem differently |
| **Combination** | Merge the core mechanism with a complementary technique from literature |
| **Pivot** | Abandon the core mechanism; propose an alternative approach to the same problem |

Each variant must:
- Cite at least 1 paper from research_notes.md
- Be concretely testable (have a clear minimum viable experiment)

### Phase 3: PRUNE — Elo Tournament

Format all candidates (K seeds + K×N branches) as proposals:

```json
{"id": "unique_id", "title": "...", "hypothesis": "...", "method_sketch": "..."}
```

Run the Elo tournament:

```
evo_run_tournament(session_id, proposals, judge_model="deepseek-chat")
```

The tournament evaluates on 4 dimensions (novelty, feasibility, relevance, clarity) via full round-robin pairwise comparison.

After ranking, **distill the results**:

```
evo_distill(session_id, "ide", proposals=ranked_proposals)
```

This persists:
- Top-half (above median Elo) → PROMISING directions in IDE memory
- Bottom-third → FAILED directions (avoid in future cycles)

### Phase 4: EXPAND — Top-1 Full Proposal

Take the #1 ranked idea from the tournament and expand it into a full research proposal:

1. **Abstract**: 150-250 word summary
2. **Problem Definition**: formal statement, scope, assumptions
3. **Related Work**: how this builds on and differs from existing work (cite specific papers from research_notes.md)
4. **Proposed Method**: detailed description with architecture/algorithm sketch
5. **Experimental Design**: datasets, baselines, metrics, ablation plan
6. **Expected Contributions**: what new knowledge this creates
7. **Limitations & Risks**: honest assessment

### Phase 5: Output

Write to `idea_report.md`:

```markdown
# Idea Report: [$ARGUMENTS]
Date: [YYYY-MM-DD]
Method: Idea Tree Search (K=3, N=3) + Elo Tournament

## Tournament Results

| Rank | Title | Elo | Novelty | Feasibility | Relevance | Clarity |
|------|-------|-----|---------|-------------|-----------|---------|
| 1 | ... | 1580 | 8.2 | 7.5 | 8.0 | 8.5 |
| 2 | ... | 1540 | 7.8 | 8.0 | 7.5 | 7.0 |
| 3 | ... | 1510 | 6.5 | 8.5 | 7.0 | 7.5 |

## #1 Expanded Proposal: [Title]

[Full expanded proposal from Phase 4]

## Runner-Up Summaries
[Brief summaries of #2 and #3]

## Literature Grounding
[Papers cited, with links to research_notes.md references]
```

**🚦 Checkpoint:** Present top-3 to user for selection. Proceed with chosen idea.

## Key Rules

- **Literature grounding is MANDATORY**: Every idea must cite at least 1 paper from research_notes.md. No floating ideas.
- **Diversity over volume**: 3 genuinely different directions > 8 variations of the same idea.
- **Evolution memory prevents repetition**: IVE FAILED patterns are hard blocks. IDE PROMISING patterns are seeds.
- **Feasibility > novelty**: A feasible good idea beats an infeasible great idea.
- **Kill bad ideas early**: Elo tournament with honest pairwise comparison.
- **IDE distillation after every run**: Build the memory so future tasks benefit.

## Composing with Other Skills

```
/evo-research "direction"     ← literature survey (MANDATORY prerequisite)
/evo-ideation "direction"     ← you are here (Idea Tree Search + Elo)
/evo-planner "selected idea"  ← plan experiments for the chosen idea
```
