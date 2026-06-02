# EvoScientist-Claude 🧬🔬

*让 Claude Code 变成你的 AI 科研团队 — 6 个专业 Agent 自动协作，从提案到论文全流程自动化*

[English](#english) | 中文

> 📰 **v0.3.0** (2026-06-02) — NEW: Claim Chain v2 SQLite 知识图谱 + Dashboard 迭代版本管理 (undo/rollback) + 跨迭代知识注入. 详见 [Updates & Bug Fixes](#-updates--bug-fixes--更新进展与缺陷修复).
>
> 📰 **v0.2.1** (2026-05-25) — Tavily Search + Direct LLM Pipeline, Dashboard Live Persona Events, Session Recovery, Watchdog Disabled.
>
> 📰 **v0.2.0** (2026-05-02) — Four-Layer Architecture: Claim Chain + MAP-Elites Grid + evo-evolve PES Loop + vis.js Dashboard. 15 Skills.
>
> 📰 **v0.1.0** (2026-04-09) — 首次发布：14 Skills + Agent Manager MCP + 3 跨模型审稿桥接

---

> 🧬 **不只是提示词，而是一个完整的 AI 科研团队。** EvoScientist-Claude 将 [EvoScientist](https://github.com/EvoScientist/EvoScientist) 的 6 个专业 AI Agent（规划师、调研员、程序员、调试员、分析师、写作者）重构为 Claude Code 原生 Skills + MCP 多 Agent 管理系统。两种使用方式：轻量 Skills 模式（零依赖），或完整多 Agent 讨论模式（通过 MCP）。
>
> 🧠 **v0.3.0 新增 Claim Chain v2** — SQLite 知识图谱 (cc.db) 替代 JSONL 附录，每条 atom 携带 iter/phase/timestamp 元数据，BGE-M3 语义嵌入。Dashboard 迭代控制面板支持 git-like 快照、undo 回退、CC 满意/不满意语义标记。
>
> 🪶 **极简架构** — Skills 模式零依赖，纯 Markdown 文件，复制即用。Agent Manager 模式通过 MCP 协议桥接 LangGraph 多 Agent 系统，支持 conda 环境和 GPU 访问，无沙箱限制。
>
> 💡 *灵感来自 [ARIS](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) 的 Skill 架构 + [EvoScientist](https://github.com/EvoScientist/EvoScientist) 的多 Agent 编排*

[![License](https://img.shields.io/badge/License-Apache_2.0-blue?style=flat)](LICENSE) · [![Skills](https://img.shields.io/badge/Skills-20+-green?style=flat)]() · [![MCP Tools](https://img.shields.io/badge/MCP_Tools-8-orange?style=flat)]() · [![CC](https://img.shields.io/badge/Claim_Chain-SQLite-purple?style=flat)]() · [![Python](https://img.shields.io/badge/Python-3.11+-blue?style=flat)]()

---

## 🎯 两种使用方式

### 方式 A：Skills 模式（轻量，零依赖）

直接在 Claude Code 中使用 20+ 个可组合的研究 Skills，无需 Python 环境。每个 Skill 是一个纯 Markdown 提示词文件。

```bash
# 安装 Skills（复制到 Claude Code 技能目录）
git clone https://github.com/ExuberantWitness/EvoScientist-claude.git
cp -r EvoScientist-claude/skills/* ~/.claude/skills/

# 在 Claude Code 中使用
/evo-pipeline "世界模型在人形机器人运动控制中的应用"
```

> 💡 Skills 模式下，Claude Code 本身作为执行者，按照 SKILL.md 中定义的工作流依次完成各阶段。适合快速使用，不需要额外环境。

### 方式 B：Agent Manager 模式（完整多 Agent 讨论 + Dashboard）

通过 MCP Server 桥接完整的 LangGraph 多 Agent 系统。6 个专业 Agent 通过共享状态自动协调讨论，支持 conda 环境和 GPU 访问。

```bash
# 一键安装（在 Claude Code 中运行 bootloader skill）
/evo-boot /path/to/EvoScientist-main

# 或手动安装
cd EvoScientist-claude/agent-manager
bash extract_core.sh /path/to/EvoScientist-main   # 提取核心模块
bash setup_env.sh                                    # 创建 conda 环境
bash register_mcp.sh                                 # 注册 MCP
```

安装后，Claude Code 自动获得 8 个 MCP 工具：

```
evo_create_session  — 创建多 Agent 会话
evo_send            — 发送消息，Agent 自动分派到子 Agent
evo_discuss         — 触发多 Agent 讨论（多视角分析）
evo_status          — 查看会话状态
evo_list_sessions   — 列出所有会话
evo_resume          — 恢复之前的会话
evo_approve         — 审批 Agent 操作（人在回路）
evo_get_memory      — 读取 Agent 自动提取的记忆
```

> 🔥 **核心区别**：Skills 模式是 "一个 Claude 按脚本执行"；Agent Manager 模式是 "6 个独立 Agent 互相讨论协调"，这是 EvoScientist 的核心创新。
>
> 🖥️ **Dashboard (v0.3.0 新增)** — `python run_dashboard.py` 启动 Web 控制台 (localhost:8420)，提供管线可视化、Claim Chain 知识图谱、迭代版本管理 (undo/rollback)、实时 Persona 事件流。

---

## ✨ Features / 功能特色

- 🧬 **6 个专业 Agent** — planner（规划）、researcher（调研）、coder（编码）、debugger（调试）、analyst（分析）、writer（写作），各司其职
- 🔄 **20+ 个可组合 Skills** — 单独使用或链式调用，覆盖研究全生命周期
- 🧬 **四层进化架构** — L1 程序化基准测试 → L2 Rubric 多维评估 → L3 MAP-Elites 质量多样性进化 → L4 Claim Chain 知识图谱，星型拓扑中心化协作
- 🧠 **Claim Chain v2** — SQLite 知识图谱 (cc.db)，18 种关系类型，BGE-M3 语义嵌入，temporal metadata (iter/phase/timestamp)
- 🔄 **迭代版本管理** — git-like 快照 + undo 回退，满意标记 iter_complete / 不满意回滚 iter_rollback，decision ledger 审计
- 🗣️ **多 Agent 讨论** — 多个 Agent 从各自专业角度分析同一问题，综合得出结论（Agent Manager 模式）
- 📊 **Dashboard 可视化** — vis.js 力导向知识图谱 + 迭代控制面板 + 实时 Persona 事件流 (SSE)，运行于 localhost:8420
- 🗺️ **MAP-Elites 进化网格** — 3×3 行为空间归档，exploit/explore 采样策略，FitnessTracker 停滞检测，PES (Plan-Execute-Summary) 循环
- 🔍 **跨模型审稿** — 通过 MCP 调用 GPT/Gemini/DeepSeek/MiniMax 作为独立评审，避免自我审查盲区
- 🧠 **持久化记忆** — 自动提取用户画像、研究偏好、实验结论，跨会话累积
- 🔓 **无沙箱限制** — Agent Manager 模式下完整支持 conda、GPU、系统路径（替换了原版的 `CustomSandboxBackend`）
- 📊 **科学严谨** — 强制报告效应量、置信区间、负面结果，禁止编造数据
- 💾 **断点恢复** — JSON 状态文件支持会话恢复 + decision ledger 审计追踪

---

## 🧰 All Skills / 全部技能

### 🚀 编排器
- [`/evo-pipeline`](skills/evo-pipeline/SKILL.md) — 全流程编排：intake → plan → research → ideation → code → run → analyze → iterate → write → review
- [`/evo-evolve`](skills/evo-evolve/SKILL.md) — PES 质量多样性进化：Plan→Execute→Summary 循环 + Claim Chain 知识图谱 + MAP-Elites 网格归档 + Island GA 迁移
- [`/evo-boot`](skills/evo-boot/SKILL.md) — Bootloader：一键安装 Agent Manager 系统

### 📋 需求与规划 (W1-W2)
- [`/evo-intake`](skills/evo-intake/SKILL.md) — 解析研究提案，提取目标、数据集、约束、成功指标
- [`/evo-planner`](skills/evo-planner/SKILL.md) — 制定实验计划，定义阶段、成功信号、依赖关系。支持 PLAN / REFLECTION 双模式

### 🔍 调研与创意 (W3)
- [`/evo-research`](skills/evo-research/SKILL.md) — 文献与方法调研，WebSearch + WebFetch，一次一个主题
- [`/evo-ideation`](skills/evo-ideation/SKILL.md) — 创意生成 + Elo 锦标赛排名 + 可行性验证
- [`/evo-refine`](skills/evo-refine/SKILL.md) — 迭代精炼方法（外部评审反馈）

### 💻 实现与执行 (W4)
- [`/evo-code-agent-pre`](skills/evo-code-agent-pre/SKILL.md) — 代码前：从 plan 提取 CC atom，理解知识图谱上下文
- [`/evo-code`](skills/evo-code/SKILL.md) — 实验代码实现，Lite / Effort 双模式，GPU preflight，实时注册函数到 CC
- [`/evo-code-agent-check`](skills/evo-code-agent-check/SKILL.md) — 代码质量检查，更新 CC atom 状态
- [`/evo-code-agent-post`](skills/evo-code-agent-post/SKILL.md) — 代码后：建立函数→proposal CC 关联
- [`/evo-debug`](skills/evo-debug/SKILL.md) — 运行时故障诊断：Reproduce → Root Cause → Minimal Fix
- [`/evo-run`](skills/evo-run/SKILL.md) — 执行实验（本地 / SSH / 云 GPU），sanity check + 后台运行

### 📊 分析与迭代 (W5)
- [`/evo-analyze`](skills/evo-analyze/SKILL.md) — 统计分析 + 可视化，强制报告 CI/效应量/多重比较校正
- [`/evo-claim`](skills/evo-claim/SKILL.md) — 结果到声明判断门：validated / refuted
- [`/evo-iterate`](skills/evo-iterate/SKILL.md) — 对比成功信号，决定迭代/转向/推进，自动提取经验教训

### 📝 写作与审稿 (W6-W7)
- [`/evo-write`](skills/evo-write/SKILL.md) — 论文级 7 节结构报告，禁止编造结果和引用
- [`/evo-review`](skills/evo-review/SKILL.md) — 跨模型 MCP 审稿循环，medium/hard 难度，最多 N 轮迭代

### 🧠 记忆管理
- [`/evo-memory`](skills/evo-memory/SKILL.md) — 持久化记忆：init / update / query / stats
- [`/research-wiki`](skills/research-wiki/SKILL.md) — 持久化知识库（论文/想法/声明关联网络）

---

## 🔄 Pipeline Flow / 工作流

```
                        ┌──────────────────────────────┐
                        │      /evo-pipeline            │
                        │   (全流程编排器，可选自动推进)    │
                        └──────────┬───────────────────┘
                                   │
            ┌──────────────────────┼──────────────────────┐
            ▼                      ▼                      ▼
    ┌───────────┐          ┌───────────┐          ┌───────────┐
    │ W1: Intake│ ──────▶  │ W2: Plan  │ ──────▶  │ W3:Research│
    │ 需求解析   │          │ 实验规划   │          │ 文献调研   │
    └───────────┘          └───────────┘          └─────┬─────┘
                                                        │
                                                        ▼
                                                 ┌───────────┐
                                                 │W3.5:Ideate│
                                                 │ 创意发现   │
                                                 └─────┬─────┘
                                                        │
            ┌───────────────────────────────────────────┘
            ▼
    ┌───────────┐     ┌───────────┐     ┌───────────┐
    │ W4: Code  │────▶│W4.5:Debug │────▶│W4.7: Run  │
    │ 代码实现   │     │ 调试修复   │     │ 运行实验   │
    └───────────┘     └───────────┘     └─────┬─────┘
                                               │
                                               ▼
                                        ┌───────────┐
                                        │ W5:Analyze│
                                        │ 数据分析   │
                                        └─────┬─────┘
                                               │
                                               ▼
                                        ┌───────────┐    未达标
                                        │W5.5:Iterate│──────────▶ 返回 W4
                                        │ 迭代评估   │
                                        └─────┬─────┘
                                              │ 达标
                                              ▼
                                        ┌───────────┐
                                        │ W6: Write │
                                        │ 报告撰写   │
                                        └─────┬─────┘
                                              │
                                              ▼
                                        ┌───────────┐
                                        │ W7: Review│  (可选)
                                        │ 跨模型审稿 │
                                        └─────┬─────┘
                                              │
                                              ▼
                                        ┌───────────┐
                                        │  Memory   │
                                        │ 记忆提取   │
                                        └───────────┘
```

> 🆕 **v0.3.0 迭代管理**: W5→满意→下一阶段 (CC 标记 iter_complete) | 不满意→重做 | 回到Plan→重新规划 (git-like 快照 + undo)。下一轮 W2 自动注入全量 CC 知识图谱作为 persona 上下文。

---

## 🗣️ 多 Agent 讨论能力（Agent Manager 模式独有）

这是 EvoScientist 最核心的创新。当你通过 MCP 调用 `evo_discuss` 时，6 个专业 Agent 从各自角度分析问题：

**测试示例**：话题 "世界模型在人形机器人运动控制领域的结合点"

| Agent | 角色 | 观点摘要 |
|-------|------|---------|
| **planner-agent** | 实验设计 | 建议 DreamerV3+MPC 路线，先在 Isaac Gym 中训练世界模型 |
| **research-agent** | 文献调研 | 引用 DayDreamer (ICLR 2024)、OMNIMOVER (RSS 2025)，指出 JEPA 趋势 |
| **code-agent** | 工程实现 | 分析状态表征对齐、实时推理延迟 ≤1ms 的挑战 |
| **data-analysis-agent** | 指标评估 | 设计评估体系：运动精度 RMSE、能量效率 CoT、泛化成功率 |
| **main-agent** | 综合 | 共识：DreamerV3+MPC 为切入点；分歧：扩散模型 vs 传统 RSSM |

> 💡 与单模型自我审查不同，多 Agent 讨论打破了思维盲区 — 不同角色的 Agent 会提出互补甚至矛盾的观点，综合后得出更全面的结论。

---

## 🎛️ 参数自定义

所有 Skills 支持行内参数覆盖，语法：`/skill-name "input" — PARAM: value, PARAM2: value2`

### 全流程编排器 (`/evo-pipeline`)

| 参数 | 默认值 | 说明 |
|------|--------|------|
| AUTO_PROCEED | false | 自动推进（true = 全自动，不暂停确认） |
| SKIP_RESEARCH | false | 跳过文献调研 |
| SKIP_IDEATION | false | 跳过创意生成 |
| SKIP_REVIEW | false | 跳过跨模型审稿 |
| CODE_MODE | lite | 代码生成模式：`lite`（直接）或 `effort`（迭代精修） |
| REVIEWER | llm-review | 审稿 MCP：`llm-review`、`gemini-review` 或 `none` |

### 实验规划 (`/evo-planner`)

| 参数 | 默认值 | 说明 |
|------|--------|------|
| MODE | plan | `plan`（生成计划）或 `reflection`（评估进度） |
| MAX_STAGES | 7 | 最大实验阶段数 |
| MODEL_DEFAULT | 7B-class | 默认模型规模（轻量优先） |

### 跨模型审稿 (`/evo-review`)

| 参数 | 默认值 | 说明 |
|------|--------|------|
| MAX_ROUNDS | 3 | 最大审稿轮数 |
| THRESHOLD | 7 | 通过分数 (1-10) |
| DIFFICULTY | medium | 审稿难度：`medium` / `hard` |
| REVIEWER | llm-review | 使用的 MCP：`llm-review` / `gemini-review` |

### 数据分析 (`/evo-analyze`)

| 参数 | 默认值 | 说明 |
|------|--------|------|
| SIGNIFICANCE_LEVEL | 0.05 | 显著性水平 |
| CORRECTION | bonferroni | 多重比较校正：`bonferroni` / `holm` / `fdr` / `none` |
| FIGURE_FORMAT | png | 图表格式：`png` / `pdf` / `svg` |

> 💡 覆盖示例：`/evo-pipeline "我的提案" — AUTO_PROCEED: true, REVIEWER: gemini-review, CODE_MODE: effort`

---

## 🔀 跨模型审稿桥接 (MCP Servers)

| MCP Server | 支持的模型 | 说明 |
|------------|-----------|------|
| **llm-review** | GPT-4o, DeepSeek, Kimi, MiniMax, GLM, 任何 OpenAI 兼容 API | 通用评审桥接 |
| **gemini-review** | Gemini 2.5 Flash, Gemini Pro | Google Gemini 专用 |
| **feishu-notify** | — | 飞书/Lark 消息推送（实验完成通知） |

安装示例：

```bash
# GPT/DeepSeek 评审
pip install mcp httpx
claude mcp add llm-review \
  -e LLM_API_KEY=sk-xxx \
  -e LLM_BASE_URL=https://api.deepseek.com/v1 \
  -e LLM_MODEL=deepseek-chat \
  -- python3 mcp-servers/llm-review/server.py

# Gemini 评审
claude mcp add gemini-review \
  -e GEMINI_API_KEY=xxx \
  -- python3 mcp-servers/gemini-review/server.py
```

> 📚 详细配置见 [MCP Setup Guide](docs/MCP_SETUP.md)

---

## ⚙️ 安装与配置

### 前置条件

**Skills 模式（零依赖）：**
- [x] Claude Code 已安装

**Agent Manager 模式（完整多 Agent）：**
- [x] Claude Code 已安装
- [x] conda 已安装
- [x] EvoScientist 源码（[下载](https://github.com/EvoScientist/EvoScientist)）
- [x] LLM API Key（Anthropic / OpenAI / DeepSeek 任一）

### Skills 模式安装

```bash
# 1. 克隆项目
git clone https://github.com/ExuberantWitness/EvoScientist-claude.git

# 2. 安装 Skills
cp -r EvoScientist-claude/skills/* ~/.claude/skills/

# 3. (可选) 安装跨模型审稿 MCP
pip install mcp httpx
claude mcp add llm-review -e LLM_API_KEY=sk-xxx -- python3 mcp-servers/llm-review/server.py

# 4. 使用
# 在 Claude Code 中：
/evo-pipeline "你的研究提案"
```

### Agent Manager 模式安装

```bash
# 方式一：使用 bootloader skill（推荐）
# 在 Claude Code 中：
/evo-boot /path/to/EvoScientist-main

# 方式二：手动安装
cd EvoScientist-claude/agent-manager

# 2a. 提取核心模块（从 EvoScientist 源码）
bash extract_core.sh /path/to/EvoScientist-main

# 2b. 创建 conda 环境
conda create -n evo-agents python=3.11 -y
conda run -n evo-agents pip install deepagents langchain langchain-anthropic langgraph langgraph-checkpoint-sqlite mcp httpx pyyaml python-dotenv rich

# 2c. 安装 agent-manager
cd agent-manager && conda run -n evo-agents pip install -e .

# 2d. 注册 MCP（注意替换路径）
claude mcp add evo-agents \
  -e PYTHONPATH="/abs/path/to/agent-manager:/abs/path/to/agent-manager/evoscientist_core" \
  -e PYTHONIOENCODING=utf-8 \
  -e OPENAI_API_KEY=sk-xxx \
  -e OPENAI_BASE_URL=https://api.deepseek.com/v1 \
  -- /path/to/conda/envs/evo-agents/python -m evo_agent_manager.server --base-dir /abs/path/to/agent-manager
```

> ⚠️ **Windows 用户注意**：`conda run` 在 Windows 上有编码问题，建议直接使用 conda env 的 Python 路径（如 `C:/Users/xxx/.conda/envs/evo-agents/python.exe`）。

### Dashboard 模式（可选，Web 控制台）

```bash
cd EvoScientist-claude
pip install -r requirements.txt  # starlette, sse-starlette, numpy, FlagEmbedding
python run_dashboard.py &
# Dashboard: http://localhost:8420
```

---

## 📁 项目结构

```
EvoScientist-claude/
├── README.md                          # 本文档
├── CLAUDE.md                          # Claude Code 项目配置
├── LICENSE                            # Apache 2.0
├── .env.example                       # 环境变量模板
├── .gitignore
├── run_dashboard.py                   # Dashboard 入口 (localhost:8420)
│
├── skills/                            # 20+ Claude Code Skills
│   ├── evo-pipeline/SKILL.md         # 全流程编排器
│   ├── evo-boot/SKILL.md             # Bootloader
│   ├── evo-intake/SKILL.md           # 需求解析
│   ├── evo-planner/SKILL.md          # 实验规划
│   ├── evo-research/SKILL.md         # 文献调研
│   ├── evo-ideation/SKILL.md         # 创意发现
│   ├── evo-refine/SKILL.md           # 方法精炼
│   ├── evo-code/SKILL.md             # 代码实现
│   ├── evo-code-agent-pre/SKILL.md   # 代码前：CC 上下文
│   ├── evo-code-agent-check/SKILL.md # 代码检查：更新 CC 状态
│   ├── evo-code-agent-post/SKILL.md  # 代码后：CC 关联
│   ├── evo-debug/SKILL.md            # 调试修复
│   ├── evo-run/SKILL.md              # 实验执行
│   ├── evo-analyze/SKILL.md          # 数据分析
│   ├── evo-claim/SKILL.md            # 结果→声明判断门
│   ├── evo-iterate/SKILL.md          # 迭代评估
│   ├── evo-write/SKILL.md            # 报告撰写
│   ├── evo-review/SKILL.md           # 跨模型审稿
│   ├── evo-memory/SKILL.md           # 记忆管理
│   └── research-wiki/SKILL.md        # 知识库
│
├── pes_controller/                    # PES 自动流转引擎
│   ├── controller.py                  # 主控制器 (W2-W8, persona, ELO, CC context)
│   ├── bootstrap.py                   # Session 初始化
│   ├── protocol.py                    # 状态读写 + 原子操作
│   └── elo/                           # ELO 锦标赛 + RND 新颖性评估
│
├── claim_chain/                       # Claim Chain v2 知识图谱
│   ├── chain.py                       # ClaimChainV2: SQLite CRUD + embedding
│   ├── query.py                       # CCQueryInterface: 语义搜索 + 图遍历
│   ├── grounding.py                   # CCGrounding: atom/relation 验证
│   └── schemas/                       # Node/Edge dataclass, taxonomy, validation
│
├── sdk/
│   ├── dashboard/monitor.py           # Starlette Web Dashboard + 迭代控制 API
│   ├── memory/evo_auto_evolve.py      # PES 自动进化循环
│   ├── search/web_search.py           # Tavily + Web 搜索
│   └── status/fitness.py              # Fitness 追踪器
│
├── plugins/
│   ├── writing/markdown_parser.py     # Vault → CC 同步 + self-wiring
│   ├── experimentation/agent_task.py  # 实验任务管理
│   └── reporting/event_log.py         # 事件日志
│
├── tools/
│   ├── experiment_recorder.py         # 实验记录 → CC + events + Markdown
│   ├── bge_socket_server.py           # BGE-M3 Unix socket 嵌入服务
│   └── cc_query_tool.py               # CC CLI: query/upsert/link
│
├── agent-manager/                     # 多 Agent MCP 管理系统
│   ├── evo_agent_manager/            # Python 包
│   │   ├── server.py                 # MCP Server (8 tools)
│   │   ├── manager.py                # Session 管理 + 多 Agent 讨论
│   │   ├── agent_factory.py          # 无沙箱 Agent 创建
│   │   ├── backend.py                # UnrestrictedBackend
│   │   └── utils.py
│   ├── evoscientist_core/            # 从源码提取的核心模块
│   ├── extract_core.sh               # 核心模块提取脚本
│   ├── setup_env.sh                  # conda 环境安装
│   ├── register_mcp.sh               # MCP 注册脚本
│   └── pyproject.toml
│
├── mcp-servers/                       # 跨模型审稿桥接
│   ├── llm-review/server.py          # GPT/DeepSeek/MiniMax/GLM
│   ├── gemini-review/server.py       # Google Gemini
│   └── feishu-notify/server.py       # 飞书通知
│
├── templates/                         # 研究工件模板
│   ├── RESEARCH_PROPOSAL_TEMPLATE.md
│   ├── EXPERIMENT_PLAN_TEMPLATE.md
│   ├── EXPERIMENT_LOG_TEMPLATE.md
│   ├── ANALYSIS_REPORT_TEMPLATE.md
│   ├── FINAL_REPORT_TEMPLATE.md
│   └── MEMORY_TEMPLATE.md
│
├── session/                           # Session 生命周期管理
├── application/                       # Personas, orchestrator, evolution
│
└── docs/                              # 文档
    ├── QUICK_START.md
    ├── SKILL_MAP.md
    └── MCP_SETUP.md
```

---

## 📊 Skills 模式 vs Agent Manager 模式对比

| 维度 | Skills 模式 | Agent Manager 模式 |
|------|-----------|-------------------|
| **依赖** | 零（纯 Markdown） | conda + Python 3.11 + ~10 包 |
| **Agent 交互** | 单 Claude 按脚本执行 | 6 个独立 Agent 自动协调讨论 |
| **多 Agent 讨论** | 不支持 | 支持（`evo_discuss` MCP tool） |
| **Dashboard 可视化** | 支持 (`run_dashboard.py`) | 支持 |
| **自动 Memory** | 手动 `/evo-memory update` | middleware 自动提取 |
| **conda/GPU 支持** | 受 Claude Code 沙箱限制 | 完整支持（UnrestrictedBackend） |
| **安装时间** | <1 分钟 | ~15 分钟 |
| **适用场景** | 快速使用、简单任务 | 复杂研究、需要多视角分析 |

---

## 📋 Roadmap

### Done / 已完成

- [x] **20+ 核心 Skills** — 覆盖研究全生命周期 + PES 质量多样性进化 + code-agent 四阶段 (pre/code/check/post)
- [x] **四层进化架构** — Claim Chain (L4) + Rubric (L2) + MAP-Elites Grid (L3) + Programmatic GT (L1)
- [x] **Claim Chain v2** — SQLite 知识图谱 (cc.db)，18 种关系类型，BGE-M3 语义嵌入，temporal metadata
- [x] **迭代版本管理** — jump_to_plan 快照 + undo，CC 满意/不满意语义，跨迭代知识注入
- [x] **Dashboard 迭代控制** — 阶段流转 + 撤销回到Plan + 迭代目录管理 + decision ledger 审计
- [x] **MAP-Elites 进化网格** — 3×3 行为归档，exploit/explore 采样，FitnessTracker 停滞检测
- [x] **Agent Manager MCP Server** — 8 个 MCP tools 控制多 Agent 系统
- [x] **UnrestrictedBackend** — 替换沙箱，支持 conda/GPU
- [x] **跨模型审稿** — 3 个 MCP bridge（GPT/Gemini/飞书）
- [x] **多 Agent 讨论** — `evo_discuss` 多视角分析
- [x] **Bootloader Skill** — `/evo-boot` 一键安装

### Planned / 计划中

- [ ] **Rubric 动态维度扩展** — LLM-as-Judge 自动提议新评估维度，人工确认加入
- [ ] **Island GA 自动合并** — LLM 检测 Island 间 derives/specializes 关系，自动提议合并
- [ ] **并行 Agent 执行** — LangGraph DAG 并行（planner + researcher 同时工作）
- [ ] **Research Wiki** — 持久化知识图谱（论文、实验、想法的关联网络）
- [ ] **更多 IDE 适配** — Cursor、Trae、Windsurf 适配文档
- [ ] **论文写作增强** — LaTeX 生成、DBLP 实时引用、venue 格式模板
- [ ] **Rebuttal Skill** — 审稿意见解析 + 安全回复生成
- [ ] **Meta-Optimize** — 自我优化：分析 Skill 使用模式，自动改进提示词

---

## 🔧 Updates & Bug Fixes / 更新进展与缺陷修复

### v0.3.0 (2026-06-02)

**Claim Chain v2 + 迭代版本管理：**

| 功能 / 修复 | 说明 |
|------------|------|
| **CC v2 SQLite** | cc.db 替代 atoms.jsonl/relations.jsonl 作为唯一真相。JSONL 临时中转 → 同步后删除 |
| **Temporal Metadata** | 每个 CC atom 携带 iter/phase/created_at_iso 元数据，`add_atom()` 支持 iteration/phase 参数 |
| **跨迭代知识注入** | `_build_cc_full_context()`: W2 persona 自动读取全量 CC，按迭代/阶段/状态分组展示 |
| **迭代版本管理** | jump_to_plan 完整快照 (git-like) → undo 恢复。满意→iter_complete，不满意→iter_rollback |
| **迭代递增修复** | iteration 始终 0→1 单次递增（修复 satisfied handler 双重递增 bug） |
| **实验记录器 CC 同步** | `_sync_experiment_to_cc()`: experiment atom 写入 cc.db + validates edges + temporal metadata |
| **BGE-M3 嵌入** | `bge_socket_server.py` Unix socket 常驻服务，nodes.embedding 列存储 1024-dim 向量 |
| **Dashboard 增强** | 撤销回到Plan 按钮 + 栈深度显示，迭代目录管理，decision_ledger 审计 |
| **重复 atom 防护** | 修复 experiment_recorder 在 W2 阶段被重复触发导致重复 atom 的问题 |

### v0.2.1 (2026-05-25)

**Pipeline 核心修复：**

| 修复 | 说明 |
|------|------|
| **Tavily 搜索 + Direct LLM 两步法** | `invoke_agent()` 先用 Tavily API 搜索论文，再将结果注入 prompt，最后用 direct LLM 生成可靠 JSON。解决了 agent 框架工具调用不稳定导致空输出和搜索不可见的问题 |
| **Session 恢复机制** | Dashboard 重启后 `invoke_agent()` 自动调用 `_load_sessions_from_disk()` 恢复 session，修复 "Session not found" 错误 |
| **产物验证放宽** | `research_notes.md` 缺失时自动创建空文件，不再阻断 W3→W3.5 的 phase 转换。改为 warning 而非 error |
| **Watchdog 超时告警禁用** | 所有 step/phase/stall/nag 超时阈值设为 999999s，不再弹出 `"Step 'elo_tournament' 已运行 301s"` 等干扰告警 |

**Dashboard 增强：**

| 功能 | 说明 |
|------|------|
| **实时 Persona 调用事件** | SSE 流推送 `persona_started`/`persona_done`/`persona_error` 事件，Agent Log 实时显示 "agent searching web..." 和 "agent done: title" |
| **Pipeline 产物展示** | 主 Dashboard 的 `renderPipelineDetail()` 从 REST API 拉取 proposals、ELO 排名、verification verdict，自动展示在 Agent Log 中 |
| **Phase 时间线修复** | `data-phase` 属性对齐 `PHASE_ORDER` 索引（W2.1=0, W2.2=1, W2.3=2），主 Dashboard Pipeline 时间线现在正确显示当前 phase |
| **addLog null 安全** | `addLog()` 增加 `#log` 元素 null 检查，防止 JS 崩溃导致页面空白 |
| **pollPipeline 错误日志** | `catch(e){}` 改为 `addLogEntry('PIPELINE', 'error', ...)` ，管道轮询失败现在可见 |

**ELO 验证与重跑：**

| 修复 | 说明 |
|------|------|
| **Phase 维度匹配** | `run_tournament()` 传入 `phase` 参数，ELO 维度与 plan 一致（W2.1=[clarity,reasonableness,product_satisfaction], W2.2=[reasonableness,product_satisfaction], W2.3=[detail,...]） |
| **Regeneration 上限** | `verify_products` 增加 `MAX_REGEN=2` 限制，超过后 force-pass，杜绝无限重跑循环 |
| **产物清理增强** | `invoke_personas` 的 JSON 提取修复：贪婪匹配嵌套 JSON、大括号计数、trailing comma 修复、短响应检测 |

**前端增强：**

| 修复 | 说明 |
|------|------|
| **Agent 调用过程展示** | `handleEvent` 新增 `pipeline_step`/`persona_started`/`persona_done`/`persona_error`/`elo_completed` 事件处理 |
| **CSS 深色主题优化** | 新增 `pipeline_det` 系列 Log Tag 样式（proposal/elo/verify），Agent Log 更易读 |
| **Phase 标签中文化** | Pipeline 时间线显示中文标签（问题分析/方案方向/检索策略），拆分 W2 为三个独立 phase 节点 |

### v0.2.0 (2026-05-02)

- 🧬 Four-Layer Architecture: Claim Chain + MAP-Elites Grid + evo-evolve PES Loop + vis.js Dashboard
- 15 Skills 全流程覆盖
- Agent Manager 8 个 MCP tools

### v0.1.0 (2026-04-09)

- 首次发布：14 Skills + 多 Agent MCP + 3 跨模型审稿桥接

---

## 🙏 Acknowledgements / 致谢

**核心灵感：**
- 🧬 [EvoScientist](https://github.com/EvoScientist/EvoScientist) — 多 Agent 科研自动化的原始实现（LangGraph + DeepAgents）
- 🌙 [ARIS](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) — Claude Code Skill 架构范式和跨模型协作理念

**基础设施：**
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (Anthropic) — AI 编程助手
- [LangGraph](https://github.com/langchain-ai/langgraph) (LangChain) — 多 Agent 编排框架
- [DeepAgents](https://github.com/deepagents/deepagents) — Agent 创建工具
- [MCP](https://modelcontextprotocol.io/) — Model Context Protocol

**算力支持：**
- [Xiaomi MiMo Orbit](https://100t.xiaomimimo.com/) — 感谢小米 MiMo 百万亿 Token 创造者激励计划提供的算力支持

---

## 📖 Citation

```bibtex
@software{evoscientist_claude_2026,
  title  = {EvoScientist-Claude: Multi-Agent Scientific Discovery for Claude Code},
  author = {EvoScientist Contributors},
  year   = {2026},
  url    = {https://github.com/ExuberantWitness/EvoScientist-claude},
  note   = {Based on EvoScientist and ARIS}
}
```

---

## License

Apache 2.0 — 同原版 EvoScientist。

---

<a name="english"></a>

## English Summary

**EvoScientist-Claude** rebuilds the [EvoScientist](https://github.com/EvoScientist/EvoScientist) multi-agent system for Claude Code. Two modes:

1. **Skills Mode** (zero-dependency): 20+ composable Markdown skills for the full research lifecycle
2. **Agent Manager Mode** (full multi-agent): MCP Server wrapping LangGraph with 6 specialized agents, unrestricted backend (conda/GPU), persistent memory

**New in v0.3.0:** Claim Chain v2 — SQLite-backed knowledge graph (cc.db) with 18 edge types, BGE-M3 semantic embeddings, and temporal metadata (iter/phase/timestamp). Iteration management with git-like snapshots, undo, and cross-iteration knowledge injection via W2 persona prompts.

Quick start: `cp -r skills/* ~/.claude/skills/ && /evo-pipeline "your proposal"`

See the Chinese sections above for full documentation.
