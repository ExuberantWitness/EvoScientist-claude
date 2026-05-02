---
name: evo-intake
description: "Parse a research proposal and extract goals, datasets, constraints, and metrics. First step of the pipeline. 需求理解与范围界定。"
argument-hint: [proposal_text_or_file_path]
allowed-tools: Read, Write, Edit, Grep, Glob
---

# EvoScientist Intake: Proposal Parsing & Scope Definition

Parse and scope: **$ARGUMENTS**

## Overview

This skill takes a raw research proposal (text, file, or URL to a paper) and extracts a structured scope definition: goals, datasets, constraints, metrics, and compute budget. It is the first step in the EvoScientist pipeline.

## Constants

- **INTERACTIVE = true** — Ask user to confirm/refine the extracted scope
- **OUTPUT_FILE = "research_proposal.md"** — Structured proposal output

## Inputs

- `$ARGUMENTS`: Raw proposal text, or path to a proposal file
- (Optional) `memory/MEMORY.md`: User profile and research preferences

## Workflow

### Phase 0: Load Proposal

1. If $ARGUMENTS looks like a file path, read the file
2. If $ARGUMENTS is raw text, use it directly
3. If `memory/MEMORY.md` exists, read user profile for context (domain, hardware, constraints)

### Phase 1: Extract Structure

Parse the proposal into:

```markdown
# Research Proposal: [Title]
Date: [YYYY-MM-DD]

## Research Question
[Single clear question this research aims to answer]

## Goals
1. [Primary goal]
2. [Secondary goal (if any)]

## Hypotheses
- H1: [Main hypothesis to test]
- H2: [Alternative hypothesis (if any)]

## Datasets
| Dataset | Source | Size | Notes |
|---------|--------|------|-------|
| [name]  | [URL/path] | [rows/samples] | [any constraints] |

## Constraints
- **Compute**: [GPU type, max hours, budget]
- **Time**: [deadline if mentioned]
- **Hardware**: [available resources]
- **Data**: [access restrictions, licensing]
- **Scope**: [what is explicitly out of scope]

## Success Metrics
| Metric | Target | Baseline | Notes |
|--------|--------|----------|-------|
| [name] | [value] | [current best] | [how measured] |

## Prior Work
[Brief mention of known related work from the proposal]

## Ambiguities & Questions
- [Anything unclear that needs user clarification]
```

### Phase 2: Checkpoint

**🚦 Checkpoint:** Present the structured proposal to the user.

If INTERACTIVE = true:
- **User confirms** → Write to OUTPUT_FILE, skill complete
- **User corrects** → Update the relevant sections and re-present
- **User adds info** → Incorporate and re-present

If INTERACTIVE = false:
- Write directly to OUTPUT_FILE

### Phase 3: Output

Write structured proposal to OUTPUT_FILE. This file is the input for `/evo-planner`.

## Key Rules

- **Extract, don't invent**: Only include information present in the proposal. Use [UNKNOWN] for missing fields.
- **Flag ambiguities**: If the proposal is vague about metrics, data, or scope, list these as questions.
- **User context**: Use memory to fill in likely defaults (e.g., if user always uses PyTorch, note that).
- **Constraints matter**: Always extract compute and time constraints — they drive planning decisions.

## Composing with Other Skills

```
/evo-intake "proposal"     ← you are here
/evo-planner "goal"        ← plans experiments based on this scope
/evo-research "topic"      ← researches methods for this scope
```