---
name: evo-analyze
description: "Analyze experiment outputs: compute metrics, make plots, summarize insights. Scientific rigor enforced. 实验数据分析与可视化。"
argument-hint: [results_path_or_description]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Agent
---

# EvoScientist Analyze: Data Analysis & Visualization

Analyze experiment results: **$ARGUMENTS**

## Overview

This skill analyzes experiment outputs — computes metrics from actual data files, creates publication-quality plots, and summarizes insights. It enforces scientific rigor: no fabricated numbers, proper statistical reporting, and honest uncertainty quantification.

## Constants

- **SIGNIFICANCE_LEVEL = 0.05** — Statistical significance threshold
- **CORRECTION = "bonferroni"** — Multiple-testing correction: `bonferroni`, `holm`, `fdr`, or `none`
- **FIGURE_FORMAT = "png"** — Output format: `png`, `pdf`, `svg`
- **ARTIFACTS_DIR = "artifacts"** — Where to save figures and tables

## Inputs

- `$ARGUMENTS`: Path to results directory/files, or description of what to analyze
- Experiment output files (CSV, JSON, logs, checkpoints)
- (Optional) `plan.md`: Expected metrics and success criteria
- (Optional) `success_criteria.md`: Thresholds to evaluate against

## Workflow

### Phase 0: Locate & Load Data

1. If $ARGUMENTS is a path, read the files at that path
2. Otherwise, scan `artifacts/` for result files (CSV, JSON, .log, .pt, .pkl)
3. Read `success_criteria.md` if it exists — note the target metrics
4. Inventory what data is available and what analyses are possible

### Phase 1: Compute Metrics

1. **Primary metrics**: Compute the main metrics defined in the plan (accuracy, F1, loss, etc.)
2. **Statistical measures**: For each metric:
   - Mean and standard deviation (across runs/seeds if available)
   - Confidence intervals (95% CI)
   - Effect sizes (Cohen's d or equivalent) when comparing methods
3. **Multiple-testing correction**: If comparing multiple methods/conditions, apply CORRECTION method
4. **Exploratory vs Confirmatory**: Clearly label which analyses were pre-registered (in the plan) vs exploratory (discovered during analysis)

Write analysis script to `artifacts/analyze.py` (or equivalent), then run it.

### Phase 2: Create Visualizations

Generate publication-friendly plots:

1. **Required plots**:
   - Training curves (loss/metric vs epoch) if training was involved
   - Bar chart or table comparing methods/conditions
   - Error bars or confidence intervals on all comparative plots
2. **Optional plots** (if data supports):
   - Confusion matrix (classification tasks)
   - Distribution plots (feature distributions, score distributions)
   - Ablation results table

Save all figures to `artifacts/figures/`. Use clear titles, axis labels, and legends.

### Phase 3: Summarize Insights

Write analysis to `analysis_report.md`:

```markdown
# Analysis Report
Date: [YYYY-MM-DD]

## Summary
[2-3 sentence overview of findings]

## Metrics

### Primary Results
| Method | Metric 1 | Metric 2 | ... |
|--------|----------|----------|-----|
| Baseline | X.XX ± Y.YY | ... | ... |
| Ours | X.XX ± Y.YY | ... | ... |

### Statistical Significance
- [Method A vs B]: p = X.XX (correction: bonferroni)
- Effect size (Cohen's d): X.XX

### Success Criteria Evaluation
| Criterion | Target | Achieved | Status |
|-----------|--------|----------|--------|
| Accuracy > 0.85 | 0.85 | 0.87 ± 0.02 | PASS |

## Figures
- `artifacts/figures/training_curves.png`: [description]
- `artifacts/figures/comparison.png`: [description]

## Exploratory Findings
[Any interesting patterns not in the original plan]

## Limitations & Caveats
- [Known issues with the data or analysis]
- [Things that should be interpreted with caution]

## Next Steps
- [Recommended follow-up experiments or analyses]
```

**🚦 Checkpoint:** Present key results and figures to the user.

## Key Rules

- **NEVER fabricate numbers**: Compute everything from actual files. If data is missing, say so.
- **Effect sizes with uncertainty**: Always report CI or error bars, not just point estimates.
- **Multiple-testing correction**: Apply when comparing 3+ conditions. State the correction method.
- **Exploratory vs confirmatory**: Label clearly. Exploratory findings need replication.
- **Reproducible analysis**: Write analysis as a script, not just manual computation.
- **Save figures properly**: All plots go to `artifacts/figures/` with descriptive filenames.
- **Negative results matter**: Report them honestly. They are scientifically valuable.

## Composing with Other Skills

```
/evo-run                    ← produces experiment results
/evo-analyze "artifacts/"   ← you are here
/evo-iterate                ← evaluates if success criteria met
/evo-write                  ← includes analysis in report
```