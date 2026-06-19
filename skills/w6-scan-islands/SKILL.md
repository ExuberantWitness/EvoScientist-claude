---
name: w6-scan-islands
description: "W6 扫描 Islands 和 Rubrics — 纯 Python 执行，不调用 LLM。"
execution: python
handler: pes_controller.handlers.scan_islands
variables:
  - name: workspace_dir
    required: true
---

# W6 Scan Islands & Rubrics

扫描 evolve_archive 中的实验 Islands，汇总 Rubric 评分。

此 skill 为 `execution: python` 模式，由 Python handler 函数执行。
