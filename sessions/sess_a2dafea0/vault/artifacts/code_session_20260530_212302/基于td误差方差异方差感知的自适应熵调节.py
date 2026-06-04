"""
TD Variance-Aware Adaptive Entropy Agent (ELO #2).

Key idea: Replace fixed entropy coefficient alpha with a dynamic beta that
adapts to the TD error variance. High TD error variance = unstable region
→ reduce entropy penalty (exploit more cautiously). Low variance →
increase entropy (explore more freely).

Mechanism: AdaptiveBetaBuffer tracks EMA of squared TD errors globally.
beta = beta_0 / (1 + momentum * var_ema).
"""

import torch
import torch.nn.functional as F
import numpy as np
from copy import deepcopy
from typing import Dict

from networks import StochasticActor, QNetwork, soft_update, hard_update


class AdaptiveBetaBuffer:
    """Tracks EMA of TD error variance to produce dynamic entropy coefficient."""

    def __init__(self, alpha: float = 0.99, beta_min: float = 0.01, beta_max: float = 1.0):
        self.alpha = alpha
        self.beta_min = beta_min
        self.beta_max = beta_max
        self.var_ema = 0.0

    def update(self, td_error: torch.Tensor):
        sq = (td_error ** 2).mean().item()
        self.var_ema = self.alpha * self.var_ema + (1 - self.alpha) * sq

    def get_beta(self, momentum_factor: float = 0.5) -> float:
        var_mean = self.var_ema
        beta = 1.0 / (1.0 + momentum_factor * var_mean)
        return max(self.beta_min, min(self.beta_max, beta))


class TDVarianceAgent:
    """SAC-based agent with TD-error variance modulated entropy coefficient."""

    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        max_action: float = 1.0,
        actor_hidden: list = None,
        critic_hidden: list = None,
        gamma: float = 0.99,
        tau: float = 0.005,
        actor_lr: float = 3e-4,
        critic_lr: float = 3e-4,
        alpha_lr: float = 3e-4,
        alpha_init: float = 0.2,
        alpha_auto_tune: bool = True,
        target_entropy: float = None,
        device: str = "cuda",
        # TD Variance specific
        beta_ema_alpha: float = 0.99,
        beta_momentum: float = 0.5,
    ):
        if actor_hidden is None:
            actor_hidden = [256, 256]
        if critic_hidden is None:
            critic_hidden = [256, 256]

        self.device = device
        self.max_action = max_action
        self.action_dim = action_dim
        self.gamma = gamma
        self.tau = tau
        self.alpha_auto_tune = alpha_auto_tune

        if target_entropy is None:
            self.target_entropy = -action_dim
        else:
            self.target_entropy = target_entropy

        # Networks: SAC backbone
        self.actor = StochasticActor(
            obs_dim, action_dim, actor_hidden, max_action=max_action,
            log_std_min=-20, log_std_max=2
        ).to(device)

        self.critic1 = QNetwork(obs_dim, action_dim, critic_hidden).to(device)
        self.critic2 = QNetwork(obs_dim, action_dim, critic_hidden).to(device)
        self.critic1_target = deepcopy(self.critic1)
        self.critic2_target = deepcopy(self.critic2)

        # Temperature
        self.log_alpha = torch.tensor(np.log(alpha_init), requires_grad=True, device=device)

        # Optimizers
        self.actor_optimizer = torch.optim.Adam(self.actor.parameters(), lr=actor_lr)
        self.critic_optimizer = torch.optim.Adam(
            list(self.critic1.parameters()) + list(self.critic2.parameters()),
            lr=critic_lr
        )
        self.alpha_optimizer = torch.optim.Adam([self.log_alpha], lr=alpha_lr)

        # TD variance tracking
        self.beta_buffer = AdaptiveBetaBuffer(alpha=beta_ema_alpha)
        self.beta_momentum = beta_momentum

        self._step_count = 0

    def select_action(self, obs: np.ndarray, deterministic: bool = False) -> np.ndarray:
        obs_t = torch.FloatTensor(obs).unsqueeze(0).to(self.device)
        with torch.no_grad():
            action, _ = self.actor.sample(obs_t, deterministic=deterministic)
        return action.cpu().numpy().flatten()

    def train(self, replay_buffer, batch_size: int = 256) -> Dict[str, float]:
        self._step_count += 1

        obs, actions, rewards, next_obs, dones = replay_buffer.sample(batch_size)

        # --- Critic update ---
        with torch.no_grad():
            next_actions, next_log_probs = self.actor.sample(next_obs)
            q1_next = self.critic1_target(next_obs, next_actions)
            q2_next = self.critic2_target(next_obs, next_actions)
            min_q_next = torch.min(q1_next, q2_next)

            # Dynamic beta from TD variance
            beta_val = self.beta_buffer.get_beta(self.beta_momentum)
            target_q = rewards + self.gamma * (1 - dones) * (min_q_next - beta_val * next_log_probs)

        q1 = self.critic1(obs, actions)
        q2 = self.critic2(obs, actions)
        critic_loss = F.mse_loss(q1, target_q) + F.mse_loss(q2, target_q)

        self.critic_optimizer.zero_grad()
        critic_loss.backward()
        self.critic_optimizer.step()

        # --- Actor update ---
        new_actions, log_probs = self.actor.sample(obs)
        q1_new = self.critic1(obs, new_actions)
        q2_new = self.critic2(obs, new_actions)
        min_q_new = torch.min(q1_new, q2_new)

        beta = self.beta_buffer.get_beta(self.beta_momentum)
        actor_loss = (beta * log_probs - min_q_new).mean()

        self.actor_optimizer.zero_grad()
        actor_loss.backward()
        self.actor_optimizer.step()

        # --- Alpha auto-tune (SAC-style, modulated by TD variance) ---
        if self.alpha_auto_tune:
            alpha_loss = -(self.log_alpha.exp() * (log_probs.detach() + self.target_entropy)).mean()

            self.alpha_optimizer.zero_grad()
            alpha_loss.backward()
            self.alpha_optimizer.step()

        # --- Soft target updates ---
        soft_update(self.critic1_target, self.critic1, self.tau)
        soft_update(self.critic2_target, self.critic2, self.tau)

        # --- Update TD variance buffer ---
        with torch.no_grad():
            td_error = rewards + self.gamma * min_q_next.detach() - min_q_new.detach()
            self.beta_buffer.update(td_error)

        alpha = self.log_alpha.exp().item()

        return {
            "critic_loss": critic_loss.item(),
            "actor_loss": actor_loss.item(),
            "alpha": alpha,
            "beta": beta,
            "td_var_ema": self.beta_buffer.var_ema,
            "q1_mean": q1.mean().item(),
            "q2_mean": q2.mean().item(),
            "entropy": -log_probs.mean().item(),
        }

    def save(self, path: str):
        torch.save({
            "actor": self.actor.state_dict(),
            "critic1": self.critic1.state_dict(),
            "critic2": self.critic2.state_dict(),
            "critic1_target": self.critic1_target.state_dict(),
            "critic2_target": self.critic2_target.state_dict(),
            "log_alpha": self.log_alpha.item(),
            "actor_optimizer": self.actor_optimizer.state_dict(),
            "critic_optimizer": self.critic_optimizer.state_dict(),
            "alpha_optimizer": self.alpha_optimizer.state_dict(),
        }, path)

    def load(self, path: str):
        ckpt = torch.load(path, map_location=self.device)
        self.actor.load_state_dict(ckpt["actor"])
        self.critic1.load_state_dict(ckpt["critic1"])
        self.critic2.load_state_dict(ckpt["critic2"])
        self.critic1_target.load_state_dict(ckpt["critic1_target"])
        self.critic2_target.load_state_dict(ckpt["critic2_target"])
        self.log_alpha.data = torch.tensor(ckpt["log_alpha"], device=self.device)
        self.actor_optimizer.load_state_dict(ckpt["actor_optimizer"])
        self.critic_optimizer.load_state_dict(ckpt["critic_optimizer"])
        self.alpha_optimizer.load_state_dict(ckpt["alpha_optimizer"])
