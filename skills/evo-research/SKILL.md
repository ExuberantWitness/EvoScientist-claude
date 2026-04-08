---
name: evo-research
description: "Web research for methods, baselines, and datasets. One topic at a time, returns actionable notes with sources. 文献与方法调研。"
argument-hint: [research_topic]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, WebSearch, WebFetch, Agent
---

# EvoScientist Research: Literature & Method Survey

Conduct focused research on: **$ARGUMENTS**

## Overview

This skill performs targeted web research to find methods, baselines, datasets, and related work for a specific research topic. It focuses on one topic per invocation and returns structured, actionable notes with verified sources.

## Constants

- **MAX_QUERIES = 5** — Maximum number of search queries (2-3 for simple topics, up to 5 for complex)
- **SOURCES = "web"** — Search sources: `web` (WebSearch), `arxiv` (arXiv-focused), `all`
- **DEPTH = "standard"** — `quick` (surface scan) or `standard` (thorough with paper reading)

## Inputs

- `$ARGUMENTS`: A specific research topic or question (not a broad field)
- (Optional) `plan.md`: Experiment plan for context on what methods are needed
- (Optional) `research_notes.md`: Existing notes to append to (not overwrite)

## Workflow

### Phase 0: Scope the Query

1. Parse $ARGUMENTS into a focused research question
2. If `plan.md` exists, read it to understand what kind of information is needed (baselines? datasets? methods? metrics?)
3. Formulate 2-3 specific search queries. Examples:
   - "state-of-the-art methods for [topic] 2025 2026"
   - "[topic] benchmark dataset comparison"
   - "[topic] baseline implementation github"

### Phase 1: Search & Collect

For each query (up to MAX_QUERIES):

1. Use **WebSearch** to find relevant results
2. For the top 2-3 most relevant results, use **WebFetch** to read the full content
3. Extract from each source:
   - **Method name** and brief description
   - **Key results** (metrics, datasets used)
   - **Strengths and limitations**
   - **Source URL** (mandatory)

If SOURCES includes `arxiv`:
- Include queries targeting arXiv specifically (e.g., "site:arxiv.org [topic]")
- Extract paper title, authors, year, abstract summary

### Phase 2: Synthesize Notes

Compile findings into structured research notes:

```markdown
# Research Notes: [Topic]
Date: [YYYY-MM-DD]

## Summary
[2-3 sentence overview of the research landscape]

## Methods Found

### [Method 1 Name]
- **Paper/Source**: [title + URL]
- **Approach**: [1-2 sentence description]
- **Results**: [key metrics on standard benchmarks]
- **Pros**: [strengths]
- **Cons**: [limitations]
- **Relevance**: [how it relates to our research goal]

### [Method 2 Name]
...

## Datasets & Benchmarks
| Dataset | Size | Task | Common Metrics | URL |
|---------|------|------|---------------|-----|
| ...     | ...  | ...  | ...           | ... |

## Recommended Baselines
1. [Method X] — strongest baseline, widely cited
2. [Method Y] — simple but effective, good sanity check

## Open Questions
- [Question that needs further investigation]

## Sources
- [Full list of URLs consulted]
```

### Phase 3: Write Output

- If `research_notes.md` exists: **append** new section (do not overwrite existing notes)
- If not: **create** `research_notes.md` with the compiled notes

**🚦 Checkpoint:** Present key findings summary to the user.

## Key Rules

- **One topic at a time**: Do not try to cover multiple unrelated topics. Invoke this skill separately for each topic.
- **No fabrication**: Every claim must have a source URL. If unsure, say "could not verify".
- **Actionable output**: Notes should help the coder implement. Include library names, GitHub URLs, specific hyperparameter values when available.
- **Recency bias**: Prefer recent work (2024-2026) unless the user asks for historical survey.
- **Stop conditions**: Stop searching when you have (a) at least 2 strong baseline candidates, (b) 1+ relevant dataset, (c) a clear picture of SOTA. Do not over-research.
- **Hard query limit**: Never exceed MAX_QUERIES search calls.

## Composing with Other Skills

```
/evo-planner "goal"         ← creates plan that identifies research needs
/evo-research "topic"       ← you are here
/evo-code "implement X"     ← implement findings
/evo-ideation "direction"   ← generate ideas based on literature gaps
```
