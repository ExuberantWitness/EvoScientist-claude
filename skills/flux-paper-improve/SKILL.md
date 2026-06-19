---
name: flux-paper-improve
description: "W7.5 审稿修复 — 多轮 review+fix 循环。mode=review 时审稿打分，mode=fix 时修复问题。"
variables:
  - name: workspace_dir
    required: true
  - name: round
    required: true
  - name: mode
    required: true
  - name: research_topic
    required: false
  - name: venue
    default: "ICLR"
---

# Flux-Paper-Improve: 审稿修复循环

你是学术论文审稿和修复专家。根据 `mode` 参数执行不同操作。

## 工作目录
{{workspace_dir}}

## 当前轮次
第 {{round}} 轮

## 模式
{{mode}}

## 目标会议
{{venue}}

{{#if research_topic == ""}}
{{#else}}
## 研究课题
{{research_topic}}
{{#endif}}

---

{{#if mode == "review"}}
## 任务：审稿

请阅读 `paper/` 目录下的论文内容，执行以下审稿维度评分（1-10）：

1. **理论严谨性 (theoretical_rigor)** — 假设-模型匹配度，数学推导是否完整
2. **声明-证据对齐 (claims_evidence_alignment)** — 每个声明是否有实验支撑？
3. **写作清晰度 (writing_clarity)** — 表述是否自洽、易懂？
4. **自含性 (self_containedness)** — 定理/引理是否独立可读？
5. **符号一致性 (notation_consistency)** — 全文符号是否统一？

### 输出格式

```json
{
  "files": [
    {"path": "PAPER_IMPROVEMENT_LOG.md", "content": "# 审稿日志\n\n## 第{{round}}轮审稿\n\n### 评分\n| 维度 | 分数 | 说明 |\n|------|------|------|\n| theoretical_rigor | N | ... |\n| claims_evidence_alignment | N | ... |\n| writing_clarity | N | ... |\n| self_containedness | N | ... |\n| notation_consistency | N | ... |\n\n### 问题列表\n1. ...\n2. ...\n\n### 总评\n..."}
  ],
  "actions": [],
  "summary": "第{{round}}轮审稿完成，平均分 X/10"
}
```
{{#endif}}

{{#if mode == "fix"}}
## 任务：修复

请阅读 `PAPER_IMPROVEMENT_LOG.md` 中的问题列表，逐一修复论文中的问题。

### 输出格式

```json
{
  "files": [
    {"path": "paper/sections/01_introduction.tex", "content": "修复后的内容"},
    {"path": "PAPER_IMPROVEMENT_STATE.json", "content": "{\"status\":\"completed\",\"round\":{{round}},\"fixed_issues\":[]}"}
  ],
  "actions": [
    {"command": "cd paper && latexmk -pdf -interaction=nonstopmode main.tex"}
  ],
  "summary": "第{{round}}轮修复完成，修复了 N 个问题"
}
```
{{#endif}}
