---
name: evo-evolve
description: "PES-driven quality-diversity evolution with Claim Chain integration. Four-layer architecture evolution engine. 四层框架的进化引擎。"
argument-hint: [task_or_search_space_description]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Agent, Skill
---

# EvoScientist Evolve: PES + Claim Chain + Island GA

Run quality-diversity evolution for: **$ARGUMENTS**

## Overview

This skill implements a PES (Plan-Execute-Summary) evolution loop integrated with the four-layer architecture:

```
L4: Claim Chain (Atom Graph) — knowledge hub (star topology center)
     ↕              ↕                ↕
L1: Scores    L2: Rubric+Judge   L3: Island GA+MAP-Elites
```

The user stays in the loop: they approve plans, run experiments, and report results.

## Constants

- **EXPLOIT_RATIO = 0.7** — Fraction of sampling from high-score cells
- **STAGNATION_WINDOW = 5** — Consecutive non-improving rounds before meta-prompting
- **STAGNATION_THRESHOLD = 0.01** — Slope below which evolution is considered stagnant
- **META_PROMPT_PROBABILITY = 0.1** — Chance of triggering meta-prompting per round
- **MAX_VARIANTS_PER_SESSION = 30** — Safety cap per evolution session
- **GRID_PERSIST_DIR = "evolve_archive"** — Archive directory
- **RUBRIC_SIMILARITY_THRESHOLD = 0.9** — Similarity above which Rubric triggers new dimension
- **MIGRATION_SCORE_FLOOR_RATIO = 0.8** — Min score ratio for island migration
- **MAX_RUBRIC_DIMENSIONS = 10** — Upper limit on rubric dimensions
- **INITIAL_RUBRIC_DIMENSIONS = ["accuracy", "robustness", "realtime", "completeness", "generalization"]**

## Inputs

- `plan.md`: Experiment plan
- `success_criteria.md`: Measurable thresholds
- `claim_chain/`: Atom Graph (created if not exists)
- `evolve_archive/`: Grid archive (created if not exists)

## Workflow

### Step 0: Setup (one-time)

1. Read `plan.md` and `success_criteria.md`

2. Read Claim Chain priors:
   ```bash
   python tools/claim_chain.py list-atoms --limit 50
   python tools/claim_chain.py list-relations --type contradicts --limit 20
   python tools/claim_chain.py list-relations --type validates --limit 20
   ```
   Synthesize relevant prior knowledge (what worked, what failed, known boundaries).

3. AskUserQuestion: Define behavior descriptor dimensions
   ```
   Options:
   - "ATEC task × robot platform × terrain type"
   - "Task type × method family × score bracket"
   - "Custom"
   ```

4. AskUserQuestion: Search strategy
   ```
   Options:
   - "MAP-Elites (grid archive, diversity-first)"
   - "CMA-MAE (covariance-guided, continuous-space-first)"
   - "Hybrid: MAP-Elites + occasional meta-prompting"
   ```

5. Initialize archive:
   ```bash
   python tools/evolve_grid.py init --config '{
     "behavior_dims": [
       {"name": "task", "values": ["A", "B"]},
       {"name": "terrain", "values": ["flat", "rough", "stair"]},
       {"name": "method", "values": ["ppo", "act", "hybrid"]}
     ]
   }'
   ```

6. Initialize Claim Chain if not exists:
   ```bash
   python tools/claim_chain.py summary
   ```

7. Prompt user: "View knowledge graph: `python tools/claim_chain.py dot | dot -Tpng -o graph.png`"

### Step 1: Plan (LLM-directed mutation)

1. Sample parent from archive:
   ```bash
   python tools/evolve_grid.py sample --strategy exploit  # 70% of the time
   python tools/evolve_grid.py sample --strategy explore   # 30% of the time
   ```

2. Read parent's history from `evolve_archive/evolve_state.json` and Claim Chain:
   ```bash
   python tools/claim_chain.py related --id [parent_method_atom_id]
   ```

3. Check for stagnation via FitnessTracker:
   ```python
   from agent-manager.evo_agent_manager.evolution.fitness import FitnessTracker
   tracker = FitnessTracker(workspace_dir)
   trend = tracker.get_trend(window=5)
   if trend["direction"] == "stable":
       # Trigger meta-prompting
   ```

4. If stagnant OR random trigger (META_PROMPT_PROBABILITY):
   - LLM analyzes the search strategy itself
   - Writes new strategy via StrategyManager.apply_patch()

5. LLM reasons about mutation direction (CITING Claim Chain priors):
   ```
   "Parent [X] scores [N] on [cell]. Claim Chain shows:
    - contradicts: [failed approaches]
    - validates: [successful approaches]
    - boundary_of: [known limits]
    Suggested mutation: [Y] because [reasoning]. Expected: [Z]."
   ```

6. Present Plan to user via AskUserQuestion:
   ```
   question: "Approve this mutation plan?"
   options:
     - "Approve and execute"
     - "Modify direction (I'll specify)"
     - "Reject, propose new plan"
   ```

### Step 2: Execute (generate experiment config)

1. Generate concrete changes based on approved Plan:
   - Training config changes (YAML)
   - Code changes (training script / reward function)
   - Hyperparameter changes

2. Write variant files:
   ```bash
   # Create variant directory
   mkdir -p evolve_archive/variants
   # Write plan, config, metadata
   ```

3. Output terminal command for user:
   ```
   "Run in another terminal:
    $ cd [project] && python [command]
    Return results via:
    - Placing file at: evolve_archive/results/v{N}_result.json
    - Or telling me the score directly"
   ```

### Step 3: Summary (user returns with results)

1. Read result from user input or file:
   ```bash
   cat evolve_archive/results/v{N}_result.json
   ```
   Expected format: `{"score": N, "behavior_dims": {...}, "log_excerpt": "..."}`

2. Classify: IMPROVEMENT / REGRESSION / STALE

3. Update grid archive:
   ```bash
   python tools/evolve_grid.py record-result --id v{N} --score [N] --dims '[JSON]'
   ```

4. Update Claim Chain (knowledge hub):
   ```bash
   # Always record the experiment result
   python tools/claim_chain.py add-atom --type verification \
     --title "v{N} result" --content "[score and context]" \
     --tags "score,[method],[domain]"

   # Record relationship
   if IMPROVEMENT:
     python tools/claim_chain.py add-relation --source [method_atom] \
       --target [verification_atom] --type validates \
       --evidence "score=[N], delta=[+X]"
   if REGRESSION:
     python tools/claim_chain.py add-relation --source [method_atom] \
       --target [verification_atom] --type contradicts \
       --evidence "score=[N], delta=[-X]"
   ```

5. Update FitnessTracker:
   ```python
   tracker.record(score=score, task_id="evolve", dimensions=behavior_dims)
   ```

6. Update experiment_log.md (dev notes only):
   ```markdown
   ## Variant v{N} — [Date]
   - Config: [key params]
   - Score: [N] ([IMPROVEMENT/REGRESSION/STALE])
   - Training: [duration, GPU usage]
   ```

7. Display updated state:
   ```bash
   python tools/evolve_grid.py heatmap --dir evolve_archive
   python tools/claim_chain.py summary
   ```
   Show FitnessTracker trend and stagnation warnings.

### Step 4: Island Management

1. **Auto-create Islands**: When a new experiment result is significantly different from existing islands (different method family or behavior pattern):
   - Create new island: `evolve_archive/islands/[island_id]/island_meta.json`
   - Record which Claims form the island's centroid

2. **Propose Merges**: When Claim Chain shows `derives` or `specializes` relations between islands:
   - AskUserQuestion: "Islands [A] and [B] share method family. Merge?"
   - If confirmed: merge variant lists, update centroid

3. **Migration with triple check**:
   - Check 1: Claim Chain — target island's Claims don't contradict the migrant
   - Check 2: Score threshold — migrant score >= target island min_score * MIGRATION_SCORE_FLOOR_RATIO
   - Check 3: AskUserQuestion — user confirms

### Step 5: Rubric (conditional, when scores are close)

When two algorithms have L1 scores within 10% of each other:

1. Read both algorithms' full context from Claim Chain

2. LLM-as-Judge multi-dimensional evaluation:
   ```
   For each dimension in CURRENT_RUBRIC_DIMENSIONS:
     Algorithm A: [score 0-10]
     Algorithm B: [score 0-10]
   ```

3. If all dimension scores are > RUBRIC_SIMILARITY_THRESHOLD similar:
   - LLM proposes 1-2 new dimensions based on observed differences
   - AskUserQuestion: "Add dimension '[name]' to rubric?"
   - If confirmed: append to rubric dimensions list

4. Write comparison to Claim Chain:
   ```bash
   python tools/claim_chain.py add-atom --type fact \
     --title "A vs B comparison" --content "[results]" \
     --tags "comparison"
   python tools/claim_chain.py add-relation --source [A_atom] \
     --target [B_atom] --type compares_to --evidence "[dimension scores]"
   ```

### Step 6: Decision

AskUserQuestion:
```
Options:
- "Continue PES loop (next Plan)"
- "Inject external insight (from literature/user)"
- "Harvest best (export per-cell elites)"
- "Stop evolution"
```

If "Continue" → increment variant counter, return to Step 1.

## Island File Structure

```
evolve_archive/islands/
├── island_001/
│   ├── island_meta.json    # {name, method_family, centroid_claim_ids, created_from}
│   └── variants.json       # [{variant_id, score, cell, timestamp}]
├── island_002/
│   └── ...
```

## Key Rules

- **Star topology**: All layers interact only through Claim Chain (L4). No direct L1→L3 shortcuts.
- **Claim Chain is truth**: Scores write to Claim Chain. Islands read from Claim Chain.
- **User in the loop**: Plans require approval, results require user input, merges require confirmation.
- **No fabrication**: Scores come from real experiments, never invented.
- **One variable per mutation**: Change one aspect at a time for clear attribution.
- **Evidence hierarchy**: experiment > literature > LLM_analysis.
- **Cap variants**: Stop after MAX_VARIANTS_PER_SESSION to prevent runaway sessions.

## Auto Mode (Autonomous PES Loop)

Use `--auto` to run fully autonomous evolution without manual plan approval or result entry:

```bash
# Dry-run first to see what would happen
python tools/evo_auto_evolve.py dry-run \
  --config evolve_archive/evolve_config.json \
  --workspace /tmp/evo_cartpole \
  --max-rounds 5

# Run autonomous evolution
python tools/evo_auto_evolve.py run \
  --config evolve_archive/evolve_config.json \
  --workspace /tmp/evo_cartpole \
  --max-rounds 20 \
  --exploit-ratio 0.7 \
  --stagnation-window 5
```

The auto engine:
- Samples from MAP-Elites grid (exploit 70% / explore 30%)
- Maps cell coordinates to hyperparameters via `param_mapping`
- Mutates parameters with random perturbation
- Runs the training command
- Parses JSON results
- Updates grid archive and Claim Chain (atoms + relations)
- Manages Islands (auto-create, detect merge candidates)
- Tracks fitness and detects stagnation
- Applies meta-strategy when stalled
- Stops when success threshold met or max rounds reached

**Performance Gate:**
```bash
python tools/evo_auto_evolve.py performance-gate --workspace [workspace]
```
Blocks Phase 5 entry if results are too poor (< 20% of target → back to W2).

**Island Detection:**
```bash
python tools/evo_auto_evolve.py detect-islands --workspace [workspace]
```
Scans variant history and Claim Chain, creates islands, proposes merges.

## Composing with Other Skills

```
/evo-pipeline (Phase 4) → /evo-evolve → user runs experiments → /evo-evolve continues
                                                ↓
/evo-analyze ← invoked within Step 3 for detailed metrics
/evo-iterate ← triggered at end if criteria not met
```

### Pipeline Integration

```
/evo-pipeline (Phase 4) → EVOLVE_MODE=explore
  └→ /evo-evolve --auto
       └→ evo_auto_evolve.py run (autonomous PES loop)
            ├→ Sample → Config → Train → Parse → Grid+Claims → Island
            ├→ Check stagnation → meta-strategy
            ├→ Check success threshold → stop
            └→ Finalize → best_variants.json
```
