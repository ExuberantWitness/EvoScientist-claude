---
name: evo-pipeline
description: "Pipeline 一键启动。清理旧进程 → GitHub搜索baseline → 用户确认 → Bootstrap → 启动 Dashboard。"
argument-hint: [research_proposal_or_question]
allowed-tools: Bash(*), Read, Write, Skill, AskUserQuestion
---

# Flux-Insight Pipeline — 一键启动

研究问题: **$ARGUMENTS**

## 路径约定

本 SKILL 使用以下变量。Claude Code 执行时自动解析为实际路径：

| 变量 | 含义 | 自动发现方式 |
|------|------|-------------|
| `PROJECT_ROOT` | Flux-Insight 项目根目录 | 搜索包含 `CLAUDE.md` + `run_dashboard.py` 的目录 |
| `WORKSPACE_ROOT` | 工作空间根目录 | `PROJECT_ROOT` 的父目录 |
| `SKILLS_ROOT` | Claude Code Skills 目录 | `~/.claude/skills` |
| `PYTHON_BIN` | Python (需 BGE-M3/FlagEmbedding) | `python3` 或 conda env，见步骤 0 |

**在开始前，先执行以下发现命令，后续所有代码块使用这些 shell 变量：**

```bash
# 自动发现 PROJECT_ROOT (从当前目录向上搜索)
_find_project_root() {
    local d="$1"
    while [ "$d" != "/" ]; do
        if [ -f "$d/CLAUDE.md" ] && [ -f "$d/run_dashboard.py" ]; then
            echo "$d"
            return 0
        fi
        d=$(dirname "$d")
    done
    # Fallback: search home directory (max depth 6)
    find "$HOME" -maxdepth 6 -name "run_dashboard.py" -path "*/Flux-Insight/*" 2>/dev/null | head -1 | xargs dirname 2>/dev/null
}
PROJECT_ROOT=$(_find_project_root "$(pwd)")
WORKSPACE_ROOT=$(dirname "$PROJECT_ROOT")

echo "PROJECT_ROOT=$PROJECT_ROOT"
echo "WORKSPACE_ROOT=$WORKSPACE_ROOT"
```

## 步骤 0: 清理旧进程 + 残留数据

杀掉旧 Dashboard，清理残留状态：

```bash
pkill -f "evo_agent_manager.server" 2>/dev/null; sleep 2
```

```bash
python3 -c "
import json
from pathlib import Path

ws = Path('$WORKSPACE_ROOT')
sp = ws / 'PIPELINE_STATE.json'
s = {}
if sp.exists():
    s = json.loads(sp.read_text())
    for key in ['agent_heartbeat', 'agent_report', 'approval_request',
                'approval_response', 'active_task', 'command',
                'code_phase_status', 'code_results', 'code_session_dir']:
        s.pop(key, None)
    sp.write_text(json.dumps(s, indent=2, ensure_ascii=False))
    print('PIPELINE_STATE.json cleaned')
else:
    print('No PIPELINE_STATE.json, skipping')

sdir = ws / '.evo_sessions'
if sdir.exists():
    current_sid = s.get('session_id', '')
    for f in sdir.glob('*.json'):
        if f.stem != current_sid:
            f.unlink()
    print('.evo_sessions cleaned')

rpath = Path('$PROJECT_ROOT') / 'agent-manager/.evo_session_registry.json'
if rpath.exists():
    registry = json.loads(rpath.read_text())
    valid = {sid: wspath for sid, wspath in registry.items()
             if (Path(wspath) / '.evo_sessions' / f'{sid}.json').exists()}
    if len(valid) != len(registry):
        rpath.write_text(json.dumps(valid, indent=2))
        print(f'Registry cleaned: {len(registry)} -> {len(valid)}')
    else:
        print('Registry clean')
"
```

## 步骤 1: GitHub 搜索 Baseline + 用户确认

**重要**: GitHub API 不支持中文搜索。必须从 `$ARGUMENTS` 中提取英文关键词后再搜索。
先用低门槛搜索获取候选，再用高门槛二次筛选。

使用 NVM Node v22 直接调用 github-search 脚本：

```bash
# 第一步: 宽搜索（低门槛，从$ARGUMENTS提取英文关键词填入<query>）
export NVM_DIR="$HOME/.nvm" && [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" && nvm use v22.22.2 && cd "$SKILLS_ROOT/github-search" && node scripts/github-search.mjs "<query>" --language python --min-stars 10 --limit 15 2>&1
```

根据研究领域补充多角度搜索：

```bash
# 搜索算法实现
export NVM_DIR="$HOME/.nvm" && [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" && nvm use v22.22.2 && cd "$SKILLS_ROOT/github-search" && node scripts/github-search.mjs "<query>" --language python --min-stars 10 --limit 15 2>&1

# 搜索框架和库
export NVM_DIR="$HOME/.nvm" && [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" && nvm use v22.22.2 && cd "$SKILLS_ROOT/github-search" && node scripts/github-search.mjs "<query>" --language python --min-stars 50 --limit 10 2>&1
```

如果 GitHub API 返回 0 结果（非 rate limit），执行 LLM 驱动的查询重试:

1. 调用 LLM 分析为什么搜索失败（关键词太长？太具体？中文术语？语言不匹配？）
2. LLM 生成 2-3 个重新表述的查询（将中文翻译为英文、简化关键词、使用更广泛的领域术语）
3. 使用重新表述的查询重试 GitHub 搜索
4. 最多循环 3 轮，直到找到结果或所有查询变体都已用尽
5. 只有在所有 LLM 生成的查询都失败时，才报告失败并要求用户手动输入基线

LLM 重试分析 prompt 模板:
```
GitHub API returned 0 results for query: '{query}'. Research topic: '{topic}'.
Analyze why this search likely failed (too specific? language mismatch? wrong technical terms?)
Then generate 2-3 alternative search queries that are more likely to return results.
Output as JSON: {"analysis":"...", "reformulated_queries":["query1","query2","query3"]}
```

从返回的仓库列表中提取方法名候选，按类别分组：
- **算法**: 名称/描述中含算法缩写（如 SAC, TD3, PPO, DDPG, BERT, GPT, LSTM 等）或方法名
- **框架**: 名称含 framework, library, platform, toolkit, suite
- **Benchmark**: 名称含 benchmark, environment, dataset, corpus

然后调用 `AskUserQuestion` 让用户确认：

- 第一个问题：展示发现的算法类 baseline（top-5），让用户勾选确认哪些是公认的基线方法，并提供"手动输入"选项
- 第二个问题：展示发现的框架/库（top-3），让用户勾选或跳过
- 第三个问题：展示发现的 benchmark（top-3），让用户勾选或跳过
- 第四个问题：「是否需要先跳到 Code 阶段验证某个 baseline 的可行性？」选项: "不需要，继续 Plan" / "需要验证（请说明哪个）"

## 步骤 2: Bootstrap 工作空间

```bash
cd "$PROJECT_ROOT" && PYTHONPATH=. python3 pes_controller/bootstrap.py '$ARGUMENTS' "$WORKSPACE_ROOT"
```

从输出中提取 `session_id`、`session_dir`。

## 步骤 3: 写入确认的 Baseline (到 cc.db) + 触发 Embedding

```bash
python3 -c "
import json, sys
from pathlib import Path

sys.path.insert(0, '$PROJECT_ROOT')
from claim_chain.chain import ClaimChainV2

sd = Path('{session_dir}')
sp = sd / 'PIPELINE_STATE.json'
state = json.loads(sp.read_text())

# 写入用户确认的 baseline
state['confirmed_baselines'] = {
    'algorithms': [...],      # 从步骤1的 AskUserQuestion 结果
    'frameworks': [...],
    'benchmarks': [...],
    'user_added': [...],
}

# 写入 CC atoms 到 cc.db (canonical store)
idx = sd / '_index'
idx.mkdir(parents=True, exist_ok=True)
cc = ClaimChainV2(idx / 'cc.db')

written = 0
for cat, items in state['confirmed_baselines'].items():
    for item in items:
        if cat == 'user_added':
            source = 'user_provided'
        else:
            source = 'github_search'
        cc.add_atom(
            type='fact',
            title=item,
            content=json.dumps({'source': source, 'category': cat, 'method': item}, ensure_ascii=False),
            tags=['baseline', 'user-confirmed', cat],
            evidence_level='verified',
            metadata={'source': source, 'category': cat},
        )
        written += 1

cc.close()
sp.write_text(json.dumps(state, indent=2, ensure_ascii=False))
print(f'Written {written} baseline atoms to cc.db')
"
```

## 步骤 3.5: 启动 BGE-M3 Embedding 服务

```bash
# 自动发现含 FlagEmbedding 的 Python
PYTHON_BIN="python3"
if ! python3 -c "import FlagEmbedding" 2>/dev/null; then
    # 尝试常见 conda 路径
    for _py in "$HOME/anaconda3/bin/python" "$HOME/miniconda3/bin/python"; do
        if [ -f "$_py" ] && "$_py" -c "import FlagEmbedding" 2>/dev/null; then
            PYTHON_BIN="$_py"
            break
        fi
    done
fi
echo "Using Python: $PYTHON_BIN"

# 后台启动 BGE socket server (常驻，agent 通过 cc_query_tool 连接)
pkill -f bge_socket_server 2>/dev/null; sleep 1
cd "$PROJECT_ROOT" && "$PYTHON_BIN" tools/bge_socket_server.py --workspace {session_dir} 2>&1 &
sleep 5
echo "BGE socket server started"
```

## 步骤 3.6: 计算 Baseline Embeddings

```bash
python3 -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT')
from tools.cc_query_tool import _ensure_embeddings

socket_path = '{session_dir}/_index/bge_socket.sock'
cc_db_path = '{session_dir}/_index/cc.db'
count = _ensure_embeddings(cc_db_path, socket_path)
print(f'Embeddings computed: {count} atoms')
"
```

## 步骤 4: 启动 Dashboard + 展示 URL

```bash
cd "$PROJECT_ROOT" && PYTHON_BIN="${PYTHON_BIN:-python3}" && "$PYTHON_BIN" run_dashboard.py 2>&1 &
sleep 2
```

```
"================================================"
"Baseline 已确认并写入 CC"
"Pipeline 已就绪。请在浏览器中打开:"
"  {dashboard_url}"
"Dashboard W2 问题分析阶段的 Persona 调用将围绕已确认 baseline 展开。"
"================================================"
```
