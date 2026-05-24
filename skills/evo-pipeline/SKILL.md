---
name: evo-pipeline
description: "Pipeline 一键启动。自动启动 Dashboard（如未运行）+ 初始化工作空间 + 输出 Dashboard URL。"
argument-hint: [research_proposal_or_question]
allowed-tools: Bash(*), Read, Write
---

# EvoScientist Pipeline — 一键启动

研究问题: **$ARGUMENTS**

项目根目录: `/home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/EvoScientist-claude`
工作空间目录: `/home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH`

## 步骤 0: 确保 Dashboard 在运行

检查 Dashboard：

```
curl -s -o /dev/null -w '%{http_code}' http://localhost:8420/
```

如果返回不是 200，后台启动：

```
/home/exuber/anaconda3/envs/evo-agents/bin/python /home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/EvoScientist-claude/tools/start_dashboard.py
```

## 步骤 1: 清理残留运行时数据

每次启动前清理上次残留的 stale 状态，避免心跳锁、重复 session 等问题：

```bash
python3 -c "
import json, os
from pathlib import Path

ws = Path('/home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH')
sp = ws / 'PIPELINE_STATE.json'
if sp.exists():
    s = json.loads(sp.read_text())
    # 清除残留 agent 状态
    for key in ['agent_heartbeat', 'agent_report', 'approval_request',
                'approval_response', 'active_task', 'command',
                'code_phase_status', 'code_results', 'code_session_dir']:
        s.pop(key, None)
    sp.write_text(json.dumps(s, indent=2, ensure_ascii=False))
    print('PIPELINE_STATE.json cleaned')

# 清理重复 session 文件，只保留当前 session_id
sdir = ws / '.evo_sessions'
if sdir.exists():
    current_sid = s.get('session_id', '')
    deleted = 0
    for f in sdir.glob('*.json'):
        if f.stem != current_sid:
            f.unlink()
            deleted += 1
    if deleted:
        print(f'Cleaned {deleted} stale session files')

# 清理 session registry
rpath = Path('/home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/EvoScientist-claude/agent-manager/.evo_session_registry.json')
if rpath.exists():
    registry = json.loads(rpath.read_text())
    valid = {}
    for sid, wspath in registry.items():
        sf = Path(wspath) / '.evo_sessions' / f'{sid}.json'
        if sf.exists():
            valid[sid] = wspath
    if len(valid) != len(registry):
        rpath.write_text(json.dumps(valid, indent=2))
        print(f'Registry cleaned: {len(registry)} -> {len(valid)}')
"
```

## 步骤 2: Bootstrap 工作空间

```
python /home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/EvoScientist-claude/tools/bootstrap.py '$ARGUMENTS' /home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH
```

注意: 研究问题用单引号包裹以避免特殊字符问题。
从输出中提取 session_id 和 dashboard_url。

## 步骤 3: 展示 Dashboard URL

**禁止提及 Obsidian、Vault、知识图谱等词。** 可视化通过 Dashboard HTML (vis-network) 完成。
只输出 bootstrap.py 的实际 stdout，不要添加额外解释。

```
"================================================"
"Pipeline 已就绪。请在浏览器中打开:"
"  {dashboard_url}"
"后续所有操作都在 Dashboard 网页端完成。"
"================================================"
```

## Phase Map (Phase 4 — 新增 W3.3 + W3.7-W4.1)

当前 7 阶段流程 + 新增子阶段:

```
W1  Intake      → /evo-intake — 解析提案, 提取域参数 → DomainConfig
W2  Plan        → /evo-planner — 实验计划 + 成功信号
W3  Research    → /evo-research — 文献调研
W3.3 LitIngest  → lit_ingest.py — PDF→Markdown→manifest (NEW, Phase 3.5)
W3.5 Ideate     → /evo-ideation — Idea Tree Search + Elo tournament
W3.7 Refine     → /evo-refine — idea→algorithm 翻译, 输出 RefinedAtom JSON (NEW)
W3.8 Verify     → verify_atom.py L2 — 独立验证, 失败→retry max 3 (NEW)
W3.9 Review     → /evo-review --mode atom — 跨模型审稿 (NEW)
W4  Code        → /evo-code — 实现实验代码
W4.1 VerifyPlan → verify_plan.py — plan 具体性检查 (NEW)
W5  Analyze     → /evo-analyze — 指标/图表/统计
W6  Write       → /evo-write — 论文级报告
W7  Review      → /evo-review — 跨模型审稿循环
```

## Dry-Run Mode (Phase 4 — 新增)

开发期只跑到 refine+verify+review, 不进 W4 Code:

```bash
python /home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/EvoScientist-claude/tools/bootstrap.py '$ARGUMENTS' ... --dry-run-from W3.7
```

Dry-run 产物写入 `sessions/{sid}/_dry_runs/{timestamp}/` — 完全沙盒化, 不写 CC v2, 不写 PIPELINE_STATE.json, 不与真实运行混淆。
