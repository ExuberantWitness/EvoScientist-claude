"""
Dual-Critic Variance Decomposition + Attention State Uncertainty Agent.

Key idea: Two orthogonal uncertainty signals:
  1. Epistemic: variance between twin Q-network predictions
  2. Aleatoric: self-attention over state features → learned state uncertainty

These are fused via a small alpha_net MLP to produce per-state entropy coefficient.
beta(s) = alpha * (1 + lambda_unc * fused_uncertainty(s))
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import math
from copy import deepcopy
from typing import Dict

from networks import StochasticActor, QNetwork, soft_update, hard_update


class AttentionUncertainty(nn.Module):
    """Self-attention over state batch for aleatoric uncertainty estimation."""

    def __init__(self, state_dim: int = 11, hidden_dim: int = 64):
        super().__init__()
        self.key = nn.Linear(state_dim, hidden_dim)
        self.query = nn.Linear(state_dim, hidden_dim)
        self.value = nn.Linear(state_dim, hidden_dim)
        self.fc_out = nn.Linear(hidden_dim, 1)
        self._scale = math.sqrt(hidden_dim)

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        """
        Args:
            state: (B, state_dim)
        Returns:
            uncertainty: (B, 1) in (0, 1)
        """
        B = state.shape[0]
        K = self.key(state).unsqueeze(1)    # (B, 1, H)
        Q = self.query(state).unsqueeze(1)   # (B, 1, H)
        V = self.value(state).unsqueeze(1)   # (B, 1, H)
        attn = torch.softmax(torch.matmul(Q, K.transpose(-2, -1)) / self._scale, dim=-1)
        out = torch.matmul(attn, V).squeeze(1)  # (B, H)
        return torch.sigmoid(self.fc_out(out))


class DualCriticAttentionAgent:
    """SAC variant with dual-critic variance + attention-based uncertainty."""

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
        # Uncertainty specific
        attention_hidden: int = 64,
        alpha_net_hidden: int = 64,
        lambda_unc: float = 0.5,
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
        self.lambda_unc = lambda_unc

        if target_entropy is None:
            self.target_entropy = -action_dim
        else:
            self.target_entropy = target_entropy

        self.actor = StochasticActor(
            obs_dim, action_dim, actor_hidden, max_action=max_action,
            log_std_min=-20, log_std_max=2
        ).to(device)

        self.critic1 = QNetwork(obs_dim, action_dim, critic_hidden).to(device)
        self.critic2 = QNetwork(obs_dim, action_dim, critic_hidden).to(device)
        self.critic1_target = deepcopy(self.critic1)
        self.critic2_target = deepcopy(self.critic2)

        self.attention_uncertainty = AttentionUncertainty(
            obs_dim, hidden_dim=attention_hidden
        ).to(device)

        self.alpha_net = nn.Sequential(
            nn.Linear(2, alpha_net_hidden), nn.ReLU(),
            nn.Linear(alpha_net_hidden, 1), nn.Sigmoid()
        ).to(device)

        self.log_alpha = torch.tensor(np.log(alpha_init), requires_grad=True, device=device)

        self.actor_optimizer = torch.optim.Adam(self.actor.parameters(), lr=actor_lr)
        self.critic_optimizer = torch.optim.Adam(
            list(self.critic1.parameters()) + list(self.critic2.parameters()),
            lr=critic_lr
        )
        self.alpha_optimizer = torch.optim.Adam([self.log_alpha], lr=alpha_lr)
        self.uncertainty_optimizer = torch.optim.Adam(
            list(self.attention_uncertainty.parameters()) +
            list(self.alpha_net.parameters()),
            lr=actor_lr
        )

        self._step_count = 0

    def select_action(self, obs: np.ndarray, deterministic: bool = False) -> np.ndarray:
        obs_t = torch.FloatTensor(obs).unsqueeze(0).to(self.device)
        with torch.no_grad():
            action, _ = self.actor.sample(obs_t, deterministic=deterministic)
        return action.cpu().numpy().flatten()

    def train(self, replay_buffer, batch_size: int = 256) -> Dict[str, float]:
        self._step_count += 1

        obs, actions, rewards, next_obs, dones = replay_buffer.sample(batch_size)
        alpha = self.log_alpha.exp()

        # --- Compute per-state uncertainty ---
        # Epistemic: twin-Q variance
        with torch.no_grad():
            q1_d = self.critic1(obs, actions)
            q2_d = self.critic2(obs, actions)
            epistemic = torch.var(torch.stack([q1_d, q2_d], dim=0), dim=0)  # (B, 1)
            epistemic_norm = torch.sigmoid(epistemic)  # (0, 1)

        # Aleatoric: attention over state
        aleatoric = self.attention_uncertainty(obs)  # (B, 1)

        # Fusion
        unc_cat = torch.cat([epistemic_norm, aleatoric], dim=-1)  # (B, 2)
        alpha_factor = self.alpha_net(unc_cat)  # (B, 1)

        # --- Critic update ---
        with torch.no_grad():
            next_actions, next_log_probs = self.actor.sample(next_obs)
            q1_next = self.critic1_target(next_obs, next_actions)
            q2_next = self.critic2_target(next_obs, next_actions)
            min_q_next = torch.min(q1_next, q2_next)

            alpha_val = alpha.detach()
            beta_next = alpha_val * (1.0 + self.lambda_unc * alpha_factor)  # (B, 1)

            target_q = rewards + self.gamma * (1 - dones) * (
                min_q_next - beta_next * next_log_probs
            )

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

        beta_state = alpha.detach() * (1.0 + self.lambda_unc * alpha_factor.detach())

        actor_loss = (beta_state * log_probs - min_q_new).mean()

        self.actor_optimizer.zero_grad()
        actor_loss.backward()
        self.actor_optimizer.step()

        # --- Alpha auto-tune ---
        alpha_loss_val = 0.0
        if self.alpha_auto_tune:
            alpha_loss = -(alpha * (log_probs.detach() + self.target_entropy)).mean()
            alpha_loss_val = alpha_loss.item()

            self.alpha_optimizer.zero_grad()
            alpha_loss.backward()
            self.alpha_optimizer.step()

        # --- Uncertainty module update (unsupervised) ---
        unc_loss = -alpha_factor.mean()
        self.uncertainty_optimizer.zero_grad()
        unc_loss.backward()
        self.uncertainty_optimizer.step()

        # --- Soft target updates ---
        soft_update(self.critic1_target, self.critic1, self.tau)
        soft_update(self.critic2_target, self.critic2, self.tau)

        return {
            "critic_loss": critic_loss.item(),
            "actor_loss": actor_loss.item(),
            "alpha_loss": alpha_loss_val,
            "alpha": alpha.item(),
            "alpha_factor_mean": alpha_factor.mean().item(),
            "epistemic_mean": epistemic.mean().item(),
            "aleatoric_mean": aleatoric.mean().item(),
            "q1_mean": q1.mean().item(),
            "entropy": -log_probs.mean().item(),
        }

    def save(self, path: str):
        torch.save({
            "actor": self.actor.state_dict(),
            "critic1": self.critic1.state_dict(),
            "critic2": self.critic2.state_dict(),
            "critic1_target": self.critic1_target.state_dict(),
            "critic2_target": self.critic2_target.state_dict(),
            "attention_uncertainty": self.attention_uncertainty.state_dict(),
            "alpha_net": self.alpha_net.state_dict(),
            "log_alpha": self.log_alpha.item(),
            "actor_optimizer": self.actor_optimizer.state_dict(),
            "critic_optimizer": self.critic_optimizer.state_dict(),
            "alpha_optimizer": self.alpha_optimizer.state_dict(),
            "uncertainty_optimizer": self.uncertainty_optimizer.state_dict(),
        }, path)

    def load(self, path: str):
        ckpt = torch.load(path, map_location=self.device)
        self.actor.load_state_dict(ckpt["actor"])
        self.critic1.load_state_dict(ckpt["critic1"])
        self.critic2.load_state_dict(ckpt["critic2"])
        self.critic1_target.load_state_dict(ckpt["critic1_target"])
        self.critic2_target.load_state_dict(ckpt["critic2_target"])
        self.attention_uncertainty.load_state_dict(ckpt["attention_uncertainty"])
        self.alpha_net.load_state_dict(ckpt["alpha_net"])
        self.log_alpha.data = torch.tensor(ckpt["log_alpha"], device=self.device)
        self.actor_optimizer.load_state_dict(ckpt["actor_optimizer"])
        self.critic_optimizer.load_state_dict(ckpt["critic_optimizer"])
        self.alpha_optimizer.load_state_dict(ckpt["alpha_optimizer"])
        self.uncertainty_optimizer.load_state_dict(ckpt["uncertainty_optimizer"])
