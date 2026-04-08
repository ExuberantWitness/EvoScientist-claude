---
name: evo-ideation
description: "Generate, rank, and validate research ideas. Combines brainstorming with Elo-style tournament ranking and feasibility checks. 创意发现与排名。"
argument-hint: [research_direction]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, WebSearch, WebFetch, Agent, mcp__llm-review__chat
---

# EvoScientist Ideation: Idea Generation & Tournament

Explore ideas for: **$ARGUMENTS**

## Overview

This skill generates research ideas for a given direction, then ranks them through a tournament process. Ideas are scored on novelty, feasibility, and impact. The top ideas get quick feasibility checks before a final recommendation.

Combines EvoScientist's research-ideation workflow with an Elo-style ranking mechanism.

## Constants

- **NUM_IDEAS = 8** — Number of initial ideas to generate
- **TOP_K = 3** — Number of top ideas to carry forward for feasibility check
- **CROSS_MODEL = false** — Use external LLM (via MCP) for independent idea scoring
- **MEMORY_CHECK = true** — Read memory to avoid re-proposing failed ideas
- **OUTPUT_FILE = "idea_report.md"** — Output file

## Inputs

- `$ARGUMENTS`: Research direction or problem area
- (Optional) `research_notes.md`: Literature survey for context
- (Optional) `memory/ideation-memory.md`: Prior ideas (to avoid repetition)
- (Optional) `memory/experiment-memory.md`: Past successes and failures

## Workflow

### Phase 0: Context Loading

1. If MEMORY_CHECK = true, read `memory/ideation-memory.md` and `memory/experiment-memory.md`
   - Note failed ideas to avoid
   - Note successful patterns to build upon
2. If `research_notes.md` exists, read it for landscape context
3. Identify gaps, trends, and opportunities from the literature

### Phase 1: Brainstorm

Generate NUM_IDEAS ideas. For each idea, specify:

```markdown
### Idea N: [Short Title]
- **Core Insight**: [One sentence: what is the key idea?]
- **Approach**: [2-3 sentences: how would this work?]
- **Novelty**: [What is new compared to existing work?]
- **Feasibility**: [Can this be done with available resources?]
- **Expected Impact**: [What would success look like?]
- **Risks**: [What could go wrong?]
```

Rules for brainstorming:
- At least 2 ideas should be "safe" (incremental improvements)
- At least 2 ideas should be "bold" (higher risk, higher reward)
- No idea should duplicate a known failed approach from memory
- Each idea must be distinct (not variations of the same thing)

### Phase 2: Tournament Ranking

Score each idea on three dimensions (1-10):

| Idea | Novelty | Feasibility | Impact | Total |
|------|---------|-------------|--------|-------|
| Idea 1 | X | X | X | XX |
| ... | ... | ... | ... | ... |

Scoring criteria:
- **Novelty (1-10)**: 1=well-known, 5=minor twist, 10=paradigm shift
- **Feasibility (1-10)**: 1=needs massive resources, 5=doable with effort, 10=trivial
- **Impact (1-10)**: 1=marginal improvement, 5=solid contribution, 10=field-changing

If CROSS_MODEL = true, also send ideas to external reviewer via MCP for independent scoring. Average the two scores.

Rank by total score. Select TOP_K ideas.

### Phase 3: Feasibility Deep-Dive

For each of the TOP_K ideas:

1. **Resource check**: Can it be done with available hardware/data/time?
2. **Quick literature check**: Has this been done before? (WebSearch)
3. **Minimum viable experiment**: What is the smallest experiment that would test this idea?
4. **Estimated effort**: Hours of compute, days of implementation

### Phase 4: Final Recommendation

**🚦 Checkpoint:** Present ranked ideas to the user.

```markdown
## Recommended Ideas (Ranked)

### #1: [Title] (Score: XX/30)
[Summary + why this is the top pick]
**Minimum Viable Experiment**: [1-2 sentences]
**Estimated Effort**: [X days implementation, Y GPU-hours]

### #2: [Title] (Score: XX/30)
...

### #3: [Title] (Score: XX/30)
...

## Ideas Not Recommended
- Idea N: [reason for exclusion]
```

- **User selects an idea** → Write to OUTPUT_FILE with full details
- **User wants more ideas** → Return to Phase 1 with refined direction
- **User wants to refine an idea** → Deep-dive on that specific idea

### Phase 5: Output

Write full idea report to OUTPUT_FILE. Update `memory/ideation-memory.md` with:
- All generated ideas (for future reference)
- Which idea was selected
- Which ideas were rejected and why

## Key Rules

- **Diversity**: Ideas must span different approaches, not variations of one theme.
- **Memory-aware**: Never re-propose ideas that failed before (check memory).
- **Honest scoring**: Don't inflate scores to make ideas look better.
- **Kill bad ideas early**: Better to discard 5 weak ideas than polish 1 mediocre idea.
- **Feasibility > novelty**: A feasible good idea beats an infeasible great idea.
- **Empirical signal**: If a quick pilot can validate an idea in <2 hours, that's better than theoretical argument.

## Composing with Other Skills

```
/evo-research "direction"     ← literature survey (do this first)
/evo-ideation "direction"     ← you are here
/evo-planner "selected idea"  ← plan experiments for the selected idea
```