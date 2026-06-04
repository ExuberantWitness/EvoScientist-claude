# Flux-Insight 🧬🔬

*让 Claude Code 变成你的 AI 科研团队 — 6 个专业 Agent 自动协作，从提案到论文全流程自动化*

[English](#english) | 中文

> 📰 **v0.3.0** (2026-06-02) — NEW: Claim Chain v2 SQLite 知识图谱 + Dashboard 迭代版本管理 (undo/rollback) + 跨迭代知识注入. 详见 [Updates & Bug Fixes](#-updates--bug-fixes--更新进展与缺陷修复).
>
> 📰 **v0.2.1** (2026-05-25) — Tavily Search + Direct LLM Pipeline, Dashboard Live Persona Events, Session Recovery.
>
> 📰 **v0.2.0** (2026-05-02) — Four-Layer Architecture: Claim Chain + Session + Plugin + Skill. 21 Skills.
>
> 📰 **v0.1.0** (2026-04-09) — 首次发布：14 Skills + Agent Manager + 跨模型审稿集成

---

> 🧬 **不只是提示词，而是一个完整的 AI 科研团队。** Flux-Insight 是一个 Claude Code 原生的科研自动化系统，通过 Claim Chain v2 知识图谱 + PES Controller 自动流转引擎 + 21 个可组合 Skills，覆盖从提案到论文的全研究生命周期。

[![License](https://img.shields.io/badge/License-Apache_2.0-blue?style=flat)](LICENSE) · [![Skills](https://img.shields.io/badge/Skills-21-green?style=flat)]() · [![CC](https://img.shields.io/badge/Claim_Chain-SQLite-8A2BE2?style=flat)]() · [![Python](https://img.shields.io/badge/Python-3.11+-blue?style=flat)]()

---

## 🔬 核心亮点

### 🧠 Claim Chain v2 — 一切的基础

Flux-Insight 的核心是一个 **SQLite 知识图谱 (cc.db)**，贯穿整个研究工作流。每一个 idea、baseline、实验结果、失败记录都以 atom 形式存入 Claim Chain，通过 20 种关系类型连接成图。BGE-M3 语义嵌入为每个 atom 提供 1024 维向量，支持语义搜索和 RND 新颖性检测。所有 atom 携带 iter/phase/timestamp 元数据，实现跨迭代知识注入。

这不是一个"附加功能"——PES Controller、4-Persona 创意生成、Dashboard 可视化、实验记录器，全部建立在 Claim Chain 之上。

### 🏗️ 四层架构

```
┌──────────────────────────────────────────────┐
│  Skills 层    21 个可组合 Skills，纯 Markdown   │
│               /evo-pipeline, /evo-ideation... │
├──────────────────────────────────────────────┤
│  Feature 层   PES Controller · 4-Persona      │
│               ELO 锦标赛 · RND 新颖性评估      │
│               Dashboard · Plugin 系统          │
├──────────────────────────────────────────────┤
│  Session 层   生命周期管理 · 状态持久化         │
│               SSE 事件流 · LLM 调用封装         │
├──────────────────────────────────────────────┤
│  Claim Chain  知识图谱 · BGE-M3 嵌入           │
│  (基础层)     20 种关系 · 语义搜索              │
│               CodeGraph 代码结构提取            │
└──────────────────────────────────────────────┘
```

> 💡 **设计原则**: 一切数据写入 Claim Chain。Skills 是用户入口，Feature 实现业务逻辑，Session 管理状态，Claim Chain 是唯一真相源。

### 🎛️ Dashboard — Web 管线控制台

`localhost:8420` 可视化管线控制，支持阶段流转（满意/不满意/回到Plan/撤销/终止）、迭代版本管理（git-like 快照 + undo 回退）、vis.js 力导向知识图谱、实时 Persona 事件流 (SSE)。

### 🔬 RND 新颖性评估

两阶段评估流程：
- **Stage 1**: BGE-M3 粗筛 — 计算 proposal 与已有知识图谱的语义距离，RND score 量化新颖性
- **Stage 2**: LLM Rubric 精评 — 5 维度（problem/method/experiment/theory/essential_difference）× 动态权重，1-10 打分

### 🤖 4-Persona 创意生成 + ELO 锦标赛

novel/conservative × academic/engineering 四种人格独立提案，通过多维度 ELO 锦标赛排名选出最优方案。打破单模型自我审查盲区。

### 📐 Baseline 分析 + CodeGraph 拆解

GitHub 搜索确认 baseline 算法后，通过 CodeGraph 提取代码结构（函数签名、类层次、调用关系）并自动写入 Claim Chain。Baseline 的代码骨架作为 RND 新颖性评估的 anchor point，proposal 与 baseline 在结构和语义两个层面进行对比。

### 🧲 BGE-M3 语义嵌入

Unix socket 常驻服务，1024 维向量。支持 Claim Chain 语义搜索、RND 粗筛、atom 去重。每个 atom 写入时自动计算嵌入向量。

---

## ✨ 其他特性

- 🔄 **21 个可组合 Skills** — 单独使用或链式调用，覆盖研究全生命周期，纯 Markdown 零依赖
- 🗺️ **MAP-Elites 进化网格** — 3×3 行为空间归档，exploit/explore 采样，FitnessTracker 停滞检测
- 🔄 **迭代版本管理** — git-like 快照 + undo 回退，decision ledger 审计追踪，跨迭代知识注入
- 🧠 **持久化记忆** — 自动提取用户画像、研究偏好、实验结论，跨会话累积
- 📊 **科学严谨** — 强制报告效应量、置信区间、负面结果，禁止编造数据
- 💾 **断点恢复** — JSON 状态文件支持会话恢复 + decision ledger 审计追踪
- 🔀 **跨模型审稿集成** — 通过 MCP 协议桥接外部 GPT/Gemini/DeepSeek 审稿服务器（需单独部署，见 [MCP Setup Guide](docs/MCP_SETUP.md)）

---

## 🎯 两种使用方式

### 方式 A：Skills 模式（轻量，零依赖）

直接在 Claude Code 中使用 21 个可组合的研究 Skills，无需 Python 环境。每个 Skill 是一个纯 Markdown 提示词文件。

```bash
# 安装 Skills（复制到 Claude Code 技能目录）
git clone https://github.com/ExuberantWitness/Flux-Insight.git
cp -r Flux-Insight/skills/* ~/.claude/skills/

# 在 Claude Code 中使用
/evo-pipeline "世界模型在人形机器人运动控制中的应用"
```

> 💡 Skills 模式下，Claude Code 本身作为执行者，按照 SKILL.md 中定义的工作流依次完成各阶段。适合快速使用，不需要额外环境。

### 方式 B：Dashboard 模式（Web 管线控制台）

启动 Dashboard 获得可视化管线控制、Claim Chain 知识图谱、迭代版本管理和实时 Persona 事件流。

```bash
cd Flux-Insight
pip install -r requirements.txt  # starlette, sse-starlette, numpy, FlagEmbedding
python run_dashboard.py &
# Dashboard: http://localhost:8420
```

Dashboard 提供：
- **管线可视化** — 阶段流转控制（满意/不满意/回到Plan/撤销/终止）
- **迭代版本管理** — git-like 快照 + undo 回退，decision ledger 审计追踪
- **Claim Chain 知识图谱** — vis.js 力导向图，atoms + edges + 语义搜索
- **实时 Persona 事件流** — SSE 推送 persona 调用过程和结果
- **ELO 锦标赛排名** — 创意质量实时排名展示

> 🔥 **核心区别**：Skills 模式是 "在 Claude Code 中直接使用"，适合快速实验；Dashboard 模式适合长时间运行的研究任务，提供完整的迭代管理和知识图谱可视化。

---

## 🧰 全部 Skills

### 🚀 编排器
- [`/evo-pipeline`](skills/evo-pipeline/SKILL.md) — 全流程编排：intake → plan → research → ideation → code → run → analyze → iterate → write → review
- [`/evo-evolve`](skills/evo-evolve/SKILL.md) — PES 质量多样性进化：Plan→Execute→Summary 循环 + Claim Chain 知识图谱 + MAP-Elites 网格归档 + Island GA 迁移

### 📋 需求与规划 (W1-W2)
- [`/evo-intake`](skills/evo-intake/SKILL.md) — 解析研究提案，提取目标、数据集、约束、成功指标
- [`/evo-planner`](skills/evo-planner/SKILL.md) — 制定实验计划，定义阶段、成功信号、依赖关系。PLAN / REFLECTION 双模式

### 🔍 调研与创意 (W3)
- [`/evo-research`](skills/evo-research/SKILL.md) — 文献与方法调研，WebSearch + WebFetch
- [`/evo-ideation`](skills/evo-ideation/SKILL.md) — 创意生成 + Elo 锦标赛排名 + 可行性验证
- [`/evo-refine`](skills/evo-refine/SKILL.md) — 迭代精炼方法（外部评审反馈）

### 💻 实现与执行 (W4)
- [`/evo-code-agent-pre`](skills/evo-code-agent-pre/SKILL.md) — 代码前：从 plan 提取 CC atom，理解知识图谱上下文
- [`/evo-code`](skills/evo-code/SKILL.md) — 实验代码实现，Lite / Effort 双模式，GPU preflight
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
- [`/evo-review`](skills/evo-review/SKILL.md) — 跨模型审稿循环，medium/hard 难度，最多 N 轮迭代

### 🧠 记忆管理
- [`/evo-memory`](skills/evo-memory/SKILL.md) — 持久化记忆：init / update / query / stats
- [`/research-wiki`](skills/research-wiki/SKILL.md) — 持久化知识库（论文/想法/声明关联网络）

---

## 🔄 Pipeline Flow / 工作流

PES Controller 自动流转的 7 个阶段，支持 W6→W2 迭代循环：

```
                         ┌──────────────────────────────┐
                         │        Dashboard              │
                         │   (Web 管线控制台 :8420)       │
                         │   满意-下一步 / 不满意-重做     │
                         │   回到Plan / 撤销 / 终止       │
                         └──────────┬───────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────┐
        ▼                           ▼                       ▼
┌───────────────┐          ┌───────────────┐       ┌───────────────┐
│ W2: 问题分析   │ ──────▶  │ W3: 方案方向   │ ────▶ │ W4: 具体方案   │
│ 4-Persona     │          │ 4-Persona     │       │ 4-Persona     │
│ Claim Chain   │          │ ELO 锦标赛    │       │ 方案精炼      │
│ 知识注入      │          │ 可行性验证    │       │ 产物规格验证  │
└───────────────┘          └───────────────┘       └───────┬───────┘
                                                            │
                                                            ▼
                              ┌─────────────────────────────────────┐
                              │         W5: 代码实现                │
                              │  experiment_recorder → CC database │
                              │  code-agent: pre → code → run      │
                              └─────────────────┬───────────────────┘
                                                │
                                                ▼
┌───────────────┐          ┌───────────────┐
│ W8: 审阅      │ ◀─────── │ W7: 论文写作   │         ┌───────────────┐
│ 跨模型评审    │          │ 7节报告        │         │ W6: 结果分析   │
└───────────────┘          └───────────────┘         │ 统计分析      │
      │                                               │ CC 写入       │
      ▼                                               │ Island 分配   │
┌───────────────┐                                     │ Grid 归档     │
│  终了 / 满意   │                                     └───────┬───────┘
└───────────────┘                                             │
                                                     未达标 / 继续迭代
                                                            │
                       ┌────────────────────────────────────┘
                       ▼
                ┌──────────────┐
                │ 下一轮 W2     │
                │ iter += 1    │
                │ CC 全量上下文 │
                │ 自动注入      │
                └──────────────┘
```

> 🆕 **v0.3.0 迭代管理**: W6→满意→W7/W8 (CC 标记 iter_complete，decision ledger 审计) | 不满意→回到W2 重新开始下一轮 (git-like 快照 + undo)。下一轮 W2 自动注入全量 CC 知识图谱 (`_build_cc_full_context`) 作为 4-Persona 上下文。

---

## 🗣️ 4-Persona 创意生成 + ELO 锦标赛

PES Controller 调用 4 种 Persona 从不同角度生成研究提案，再通过 ELO 锦标赛排名选出最优方案。

**Persona 维度**：

| Persona | 视角 | 特点 |
|----------|------|------|
| **novel** | 激进创新 | 提出大胆的、突破性的研究方向 |
| **academic** | 学术严谨 | 强调理论基础、文献支撑和统计严密性 |
| **conservative** | 稳健实用 | 优先可靠性、简洁性和增量改进 |
| **engineering** | 工程导向 | 关注实现可行性、计算效率和可扩展性 |

> 💡 与单模型自我审查不同，多 Persona 生成打破了思维盲区 — 不同视角的提案互补甚至矛盾，ELO 锦标赛综合评估后得出更全面的结论。

---

## 🔀 跨模型审稿集成

跨模型审稿服务器来自 [ARIS](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) 项目，需单独克隆部署：

```bash
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git

# GPT/DeepSeek/MiniMax/GLM/Kimi — 通用 OpenAI 兼容 API
pip install mcp httpx
claude mcp add llm-review \
  -e LLM_API_KEY=sk-xxx \
  -e LLM_BASE_URL=https://api.deepseek.com/v1 \
  -e LLM_MODEL=deepseek-chat \
  -- python3 /path/to/ARIS/mcp-servers/llm-review/server.py

# Google Gemini
claude mcp add gemini-review \
  -e GEMINI_API_KEY=xxx \
  -- python3 /path/to/ARIS/mcp-servers/gemini-review/server.py
```

或者直接使用 Claude Code 内置的 MCP 聊天工具 (`mcp__llm-chat__chat`) 进行单模型评审。

> 📚 详细配置见 [MCP Setup Guide](docs/MCP_SETUP.md)

---

## ⚙️ 安装与配置

### 前置条件

**Skills 模式（零依赖）：**
- [x] Claude Code 已安装

**Dashboard 模式（Web 控制台）：**
- [x] Python 3.11+
- [x] pip install -r requirements.txt

### Skills 模式安装

```bash
# 1. 克隆项目
git clone https://github.com/ExuberantWitness/Flux-Insight.git

# 2. 安装 Skills
cp -r Flux-Insight/skills/* ~/.claude/skills/

# 3. 使用
# 在 Claude Code 中：
/evo-pipeline "你的研究提案"
```

### Dashboard 模式安装

```bash
cd Flux-Insight
pip install -r requirements.txt  # starlette, sse-starlette, numpy, FlagEmbedding
python run_dashboard.py &
# Dashboard: http://localhost:8420
```

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

## 📁 项目结构

```
Flux-Insight/
├── README.md
├── CLAUDE.md                          # Claude Code 项目配置
├── LICENSE                            # Apache 2.0
├── .env.example
├── .gitignore
├── run_dashboard.py                   # Dashboard 入口 (localhost:8420)
│
├── skills/                            # 21 个 Claude Code Skills (纯 Markdown)
│   ├── evo-pipeline/SKILL.md          # 全流程编排器 (一键启动)
│   ├── evo-evolve/SKILL.md            # PES 质量多样性进化循环
│   ├── evo-boot/SKILL.md              # Session 初始化 bootstrap
│   ├── evo-intake/SKILL.md            # 需求解析 (W1)
│   ├── evo-planner/SKILL.md           # 实验规划 (W2) — PLAN/REFLECTION 双模式
│   ├── evo-research/SKILL.md          # 文献调研 (W3)
│   ├── evo-ideation/SKILL.md          # 创意发现 (W3.5) — Elo 锦标赛排名
│   ├── evo-refine/SKILL.md            # 方法精炼 (W3.6)
│   ├── evo-code/SKILL.md              # 代码实现 (W4)
│   ├── evo-code-agent-pre/SKILL.md    # 代码前置 — CC 上下文读取
│   ├── evo-code-agent-check/SKILL.md  # 代码检查 — CC 状态更新
│   ├── evo-code-agent-post/SKILL.md   # 代码后置 — CC 关联建立
│   ├── evo-debug/SKILL.md             # 运行时调试 (W4.5)
│   ├── evo-run/SKILL.md               # 实验执行 (W4.7)
│   ├── evo-analyze/SKILL.md           # 数据分析 (W5)
│   ├── evo-claim/SKILL.md             # 结果→声明判断门 (W5.6)
│   ├── evo-iterate/SKILL.md           # 迭代评估 (W5.5)
│   ├── evo-write/SKILL.md             # 论文写作 (W6)
│   ├── evo-review/SKILL.md            # 跨模型审稿 (W7)
│   ├── evo-memory/SKILL.md            # 持久化记忆管理
│   └── research-wiki/SKILL.md         # 持久化知识库
│
├── claim_chain/                       # Claim Chain v2 — 基础层 (12 文件)
│   ├── chain.py                       # ClaimChainV2 — CRUD + BGE-M3 embedding + session context
│   ├── query.py                       # CCQueryInterface — 语义搜索 + 图遍历
│   ├── grounding.py                   # CCGrounding — atom/relation 验证 + 门禁
│   ├── codegraph.py                   # CodeGraph 集成 — 代码结构提取 → CC
│   ├── cell_grid.py                   # MAP-Elites 行为网格
│   ├── island_manager.py              # Island 管理 — 检测/分配/迁移
│   ├── negative_archive.py            # 负样本归档 — 失败记录防重复
│   ├── decomposer.py                  # 问题分解
│   └── api.py                         # HTTP API 封装
│
├── pes_controller/                    # Feature 层 — PES 自动流转引擎 (58 文件)
│   ├── controller.py                  # 主控制器 — 4-Persona, ELO, CC 上下文注入
│   ├── bootstrap.py                   # Session 初始化 + 资源创建
│   ├── protocol.py                    # 原子状态读写 + 产物验证
│   ├── elo/                           # ELO 锦标赛引擎 + RND 新颖性评估
│   └── rubric/                        # Rubric 多维评估 + 调度器 + 新颖性检测
│
├── session/                           # Session 层 — 生命周期管理 (26 文件)
│   ├── session.py                     # Session 核心
│   ├── manager.py                     # Session 管理器
│   ├── persistence.py                 # 持久化 (.evo_sessions/)
│   ├── registry.py                    # 注册表 + 恢复
│   ├── stream/                        # SSE 事件流 (emitter, events, tracker)
│   ├── llm/                           # LLM 调用封装 (models, patches)
│   └── config/settings.py             # 配置系统
│
├── sdk/                               # 运行时 SDK (31 文件)
│   ├── dashboard/                     # Starlette Web Dashboard — 管线 + 迭代控制 + SSE 事件
│   ├── memory/evo_auto_evolve.py      # PES 自动进化循环 (Plan→Execute→Summary)
│   ├── search/web_search.py           # Tavily + Web 搜索
│   ├── status/fitness.py              # FitnessTracker 停滞检测
│   └── server.py                      # HTTP server 启动入口
│
├── plugins/                           # 插件系统 (22 文件)
│   ├── writing/markdown_parser.py     # Vault → CC 同步 + self-wiring + IndexSyncer
│   ├── ideation/                      # 创意插件 — plan_templates, domain_presets
│   ├── experimentation/               # 实验插件 — agent_task, trainer_contract, recorder
│   ├── grounding/                     # 知识锚定
│   ├── reporting/                     # 报告插件 — event_log, vault_manager
│   └── validation/                    # 验证插件 — verify_atom, verify_plan, cleanup
│
├── application/                       # 应用层 (18 文件)
│   ├── orchestrator.py                # ResearchPipeline — 全流程编排
│   ├── personas/                      # 4-Persona 提示词系统
│   └── evolution/                     # 进化引擎 — pipeline, scoring, strategy, tree_search
│
├── tools/                             # 遗留工具集 (39 文件) — 逐步迁移到 claim_chain/plugins/sdk
│   ├── experiment_recorder.py         # 实验记录 → CC + events + Markdown
│   ├── bge_socket_server.py           # BGE-M3 Unix socket 嵌入服务 (1024-dim)
│   └── cc_query_tool.py               # CC CLI: query/upsert/link
│
├── agent-manager/                     # Evo Agent Manager (入口目录)
├── agent-manager_legacy/              # (Legacy) 旧版多 Agent MCP 系统 — 不再维护
├── templates/                         # 研究工件模板 (6 个 Markdown)
├── docs/                              # 文档
├── old/                               # 旧版代码 — 保留供参考
└── tests/                             # 测试
```

---

## 📊 Skills 模式 vs Dashboard 模式对比

| 维度 | Skills 模式 | Dashboard 模式 |
|------|-----------|-------------------|
| **依赖** | 零（纯 Markdown） | Python 3.11+ + starlette + numpy |
| **管线可视化** | 无 | Web 控制台 (localhost:8420) |
| **迭代管理** | 手动 | git-like 快照 + undo + decision ledger |
| **Claim Chain 可视化** | 无（仅 CLI 查询） | vis.js 力导向知识图谱 + 语义搜索 |
| **实时 Persona 事件** | 无 | SSE 流推送 |
| **安装时间** | <1 分钟 | ~5 分钟 |
| **适用场景** | 快速实验、单发任务 | 长周期研究、需要迭代追踪 |

---

## 📋 Roadmap

### Done / 已完成

- [x] **21 核心 Skills** — 覆盖研究全生命周期 + PES 质量多样性进化 + code-agent 四阶段
- [x] **Claim Chain v2** — SQLite 知识图谱，20 种关系类型，BGE-M3 语义嵌入，temporal metadata
- [x] **四层架构** — Claim Chain (基础层) → Session (状态层) → Feature (功能层) → Skill (接口层)
- [x] **Dashboard 迭代控制** — 阶段流转 + 撤销回到Plan + 迭代目录管理 + decision ledger 审计
- [x] **RND 新颖性评估** — BGE-M3 粗筛 + LLM Rubric 5 维度精评 + 动态权重
- [x] **4-Persona + ELO 锦标赛** — novel/conservative × academic/engineering，多维度排名
- [x] **CodeGraph 代码结构提取** — 自动索引 baseline 代码 → CC atoms，函数/类/调用关系
- [x] **MAP-Elites 进化网格** — 3×3 行为归档，exploit/explore 采样，FitnessTracker 停滞检测
- [x] **跨模型审稿集成** — 桥接外部 MCP 审稿服务器 (GPT/Gemini/DeepSeek)

### Planned / 计划中

- [ ] **Rubric 动态维度扩展** — LLM-as-Judge 自动提议新评估维度
- [ ] **Island GA 自动合并** — LLM 检测 Island 间关系，自动提议合并
- [ ] **并行 Agent 执行** — DAG 并行（planner + researcher 同时工作）
- [ ] **论文写作增强** — LaTeX 生成、DBLP 实时引用
- [ ] **Rebuttal Skill** — 审稿意见解析 + 安全回复生成
- [ ] **Meta-Optimize** — 自我优化：分析 Skill 使用模式，自动改进提示词

---

## 🔧 Updates & Bug Fixes / 更新进展与缺陷修复

### v0.3.0 (2026-06-02)

| 功能 / 修复 | 说明 |
|------------|------|
| **CC v2 SQLite** | cc.db 替代 atoms.jsonl/relations.jsonl 作为唯一真相源。JSONL 临时中转 → 同步后删除 |
| **Temporal Metadata** | 每个 CC atom 携带 iter/phase/created_at_iso 元数据，`add_atom()` 支持 iteration/phase 参数 |
| **跨迭代知识注入** | `_build_cc_full_context()`: W2 persona 自动读取全量 CC，按迭代/阶段/状态分组展示 |
| **迭代版本管理** | jump_to_plan 完整快照 (git-like) → undo 恢复。满意→iter_complete，不满意→iter_rollback |
| **BGE-M3 嵌入** | `bge_socket_server.py` Unix socket 常驻服务，nodes.embedding 列存储 1024-dim 向量 |
| **Dashboard 增强** | 撤销回到Plan 按钮 + 栈深度显示，迭代目录管理，decision_ledger 审计 |
| **重复 atom 防护** | 修复 experiment_recorder 在 W2 阶段被重复触发导致重复 atom 的问题 |

### v0.2.1 (2026-05-25)

| 修复 | 说明 |
|------|------|
| **Tavily 搜索 + Direct LLM 两步法** | `invoke_agent()` 先用 Tavily API 搜索论文，再将结果注入 prompt，最后用 direct LLM 生成可靠 JSON |
| **Session 恢复机制** | Dashboard 重启后自动调用 `_load_sessions_from_disk()` 恢复 session |
| **产物验证放宽** | `research_notes.md` 缺失时自动创建空文件，不再阻断 W3→W3.5 的 phase 转换 |

**Dashboard 增强：**

| 功能 | 说明 |
|------|------|
| **实时 Persona 调用事件** | SSE 流推送 `persona_started`/`persona_done`/`persona_error` 事件 |
| **Pipeline 产物展示** | 主 Dashboard 从 REST API 拉取 proposals、ELO 排名、verification verdict |
| **Phase 时间线修复** | `data-phase` 属性对齐 `PHASE_ORDER` 索引 |

**ELO 验证与重跑：**

| 修复 | 说明 |
|------|------|
| **Phase 维度匹配** | `run_tournament()` 传入 `phase` 参数，ELO 维度与 plan 一致 |
| **Regeneration 上限** | `verify_products` 增加 `MAX_REGEN=2` 限制，杜绝无限重跑 |

### v0.2.0 (2026-05-02)

- 🧬 四层架构：Claim Chain + Session + Plugin + Skill
- 21 Skills 全流程覆盖

### v0.1.0 (2026-04-09)

- 首次发布：14 Skills + 多 Agent MCP + 跨模型审稿集成

---

## 🙏 Acknowledgements / 致谢

**基础设施：**
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (Anthropic) — AI 编程助手
- [MCP](https://modelcontextprotocol.io/) — Model Context Protocol

**参考项目：**
- [EvoScientist](https://github.com/EvoScientist/EvoScientist) — 多 Agent 科研自动化
- [ARIS](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) — Claude Code Skill 架构范式

**算力支持：**
- [Xiaomi MiMo Orbit](https://100t.xiaomimimo.com/) — 感谢小米 MiMo 百万亿 Token 创造者激励计划提供的算力支持

---

## 📖 Citation

```bibtex
@software{flux_insight_2026,
  title  = {Flux-Insight: Multi-Agent Scientific Discovery for Claude Code},
  author = {Flux-Insight Contributors},
  year   = {2026},
  url    = {https://github.com/ExuberantWitness/Flux-Insight}
}
```

---

## License

Apache 2.0

---

<a name="english"></a>

## English Summary

**Flux-Insight** is a Claude Code-native scientific discovery system. Two modes:

1. **Skills Mode** (zero-dependency): 21 composable Markdown skills for the full research lifecycle
2. **Dashboard Mode** (Web console): localhost:8420 with phase transitions, iteration management (undo/rollback), Claim Chain v2 visualization, and decision ledger audit

**Core architecture: Claim Chain → Session → Feature → Skill.** Claim Chain v2 is the foundation — a SQLite-backed knowledge graph (cc.db) with 20 edge types, BGE-M3 semantic embeddings, and temporal metadata on every atom. Everything else (PES Controller, 4-Persona ideation, ELO tournament, RND novelty evaluation, Dashboard) builds on top of it.

**Key highlights:**
- **Claim Chain v2** — SQLite knowledge graph as single source of truth, 20 edge types, BGE-M3 embeddings
- **RND Novelty Evaluation** — BGE-M3 coarse filter + 5-dimension LLM rubric with dynamic weights
- **4-Persona Ideation + ELO Tournament** — novel/conservative × academic/engineering, multi-dimension ranking
- **Baseline Analysis + CodeGraph** — GitHub search → CodeGraph structure extraction → CC decomposition
- **Dashboard** — Web console with vis.js graph visualization, iteration snapshots, SSE event streaming

Quick start: `cp -r skills/* ~/.claude/skills/ && /evo-pipeline "your proposal"`

See the Chinese sections above for full documentation.
