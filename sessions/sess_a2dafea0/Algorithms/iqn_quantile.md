---
algo_id: iqn_quantile
name: IQN Quantile (完整版, 异方差var_net)
status: REFUTED
created: 2026-06-02
iteration: 1
---

# IQN Quantile

完整 IQN + heteroscedastic variance adaptive entropy。

- **Actor**: StochasticActor (复用)
- **Critics**: 2x QuantileQNetwork (n_quantiles=32) + 2x target
- **var_net**: HeteroscedasticVarNet (MLP: 14→128→1) 预测 TD 误差 log-variance
- **Uncertainty**: quantile_var + lambda_hetero * predicted_var, batch-normalize → sigmoid → alpha_effective
- **Loss**: Quantile Huber loss + SAC actor loss + alpha auto-tune + var MSE loss
- **稳定性措施**: Gradient clipping (max_norm=10.0), beta clamping [0.001, 5.0], combined uncertainty clamp [-5,5], sigmoid output clamping

## 实验历史 (只追加, 不修改)

### 2026-06-03: Hopper-v4 (1 seeds, test)
- score: 0.0 ± 0.0
- 备注: 3次NaN崩溃(step ~390k, ~790k, ~480k). Heteroscedastic var_net根本不稳定. 最高return 1904(第1次)和985(第3次)但均未完成.
### 2026-06-03: Hopper-v4 (1 seeds, test)
- score: 0.0 ± 0.0
- 备注: 3次NaN崩溃(step ~390k, ~790k, ~480k). Heteroscedastic var_net根本不稳定.
