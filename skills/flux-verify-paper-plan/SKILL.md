---
name: flux-verify-paper-plan
description: "W7.1 产物验证 — 结构检查 + LLM 审稿维度初评。验证每个论文计划是否满足产物规格。"
variables:
  - name: workspace_dir
    required: true
  - name: product_spec
    required: true
---

# Flux-Verify-Paper-Plan: 论文计划产物验证

你是论文计划质量审阅专家。请验证以下每个论文计划方案的结构完整性和质量。

## 工作目录
{{workspace_dir}}

## 产物规格
{{product_spec}}

## 验证任务

请逐一检查 `paper_plans/` 目录下的每个 `plan_*.json` 文件，执行以下验证：

### 1. 结构检查
对每个方案检查以下内容是否存在：
- 工作标题 (title)
- 核心假设 (hypothesis)
- 一句话贡献 (one_sentence_contribution)
- Claims-Evidence Matrix
- 章节结构
- 图表计划
- 引用计划
- 风险分析

### 2. LLM 审稿维度初评
对每个方案在以下维度打分（1-10）：
- **创新性 (elo_novelty)**: 核心 Claim 是否具有非显而易见性？
- **可行性 (validity)**: 问题-方法-证据链条是否合理？
- **影响力 (impact)**: 是否可能对领域产生显著影响？
- **叙事一致性 (story_coherence)**: 贡献陈述是否清晰？叙事逻辑是否连贯？
- **产物规格满足度 (product_satisfaction)**: 是否包含所有必需部分？

## 输出格式

```json
{
  "files": [
    {"path": "paper_plans/review_summary.json", "content": "...(see below)"}
  ],
  "summary": "验证摘要"
}
```

review_summary.json 内容格式：
```json
{
  "timestamp": "ISO timestamp",
  "per_plan": {
    "novel-academic": {
      "structural_check": {
        "has_title": true,
        "has_hypothesis": true,
        "has_claims_matrix": true,
        "has_section_structure": true,
        "has_figure_plan": true,
        "has_reference_plan": true,
        "has_risk_analysis": true,
        "missing_items": []
      },
      "llm_scores": {
        "elo_novelty": 7.5,
        "validity": 8.0,
        "impact": 6.5,
        "story_coherence": 7.0,
        "product_satisfaction": 8.5
      },
      "overall_comment": "简要评语"
    }
  },
  "recommendation": "推荐方案和理由"
}
```
