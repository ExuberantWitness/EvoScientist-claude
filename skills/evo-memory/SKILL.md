---
name: evo-memory
description: "Manage persistent memory: extract user profile, research preferences, experiment conclusions, and learnings. Subcommands: init, update, query, stats. 记忆管理。"
argument-hint: [subcommand]
allowed-tools: Read, Write, Edit, Grep, Glob
---

# EvoScientist Memory: Persistent Knowledge Management

Manage memory: **$ARGUMENTS**

## Overview

This skill manages EvoScientist's persistent memory system. It extracts structured information from conversations and experiment results, storing them in `/memory/` for use across sessions. The memory system tracks four dimensions: user profile, research preferences, experiment history, and learned preferences.

## Subcommands

- `/evo-memory init` — Create memory directory and template files
- `/evo-memory update` — Extract new information from recent work and update memory
- `/evo-memory query "topic"` — Search memory for relevant prior knowledge
- `/evo-memory stats` — Show memory overview and statistics

## Memory Structure

```
memory/
├── MEMORY.md               # Main memory file (user profile + preferences)
├── ideation-memory.md      # Ideas explored, selected, rejected
└── experiment-memory.md    # Proven strategies, failed approaches, key results
```

## Workflow

### Subcommand: init

Create the memory directory and template files:

**memory/MEMORY.md**:
```markdown
# EvoScientist Memory

## User Profile
- **Name**: (unknown)
- **Role**: (unknown)
- **Institution**: (unknown)
- **Language**: (unknown)

## Research Preferences
- **Primary Domain**: (unknown)
- **Sub-fields**: (unknown)
- **Preferred Frameworks**: (unknown)
- **Preferred Models**: (unknown)
- **Hardware**: (unknown)
- **Constraints**: (unknown)

## Learned Preferences
- (none yet)
```

**memory/ideation-memory.md**:
```markdown
# Ideation Memory

## Ideas Explored
(none yet)

## Ideas Selected
(none yet)

## Ideas Rejected (and why)
(none yet)
```

**memory/experiment-memory.md**:
```markdown
# Experiment Memory

## Proven Strategies
(none yet)

## Failed Approaches (avoid repeating)
(none yet)

## Key Results
(none yet)
```

### Subcommand: update

1. Read current memory files
2. Scan recent project files for new information:
   - `research_proposal.md` → user's research domain and goals
   - `experiment_log.md` → experiment conclusions
   - `analysis_report.md` → key results and findings
   - `idea_report.md` → ideas explored and outcomes
   - `AUTO_REVIEW.md` → review feedback patterns
3. Extract NEW information (skip what's already in memory):

   **User Profile**: name, role, institution, language (from proposal or conversation context)

   **Research Preferences**: domain, frameworks, models, hardware (from experiment setup)

   **Experiment Conclusions**: For each completed experiment:
   ```markdown
   ### [YYYY-MM-DD] [Title]
   - **Question**: [what was tested]
   - **Method**: [approach used]
   - **Key Result**: [main finding]
   - **Conclusion**: [what we learned]
   - **Artifacts**: [paths to relevant files]
   ```

   **Learned Preferences**: Patterns in user behavior and choices

4. **Merge** new information into existing memory (append, don't overwrite):
   - User Profile: update individual fields only if new value found
   - Research Preferences: update individual fields
   - Experiment History: append new entries, deduplicate by title
   - Learned Preferences: append new items, deduplicate

5. Write updated memory files

### Subcommand: query "topic"

1. Read all memory files
2. Search for entries relevant to the query topic
3. Compile a compressed context pack:

```markdown
## Memory Query: [topic]

### Relevant Experiments
- [matching experiment summaries]

### Relevant Ideas
- [matching idea entries]

### Relevant Strategies
- [matching proven/failed approaches]

### User Context
- [relevant preferences or constraints]
```

### Subcommand: stats

Read memory files and report:

```markdown
## Memory Statistics
- **User Profile**: [X/6 fields filled]
- **Research Preferences**: [X/6 fields filled]
- **Experiments Logged**: [N]
- **Ideas Explored**: [N] (selected: N, rejected: N)
- **Proven Strategies**: [N]
- **Failed Approaches**: [N]
- **Learned Preferences**: [N]
- **Last Updated**: [date]
```

## Key Rules

- **Extract, don't invent**: Only store information that actually exists in project files or conversation.
- **No duplication**: Always check existing memory before adding. Deduplicate on merge.
- **Privacy aware**: Do not store sensitive information (API keys, passwords, personal identifiers beyond name/role).
- **Concise entries**: Each memory entry should be a short phrase or sentence, not a paragraph.
- **Update immediately**: When user shares personal/research information, update memory before anything else.
- **Staleness**: Memory can become stale. When queried, note that entries may be outdated.

## Composing with Other Skills

All EvoScientist skills read from memory. This skill writes to memory.

```
/evo-memory init           ← first-time setup
/evo-intake "proposal"     ← may trigger memory update (user info)
/evo-iterate               ← triggers memory evolution (experiment learnings)
/evo-memory update         ← explicit full update
/evo-memory query "topic"  ← before starting new research
```