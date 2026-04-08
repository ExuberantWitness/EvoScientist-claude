# EvoScientist-Claude 🧬🔬

*让 Claude Code 变成你的 AI 科研团队 — 6 个专业 Agent 自动协作，从提案到论文全流程自动化*

[English](#english) | 中文

> 📰 **v0.1.0** (2026-04-09) — 首次发布：14 个 Skills + 多 Agent MCP 管理系统 + 3 个跨模型审稿桥接

---

> 🧬 **不只是提示词，而是一个完整的 AI 科研团队。** EvoScientist-Claude 将 [EvoScientist](https://github.com/EvoScientist/EvoScientist) 的 6 个专业 AI Agent（规划师、调研员、程序员、调试员、分析师、写作者）重构为 Claude Code 原生 Skills + MCP 多 Agent 管理系统。两种使用方式：轻量 Skills 模式（零依赖），或完整多 Agent 讨论模式（通过 MCP）。
>
> 🪶 **极简架构** — Skills 模式零依赖，纯 Markdown 文件，复制即用。Agent Manager 模式通过 MCP 协议桥接 LangGraph 多 Agent 系统，支持 conda 环境和 GPU 访问，无沙箱限制。
>
> 💡 *灵感来自 [ARIS](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) 的 Skill 架构 + [EvoScientist](https://github.com/EvoScientist/EvoScientist) 的多 Agent 编排*

[![License](https://img.shields.io/badge/License-Apache_2.0-blue?style=flat)](LICENSE) · [![Skills](https://img.shields.io/badge/Skills-14-green?style=flat)]() · [![MCP Tools](https://img.shields.io/badge/MCP_Tools-8-orange?style=flat)]() · [![Python](https://img.shields.io/badge/Python-3.11+-blue?style=flat)]()

---

## 🎯 两种使用方式

### 方式 A：Skills 模式（轻量，零依赖）

直接在 Claude Code 中使用 14 个可组合的研究 Skills，无需 Python 环境。每个 Skill 是一个纯 Markdown 提示词文件。

```bash
# 安装 Skills（复制到 Claude Code 技能目录）
git clone https://github.com/EvoScientist/EvoScientist-claude.git
cp -r EvoScientist-claude/skills/* ~/.claude/skills/

# 在 Claude Code 中使用
/evo-pipeline "世界模型在人形机器人运动控制中的应用"
```

> 💡 Skills 模式下，Claude Code 本身作为执行者，按照 SKILL.md 中定义的工作流依次完成各阶段。适合快速使用，不需要额外环境。

### 方式 B：Agent Manager 模式（完整多 Agent 讨论）

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

---

## ✨ Features / 功能特色

- 🧬 **6 个专业 Agent** — planner（规划）、researcher（调研）、coder（编码）、debugger（调试）、analyst（分析）、writer（写作），各司其职
- 🔄 **14 个可组合 Skills** — 单独使用或链式调用，覆盖研究全生命周期
- 🗣️ **多 Agent 讨论** — 多个 Agent 从各自专业角度分析同一问题，综合得出结论（Agent Manager 模式）
- 🔍 **跨模型审稿** — 通过 MCP 调用 GPT/Gemini/DeepSeek/MiniMax 作为独立评审，避免自我审查盲区
- 🧠 **持久化记忆** — 自动提取用户画像、研究偏好、实验结论，跨会话累积
- 🔓 **无沙箱限制** — Agent Manager 模式下完整支持 conda、GPU、系统路径（替换了原版的 `CustomSandboxBackend`）
- 📊 **科学严谨** — 强制报告效应量、置信区间、负面结果，禁止编造数据
- 💾 **断点恢复** — JSON 状态文件支持 24 小时内会话恢复
- 🌐 **多 LLM 支持** — Anthropic Claude、OpenAI GPT、DeepSeek、Gemini、MiniMax、GLM 等

---

## 🧰 All Skills / 全部技能

### 🚀 编排器
- [`/evo-pipeline`](skills/evo-pipeline/SKILL.md) — 全流程编排：intake → plan → research → ideation → code → run → analyze → iterate → write → review
- [`/evo-boot`](skills/evo-boot/SKILL.md) — Bootloader：一键安装 Agent Manager 系统

### 📋 需求与规划 (W1-W2)
- [`/evo-intake`](skills/evo-intake/SKILL.md) — 解析研究提案，提取目标、数据集、约束、成功指标
- [`/evo-planner`](skills/evo-planner/SKILL.md) — 制定实验计划，定义阶段、成功信号、依赖关系。支持 PLAN / REFLECTION 双模式

### 🔍 调研与创意 (W3)
- [`/evo-research`](skills/evo-research/SKILL.md) — 文献与方法调研，WebSearch + WebFetch，一次一个主题
- [`/evo-ideation`](skills/evo-ideation/SKILL.md) — 创意生成 + Elo 锦标赛排名 + 可行性验证

### 💻 实现与执行 (W4)
- [`/evo-code`](skills/evo-code/SKILL.md) — 实验代码实现，Lite / Effort 双模式，GPU preflight
- [`/evo-debug`](skills/evo-debug/SKILL.md) — 运行时故障诊断：Reproduce → Root Cause → Minimal Fix
- [`/evo-run`](skills/evo-run/SKILL.md) — 执行实验（本地 / SSH / 云 GPU），sanity check + 后台运行

### 📊 分析与迭代 (W5)
- [`/evo-analyze`](skills/evo-analyze/SKILL.md) — 统计分析 + 可视化，强制报告 CI/效应量/多重比较校正
- [`/evo-iterate`](skills/evo-iterate/SKILL.md) — 对比成功信号，决定迭代/转向/推进，自动提取经验教训

### 📝 写作与审稿 (W6-W7)
- [`/evo-write`](skills/evo-write/SKILL.md) — 论文级 7 节结构报告，禁止编造结果和引用
- [`/evo-review`](skills/evo-review/SKILL.md) — 跨模型 MCP 审稿循环，medium/hard 难度，最多 N 轮迭代

### 🧠 记忆管理
- [`/evo-memory`](skills/evo-memory/SKILL.md) — 持久化记忆：init / update / query / stats

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
git clone https://github.com/EvoScientist/EvoScientist-claude.git

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

---

## 📁 项目结构

```
EvoScientist-claude/
├── README.md                          # 本文档
├── CLAUDE.md                          # Claude Code 项目配置
├── LICENSE                            # Apache 2.0
├── .env.example                       # 环境变量模板
├── .gitignore
│
├── skills/                            # 14 个 Claude Code Skills
│   ├── evo-pipeline/SKILL.md         # 全流程编排器
│   ├── evo-boot/SKILL.md             # Bootloader
│   ├── evo-intake/SKILL.md           # 需求解析
│   ├── evo-planner/SKILL.md          # 实验规划
│   ├── evo-research/SKILL.md         # 文献调研
│   ├── evo-ideation/SKILL.md         # 创意发现
│   ├── evo-code/SKILL.md             # 代码实现
│   ├── evo-debug/SKILL.md            # 调试修复
│   ├── evo-run/SKILL.md              # 实验执行
│   ├── evo-analyze/SKILL.md          # 数据分析
│   ├── evo-iterate/SKILL.md          # 迭代评估
│   ├── evo-write/SKILL.md            # 报告撰写
│   ├── evo-review/SKILL.md           # 跨模型审稿
│   └── evo-memory/SKILL.md           # 记忆管理
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
| **自动 Memory** | 手动 `/evo-memory update` | middleware 自动提取 |
| **conda/GPU 支持** | 受 Claude Code 沙箱限制 | 完整支持（UnrestrictedBackend） |
| **安装时间** | <1 分钟 | ~15 分钟 |
| **适用场景** | 快速使用、简单任务 | 复杂研究、需要多视角分析 |

---

## 📋 Roadmap

### Done / 已完成

- [x] **14 个核心 Skills** — 覆盖研究全生命周期
- [x] **Agent Manager MCP Server** — 8 个 MCP tools 控制多 Agent 系统
- [x] **UnrestrictedBackend** — 替换沙箱，支持 conda/GPU
- [x] **跨模型审稿** — 3 个 MCP bridge（GPT/Gemini/飞书）
- [x] **多 Agent 讨论** — `evo_discuss` 多视角分析
- [x] **Bootloader Skill** — `/evo-boot` 一键安装

### Planned / 计划中

- [ ] **并行 Agent 执行** — LangGraph DAG 并行（planner + researcher 同时工作）
- [ ] **Research Wiki** — 持久化知识图谱（论文、实验、想法的关联网络）
- [ ] **更多 IDE 适配** — Cursor、Trae、Windsurf 适配文档
- [ ] **论文写作增强** — LaTeX 生成、DBLP 实时引用、venue 格式模板
- [ ] **Rebuttal Skill** — 审稿意见解析 + 安全回复生成
- [ ] **Meta-Optimize** — 自我优化：分析 Skill 使用模式，自动改进提示词

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

---

## 📖 Citation

```bibtex
@software{evoscientist_claude_2026,
  title  = {EvoScientist-Claude: Multi-Agent Scientific Discovery for Claude Code},
  author = {EvoScientist Contributors},
  year   = {2026},
  url    = {https://github.com/EvoScientist/EvoScientist-claude},
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

1. **Skills Mode** (zero-dependency): 14 composable Markdown skills for the full research lifecycle
2. **Agent Manager Mode** (full multi-agent): MCP Server wrapping LangGraph with 6 specialized agents, unrestricted backend (conda/GPU), persistent memory

Quick start: `cp -r skills/* ~/.claude/skills/ && /evo-pipeline "your proposal"`

See the Chinese sections above for full documentation.
