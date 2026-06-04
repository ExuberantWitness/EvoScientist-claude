---
algo_id: iqn_quantile_simple
name: IQN Quantile Simple (简化版)
status: VALIDATED
created: 2026-06-02
iteration: 1
---

# IQN Quantile Simple

IQN简化版: 仅使用交叉分位数方差 (无 heteroscedastic var_net)。

- **Actor**: StochasticActor (复用)
- **Critics**: 2x QuantileQNetwork (n_quantiles=32)
- **Uncertainty**: 仅 quantile_variance → sigmoid((var - threshold)/temperature) → alpha_effective
- **Hyperparams**: lambda_unc=0.5, threshold=0.01, temperature=0.1

## 实验历史 (只追加, 不修改)

### 2026-06-03: Hopper-v4 (5 seeds, test)
- score: 820.4 ± 446.0
- 备注: IQN简化版(仅分位数方差,无异方差网络). 5 seeds: 664,945,793,1000,275. 高方差但单seed最高1360.
- 状态: ✅ VALIDATED
### 2026-06-03: Hopper-v4 (5 seeds, test)
- score: 820.4 ± 446.0
- 备注: IQN简化版(仅分位数方差,无异方差网络). 5 seeds: 664,945,793,1000,275. 高方差但单seed最高1360.
- 状态: ✅ VALIDATED
