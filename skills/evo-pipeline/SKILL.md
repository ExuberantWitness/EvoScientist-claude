---
name: evo-pipeline
description: "PES 全流程编排器。由 Python PESController MCP 驱动流程控制。"
argument-hint: [research_proposal_or_question]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, WebSearch, WebFetch, Agent, Skill, AskUserQuestion, mcp__pes_controller__init, mcp__pes_controller__resume, mcp__pes_controller__state, mcp__pes_controller__pre_loop, mcp__pes_controller__sub_loop, mcp__pes_controller__post_loop, mcp__evo-agents__evo_create_session, mcp__evo-agents__evo_send, mcp__evo-agents__evo_discuss, mcp__evo-agents__evo_status, mcp__evo-agents__evo_list_sessions, mcp__evo-agents__evo_get_memory, mcp__evo-agents__evo_run_tournament, mcp__evo-agents__evo_distill, mcp__evo-agents__evo_pipeline_control
---

# EvoScientist Pipeline — PES Controller 驱动

研究问题: **$ARGUMENTS**

## 执行流程

本 SKILL.md 是哑巴执行器。所有流程控制由 Python `mcp__pes_controller__*` MCP tools 驱动。

### 步骤 0: 初始化

```
mcp__pes_controller__init(workspace_dir="$PWD", research_topic="$ARGUMENTS")
```
Cell Grid 维度 Part2 通过 AskUserQuestion 交互定义。
W1 Intake 自动调用 `/evo-intake`。

### 步骤 1: 主循环

```
while True:
    pre = mcp__pes_controller__pre_loop(workspace_dir="$PWD")
    展示 pre.user_prompt

    while True:
        step = mcp__pes_controller__sub_loop(workspace_dir="$PWD")
        if step.done: break

        根据 step.action 执行:
          "invoke_skill"   → 调对应 Skill
          "multi_agent"    → 调对应 MCP tool (evo_discuss / evo_run_tournament / evo_distill)
          "wait_external"  → AskUserQuestion 等待用户操作

    AskUserQuestion: 是否满意当前阶段结果?
    post = mcp__pes_controller__post_loop(workspace_dir="$PWD", satisfied=..., chosen_next_phase=...)
    if post.next_phase == "已终止": break
```

### 步骤 2: 写作阶段

```
while 用户不满意:
    /evo-write "$ARGUMENTS"
    AskUserQuestion 确认
    if 不满意: /evo-review "final report"
```

## 关键规则

- **流程控制由 Python 决定** — 本 SKILL.md 不做任何流程判断
- **PIPELINE_STATE.json** — 崩溃恢复的唯一真相源
- **Claim Chain 写入** — 仅 W3 Research (真实文献) 和 W5 Analyze (真实实验结果) 后写入
- **ELO** — 仅在锦标赛内一次性使用
- **Dashboard** — localhost:8420 可追踪进度
