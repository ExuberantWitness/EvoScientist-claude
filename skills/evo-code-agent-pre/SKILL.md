---
name: evo-code-agent-pre
description: W4 Code 前置阶段 — 读取 PES Controller 生成的 implementation_plan.md，创建时间戳 session 文件夹，进入 PLAN MODE 设计实现路线图。
argument-hint: [implementation_plan_path]
allowed-tools: Bash(*), Read, Write, Edit, Glob, Grep, WebSearch, WebFetch, AskUserQuestion, TaskOutput, Agent, EnterPlanMode, ExitPlanMode
---

# W4 Code — 前置：读取计划，进入 PLAN MODE

Plan 文件路径: **$ARGUMENTS**

项目根目录: `/home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/EvoScientist-claude`
工作空间目录: `/home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH`
PIPELINE_STATE: `/home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/PIPELINE_STATE.json`

## 步骤 1: 读取 Plan 文件

读取 `$ARGUMENTS` 中的实现计划。如果路径不存在，查找 `artifacts/implementation_plan.md`。

## 步骤 2: 创建 Session 文件夹

以当前时间戳在工作空间下创建 session 文件夹：

```
mkdir -p /home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/artifacts/code_session_$(date +%Y%m%d_%H%M%S)
```

记录 SESSION_DIR 路径，后续中间产物、交付物均存放在此目录下。

## 步骤 3: 提取 Plan 关键信息

从 Plan 中提取并打印：
- 研究目标 (一句话)
- 需要实现的算法/方法列表
- 需要的实验脚本列表
- 输入/输出数据格式
- 评估指标

## 步骤 4: 进入 PLAN MODE

使用 EnterPlanMode 进入 PLAN MODE。Plan 应包含：

1. **交付物清单** (所有需要创建/修改的文件)
2. **实现顺序** (先实现什么，后实现什么)
3. **依赖关系** (需要哪些外部库/数据)
4. **验证方式** (如何确认每步实现正确)
5. **预期时间** (粗略估计每步耗时)

Plan 写完后用 ExitPlanMode 请求用户批准。

## 步骤 5: 写状态回 PIPELINE_STATE.json

```
python3 -c "
import json
p = '/home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/PIPELINE_STATE.json'
s = json.loads(open(p).read())
s['code_session_dir'] = '<SESSION_DIR>'
s['code_phase_status'] = 'plan_approved'
json.dump(s, open(p, 'w'), indent=2, ensure_ascii=False)
"
```
