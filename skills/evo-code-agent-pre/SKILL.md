---
name: evo-code-agent-pre
description: W5 代码实现 前置阶段 — 从 vault 读取 implementation_plan.md，创建 code session，进入 PLAN MODE。
argument-hint: [session_dir_path]
allowed-tools: Bash(*), Read, Write, Edit, Glob, Grep, WebSearch, WebFetch, AskUserQuestion, TaskOutput, Agent, EnterPlanMode, ExitPlanMode
---

# W5 代码实现 — 前置：读取计划，进入 PLAN MODE

Session 目录: **$ARGUMENTS**

## 路径约定

执行前通过以下命令发现项目根目录：

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
WORKSPACE_ROOT=$(dirname "$PROJECT_ROOT")
echo "PROJECT_ROOT=$PROJECT_ROOT"
```

## 步骤 1: 确定 Session 路径

从 PIPELINE_STATE.json 读取 session_dir:

```
python3 -c "
import json
state = json.loads(open('$ARGUMENTS/PIPELINE_STATE.json').read())
print(state.get('session_dir', state.get('vault_dir', '')))
"
```

如果 $ARGUMENTS 为空，从 `$PROJECT_ROOT/sessions/` 下找最新 session。

## 步骤 2: 读取 Plan 文件

Plan 文件位于 vault 中:
- `{session_dir}/iterations/{n}/implementation_plan.md`
- 或 `{session_dir}/vault/_pipeline/implementation_plan.md`

读取 Plan，提取关键信息。

## 步骤 2.5: 查询 Claim Chain 理解上下文

从 Plan 中提取 CC atom ID → 用 `cc_query_tool neighbors` 获取 2-hop 邻域子图:

```bash
cd "$PROJECT_ROOT" && PYTHONPATH=. python3 tools/cc_query_tool.py neighbors --atom-id <atom_id> --depth 2 --workspace {session_dir}
```

也对 plan 中引用的每个 proposal/method atom 重复此操作。

将获取的 CC 上下文整合到 Plan 中——理解该 atom 与哪些方法/组件/实验关联。

## 步骤 3: 创建 Code Session 文件夹

在 vault/artifacts/ 下创建:

```
mkdir -p {session_dir}/vault/artifacts/code_session_$(date +%Y%m%d_%H%M%S)
```

记录 CODE_SESSION_DIR 路径。

## 步骤 4: 从 Plan 提取关键信息

从 Plan 中提取并打印：
- 研究目标 (一句话)
- 需要实现的算法/方法列表 (带 [NEW]/[KEEP]/[RESOLVE] 标记)
- 每个算法的 SPEC.md 路径 (如有)
- 需要的实验脚本列表
- 输入/输出数据格式
- 评估指标

## 步骤 5: 进入 PLAN MODE

使用 EnterPlanMode 进入 PLAN MODE。Plan 应包含：

1. **交付物清单** (所有需要创建/修改的文件)
2. **实现顺序** (先实现什么，后实现什么)
3. **依赖关系** (需要哪些外部库/数据)
4. **验证方式** (如何确认每步实现正确)
5. **预期时间** (粗略估计每步耗时)

Plan 写完后用 ExitPlanMode 请求用户批准。

## 步骤 6: 写状态回 PIPELINE_STATE.json

```
python3 -c "
import json
p = '{session_dir}/PIPELINE_STATE.json'
s = json.loads(open(p).read())
s['code_session_dir'] = '{CODE_SESSION_DIR}'
s['code_phase_status'] = 'plan_approved'
json.dump(s, open(p, 'w'), indent=2, ensure_ascii=False)
"
```
