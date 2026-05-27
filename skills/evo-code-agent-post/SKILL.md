---
name: evo-code-agent-post
description: W4 Code 完成确认 — 对照 plan 检查交付物完整性，通过 AskUserQuestion 逐项确认产出，将结果回写到 PIPELINE_STATE.json 触发 Dashboard 进入下一阶段。
argument-hint: [implementation_plan_path]
allowed-tools: Bash(*), Read, Write, Glob, AskUserQuestion
---

# W4 Code — 完成确认：交付物检查 + 结果回传

Plan 文件路径: **$ARGUMENTS**

工作空间目录: `/home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH`
PIPELINE_STATE: `/home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/PIPELINE_STATE.json`

## 步骤 1: 交付物完整性检查

从 `$ARGUMENTS` 读取 plan，列出全部交付物。
从 PIPELINE_STATE.json 读取 `code_session_dir`，检查对应文件是否存在且非空。

```
for file in <deliverable list>; do
  if [ -s "$file" ]; then
    echo "[OK] $file ($(wc -l < $file) lines)"
  else
    echo "[MISSING] $file"
  fi
done
```

## 步骤 2: 代码质量基础检查

```
# 检查 Python 语法
find <SESSION_DIR> -name "*.py" -exec python -m py_compile {} \; 2>&1

# 检查文件大小 (排除空文件)
find <SESSION_DIR> -type f -size 0
```

## 步骤 2.5: CodeGraph 最终变更核验

使用 CodeGraph MCP tools 生成实现代码的完整结构变更摘要：

### 2.5.1 索引代码目录
```
cd <SESSION_DIR> && npx @colbymchenry/codegraph init -i
```

### 2.5.2 对每个 proposal algorithm 分析
- `codegraph_files` — 确认所有 plan 中的文件存在
- `codegraph_search <algo_name>` — 找到对应 class/function
- `codegraph_impact <main_function>` — 分析变更影响范围
- `codegraph_node <symbol>` — 获取签名和实现细节

### 2.5.3 生成变更摘要
```
| 算法 | 新增 Class | 新增 Fn | 修改 Fn | 删除 | 新增依赖 |
|------|----------|--------|--------|------|---------|
| sac | 0 | 0 | 0 | 0 | 0 |
| td3 | 0 | 0 | 0 | 0 | 0 |
| cdr_critic | 2 | 3 | 1 | 0 | 5 |
```

### 2.5.4 与 implementation_plan 对比
将变更摘要与 implementation_plan.md 的 deliverables 清单对比，确认每个计划中的文件都存在且有内容。

### 2.5.5 写入 PIPELINE_STATE
将 CodeGraph 变更摘要存入 `code_results.codegraph_diff`

## 步骤 3: AskUserQuestion 逐项确认交付

向用户确认每个交付物：
- 文件是否完整？
- 实现是否符合预期？
- 是否还有需要补充的内容？

## 步骤 4: AskUserQuestion 确认实验配置

确认实验运行所需的：
- Python 版本 / 依赖 (requirements.txt 是否完整?)
- 数据集 / 环境配置
- 运行命令 (是否有 run.sh 或明确的 `python train.py --args`?)

## 步骤 5: AskUserQuestion 收集实验结果 (**关键步骤**)

逐算法收集实验数据，供 W5 Analyze 写入 CC 和分配 island。

对每个已跑实验的算法，收集：
- 算法名称 (如 SAC, TD3, EMTD3)
- 是否成功运行 (成功/部分成功/失败)
- 最终分数 (mean±std over seeds)
- 种子数
- 代码文件路径 (如 artifacts/sac.py)
- 关键发现 (是否超越基线, 是否有异常行为, 天花板效应等)

## 步骤 6: AskUserQuestion 收集用户评价

询问用户对代码实现的整体评价和后续期望。

## 步骤 7: 汇总结果回写到 PIPELINE_STATE.json

```bash
python3 -c "
import json
p = '/home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/PIPELINE_STATE.json'
s = json.loads(open(p).read())
s['code_session_dir'] = '<SESSION_DIR>'
s['code_phase_status'] = 'completed'
s['code_deliverables'] = [<list of files>]
s['code_results'] = [
    {
        'algorithm': '<name>',
        'status': 'success',
        'score_mean': <float>,
        'score_std': <float>,
        'seeds': <int>,
        'code_path': '<relative path>',
        'key_findings': '<findings>',
    },
]
s['code_user_feedback'] = '<user feedback>'
s['status'] = 'awaiting_decision'
s['command'] = None
json.dump(s, open(p, 'w'), indent=2, ensure_ascii=False)
print('PIPELINE_STATE updated: code phase completed')
"
```

## 步骤 8: 汇总到 Memory

```
echo "
## Code Phase Complete $(date +%Y-%m-%d_%H:%M:%S)
- Plan: $ARGUMENTS
- 交付物: [deliverable list]
- 实验结果: [algorithm results summary]
- 用户评价: [user feedback]
" >> /home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/memory/MEMORY.md
```
