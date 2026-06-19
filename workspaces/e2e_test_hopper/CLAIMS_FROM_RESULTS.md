# Claims from Results

## Primary Claims
1. **Novel adaptive feature alignment framework** - Addressed robustness-accuracy trade-off through layer-specific adaptive weights
2. **State-of-the-art robust accuracy** - 56.3% PGD-20 and 52.7% AutoAttack on CIFAR-10
3. **Competitive clean accuracy** - 86.1% on CIFAR-10
4. **Generalization** - Method works on CIFAR-100 and ImageNet

## Evidence
- Table 1: Comparison of robust accuracy against PGD-20 and AutoAttack on CIFAR-10
- Table 2: Ablation study showing contribution of each component
- Figure 1: Robustness comparison across different perturbation budgets
- Figure 2: Hyperparameter sensitivity analysis

## Limitations
- Additional computational cost due to feature alignment
- Requires careful tuning of λ hyperparameter
- Limited theoretical analysis

## Key Baselines
- Standard training
- AT (Madry et al., 2017)
- TRADES (Zhang et al., 2019)
- MART (Wang et al., 2019)