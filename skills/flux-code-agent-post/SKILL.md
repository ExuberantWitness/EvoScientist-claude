---
name: flux-code-agent-post
description: W5 代码实现 完成确认 — 检查交付物，通过 experiment_recorder tool 记录实验结果，触发 Dashboard 进入 W6 结果分析。
argument-hint: [session_dir_path]
allowed-tools: Bash(*), Read, Write, Glob, AskUserQuestion
---

# W5 代码实现 — 完成确认：交付物检查 + experiment_recorder

Session 目录: **$ARGUMENTS**

## 路径约定

执行前通过以下命令发现路径：

```bash
_find_project_root() {
    local d="${1:-$(pwd)}"
    while [ "$d" != "/" ]; do
        if [ -f "$d/CLAUDE.md" ] && [ -f "$d/run_dashboard.py" ]; then
            echo "$d"
            return 0
        fi
        d=$(dirname "$d")
    done
    find "$HOME" -maxdepth 6 -name "run_dashboard.py" -path "*/Flux-Insight/*" 2>/dev/null | head -1 | xargs dirname 2>/dev/null
}
PROJECT_ROOT=$(_find_project_root "$(pwd)")
echo "PROJECT_ROOT=$PROJECT_ROOT"
```

## 步骤 1: 交付物完整性检查

从 PIPELINE_STATE.json 读取 session 信息:

```
python3 -c "
import json
s = json.loads(open('$ARGUMENTS/PIPELINE_STATE.json').read())
print('session_dir:', s.get('session_dir', 'N/A'))
print('vault_dir:', s.get('vault_dir', 'N/A'))
print('code_session_dir:', s.get('code_session_dir', 'N/A'))
"
```

从 code_session_dir 检查所有交付物文件存在且非空。

## 步骤 2: 代码质量检查

```
find {code_session_dir} -name "*.py" -exec python3 -m py_compile {} \;
find {code_session_dir} -type f -size 0
```

## 步骤 3: 记录实验结果 (使用 experiment_recorder tool)

**重要**: 不再通过 AskUserQuestion 收集散文结果。使用 Python tool 确定性记录:

对每个已跑实验的算法:

```
python3 -c "
import sys; sys.path.insert(0, '$PROJECT_ROOT/tools')
from experiment_recorder import record_experiment_result

result = record_experiment_result(
    session_dir='{session_dir}',
    algo_id='{algo_id}',
    env='{env_name}',  # 从 PIPELINE_STATE.confirmed_benchmark 获取
    score_mean={score_mean},
    score_std={score_std},
    seeds={seeds},
    code_path='artifacts/{filename}.py',
    success=True,
    extra_notes='{notes}',
)
print('Recorded:', result)
"
```

重复对每个算法调用。

## 步骤 3.5: 建立 CC 函数→方案关联

将已实现的代码 atom 与 proposal atom 关联:

```bash
cd "$PROJECT_ROOT" && PYTHONPATH=. python3 tools/cc_query_tool.py link \
    --source <function_atom_id> \
    --target <proposal_atom_id> \
    --type implements \
    --evidence "Implemented in artifacts/<file>.py" \
    --workspace {session_dir}
```

对每个已实现的函数，找到对应的 proposal atom (从 implementation_plan.md 的 deliverables 中查)，建立 `implements` 边。

先查当前 CC 中有哪些 atom:
```bash
cd "$PROJECT_ROOT" && PYTHONPATH=. python3 tools/cc_query_tool.py summary --workspace {session_dir}
```

## 步骤 4: AskUserQuestion 确认特殊情况

仅对以下情况使用 AskUserQuestion:
- 实验失败 (success=False): 确认失败原因
- 异常行为: 天花板效应、高方差、NaN 等
- 用户有额外备注

## 步骤 5: 更新 PIPELINE_STATE 触发下一阶段

```
python3 -c "
import json
p = '{session_dir}/PIPELINE_STATE.json'
s = json.loads(open(p).read())
s['code_phase_status'] = 'completed'
s['code_session_dir'] = '{CODE_SESSION_DIR}'
s['status'] = 'awaiting_decision'
s['command'] = None
json.dump(s, open(p, 'w'), indent=2, ensure_ascii=False)
print('PIPELINE_STATE updated. Dashboard should now show W6 结果分析.')
"
```

## 步骤 6: 同步 JSONL 索引

```
python3 -c "
import sys; sys.path.insert(0, '$PROJECT_ROOT/tools')
from markdown_parser import IndexSyncer
syncer = IndexSyncer('{session_dir}/vault')
result = syncer.sync_all()
print(f'Index synced: {result[\"atoms_count\"]} atoms, {result[\"relations_count\"]} relations')
"
```
