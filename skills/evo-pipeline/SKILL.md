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

如果 init_result.needs_session:
```
session = mcp__evo-agents__evo_create_session(workspace_dir="$PWD")
```
**重要**: session_id 必须保存，后续所有 `evo_discuss` / `evo_run_tournament` / `evo_distill` 都需要它。

### 步骤 1: 主循环（所有阶段统一走此循环，包括写作）

```
context_bundle = null
proposals = null
tournament_result = null

while True:
    pre = mcp__pes_controller__pre_loop(workspace_dir="$PWD")
    展示 pre.user_prompt

    while True:
        step = mcp__pes_controller__sub_loop(workspace_dir="$PWD")
        if step.done: break

        根据 step.action 执行:

          "pipeline_context":
            context_bundle = step.context_bundle
            展示 step.instruction

          "multi_agent":
            if step.tool == "evo_discuss":
              result = mcp__evo-agents__evo_discuss(
                session_id=session.session_id,
                topic=step.topic,
                agents=step.agents,
                exclude_agents=step.exclude_agents,
              )
              从 result 提取 proposals 列表
              如果 step.step == "web_reconnaissance":
                将搜索结果保存到 workspace/web_research.json

            elif step.tool == "evo_run_tournament":
              result = mcp__evo-agents__evo_run_tournament(
                session_id=session.session_id,
                proposals=proposals 格式化为 [{id, title, hypothesis, method_sketch}],
              )
              tournament_result = result

            elif step.tool == "evo_distill":
              mcp__evo-agents__evo_distill(
                session_id=session.session_id,
                distill_type=step.distill_type,
                proposals=tournament_result.ranked,
              )

          "ingest_results":
            展示 step.instruction
            experiment_results = step.experiment_results（将传入 post_loop）

          "invoke_skill":
            调对应 Skill（/evo-research, /evo-code, /evo-analyze, /evo-claim, /evo-iterate, /evo-write, /evo-review）

          "wait_external":
            AskUserQuestion(step.prompt)
            将用户输入结果记录

    # --- 数据提取（post_loop 前）---
    cc_atoms = []
    experiment_results = []

    if pre.current_phase == "文献调研":
      读取 research_notes.md，提取真实论文数据作为 cc_atoms
      格式: [{type:"fact", title:"论文标题", content:"摘要/关键发现", tags:["literature"]}]

    if pre.current_phase == "结果分析":
      # ingest_results 步骤已自动扫描结果文件
      # 如需补充，优先级:
      # 1. analysis_report.md
      # 2. results/ablation/summary.json
      # 3. ingest_results 自动扫描（已内置到 post_loop fallback）
      同时从 evo-claim / evo-iterate 产出提取真实发现作为 cc_atoms

    AskUserQuestion: 是否满意当前阶段结果?
    post = mcp__pes_controller__post_loop(
      workspace_dir="$PWD",
      satisfied=...,
      chosen_next_phase=...,
      cc_atoms=cc_atoms,
      experiment_results=experiment_results,
    )

    # --- 展示迭代状态 ---
    if post.gap_analysis:
      gap = post.gap_analysis
      展示: "目标={target_score} 当前最佳={best_score} 差距={gap}({gap_percent}%) CC={cc_atom_count} Grid={grid_filled}/{grid_total} 轮次={iteration}"
      如果 gap.target_met: 展示 "达标！进入写作阶段。"
      否则: 展示 "未达标，开始新一轮迭代。"

    展示 post.message
    if post.next_phase == "已终止": break
```

## 关键规则

- **流程控制由 Python 决定** — 本 SKILL.md 不做任何流程判断
- **绝对不要跳过任何 sub_loop 步骤** — 每个步骤都必须调用，即使看起来没用
- **绝对不要绕过状态机** — 所有工作必须通过 sub_loop→post_loop 循环完成
- **不要直接创建 EXPERIMENT_REPORT.md** — 写作必须通过 PHASE_WRITE 阶段
- **PIPELINE_STATE.json** — 崩溃恢复的唯一真相源
- **Claim Chain 写入** — 仅 W3 Research (真实文献) 和 W5 Analyze (真实实验结果) 后写入，通过 post_loop 的 cc_atoms 参数
- **Experiment Results** — W5 Analyze 后 ingest_results 自动扫描 + post_loop fallback
- **ELO** — 仅在锦标赛内一次性使用
- **Dashboard** — localhost:8420 可追踪进度（包括 STEP 管线和 ingest_results）
- **session_id** — 步骤0创建，全程复用
- **Web 侦察** — 每个创造性阶段(plan/research/elo)开始前先 web_reconnaissance，搜索结果保存到 web_research.json 供 STEP 管线使用
- **迭代循环** — W5 Analyze 后自动判断：达标→W6 写作，未达标→回到 W2 新一轮迭代
- **写作循环** — W6 写作→W7 审阅→不通过→post_loop(satisfied=false)→自动回到 W6 重写
- **MCP 超时** — 配置 300 秒。如果 evo_discuss/evo_run_tournament 接近超时，调 evo_status(session_id) 检查进度
