---
name: research-wiki
description: "Persistent research knowledge base that accumulates papers, ideas, experiments, claims, and their relationships across the research lifecycle. Use when user says \"知识库\", \"research wiki\", \"add paper\", \"wiki query\", or wants to build/query a persistent field map."
argument-hint: [subcommand: init|ingest|query|update|lint|stats]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Agent, WebSearch, WebFetch
---

# Research Wiki: Persistent Research Knowledge Base

Subcommand: **$ARGUMENTS**

## Overview

Persistent, per-project knowledge base that **compounds** across pipeline runs. Every paper read, idea tested, experiment run, and claim verdict makes the wiki smarter.

Inspired by [Karpathy's LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

## Core Concepts

### Four Entity Types

| Entity | Directory | Node ID | What it represents |
|--------|-----------|---------|--------------------|
| **Paper** | `papers/` | `paper:<slug>` | A published/preprint paper |
| **Idea** | `ideas/` | `idea:<id>` | A research idea |
| **Experiment** | `experiments/` | `exp:<id>` | A concrete experiment run |
| **Claim** | `claims/` | `claim:<id>` | A testable scientific claim |

### Typed Relationships (`graph/edges.jsonl`)

| Edge type | From → To | Meaning |
|-----------|-----------|---------|
| `extends` | paper → paper | Builds on prior work |
| `contradicts` | paper → paper | Disagrees with results |
| `inspired_by` | idea → paper | Idea sourced from this paper |
| `supports` | exp → claim | Experiment confirms claim |
| `invalidates` | exp → claim | Experiment disproves claim |
| `supersedes` | paper → paper | Newer work replaces older |

## Wiki Structure

```
research-wiki/
  index.md           # auto-generated categorical index
  log.md             # append-only timeline
  gap_map.md         # field gaps with stable IDs (G1, G2, ...)
  query_pack.md      # compressed summary for /evo-ideation (max 8000 chars)
  papers/<slug>.md
  ideas/<idea_id>.md
  experiments/<exp_id>.md
  claims/<claim_id>.md
  graph/edges.jsonl
```

## Subcommands

### `/research-wiki init`

Initialize wiki for current project:
```bash
python3 tools/research_wiki.py init research-wiki/
```
Creates directory structure, empty index/log/gap_map/query_pack, empty edges.jsonl.

### `/research-wiki ingest "<paper title>" — arxiv: <id>`

Add a paper:
1. Fetch metadata via arXiv/Semantic Scholar
2. Generate slug: `<author><year>_<keyword>` 
3. Create `papers/<slug>.md` with schema
4. Extract relationships, add edges
5. Regenerate index and query_pack

Paper page schema:
```markdown
---
type: paper
node_id: paper:<slug>
title: "<full title>"
authors: ["..."]
year: 2025
venue: arXiv
tags: [tag1, tag2]
relevance: core  # core | related | peripheral
---

# One-line thesis

## Problem / Gap
## Method
## Key Results
## Limitations
## Reusable Ingredients
## Connections [AUTO-GENERATED]
## Relevance to This Project
```

### `/research-wiki query "<topic>"`

Generate `query_pack.md` — compressed summary for ideation context window (max 8000 chars):

| Section | Budget | Content |
|---------|--------|---------|
| Top 5 gaps | 1200 chars | Unresolved gaps with linked ideas |
| Paper clusters | 1600 chars | 3-5 clusters by tag overlap |
| Failed ideas | 1400 chars | Highest anti-repetition value |
| Top papers | 1800 chars | 8-12 papers ranked by centrality |
| Active chains | 900 chars | limitation → opportunity chains |

**Never prune** failed ideas or top gaps first.

### `/research-wiki update <node_id> — <field>: <value>`

Update entity fields. After update: rebuild query_pack, update log.

### `/research-wiki lint`

Health check: orphan pages, stale claims, contradictions, missing connections, dead ideas.

### `/research-wiki stats`

Quick overview: papers/ideas/experiments/claims/edges/gaps counts.

## Integration Hooks

### After `/evo-research` finds papers
```
if research-wiki/ exists:
    for paper in top_papers (limit 8-12):
        /research-wiki ingest paper
    rebuild query_pack
```

### `/evo-ideation` reads wiki
```
if research-wiki/query_pack.md exists:
    prepend query_pack to context
    treat failed ideas as banlist
    treat top gaps as search seeds
```

### After `/evo-claim` verdict
```
Create experiment page
Update claim status → supported/partial/invalidated
Add edges
Update idea outcome
If failed: record WHY
rebuild query_pack
```

## Key Rules

- **One source of truth**: `graph/edges.jsonl`. Page `Connections` sections are auto-generated.
- **Canonical node IDs everywhere**: `paper:<slug>`, `idea:<id>`, `exp:<id>`, `claim:<id>`.
- **Failed ideas are the most valuable memory.** Never prune from query_pack.
- **query_pack.md hard-budgeted at 8000 chars**.
- **Append to log.md for every mutation.**
