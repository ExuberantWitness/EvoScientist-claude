# Code Proposals — W6 综合讨论

基于四个Agent的讨论，以下是从讨论中的方案提炼出的可实现代码提案。按Phase 0→1→2→3顺序排列。

---

## Phase 0: 管线修复（紧急 — 立即执行）

### P0.1: 添加观测与奖励归一化

**来源**: Conservative-Engineering 提案A（一致共识）

```python
# === 修复: 添加归一化包装器 ===
import gymnasium as gym
from gymnasium.wrappers import NormalizeObservation, NormalizeReward, TransformReward

def make_env():
    env = gym.make("Hopper-v4")
    env = NormalizeObservation(env)
    # NormalizeReward有风险影响SAC的α自适应，建议先只用NormalizeObservation
    env = NormalizeReward(env, gamma=0.99)
    return env
```

**预期效果**: DDPG 1031.8 → 1500-2000; SAC 436.6 → 1500-2500

### P0.2: 修正终止/截断处理

**来源**: Conservative-Engineering 提案A

```python
# === 修复前（错误 — 所有done都阻止bootstrapping）===
if done:
    target = reward
else:
    target = reward + gamma * next_q * (1 - done)

# === 修复后（正确）===
# 仅当episode自然终止（摔倒）时不bootstrapping
# 截断（达到max_steps）仍然bootstrapping
if terminated:
    target = reward
else:
    target = reward + gamma * next_q  # truncated时也可bootstrapping
```

### P0.3: 校验SAC超参数

**来源**: Conservative-Engineering 

```python
# SAC验证配置
config = {
    "actor_lr": 3e-4,
    "critic_lr": 3e-4,
    "alpha_lr": 3e-4,     # 自适应α
    "gamma": 0.99,
    "tau": 0.005,
    "hidden_dim": 256,
    "batch_size": 256,
    "buffer_size": 1_000_000,
    "n_hidden_layers": 2,
}
```

---

## Phase 1: DDPG + 裁剪双Q（最小TD3借用）

### P1.1: 裁剪双Q实现

**来源**: Conservative-Engineering 提案C；Novel-Academic认同需要

```python
# === 追加到DDPG训练循环 ===

class DDPGDoubleCritic(nn.Module):
    def __init__(self, state_dim, action_dim, hidden_dim=256):
        super().__init__()
        self.q1 = MLP(state_dim + action_dim, hidden_dim, 1)
        self.q2 = MLP(state_dim + action_dim, hidden_dim, 1)

    def forward(self, state, action):
        x = torch.cat([state, action], dim=-1)
        return self.q1(x), self.q2(x)

# 更新时：
q1, q2 = critic(states, actions)
with torch.no_grad():
    next_actions = target_actor(next_states)
    next_q1, next_q2 = target_critic(next_states, next_actions)
    target_q = torch.min(next_q1, next_q2)  # Clipped double-Q
    target = rewards + gamma * target_q * (1 - terminated.float())
    
critic_loss = F.mse_loss(q1, target) + F.mse_loss(q2, target)

# Actor更新仍用Q1（或min(Q1,Q2)）
actor_loss = -critic.q1(states, actor(states)).mean()
```

**成本**: ~25行，0新超参数

---

## Phase 2: 接触门控探索 (CGE-Hybrid)

### P2.1: ContactNet + 门控探索

**来源**: Novel-Engineering 提案1；Novel-Academic 提案1（IGH-AC）

```python
# === 核心创新：接触门控探索 ===

class ContactGate(nn.Module):
    """预测足地接触概率，用于门控探索"""
    def __init__(self, state_dim, hidden_dim=64):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )
        # 初始偏置~-2使得contact_prob≈0.12（保守启动）
        nn.init.constant_(self.net[-1].bias, -2.0)
        
    def forward(self, state):
        return torch.sigmoid(self.net(state))

class ContactGatedDDPGPolicy(nn.Module):
    def __init__(self, state_dim, action_dim):
        super().__init__()
        self.deterministic = MLP(state_dim, 256, action_dim)  # DDPG主策略
        self.contact_gate = ContactGate(state_dim)
        self.log_std = nn.Parameter(torch.ones(action_dim) * -2.0)
        
    def forward(self, state, explore=True):
        mu = self.deterministic(state)
        if not explore:
            return torch.tanh(mu)
        
        contact_prob = self.contact_gate(state)
        noise = torch.randn_like(mu) * self.log_std.exp()
        
        # 仅在接触附近注入噪声
        action = mu + contact_prob * noise
        return torch.tanh(action)
```

**接触门控训练**: 自监督——使用MuJoCo接触传感器作为真值

```python
def train_contact_gate(contact_net, replay_buffer):
    """自监督训练ContactNet"""
    batch = replay_buffer.sample(256)
    states = batch.states
    
    # 真值：下一个时间步足传感器是否接触
    # MuJoCo Hopper-v4: foot_force = obs[10] 或接触传感器
    contact_gt = (batch.next_obs[:, 10] > 0.01).float().unsqueeze(-1)
    
    contact_pred = contact_net(states)
    loss = F.binary_cross_entropy(contact_pred, contact_gt)
    return loss
```

**预期效果**: DDPG 1031.8 → 1200-1300，约20-30%提升

---

## Phase 3: 高级方案（可选 — 高风险高回报）

### P3.1: ASP-SVD 动作子空间投影探索

**来源**: Novel-Engineering 提案2

```python
def get_exploration_basis(policy, state, k=2):
    """策略Jacobian的SVD → 探索基"""
    state.requires_grad_(True)
    action = policy(state)
    
    # 计算da/ds Jacobian
    J = torch.zeros(action.shape[-1], state.shape[-1])
    for i in range(action.shape[-1]):
        grad = torch.autograd.grad(action[0, i], state, retain_graph=True)[0]
        J[i] = grad[0]
    
    U, S, Vh = torch.linalg.svd(J, full_matrices=False)
    basis = U[:, :k] * S[:k]  # top-k方向，按奇异值加权
    return basis

def structured_noise(policy, state, base_std=0.1, k=2):
    """在可控子空间中投影的探索噪声"""
    basis = get_exploration_basis(policy, state, k)
    low_dim_noise = torch.randn(k)
    structured = basis @ low_dim_noise
    nullspace = torch.randn(state.shape[-1]) * 0.05  # 5%残差
    return base_std * (structured + nullspace)
```

**预期效果**: DDPG 1031.8 → 1150-1300

### P3.2: VEL-Recovery 值熵监测与恢复

**来源**: Novel-Engineering 提案3

```python
def detect_value_collapse(q_net, state, n_samples=64, threshold=0.3):
    """检测Q函数是否崩塌为平坦"""
    with torch.no_grad():
        mu = policy(state)
        actions = mu + 0.1 * torch.randn(n_samples, action_dim)
        states_expanded = state.expand(n_samples, -1)
        q_values = q_net(states_expanded, actions)
        probs = F.softmax(q_values / 0.1, dim=0)
        entropy = -(probs * torch.log(probs + 1e-8)).sum()
        norm_entropy = entropy / math.log(n_samples)
        return norm_entropy < threshold, norm_entropy

def trigger_recovery(optimizer):
    """重启优化器LR，重置探索参数"""
    for group in optimizer.param_groups:
        group['lr'] = group['initial_lr']
    # 可选：重置policy的log_std
    # policy.log_std.data.fill_(-2.0)
```

**预期效果**: 消除~400分种子。最差种子从~400→~700+

---

## 优先级总结

| Phase | 提案 | 代码行 | 新超参 | 风险 | 预期Δ均值 | 前置依赖 |
|-------|------|--------|--------|------|----------|---------|
| **P0** | 管线修复 | ~10 | 0 | 极低 | 3-5× (全部算法) | 无 |
| **P1** | 裁剪双Q | ~25 | 0 | 低 | 16-55% | 建议P0先 |
| **P2** | 接触门控 | ~60 | 1 | 中 | 20-30% | 建议P0先 |
| **P3.1** | SVD探索 | ~40 | 1 | 中高 | 15-25% | P2更好 |
| **P3.2** | 崩塌恢复 | ~50 | 2 | 中 | 最差种子~300分提升 | P1更好 |

**强烈建议**: 先执行P0，验证SAC/TD3/DDPG恢复正常范围后再推进更高Phase。

**Phase 0后重新评估**: 如果DDPG达到1500+，则P1/P2的目标变为1750-2300。基线越高，改进信号越清晰。
