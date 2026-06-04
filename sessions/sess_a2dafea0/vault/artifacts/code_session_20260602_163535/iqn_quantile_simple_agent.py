"""
IQN Quantile Simple Agent — simplified IQN-based adaptive entropy.

Key idea: Replace SAC's scalar Q-networks with IQN-style QuantileQNetworks.
Cross-quantile variance of N=32 quantile values per (s,a) measures aleatoric
uncertainty. This variance is mapped through sigmoid to produce a per-state
entropy coefficient alpha(s).

Simplified vs Top-1: no separate heteroscedastic var_net.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from copy import deepcopy
from typing import Dict

from networks import StochasticActor, QuantileQNetwork, soft_update, hard_update


class IQNQuantileSimpleAgent:
    """SAC with IQN quantile variance as per-state entropy modulation."""

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
        # IQN specific
        n_quantiles: int = 32,
        embedding_dim: int = 64,
        lambda_unc: float = 0.5,
        threshold: float = 0.01,
        temperature: float = 0.1,
        huber_kappa: float = 1.0,
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
        self.n_quantiles = n_quantiles
        self.lambda_unc = lambda_unc
        self.threshold = threshold
        self.temperature = temperature
        self.huber_kappa = huber_kappa

        if target_entropy is None:
            self.target_entropy = -action_dim
        else:
            self.target_entropy = target_entropy

        self.actor = StochasticActor(
            obs_dim, action_dim, actor_hidden, max_action=max_action,
            log_std_min=-20, log_std_max=2
        ).to(device)

        # Twin quantile Q-networks
        self.critic1 = QuantileQNetwork(
            obs_dim, action_dim, n_quantiles=n_quantiles,
            hidden_dims=critic_hidden, embedding_dim=embedding_dim
        ).to(device)
        self.critic2 = QuantileQNetwork(
            obs_dim, action_dim, n_quantiles=n_quantiles,
            hidden_dims=critic_hidden, embedding_dim=embedding_dim
        ).to(device)
        self.critic1_target = deepcopy(self.critic1)
        self.critic2_target = deepcopy(self.critic2)

        self.log_alpha = torch.tensor(np.log(alpha_init), requires_grad=True, device=device)

        self.actor_optimizer = torch.optim.Adam(self.actor.parameters(), lr=actor_lr)
        self.critic_optimizer = torch.optim.Adam(
            list(self.critic1.parameters()) + list(self.critic2.parameters()),
            lr=critic_lr
        )
        self.alpha_optimizer = torch.optim.Adam([self.log_alpha], lr=alpha_lr)

        self._step_count = 0

    def select_action(self, obs: np.ndarray, deterministic: bool = False) -> np.ndarray:
        obs_t = torch.FloatTensor(obs).unsqueeze(0).to(self.device)
        with torch.no_grad():
            action, _ = self.actor.sample(obs_t, deterministic=deterministic)
        return action.cpu().numpy().flatten()

    def _sample_taus(self, batch_size: int) -> torch.Tensor:
        """Sample N random quantile fractions. Returns: (B, N, 1)."""
        taus = torch.rand(batch_size, self.n_quantiles, 1, device=self.device)
        return taus

    def _quantile_huber_loss(
        self, td_error: torch.Tensor, taus: torch.Tensor
    ) -> torch.Tensor:
        """Asymmetric quantile Huber loss.

        td_error: (B, N, 1) — target_q - current_quantile_q
        taus: (B, N, 1) — random quantile fractions
        """
        k = self.huber_kappa
        huber = torch.where(
            td_error.abs() <= k,
            0.5 * td_error ** 2,
            k * (td_error.abs() - 0.5 * k)
        )
        # Asymmetric weighting: penalize over/under estimation by quantile
        weight = (taus - (td_error.detach() < 0).float()).abs()
        return (weight * huber).mean()

    def train(self, replay_buffer, batch_size: int = 256) -> Dict[str, float]:
        self._step_count += 1

        obs, actions, rewards, next_obs, dones = replay_buffer.sample(batch_size)
        B = obs.shape[0]
        alpha = self.log_alpha.exp()

        # Sample quantile fractions
        taus = self._sample_taus(B)  # (B, N, 1)
        taus_next = self._sample_taus(B)

        # --- Critic update ---
        with torch.no_grad():
            next_actions, next_log_probs = self.actor.sample(next_obs)

            # Next quantile values from both target networks
            q1_next_quantiles = self.critic1_target(next_obs, next_actions, taus_next)  # (B, N, 1)
            q2_next_quantiles = self.critic2_target(next_obs, next_actions, taus_next)

            # Clipped double-Q across quantile dimension
            min_q_next = torch.min(q1_next_quantiles, q2_next_quantiles)  # (B, N, 1)
            mean_q_next = min_q_next.mean(dim=1)  # (B, 1)

            # Per-state uncertainty from next state quantile variance
            quantile_std_next = q1_next_quantiles.std(dim=1)  # (B, 1)
            beta_next = (alpha.detach() * (
                1.0 + self.lambda_unc * torch.sigmoid(
                    (quantile_std_next - self.threshold) / self.temperature
                ).clamp(0.0, 1.0)
            )).clamp(0.001, 5.0)

            target_q = rewards + self.gamma * (1 - dones) * (
                mean_q_next - beta_next * next_log_probs
            )
            target_q = target_q.unsqueeze(1).expand(-1, self.n_quantiles, -1)  # (B, N, 1)

        q1_quantiles = self.critic1(obs, actions, taus)  # (B, N, 1)
        q2_quantiles = self.critic2(obs, actions, taus)

        td1 = target_q - q1_quantiles
        td2 = target_q - q2_quantiles
        critic_loss = self._quantile_huber_loss(td1, taus) + self._quantile_huber_loss(td2, taus)

        self.critic_optimizer.zero_grad()
        critic_loss.backward()
        torch.nn.utils.clip_grad_norm_(self.critic1.parameters(), 10.0)
        torch.nn.utils.clip_grad_norm_(self.critic2.parameters(), 10.0)
        self.critic_optimizer.step()

        # --- Actor update ---
        new_actions, log_probs = self.actor.sample(obs)
        taus_new = self._sample_taus(B)

        q1_new = self.critic1(obs, new_actions, taus_new)  # (B, N, 1)
        q2_new = self.critic2(obs, new_actions, taus_new)
        min_q_new = torch.min(q1_new, q2_new).mean(dim=1)  # (B, 1)

        # Detached uncertainty for actor
        quantile_std = q1_new.std(dim=1).detach()  # (B, 1)
        beta_state = (alpha.detach() * (
            1.0 + self.lambda_unc * torch.sigmoid(
                (quantile_std - self.threshold) / self.temperature
            ).clamp(0.0, 1.0)
        )).clamp(0.001, 5.0)

        actor_loss = (beta_state * log_probs - min_q_new).mean()

        self.actor_optimizer.zero_grad()
        actor_loss.backward()
        torch.nn.utils.clip_grad_norm_(self.actor.parameters(), 10.0)
        self.actor_optimizer.step()

        # --- Alpha auto-tune ---
        alpha_loss_val = 0.0
        if self.alpha_auto_tune:
            alpha_loss = -(alpha * (log_probs.detach() + self.target_entropy)).mean()
            alpha_loss_val = alpha_loss.item()

            self.alpha_optimizer.zero_grad()
            alpha_loss.backward()
            self.alpha_optimizer.step()

        # --- Soft target updates ---
        soft_update(self.critic1_target, self.critic1, self.tau)
        soft_update(self.critic2_target, self.critic2, self.tau)

        return {
            "critic_loss": critic_loss.item(),
            "actor_loss": actor_loss.item(),
            "alpha_loss": alpha_loss_val,
            "alpha": alpha.item(),
            "quantile_std_mean": quantile_std.mean().item(),
            "beta_mean": beta_state.mean().item(),
            "q_mean": min_q_new.mean().item(),
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
