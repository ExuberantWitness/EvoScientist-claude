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
