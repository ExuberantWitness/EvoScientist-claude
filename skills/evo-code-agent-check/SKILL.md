---
name: evo-code-agent-check
description: W4 Code 中期检查 — 对比实现进度与 plan，检测偏离，通过 AskUserQuestion 确认偏离原因，同步到 memory 回传系统。
argument-hint: [implementation_plan_path]
allowed-tools: Bash(*), Read, Write, Edit, Glob, Grep, AskUserQuestion
---

# W4 Code — 中期检查：Plan vs 实际执行

Plan 文件路径: **$ARGUMENTS**

工作空间目录: `/home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH`
PIPELINE_STATE: `/home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/PIPELINE_STATE.json`
Memory 目录: `/home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/memory/`

## 步骤 1: 读取 Plan + 当前状态

从 `$ARGUMENTS` 读取 plan。从 PIPELINE_STATE.json 读取 `code_session_dir` 找到交付物目录。

列出到目前为止已创建/修改的文件：

```
find <SESSION_DIR> -type f | sort
```

## 步骤 2: 逐项对比 Plan vs 实际

对 Plan 中的每个交付物，检查是否已创建：
- 已完成的项 → 标记 [DONE]
- 部分完成 → 标记 [PARTIAL]
- 未开始 → 标记 [TODO]

## 步骤 2.5: CodeGraph 结构差异分析

对每个已修改的算法文件，使用 CodeGraph MCP tools 检查代码结构变更是否与 proposal 一致：

### 2.5.1 确保 CodeGraph 索引是最新的
```
npx @colbymchenry/codegraph init -i
```

### 2.5.2 对每个 modified 文件分析
- 使用 `codegraph_node <function_name>` 获取修改后的函数签名
- 使用 `codegraph_impact <modified_symbol>` 分析变更影响范围
- 使用 `codegraph_callers <modified_symbol>` 检查上游依赖是否受影响

### 2.5.3 与 refined_proposal 对比
读取 `refined_proposals/<algo_name>.json` 中的 `core_method_body`:
- proposal 说 **ADD** class X → `codegraph_search X` 确认 X 存在?
- proposal 说 **MODIFY** fn Y → `codegraph_node Y` 签名是否匹配预期改动?
- proposal 说 **REMOVE** module Z → `codegraph_files` 中 Z 是否已移除?

### 2.5.4 检测三类偏差
- **Missing**: proposal 要求的架构改动未在代码中体现
- **Extra**: 新增了 proposal 未提及的 class/function (scope creep)
- **Mismatch**: 改动存在但方向与 proposal 描述不一致

将 CodeGraph 差异报告写入 `code_check_result.codegraph_diff`。

## 步骤 3: 检测偏离

对比当前实现与 plan 的差异：

1. **是否有新增的文件/功能不在原 plan 中？** → 可能是 scope creep 或用户的新想法
2. **是否跳过了 plan 中的某些步骤？** → 可能执行偏了
3. **实现方式是否与 plan 描述不同？** → 可能技术选型变了

## 步骤 4: AskUserQuestion 确认偏离

如果检测到偏离，通过 AskUserQuestion 和用户确认：

问题选项应包含：
- "这是我有意调整的新方向" (用户主动调整)
- "Plan 执行有误，需要纠正" (执行偏离)
- "原 Plan 有问题，需要回传修改" (Plan 本身需改进)

## 步骤 5: 汇总到 Memory

将检查结果写入 Memory：

```
echo "
## Code Check $(date +%Y-%m-%d_%H:%M:%S)

- Plan: $ARGUMENTS
- 完成项: [DONE items list]
- 偏离项: [deviation items]
- 偏离原因: [user adjustment / execution deviation / plan issue]
- 用户反馈: [user response summary]
" >> /home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/memory/MEMORY.md
```

## 步骤 6: 写状态回 PIPELINE_STATE.json

```
python3 -c "
import json
p = '/home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH/PIPELINE_STATE.json'
s = json.loads(open(p).read())
s['code_check_result'] = {
    'completed': [<DONE items>],
    'deviations': [<deviation items>],
    'user_intent': '<user response>'
}
json.dump(s, open(p, 'w'), indent=2, ensure_ascii=False)
"
```
