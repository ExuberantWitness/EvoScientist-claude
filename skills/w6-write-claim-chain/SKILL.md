---
name: w6-write-claim-chain
description: "W6 写入 Claim Chain — 纯 Python 执行。"
execution: python
handler: pes_controller.handlers.write_claim_chain
variables:
  - name: workspace_dir
    required: true
---

# W6 Write Claim Chain

将分析结果写入 Claim Chain 数据库。

此 skill 为 `execution: python` 模式，由 Python handler 函数执行。
