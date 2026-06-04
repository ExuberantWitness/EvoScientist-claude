---
algo_id: dual_critic_attention
name: Dual Critic Attention (双Critic方差分解+注意力)
status: VALIDATED
created: 2026-06-02
iteration: 1
---

# Dual Critic Attention

双Critic方差分解 + 注意力状态不确定性。

- **Actor**: StochasticActor (复用)
- **Critics**: 2x QNetwork (标准, 非量化)
- **AttentionUncertainty**: K/Q/V projections (64-dim) + self-attention → aleatoric uncertainty
- **alpha_net**: MLP(2→64→1, sigmoid) 融合 epistemic + aleatoric
- **Uncertainty**: twin-Q variance (epistemic) + attention state uncertainty (aleatoric)

## 实验历史 (只追加, 不修改)

### 2026-06-03: Hopper-v4 (5 seeds, test)
- score: 785.9 ± 228.2
- 备注: 双Critic方差分解+注意力状态不确定性. 5 seeds: 1031,229,1083,310,1027. 双峰分布(3 seeds ~1030, 2 seeds ~230-310).
- 状态: ✅ VALIDATED
### 2026-06-03: Hopper-v4 (5 seeds, test)
- score: 785.9 ± 228.2
- 备注: 双Critic方差分解+注意力状态不确定性. 5 seeds: 1031,229,1083,310,1027. 双峰分布(3 seeds ~1030, 2 seeds ~230-310).
- 状态: ✅ VALIDATED
