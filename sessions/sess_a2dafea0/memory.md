# EvoScientist Research Memory

Topic: 如何改进actor critic算法提升Hopper-v4控制能力

## W2 问题分析 — 2026-05-30 20:51

### Deliverables
- **invoke_four_personas** (persona_proposals): Persona proposals: 4
- **evaluate_novelty** (evaluate_novelty): RND+Rubric完成: 4提案, verified_novelty=[5.0, 4.7, 5.4, 4.5]
- **elo_tournament** (elo_tournament): ELO排序完成: 4方案, 胜者基于状态值方差与动作离散度的混合自适应熵正则化AC算法
- **verify_products** (verify_products): Verdict: pass
- **evolution_memory** (evolution_memory): EM已记录 (type=ide)
- **write_claim_chain** (write_claim_chain): CC写入: 0 atoms, 0 relations

### Top Proposals
1. 基于状态值方差与动作离散度的混合自适应熵正则化AC算法 (Elo: 1546)
2. 基于值函数不确定性量化的自适应熵调节AC算法 (Elo: 1517)
3. AC算法中基于时序差分误差方差异方差的自适应熵调节方法 (Elo: 1483)

---
## W3 方案方向 — 2026-05-30 20:54

### Deliverables
- **invoke_four_personas** (persona_proposals): Persona proposals: 4
- **evaluate_novelty** (evaluate_novelty): RND+Rubric完成: 4提案, verified_novelty=[5.5, 5.7, 6.1, 5.5]
- **elo_tournament** (elo_tournament): ELO排序完成: 4方案, 胜者基于动态规划深度与交互熵的混合异方差自适应AC算法
- **verify_products** (verify_products): Verdict: pass
- **evolution_memory** (evolution_memory): EM已记录 (type=ide)
- **write_claim_chain** (write_claim_chain): CC写入: 0 atoms, 0 relations

### Top Proposals
1. 基于动态规划深度与交互熵的混合异方差自适应AC算法 (Elo: 1546)
2. 跨步态相位时序差分噪声驱动的动态熵调节AC算法 (Elo: 1515)
3. 基于Taylor展开的局部熵曲率自适应AC算法 (Elo: 1483)

---
## W4 具体方案生成 — 2026-05-30 21:00

### Deliverables
- **invoke_four_personas** (persona_proposals): Persona proposals: 4
- **evaluate_novelty** (evaluate_novelty): RND+Rubric完成: 4提案, verified_novelty=[5.0, 5.5, 4.9, 5.0]
- **elo_tournament** (elo_tournament): ELO排序完成: 4方案, 胜者基于注意力机制与状态先验不确定性的自适应熵调节AC算法
- **verify_products** (verify_products): Verdict: pass
- **evolution_memory** (evolution_memory): EM已记录 (type=ide)
- **write_claim_chain** (write_claim_chain): CC写入: 0 atoms, 0 relations

### Top Proposals
1. 基于注意力机制与状态先验不确定性的自适应熵调节AC算法 (Elo: 1546)
2. 基于TD误差方差异方差感知的自适应熵调节AC算法 (Elo: 1515)
3. novel-engineering-agent proposal (Elo: 1486)

---
## W5 代码实现 — 2026-06-02 07:45

### Top Proposals
1. 基于注意力机制与状态先验不确定性的自适应熵调节AC算法 (Elo: 1546)
2. 基于TD误差方差异方差感知的自适应熵调节AC算法 (Elo: 1515)
3. novel-engineering-agent proposal (Elo: 1486)

---
## W2 问题分析 — 2026-06-02 15:27

### Deliverables
- **invoke_four_personas** (persona_proposals): Persona proposals: 4
- **evaluate_novelty** (evaluate_novelty): RND+Rubric完成: 4提案, verified_novelty=[5.0, 4.7, 5.4, 4.5]
- **elo_tournament** (elo_tournament): ELO排序完成: 4方案, 胜者基于状态值方差与动作离散度的混合自适应熵正则化AC算法
- **verify_products** (verify_products): Verdict: pass
- **evolution_memory** (evolution_memory): EM已记录 (type=ide)
- **write_claim_chain** (write_claim_chain): CC写入: 0 atoms, 0 relations
- **invoke_four_personas** (persona_proposals): Persona proposals: 4
- **invoke_four_personas** (persona_proposals): Persona proposals: 4
- **invoke_four_personas** (persona_proposals): Persona proposals: 4
- **invoke_four_personas** (persona_proposals): Persona proposals: 4
- **invoke_four_personas** (persona_proposals): Persona proposals: 4
- **evaluate_novelty** (evaluate_novelty): RND+Rubric完成: 4提案, verified_novelty=[5.6, 6.0, 5.2, 5.1]
- **elo_tournament** (elo_tournament): ELO排序完成: 4方案, 胜者基于相位耦合双Q方差对齐与力矩残差学习的自适应熵AC算法
- **verify_products** (verify_products): Verdict: pass
- **evolution_memory** (evolution_memory): EM已记录 (type=ide)

### Top Proposals
1. 基于相位耦合双Q方差对齐与力矩残差学习的自适应熵AC算法 (Elo: 1545)
2. 基于相位调制动作分布与双Q不确定性对齐的Hopper-v4自适应熵AC算法 (Elo: 1517)
3. 基于相位耦合双Q方差对齐与力矩残差学习的自适应熵AC算法 (Elo: 1485)

### Experiment Results
| Algorithm | Mean | N |
|-----------|------|---|
| attention_prior | 562.3 | 2 |
| ddpg | 1009.6 | 2 |
| dp_depth | 985.1 | 2 |
| gait_phase | 967.5 | 2 |
| sac | 387.6 | 2 |
| taylor_curvature | 789.6 | 2 |
| td3 | 707.0 | 2 |
| td_variance | 854.5 | 2 |
| value_uncertainty | 688.8 | 2 |

---
## W3 方案方向 — 2026-06-02 15:31

### Deliverables
- **invoke_four_personas** (persona_proposals): Persona proposals: 4
- **evaluate_novelty** (evaluate_novelty): RND+Rubric完成: 4提案, verified_novelty=[5.5, 5.7, 6.1, 5.5]
- **elo_tournament** (elo_tournament): ELO排序完成: 4方案, 胜者基于动态规划深度与交互熵的混合异方差自适应AC算法
- **verify_products** (verify_products): Verdict: pass
- **evolution_memory** (evolution_memory): EM已记录 (type=ide)
- **write_claim_chain** (write_claim_chain): CC写入: 0 atoms, 0 relations
- **invoke_four_personas** (persona_proposals): Persona proposals: 4
- **evaluate_novelty** (evaluate_novelty): RND+Rubric完成: 4提案, verified_novelty=[5.2, 5.1, 5.1, 5.1]
- **elo_tournament** (elo_tournament): ELO排序完成: 4方案, 胜者基于价值分布分位数方差的自适应熵调节AC算法
- **verify_products** (verify_products): Verdict: pass
- **evolution_memory** (evolution_memory): EM已记录 (type=ide)

### Top Proposals
1. 基于价值分布分位数方差的自适应熵调节AC算法 (Elo: 1546)
2. 基于轨迹片段优势函数值方差的自适应熵调节AC算法 (Elo: 1485)
3. 基于轨迹片段优势值方差的自适应熵调节AC算法 (Elo: 1485)

### Experiment Results
| Algorithm | Mean | N |
|-----------|------|---|
| attention_prior | 562.3 | 2 |
| ddpg | 1009.6 | 2 |
| dp_depth | 985.1 | 2 |
| gait_phase | 967.5 | 2 |
| sac | 387.6 | 2 |
| taylor_curvature | 789.6 | 2 |
| td3 | 707.0 | 2 |
| td_variance | 854.5 | 2 |
| value_uncertainty | 688.8 | 2 |

---
## W4 具体方案生成 — 2026-06-02 15:34

### Deliverables
- **invoke_four_personas** (persona_proposals): Persona proposals: 4
- **evaluate_novelty** (evaluate_novelty): RND+Rubric完成: 4提案, verified_novelty=[5.0, 5.5, 4.9, 5.0]
- **elo_tournament** (elo_tournament): ELO排序完成: 4方案, 胜者基于注意力机制与状态先验不确定性的自适应熵调节AC算法
- **verify_products** (verify_products): Verdict: pass
- **evolution_memory** (evolution_memory): EM已记录 (type=ide)
- **write_claim_chain** (write_claim_chain): CC写入: 0 atoms, 0 relations
- **invoke_four_personas** (persona_proposals): Persona proposals: 4
- **evaluate_novelty** (evaluate_novelty): RND+Rubric完成: 4提案, verified_novelty=[5.0, 4.8, 4.4, 4.8]
- **elo_tournament** (elo_tournament): ELO排序完成: 4方案, 胜者基于分位数价值方差与TD误差异方差的自适应熵调节AC算法
- **verify_products** (verify_products): Verdict: pass
- **evolution_memory** (evolution_memory): EM已记录 (type=ide)

### Top Proposals
1. 基于分位数价值方差与TD误差异方差的自适应熵调节AC算法 (Elo: 1546)
2. 基于分位价值方差与TD误差异方差的自适应熵调节AC算法 (Elo: 1515)
3. 基于双Critic方差分解与注意力状态不确定性的自适应熵调节AC算法 (Elo: 1485)

### Experiment Results
| Algorithm | Mean | N |
|-----------|------|---|
| attention_prior | 562.3 | 2 |
| ddpg | 1009.6 | 2 |
| dp_depth | 985.1 | 2 |
| gait_phase | 967.5 | 2 |
| sac | 387.6 | 2 |
| taylor_curvature | 789.6 | 2 |
| td3 | 707.0 | 2 |
| td_variance | 854.5 | 2 |
| value_uncertainty | 688.8 | 2 |

---
## W5 代码实现 — 2026-06-03 15:26

### Top Proposals
1. 基于分位数价值方差与TD误差异方差的自适应熵调节AC算法 (Elo: 1546)
2. 基于分位价值方差与TD误差异方差的自适应熵调节AC算法 (Elo: 1515)
3. 基于双Critic方差分解与注意力状态不确定性的自适应熵调节AC算法 (Elo: 1485)

### Experiment Results
| Algorithm | Mean | N |
|-----------|------|---|
| attention_prior | 562.3 | 2 |
| ddpg | 1009.6 | 2 |
| dp_depth | 985.1 | 2 |
| gait_phase | 967.5 | 2 |
| sac | 387.6 | 2 |
| taylor_curvature | 789.6 | 2 |
| td3 | 707.0 | 2 |
| td_variance | 854.5 | 2 |
| value_uncertainty | 688.8 | 2 |

---
## W2 问题分析 — 2026-06-03 21:33

### Deliverables
- **invoke_four_personas** (persona_proposals): Persona proposals: 4
- **evaluate_novelty** (evaluate_novelty): RND+Rubric完成: 4提案, verified_novelty=[5.0, 4.7, 5.4, 4.5]
- **elo_tournament** (elo_tournament): ELO排序完成: 4方案, 胜者基于状态值方差与动作离散度的混合自适应熵正则化AC算法
- **verify_products** (verify_products): Verdict: pass
- **evolution_memory** (evolution_memory): EM已记录 (type=ide)
- **write_claim_chain** (write_claim_chain): CC写入: 0 atoms, 0 relations
- **invoke_four_personas** (persona_proposals): Persona proposals: 4
- **invoke_four_personas** (persona_proposals): Persona proposals: 4
- **invoke_four_personas** (persona_proposals): Persona proposals: 4
- **invoke_four_personas** (persona_proposals): Persona proposals: 4
- **invoke_four_personas** (persona_proposals): Persona proposals: 4
- **evaluate_novelty** (evaluate_novelty): RND+Rubric完成: 4提案, verified_novelty=[5.6, 6.0, 5.2, 5.1]
- **elo_tournament** (elo_tournament): ELO排序完成: 4方案, 胜者基于相位耦合双Q方差对齐与力矩残差学习的自适应熵AC算法
- **verify_products** (verify_products): Verdict: pass
- **evolution_memory** (evolution_memory): EM已记录 (type=ide)
- **invoke_four_personas** (persona_proposals): Persona proposals: 4
- **evaluate_novelty** (evaluate_novelty): RND+Rubric完成: 4提案, verified_novelty=[4.0, 5.7, 5.9, 5.0]
- **elo_tournament** (elo_tournament): ELO排序完成: 4方案, 胜者基于多尺度时序差分梯度方差解耦与状态条件熵调制的Hopper-v4 AC算法
- **verify_products** (verify_products): Verdict: pass
- **evolution_memory** (evolution_memory): EM已记录 (type=ide)

### Top Proposals
1. 基于多尺度时序差分梯度方差解耦与状态条件熵调制的Hopper-v4 AC算法 (Elo: 1546)
2. 基于双Critic分位数方差与状态条件梯度融合的Hopper-v4 AC算法 (Elo: 1500)
3. 基于状态依赖TD误差分位数方差与双Critic自适应融合的Hopper-v4 AC算法 (Elo: 1499)

### Experiment Results
| Algorithm | Mean | N |
|-----------|------|---|
| attention_prior | 562.3 | 2 |
| ddpg | 1009.6 | 2 |
| dp_depth | 985.1 | 2 |
| dual_critic_attention | 785.9 | 3 |
| gait_phase | 967.5 | 2 |
| iqn_quantile | 0.0 | 3 |
| iqn_quantile_simple | 820.4 | 3 |
| sac | 387.6 | 2 |
| taylor_curvature | 789.6 | 2 |
| td3 | 707.0 | 2 |

---
## W3 方案方向 — 2026-06-03 21:55

### Deliverables
- **invoke_four_personas** (persona_proposals): Persona proposals: 4
- **evaluate_novelty** (evaluate_novelty): RND+Rubric完成: 4提案, verified_novelty=[5.5, 5.7, 6.1, 5.5]
- **elo_tournament** (elo_tournament): ELO排序完成: 4方案, 胜者基于动态规划深度与交互熵的混合异方差自适应AC算法
- **verify_products** (verify_products): Verdict: pass
- **evolution_memory** (evolution_memory): EM已记录 (type=ide)
- **write_claim_chain** (write_claim_chain): CC写入: 0 atoms, 0 relations
- **invoke_four_personas** (persona_proposals): Persona proposals: 4
- **evaluate_novelty** (evaluate_novelty): RND+Rubric完成: 4提案, verified_novelty=[5.2, 5.1, 5.1, 5.1]
- **elo_tournament** (elo_tournament): ELO排序完成: 4方案, 胜者基于价值分布分位数方差的自适应熵调节AC算法
- **verify_products** (verify_products): Verdict: pass
- **evolution_memory** (evolution_memory): EM已记录 (type=ide)
- **invoke_four_personas** (persona_proposals): Persona proposals: 4
- **evaluate_novelty** (evaluate_novelty): RND+Rubric完成: 4提案, verified_novelty=[5.7, 5.1, 5.0, 5.2]
- **elo_tournament** (elo_tournament): ELO排序完成: 4方案, 胜者基于动作熵与值函数不确定性联合量化的自适应探索AC算法
- **verify_products** (verify_products): Verdict: pass
- **evolution_memory** (evolution_memory): EM已记录 (type=ide)

### Top Proposals
1. 基于动作熵与值函数不确定性联合量化的自适应探索AC算法 (Elo: 1545)
2. 基于值函数梯度范数与双Critic分位数方差融合的自适应探索AC算法 (Elo: 1499)
3. 基于值函数梯度的自适应噪声与熵联合调度AC算法 (Elo: 1485)

### Experiment Results
| Algorithm | Mean | N |
|-----------|------|---|
| attention_prior | 562.3 | 2 |
| ddpg | 1009.6 | 2 |
| dp_depth | 985.1 | 2 |
| dual_critic_attention | 785.9 | 3 |
| gait_phase | 967.5 | 2 |
| iqn_quantile | 0.0 | 3 |
| iqn_quantile_simple | 820.4 | 3 |
| sac | 387.6 | 2 |
| taylor_curvature | 789.6 | 2 |
| td3 | 707.0 | 2 |

---
## W4 具体方案生成 — 2026-06-03 22:06

### Deliverables
- **invoke_four_personas** (persona_proposals): Persona proposals: 4
- **evaluate_novelty** (evaluate_novelty): RND+Rubric完成: 4提案, verified_novelty=[5.0, 5.5, 4.9, 5.0]
- **elo_tournament** (elo_tournament): ELO排序完成: 4方案, 胜者基于注意力机制与状态先验不确定性的自适应熵调节AC算法
- **verify_products** (verify_products): Verdict: pass
- **evolution_memory** (evolution_memory): EM已记录 (type=ide)
- **write_claim_chain** (write_claim_chain): CC写入: 0 atoms, 0 relations
- **invoke_four_personas** (persona_proposals): Persona proposals: 4
- **evaluate_novelty** (evaluate_novelty): RND+Rubric完成: 4提案, verified_novelty=[5.0, 4.8, 4.4, 4.8]
- **elo_tournament** (elo_tournament): ELO排序完成: 4方案, 胜者基于分位数价值方差与TD误差异方差的自适应熵调节AC算法
- **verify_products** (verify_products): Verdict: pass
- **evolution_memory** (evolution_memory): EM已记录 (type=ide)
- **invoke_four_personas** (persona_proposals): Persona proposals: 4
- **evaluate_novelty** (evaluate_novelty): RND+Rubric完成: 4提案, verified_novelty=[5.4, 5.0, 4.8, 4.2]
- **elo_tournament** (elo_tournament): ELO排序完成: 4方案, 胜者基于分位数方差与梯度范数融合的状态依赖自适应探索AC算法
- **verify_products** (verify_products): Verdict: pass
- **evolution_memory** (evolution_memory): EM已记录 (type=ide)

### Top Proposals
1. 基于分位数方差与梯度范数融合的状态依赖自适应探索AC算法 (Elo: 1545)
2. 基于分位数方差与梯度范数融合的状态依赖自适应探索AC算法 (Elo: 1516)
3. 基于分位数方差与梯度范数融合的状态依赖自适应探索AC算法 (Elo: 1485)

### Experiment Results
| Algorithm | Mean | N |
|-----------|------|---|
| attention_prior | 562.3 | 2 |
| ddpg | 1009.6 | 2 |
| dp_depth | 985.1 | 2 |
| dual_critic_attention | 785.9 | 3 |
| gait_phase | 967.5 | 2 |
| iqn_quantile | 0.0 | 3 |
| iqn_quantile_simple | 820.4 | 3 |
| sac | 387.6 | 2 |
| taylor_curvature | 789.6 | 2 |
| td3 | 707.0 | 2 |

---
