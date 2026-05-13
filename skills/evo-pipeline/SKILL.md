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

```
"================================================"
"Pipeline 已就绪。请在浏览器中打开:"
"  {dashboard_url}"
"后续所有操作都在 Dashboard 网页端完成。"
"================================================"
```
