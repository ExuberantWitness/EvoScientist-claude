---
name: evo-pipeline
description: "Full end-to-end scientific experiment pipeline. Orchestrates all EvoScientist skills with optional multi-agent discussion mode. 全流程编排器，支持多Agent讨论。"
argument-hint: [research_proposal_or_question]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, WebSearch, WebFetch, Agent, Skill, mcp__llm-review__chat, mcp__gemini-review__review, mcp__evo-agents__evo_create_session, mcp__evo-agents__evo_send, mcp__evo-agents__evo_discuss, mcp__evo-agents__evo_status, mcp__evo-agents__evo_list_sessions, mcp__evo-agents__evo_get_memory
---

# EvoScientist Pipeline: End-to-End Scientific Discovery with Multi-Agent Support

Run full experiment pipeline for: **$ARGUMENTS**

## Overview

This is the master orchestrator that chains all EvoScientist skills into a complete scientific discovery workflow. It manages state across phases, handles checkpoints, and supports recovery from interruptions.

**NEW: Multi-Agent Mode** — When `USE_MULTI_AGENT = true`, key phases use the Agent Manager MCP to get multi-perspective analysis from 6 specialized agents (planner, researcher, coder, debugger, analyst, writer).

```
W1: Intake → W2: Plan → W3: Research → W3.5: Ideation
    ↓           ↓           ↓ (MA)        ↓ (MA)
W4: Code → W4.5: Debug → W4.7: Run
    ↓
W5: Analyze → W5.5: Iterate ←──────┐
    ↓ (MA)                           │
    ├── criteria NOT met ────────────┘
    │
    ├── criteria MET
    ↓
W6: Write → W7: Review (optional) → W8: Memory

(MA) = Multi-Agent discussion enabled
```

## Constants

- **AUTO_PROCEED = false** — Skip checkpoints and auto-advance (true = fully autonomous)
- **SKIP_RESEARCH = false** — Skip literature survey (if user already has context)
- **SKIP_IDEATION = false** — Skip idea generation (if user already has a specific idea)
- **SKIP_REVIEW = false** — Skip cross-model review at the end
- **MAX_PIPELINE_ITERATIONS = 3** — Maximum full iterate-loops before stopping
- **CODE_MODE = "lite"** — Code generation mode: `lite` or `effort`
- **REVIEWER = "llm-review"** — MCP for review: `llm-review`, `gemini-review`, or `none`
- **STATE_FILE = "PIPELINE_STATE.json"** — Pipeline state for recovery

### Multi-Agent Constants (NEW)

- **USE_MULTI_AGENT = true** — Enable multi-agent discussion for key phases
- **MULTI_AGENT_STAGES = ["research", "analyze", "ideation"]** — Phases to use multi-agent (code/debug always in Claude Code)
- **EXCLUDE_AGENTS = ["code-agent", "debug-agent"]** — Agents excluded from multi-agent; proposals returned to Claude Code
- **MULTI_AGENT_MODEL = "claude-sonnet-4-5"** — Model for multi-agent sessions

> Override: `/evo-pipeline "proposal" — USE_MULTI_AGENT: false, AUTO_PROCEED: true`

## Code/Debug Handoff Protocol (CRITICAL)

**Why**: code-agent and debug-agent are EXCLUDED from multi-agent discussions. DeepSeek's multi-agent cannot execute code — only Claude Code can. When multi-agent discussions identify implementation needs, Claude Code MUST take over.

### Handoff Trigger

After EVERY `mcp__evo-agents__evo_discuss()` call, check the return value:

```
result.code_proposals      → list of identified code/debug tasks
result.has_code_proposals   → boolean flag
result.requires_claude_code → boolean flag (same semantics)
```

### Handoff Flow (5 steps)

**Step 1 — DETECT**: If `has_code_proposals` is `true` OR `code_proposals` is non-empty:
- The multi-agent has identified concrete implementation tasks it cannot execute

**Step 2 — NOTIFY DASHBOARD**:
```
mcp__evo-agents__evo_pipeline_control(session_id, action="switch_to_claude")
```
Dashboard shows purple "awaiting Claude Code" banner.

**Step 3 — CONFIRM WITH USER** (unless AUTO_PROCEED = true):
```
AskUserQuestion:
  "Multi-agent identified {N} code/debug task(s):\n{proposals}\n\nHand off to Claude Code for execution?"
  Options: ["Execute all in Claude Code", "Skip code tasks, continue pipeline", "Show transcript first"]
```

**Step 4 — EXECUTE IN CLAUDE CODE**:
- For implementation: `/evo-code "Stage N: [description]"`
- For debugging: `/evo-debug "[error message]"`
- For multi-stage plans: follow `plan.md` stages in dependency order
- After each stage: `/evo-run` with SANITY_FIRST first, then full run
- Max 2 debug-retry loops per stage

**Step 5 — RETURN TO MULTI-AGENT**:
```
mcp__evo-agents__evo_pipeline_control(session_id, action="switch_to_agent")
mcp__evo-agents__evo_send(session_id, message="[Code Execution Report]\nStages completed: N\nFiles changed: [list]\nResults: [summary]\nErrors: [any]")
```
Then AskUserQuestion: "Code execution done. Continue multi-agent analysis?"

### Handoff Checks Per Phase

| Phase | After | Check for proposals? | If yes → |
|-------|-------|---------------------|----------|
| W3: Research | evo_discuss (research) | YES | Execute proposals, THEN return to Phase 3 |
| W3.5: Ideation | evo_discuss (ideation) | YES | Execute proposals, THEN checkpoint 3 |
| W5: Analysis | evo_discuss (analysis) | YES | Execute proposals, THEN re-analyze |

### Dashboard States During Handoff

| State | Dashboard Color | Meaning |
|-------|----------------|---------|
| `control: "pipeline"` | Green | Multi-agent running |
| `control: "claude_code"` | Purple | Claude Code executing |
| `control: "paused"` | Red | System paused |

## Inputs

- `$ARGUMENTS`: Research proposal, question, or goal

## Workflow

### Phase 0: State Recovery & Initialization

1. Check `PIPELINE_STATE.json`. If exists with `status: in_progress` and timestamp < 24h:
   - Resume from the saved phase
   - Load all intermediate files
   - If `session_id` exists and USE_MULTI_AGENT = true, verify session is still active
   - Print: "Resuming pipeline from Phase [N]..."

2. Otherwise, start fresh:
   - Initialize: `mkdir -p artifacts/figures artifacts/tables memory`
   - If `memory/MEMORY.md` doesn't exist, run `/evo-memory init`

3. **Multi-Agent Session Creation** (if USE_MULTI_AGENT = true):
   - Use `mcp__evo-agents__evo_create_session` with:
     - `workspace_dir`: current working directory
     - `model`: MULTI_AGENT_MODEL
   - Store the returned `session_id` in pipeline state

Save state:
```json
{
  "phase": 0,
  "status": "in_progress",
  "iteration": 0,
  "timestamp": "2026-04-08T22:00:00",
  "skipped": [],
  "session_id": "evo_xxx"  // if USE_MULTI_AGENT
}
```

### Phase 1 (W1): Intake & Scope

Invoke: `/evo-intake "$ARGUMENTS"`

Output: `research_proposal.md` with structured scope.

If AUTO_PROCEED = false:
**🚦 Checkpoint 1:** Present extracted scope. Ask user to confirm or refine.

Update state: `"phase": 1`

### Phase 2 (W2): Experiment Planning

Invoke: `/evo-planner "$ARGUMENTS"`

Reads: `research_proposal.md`
Output: `plan.md`, `success_criteria.md`

If AUTO_PROCEED = false:
**🚦 Checkpoint 2:** Present experiment plan. Ask user to approve or modify.

Update state: `"phase": 2`

### Phase 3 (W3): Literature Research

If SKIP_RESEARCH = true → skip to Phase 3.5

Extract key research topics from `plan.md`.

**Multi-Agent Mode** (if "research" in MULTI_AGENT_STAGES and session_id exists):
- Use `mcp__evo-agents__evo_discuss` with:
  - `session_id`: from pipeline state
  - `topic`: "Literature review and method survey for: [research topics from plan.md]"
  - `agents`: ["researcher", "planner", "analyst"]
- The researcher agent leads the literature search
- The planner evaluates methodological fit
- The analyst identifies gaps and opportunities
- Save the discussion transcript to `research_notes.md`

**Code Handoff Check**: After evo_discuss, check `result.requires_claude_code`. If true → execute [Code/Debug Handoff Protocol](#codedebug-handoff-protocol-critical) Steps 1-5, then return here to continue Phase 3.

**Skills Mode** (fallback or single-agent preference):
- For each topic: Invoke `/evo-research "[topic]"`
- Output: `research_notes.md`

Update state: `"phase": 3`

### Phase 3.5 (W3.5): Ideation

If SKIP_IDEATION = true → skip to Phase 4

**Multi-Agent Mode** (if "ideation" in MULTI_AGENT_STAGES and session_id exists):
- Use `mcp__evo-agents__evo_discuss` with:
  - `session_id`: from pipeline state
  - `topic`: "Generate and evaluate research ideas for: $ARGUMENTS. Consider: feasibility, novelty, resources needed."
  - `agents`: ["planner", "researcher", "analyst"]
  - `exclude_agents`: ["code-agent", "debug-agent"] (default — code/debug returned as proposals)
- The planner evaluates resource constraints
- The researcher assesses novelty and related work
- The analyst identifies success metrics and implementation complexity
- Each agent proposes ideas, then votes on the best ones
- Implementation needs are returned as `code_proposals` (not executed by DeepSeek)
- Save the discussion transcript to `idea_report.md`

**Code Proposal Switch** (if code_proposals is non-empty):
- Use `mcp__evo-agents__evo_pipeline_control` with action "switch_to_claude" to notify dashboard
- Use AskUserQuestion to ask: "多 agent 系统识别到 {N} 个实现建议：{proposals}。切换到 Claude Code 执行实现？"
- If user confirms → execute `/evo-code` directly in Claude Code
- After coding → use `mcp__evo-agents__evo_pipeline_control` with action "switch_to_agent"
- Use AskUserQuestion: "实现完成，切回多 agent 继续分析？"
- If user confirms → advance to Phase 4 (or skip if code already done)

**Skills Mode** (fallback):
- Invoke: `/evo-ideation "$ARGUMENTS"`
- Output: `idea_report.md`

If AUTO_PROCEED = false:
**🚦 Checkpoint 3:** Present ranked ideas. Ask user to select one.

If user selects an idea different from the current plan:
- Re-invoke `/evo-planner` with the selected idea
- Update `plan.md` and `success_criteria.md`

Update state: `"phase": 3.5`

### Phase 4 (W4): Implementation

**Before starting Phase 4:**
- Use `mcp__evo-agents__evo_pipeline_control` with action "switch_to_claude" to notify dashboard
- Dashboard shows purple "awaiting Claude Code" status
- AskUserQuestion: "即将进入代码实现阶段，切换到 Claude Code 直接执行。确认？"

For each stage in `plan.md` (in dependency order):

1. **Code**: Invoke `/evo-code "Stage N: [description]" — CODE_MODE: [CODE_MODE]`
2. **Run sanity**: Invoke `/evo-run "Stage N" — SANITY_FIRST: true`
3. If sanity fails: Invoke `/evo-debug "[error]"`
   - After debug, retry run (max 2 retries per stage)
4. **Run full**: Invoke `/evo-run "Stage N" — SANITY_FIRST: false`
5. If full run fails: Invoke `/evo-debug "[error]"`, retry once

**After Phase 4 complete:**
- Use `mcp__evo-agents__evo_pipeline_control` with action "switch_to_agent" to notify dashboard
- AskUserQuestion: "实现完成，切回多 agent 系统继续分析？"
- If user confirms → advance to Phase 5

Update state: `"phase": 4, "current_stage": N`

### Phase 5 (W5): Analysis

**Multi-Agent Mode** (if "analyze" in MULTI_AGENT_STAGES and session_id exists):
- Use `mcp__evo-agents__evo_discuss` with:
  - `session_id`: from pipeline state
  - `topic`: "Analyze experiment results from artifacts/. Compute metrics, identify patterns, assess statistical significance, compare with baselines. Results files: [list artifact files]"
  - `agents`: ["analyst", "planner", "researcher"]
- The analyst leads statistical analysis and visualization
- The planner evaluates against success criteria
- The researcher compares with literature baselines
- Save the discussion transcript to `analysis_report.md`

**Code Handoff Check**: After evo_discuss, check `result.requires_claude_code`. If true → execute [Code/Debug Handoff Protocol](#codedebug-handoff-protocol-critical) Steps 1-5, then re-run analysis to incorporate changes.

**Skills Mode** (fallback):
- Invoke: `/evo-analyze "artifacts/"`
- Output: `analysis_report.md`, `artifacts/figures/`

Update state: `"phase": 5`

### Phase 5.5 (W5.5): Evaluate & Iterate

Invoke: `/evo-iterate`

Reads: `plan.md`, `success_criteria.md`, `analysis_report.md`

**Decision tree:**
- **All criteria met** → advance to Phase 6
- **Criteria not met, iteration < MAX_PIPELINE_ITERATIONS** →
  - Apply suggested adjustments
  - Return to Phase 4 (Code → Run → Analyze → Iterate)
  - Increment iteration counter
- **Criteria not met, iteration >= MAX_PIPELINE_ITERATIONS** →
  - If AUTO_PROCEED = true: advance with best results so far
  - If AUTO_PROCEED = false: 🚦 Checkpoint: present status, ask user

Update state: `"phase": 5.5, "iteration": N`

### Phase 6 (W6): Write Report

Invoke: `/evo-write "$ARGUMENTS"`

Output: `final_report.md`

If AUTO_PROCEED = false:
**🚦 Checkpoint 6:** Present report summary. Ask user to review before proceeding to external review.

Update state: `"phase": 6`

### Phase 7 (W7): Cross-Model Review (Optional)

If SKIP_REVIEW = true OR REVIEWER = "none" → skip to Phase 8

Invoke: `/evo-review "final report" — REVIEWER: [REVIEWER]`

Output: `AUTO_REVIEW.md`, updated `final_report.md`

Update state: `"phase": 7`

### Phase 8 (W8): Memory & Cleanup

1. Invoke: `/evo-memory update`

2. **Multi-Agent Session Cleanup** (if session_id exists):
   - Use `mcp__evo-agents__evo_get_memory` to extract final agent memory
   - Optionally save memory insights to `memory/agent_memory.md`
   - Note: Session persists for potential future resume

3. Update `PIPELINE_STATE.json` with `"status": "completed"`

4. Present final summary:

```markdown
## Pipeline Complete

### Research Question
[from research_proposal.md]

### Key Results
[from analysis_report.md — top metrics]

### Success Criteria
| Criterion | Target | Achieved | Status |
|-----------|--------|----------|--------|
| ... | ... | ... | PASS/FAIL |

### Iterations
- Total iterations: N
- Stages completed: N/M

### Multi-Agent Usage
- Session ID: evo_xxx (or "not used")
- Agents consulted: planner, researcher, coder, debugger, analyst, writer
- Key discussions: research, ideation, analysis

### Output Files
- Report: final_report.md
- Analysis: analysis_report.md
- Plan: plan.md
- Figures: artifacts/figures/
- Review: AUTO_REVIEW.md (if reviewed)

### Learnings Extracted
- [N] new entries added to experiment memory
```

## Multi-Agent Integration Details

### When to Use Multi-Agent

| Phase | Multi-Agent Value | Agents Involved |
|-------|-------------------|-----------------|
| W3: Research | Cross-verify findings, identify gaps | researcher, planner, analyst |
| W3.5: Ideation | Diverse perspectives, feasibility check | planner, researcher, coder, analyst |
| W5: Analyze | Statistical rigor, baseline comparison | analyst, planner, researcher |
| W4.5: Debug | Root cause analysis, fix strategies | coder, debugger, analyst |

### MCP Tool Usage

```
# Create session (Phase 0)
mcp__evo-agents__evo_create_session(
  workspace_dir="/path/to/project",
  model="claude-sonnet-4-5"
)
→ {"session_id": "evo_abc123", ...}

# Trigger discussion (various phases)
mcp__evo-agents__evo_discuss(
  session_id="evo_abc123",
  topic="Literature review for world models in robotics",
  agents=["researcher", "planner", "analyst"]
)
→ {"transcript": "...", "agents_participated": [...]}

# Check status
mcp__evo-agents__evo_status(session_id="evo_abc123")
→ {"status": "idle", "sub_agents_used": [...]}
```

### Graceful Degradation

If MCP tools are unavailable:
- Log a warning (not an error)
- Fall back to Skills Mode (single-agent)
- Continue pipeline execution

## Key Rules

- **State persistence**: Write PIPELINE_STATE.json after every phase transition. Recovery is critical for long pipelines.
- **Checkpoint discipline**: In non-auto mode, ALWAYS pause at checkpoints. The user must stay in control.
- **Fail forward**: If a non-critical skill fails (e.g., ideation, review), log the error and continue. Only stop for critical failures (code won't run, no data).
- **One iteration at a time**: Do not try to change multiple things between iterations. Follow plan adjustments from `/evo-iterate`.
- **Time awareness**: Log timestamps. The user should know how long each phase took.
- **Graceful MCP degradation**: If review MCP or multi-agent MCP is unavailable, skip with a warning (not an error).
- **24h staleness**: Pipeline state older than 24h is considered stale. Start fresh.

## Composing with Individual Skills

Each phase can be run independently:

```bash
# Run just the parts you need
/evo-intake "proposal"
/evo-planner "goal"
/evo-research "topic"
/evo-ideation "direction"
/evo-code "stage 1"
/evo-run "stage 1"
/evo-debug "error"
/evo-analyze "artifacts/"
/evo-iterate
/evo-write "report"
/evo-review "report"
/evo-memory update
```

Or run end-to-end with multi-agent:
```bash
/evo-pipeline "Your research proposal" — USE_MULTI_AGENT: true, AUTO_PROCEED: true
```

Or run single-agent (classic mode):
```bash
/evo-pipeline "Your research proposal" — USE_MULTI_AGENT: false
```
