"""
Value-Uncertainty Adaptive Entropy Agent.

Key idea: Use ensemble of K critics. The standard deviation of Q-values across
the ensemble (sigma_Q) serves as an uncertainty measure. Higher uncertainty →
higher entropy coefficient (explore more in uncertain regions). Lower uncertainty
→ lower entropy (exploit more in well-understood regions).

beta(s) = alpha * (1 + lambda_unc * sigma_Q(s, a))
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from copy import deepcopy
from typing import Dict, List

from networks import StochasticActor, QNetwork, soft_update, hard_update


class ValueUncertaintyAgent:
    """SAC with ensemble Q-uncertainty as per-state entropy modulation."""

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
        # Ensemble uncertainty specific
        n_critics: int = 5,
        lambda_unc: float = 1.0,
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
        self.n_critics = n_critics
        self.lambda_unc = lambda_unc

        if target_entropy is None:
            self.target_entropy = -action_dim
        else:
            self.target_entropy = target_entropy

        self.actor = StochasticActor(
            obs_dim, action_dim, actor_hidden, max_action=max_action,
            log_std_min=-20, log_std_max=2
        ).to(device)

        # Ensemble of K critics
        self.critics = nn.ModuleList([
            QNetwork(obs_dim, action_dim, critic_hidden).to(device)
            for _ in range(n_critics)
        ])
        self.critics_target = nn.ModuleList([
            deepcopy(c) for c in self.critics
        ])

        self.log_alpha = torch.tensor(np.log(alpha_init), requires_grad=True, device=device)

        self.actor_optimizer = torch.optim.Adam(self.actor.parameters(), lr=actor_lr)
        self.critic_optimizer = torch.optim.Adam(
            [p for c in self.critics for p in c.parameters()], lr=critic_lr
        )
        self.alpha_optimizer = torch.optim.Adam([self.log_alpha], lr=alpha_lr)

        self._step_count = 0

    def select_action(self, obs: np.ndarray, deterministic: bool = False) -> np.ndarray:
        obs_t = torch.FloatTensor(obs).unsqueeze(0).to(self.device)
        with torch.no_grad():
            action, _ = self.actor.sample(obs_t, deterministic=deterministic)
        return action.cpu().numpy().flatten()

    def _all_q(self, obs: torch.Tensor, action: torch.Tensor) -> torch.Tensor:
        """Returns Q-values from all critics: (n_critics, B, 1)."""
        return torch.stack([c(obs, action) for c in self.critics], dim=0)

    def _all_q_target(self, obs: torch.Tensor, action: torch.Tensor) -> torch.Tensor:
        """Returns target Q-values from all critics: (n_critics, B, 1)."""
        return torch.stack([c(obs, action) for c in self.critics_target], dim=0)

    def train(self, replay_buffer, batch_size: int = 256) -> Dict[str, float]:
        self._step_count += 1

        obs, actions, rewards, next_obs, dones = replay_buffer.sample(batch_size)
        alpha = self.log_alpha.exp()
        alpha_val = alpha.detach()

        # --- Critic update ---
        with torch.no_grad():
            next_actions, next_log_probs = self.actor.sample(next_obs)
            all_q_next = self._all_q_target(next_obs, next_actions)  # (K, B, 1)
            min_q_next = all_q_next.min(dim=0).values  # (B, 1)

            # Per-state uncertainty from next state
            sigma_q_next = all_q_next.std(dim=0)  # (B, 1)
            beta_next = alpha_val * (1.0 + self.lambda_unc * sigma_q_next)  # (B, 1)

            target_q = rewards + self.gamma * (1 - dones) * (min_q_next - beta_next * next_log_probs)

        all_q = self._all_q(obs, actions)  # (K, B, 1)
        target_q_expanded = target_q.unsqueeze(0).expand(self.n_critics, -1, -1)
        critic_loss = F.mse_loss(all_q, target_q_expanded)

        self.critic_optimizer.zero_grad()
        critic_loss.backward()
        self.critic_optimizer.step()

        # --- Actor update ---
        new_actions, log_probs = self.actor.sample(obs)
        all_q_new = self._all_q(obs, new_actions)  # (K, B, 1)
        min_q_new = all_q_new.min(dim=0).values  # (B, 1)

        sigma_q = all_q_new.std(dim=0).detach()  # (B, 1)
        beta_state = alpha_val * (1.0 + self.lambda_unc * sigma_q)  # (B, 1)

        actor_loss = (beta_state * log_probs - min_q_new).mean()

        self.actor_optimizer.zero_grad()
        actor_loss.backward()
        self.actor_optimizer.step()

        # --- Alpha auto-tune ---
        alpha_loss_val = 0.0
        if self.alpha_auto_tune:
            alpha_loss = -(self.log_alpha.exp() * (log_probs.detach() + self.target_entropy)).mean()
            alpha_loss_val = alpha_loss.item()

            self.alpha_optimizer.zero_grad()
            alpha_loss.backward()
            self.alpha_optimizer.step()

        # --- Soft target updates ---
        for c, ct in zip(self.critics, self.critics_target):
            soft_update(ct, c, self.tau)

        return {
            "critic_loss": critic_loss.item(),
            "actor_loss": actor_loss.item(),
            "alpha_loss": alpha_loss_val,
            "alpha": alpha.item(),
            "sigma_q_mean": sigma_q.mean().item(),
            "beta_mean": beta_state.mean().item(),
            "q_mean": all_q_new.mean().item(),
            "entropy": -log_probs.mean().item(),
        }

    def save(self, path: str):
        data = {
            "actor": self.actor.state_dict(),
            "log_alpha": self.log_alpha.item(),
            "actor_optimizer": self.actor_optimizer.state_dict(),
            "critic_optimizer": self.critic_optimizer.state_dict(),
            "alpha_optimizer": self.alpha_optimizer.state_dict(),
        }
        for i, (c, ct) in enumerate(zip(self.critics, self.critics_target)):
            data[f"critic_{i}"] = c.state_dict()
            data[f"critic_{i}_target"] = ct.state_dict()
        torch.save(data, path)

    def load(self, path: str):
        ckpt = torch.load(path, map_location=self.device)
        self.actor.load_state_dict(ckpt["actor"])
        self.log_alpha.data = torch.tensor(ckpt["log_alpha"], device=self.device)
        self.actor_optimizer.load_state_dict(ckpt["actor_optimizer"])
        self.critic_optimizer.load_state_dict(ckpt["critic_optimizer"])
        self.alpha_optimizer.load_state_dict(ckpt["alpha_optimizer"])
        for i in range(self.n_critics):
            self.critics[i].load_state_dict(ckpt[f"critic_{i}"])
            self.critics_target[i].load_state_dict(ckpt[f"critic_{i}_target"])
