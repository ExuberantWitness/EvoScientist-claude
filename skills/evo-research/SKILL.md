---
name: evo-research
description: "Web research for methods, baselines, and datasets. Uses paper-navigator scripts for academic search with arXiv fallback. One topic at a time, returns actionable notes with sources. 文献与方法调研。"
argument-hint: [research_topic]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, WebSearch, WebFetch, Agent
---

# EvoScientist Research: Literature & Method Survey

Conduct focused research on: **$ARGUMENTS**

## Overview

This skill performs targeted academic research using **paper-navigator** scripts (Semantic Scholar + arXiv + citation graph) supplemented by web search. It focuses on one topic per invocation and returns structured, actionable notes with verified academic sources.

## Constants

- **PAPER_NAV_DIR = "~/.evoscientist/skills/paper-navigator/scripts"** — Path to paper-navigator Python scripts
- **MAX_ACADEMIC_PAPERS = 30** — Target number of papers for survey-depth research
- **MAX_ACADEMIC_PAPERS_QUICK = 10** — Target for quick scans
- **DEPTH = "standard"** — `quick` (10 papers, surface) or `standard` (30 papers, exhaustive)

## Prerequisites Check

Before starting, check available search backends:

```bash
# Check if S2_API_KEY is set (enables full Semantic Scholar features)
echo "S2_API_KEY: ${S2_API_KEY:-NOT SET (arXiv-only mode)}"
# Check paper-navigator scripts exist
ls ~/.evoscientist/skills/paper-navigator/scripts/scholar_search.py
```

**Two modes:**
- **S2 mode** (S2_API_KEY set): scholar_search → citation_traverse → recommend (full academic graph)
- **arXiv-only mode** (no key): scholar_search auto-falls-back to arXiv API + arxiv_monitor

## Workflow

### Phase 0: Scope the Query

1. Parse $ARGUMENTS into a focused research question
2. If `plan.md` exists, read it to understand what information is needed
3. Formulate 4-6 variant queries covering distinct research angles (synonym substitution, specificity adjustment)

### Phase 1: Academic Paper Search (PRIMARY)

Run paper-navigator scripts in sequence. All scripts are Python CLI tools at `$PAPER_NAV_DIR/`.

#### 1a. Primary Search (always available — S2 with arXiv fallback)

```bash
python ~/.evoscientist/skills/paper-navigator/scripts/scholar_search.py \
  --query "<query>" --limit 20 --json
```

Repeat for 2-3 main queries. Collect paper IDs, titles, authors, years, citation counts.

#### 1b. Citation Expansion (S2_API_KEY required)

If `S2_API_KEY` is set, expand from top-3 seed papers:

```bash
python ~/.evoscientist/skills/paper-navigator/scripts/citation_traverse.py \
  --paper-id <paper_id> --direction forward --limit 15 --json

python ~/.evoscientist/skills/paper-navigator/scripts/citation_traverse.py \
  --paper-id <paper_id> --direction backward --limit 10 --json

python ~/.evoscientist/skills/paper-navigator/scripts/citation_traverse.py \
  --paper-id <paper_id> --direction co-citation --limit 10 --json
```

#### 1c. Recommendations (S2_API_KEY required)

```bash
python ~/.evoscientist/skills/paper-navigator/scripts/recommend.py \
  --positive <top3_ids_comma_separated> --limit 15 --json
```

#### 1d. arXiv Monitor (always available, supplementary)

```bash
python ~/.evoscientist/skills/paper-navigator/scripts/arxiv_monitor.py \
  --keywords "<comma_separated_keywords>" --match-mode flexible --limit 15 --json
```

### Phase 2: Web Search Supplement

Use **WebSearch** (max 3 queries) for:
- Blog posts and technical reports not on arXiv
- GitHub repositories for implementations
- Benchmark leaderboard pages
- Recent news/industry developments

### Phase 3: Read Key Papers

For the top 8-12 most relevant papers (by citation count + relevance):
1. Use `WebFetch` on arXiv abstract pages to read abstracts
2. For critical papers: use the paper-navigator fetch script to get full text
   ```bash
   python ~/.evoscientist/skills/paper-navigator/scripts/fetch_paper.py --paper-id <paper_id_or_url> --limit-chars 30000
   ```

### Phase 4: Synthesize Notes

Compile findings into structured research notes:

```markdown
# Research Notes: [Topic]
Date: [YYYY-MM-DD]
Sources: [S2+arXiv | arXiv-only | web]

## Summary
[3-5 sentence overview of the research landscape, citing specific papers]

## Key Papers (ranked by relevance)

### [Paper Title]
- **Authors**: [names] ([year])
- **Venue**: [journal/conference], Citations: [N]
- **Approach**: [1-2 sentence description]
- **Key Results**: [metrics on standard benchmarks]
- **Strengths**: [what's good]
- **Limitations**: [what's missing]
- **Relevance**: [how it connects to our goal]

[...repeat for top 8-12 papers]

## Methods Landscape

| Family | Key Idea | Representative Papers | Maturity |
|--------|----------|----------------------|----------|
| ...    | ...      | [1], [2]             | ...      |

## Datasets & Benchmarks
| Dataset | Size | Task | Standard Metrics | SOTA |
|---------|------|------|-----------------|------|
| ...     | ...  | ...  | ...             | ...  |

## Challenge-Insight Tree
[Map of challenges → insights → papers, highlighting unsolved challenges]

## Recommended Baselines
1. [Method X] [citation_N] — strongest overall, widely cited
2. [Method Y] [citation_N] — simple but effective, good sanity check

## Open Questions & Research Gaps
- [Gap identified from literature]

## Sources
[Numbered list of all papers/URLs with full citations]
```

### Phase 5: Write Output

- If `research_notes.md` exists: **append** new section
- If not: **create** `research_notes.md`

**🚦 Checkpoint:** Present key findings summary to user.

## Key Rules

- **Paper-navigator first**: Always start with academic scripts before web search. Academic papers are the primary source.
- **No S2 key = no problem**: scholar_search auto-falls-back to arXiv. What you lose: citation counts, citation_traverse, recommend. arxiv_monitor still works.
- **Citation expansion is mandatory when S2 is available**: After finding 3+ seeds, run forward + backward + co-citation on top seeds.
- **Coverage gap check**: After collecting, check if all identified sub-topics are covered. If not, run additional searches.
- **One topic at a time**: Single research question per invocation.
- **No fabrication**: Every claim must have a source. State "could not verify" when unsure.
- **Deduplicate**: Same paper from multiple sources → keep the best metadata.
- **Hard limits**: MAX_ACADEMIC_PAPERS for standard, MAX_ACADEMIC_PAPERS_QUICK for quick.

## Composing with Other Skills

```
/evo-planner "goal"         ← creates plan identifying research needs
/evo-research "topic"       ← you are here (academic paper search)
/evo-ideation "direction"   ← generate ideas from literature gaps
/evo-code "implement X"     ← implement findings
```
