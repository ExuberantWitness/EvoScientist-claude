---
name: evo-write
description: "Draft a paper-ready Markdown experiment report. No fabricated results or citations. Includes negative results and limitations. 论文级报告撰写。"
argument-hint: [report_topic_or_scope]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, WebSearch, WebFetch, Agent
---

# EvoScientist Write: Paper-Ready Report Drafting

Draft a report for: **$ARGUMENTS**

## Overview

This skill drafts a paper-ready Markdown experiment report using the experiment plan, logs, analysis, and artifacts. It follows a structured 7-section format, enforces citation discipline, and includes negative results and limitations.

## Constants

- **FORMAT = "markdown"** — Output format: `markdown` or `latex`
- **SECTIONS = 7** — Number of report sections (default 7-section structure)
- **CITATIONS = "inline"** — Citation style: `inline` (URLs) or `bibtex` (fetch from DBLP)
- **OUTPUT_FILE = "final_report.md"** — Output file path

## Inputs

- `$ARGUMENTS`: Report scope or topic
- (Required) `plan.md`: Experiment plan and stages
- (Required) `experiment_log.md`: What was actually run
- (Optional) `analysis_report.md`: Statistical analysis and figures
- (Optional) `research_notes.md`: Literature survey results
- (Optional) `artifacts/figures/`: Generated plots and visualizations

## Workflow

### Phase 0: Gather All Sources

1. Read all available source files:
   - `plan.md` — what was planned
   - `experiment_log.md` — what was run
   - `analysis_report.md` — analysis results
   - `research_notes.md` — related work
   - `success_criteria.md` — evaluation criteria
2. List all figures in `artifacts/figures/`
3. Identify gaps: what data is missing for a complete report?

### Phase 1: Draft Report (7-Section Structure)

Write to OUTPUT_FILE section by section:

```markdown
# [Report Title]

## 1. Summary & Goals
[Research question, motivation, and what this experiment set out to test]
[Key findings in 2-3 sentences]

## 2. Experiment Plan
[Stages, dependencies, and success criteria — summarized from plan.md]
[What changed from the original plan and why]

## 3. Setup & Environment
[Hardware, software versions, package dependencies]
[Datasets used, preprocessing steps, train/val/test splits]
[Random seeds and reproducibility measures]

## 4. Baselines & Comparisons
[What baselines were used and why]
[Implementation details for each method]
[Fair comparison measures (same data splits, compute budget)]

## 5. Results
[Tables with metrics, CIs, significance tests]
[Figures with clear captions]
[Reference to specific artifacts: "See artifacts/figures/X.png"]

## 6. Analysis, Limitations & Next Steps
[Interpretation of results]
[**Negative results**: what did NOT work and why]
[**Limitations**: known issues, threats to validity]
[**Next steps**: recommended follow-up experiments]

## 7. Sources & References
[All referenced papers, datasets, codebases with URLs]
```

### Phase 2: Quality Checks

Before finalizing, verify:

1. **No fabricated results**: Every number traces to `analysis_report.md` or `experiment_log.md`
2. **No fabricated citations**: Every reference has a verifiable URL or DOI
   - If CITATIONS = "bibtex" and WebSearch is available, fetch real BibTeX from DBLP/CrossRef
3. **Figures referenced**: Every figure mentioned exists in `artifacts/figures/`
4. **Negative results included**: Section 6 must include what didn't work
5. **Limitations included**: Section 6 must list at least 2 limitations
6. **Effect sizes reported**: Section 5 includes uncertainty measures (CI or ± std)

Add `[TODO: ...]` markers for any missing information rather than fabricating.

### Phase 3: Write Output

Write the complete report to OUTPUT_FILE.

If FORMAT = latex:
- Convert Markdown to LaTeX (section headings, tables, figure includes)
- Wrap in a standard article template
- Write to `final_report.tex`

**🚦 Checkpoint:** Present report summary (section list + key findings) to the user.

## Key Rules

- **NEVER fabricate results or citations**: Use [TODO] markers for missing data.
- **Include negative results**: What didn't work is as important as what did.
- **Include limitations**: At least 2 specific limitations per report.
- **Effect sizes + uncertainty**: No metric without a confidence measure.
- **Reference actual files**: Point to real paths in `artifacts/` — reader should be able to verify.
- **Evaluation protocol transparency**: State how evaluation was done. Never use model output as ground truth.
- **Honest framing**: Do not overclaim. "Improves by 2% on this dataset" not "solves the problem".

## Composing with Other Skills

```
/evo-analyze "results"    ← produces analysis_report.md + figures
/evo-write "report"       ← you are here
/evo-review               ← cross-model review of the report
```

Or use `/evo-pipeline` for the full end-to-end flow.