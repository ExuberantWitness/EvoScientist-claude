# Experiment Plan

## Overview
- **Goal**: [One sentence]
- **Duration**: [Estimated total time]
- **Compute**: [Total GPU-hours estimated]

## Stages

### Stage 1: [Name]
- **Goal**: [What this stage achieves]
- **Success Signals**:
  - [ ] [Measurable criterion 1]
  - [ ] [Measurable criterion 2]
- **What to Run**: `[command]`
- **Expected Artifacts**: [files produced]
- **Estimated Time**: [hours]
- **Dependencies**: [none / Stage N]

### Stage 2: [Name]
- **Goal**: ...
- **Success Signals**:
  - [ ] ...
- **What to Run**: `...`
- **Expected Artifacts**: ...
- **Estimated Time**: ...
- **Dependencies**: Stage 1

## Dependency Graph
```
Stage 1 → Stage 2 → Stage 3
                  ↘ Stage 4 (parallel)
```

## Iteration Triggers
- If Stage N metric < threshold → revisit Stage N-1
- If training diverges → reduce learning rate, re-run

## Evaluation Protocol
- **Primary Metric**: [name] > [threshold]
- **Secondary Metrics**: [list]
- **Statistical Requirements**: [N runs, significance level]

## Environment Preflight
- [ ] GPU available (`nvidia-smi`)
- [ ] Python version checked
- [ ] Key packages installed
- [ ] Dataset accessible
- [ ] Sufficient disk space
