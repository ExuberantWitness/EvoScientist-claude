"""
SAC (Soft Actor-Critic) Agent.

Haarnoja et al., "Soft Actor-Critic: Off-Policy Maximum Entropy Deep RL"
ICML 2018. https://arxiv.org/abs/1801.01290

Key features:
  - Maximum entropy framework (learns stochastic policy)
  - Twin Q-networks (clipped double-Q)
  - Automatic temperature tuning
  - Reparameterization trick for policy gradient
"""

import torch
import torch.nn.functional as F
import numpy as np
from typing import Dict, Optional

from networks import StochasticActor, QNetwork, soft_update, hard_update


class SACAgent:
    """SAC Agent with automatic entropy tuning."""

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
        target_entropy: Optional[float] = None,
        log_std_min: float = -20.0,
        log_std_max: float = 2.0,
        device: str = "cuda",
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

        # Target entropy: -dim(A) if not specified (common default)
        if target_entropy is None:
            self.target_entropy = -action_dim
        else:
            self.target_entropy = target_entropy

        # Log alpha (temperature parameter)
        self.log_alpha = torch.tensor(
            np.log(alpha_init), requires_grad=alpha_auto_tune, device=device
        )
        self.alpha = self.log_alpha.exp().detach()

        # Networks
        self.actor = StochasticActor(
            obs_dim, action_dim, actor_hidden, max_action,
            log_std_min, log_std_max
        ).to(device)

        self.critic1 = QNetwork(obs_dim, action_dim, critic_hidden).to(device)
        self.critic2 = QNetwork(obs_dim, action_dim, critic_hidden).to(device)
        self.critic1_target = QNetwork(obs_dim, action_dim, critic_hidden).to(device)
        self.critic2_target = QNetwork(obs_dim, action_dim, critic_hidden).to(device)

        hard_update(self.critic1_target, self.critic1)
        hard_update(self.critic2_target, self.critic2)

        # Optimizers
        self.actor_optimizer = torch.optim.Adam(self.actor.parameters(), lr=actor_lr)
        self.critic_optimizer = torch.optim.Adam(
            list(self.critic1.parameters()) + list(self.critic2.parameters()),
            lr=critic_lr,
        )
        if alpha_auto_tune:
            self.alpha_optimizer = torch.optim.Adam([self.log_alpha], lr=alpha_lr)

        self.total_it = 0
        self.metrics = {}

    def select_action(
        self, obs: np.ndarray, deterministic: bool = False
    ) -> np.ndarray:
        """Select action. If deterministic=False, samples from stochastic policy."""
        obs_t = torch.from_numpy(obs).float().unsqueeze(0).to(self.device)
        with torch.no_grad():
            action, _ = self.actor.sample(obs_t, deterministic=deterministic)
        return action.cpu().numpy().flatten()

    def train(self, replay_buffer, batch_size: int = 256) -> Dict:
        """Perform one SAC training step."""
        self.total_it += 1

        obs, actions, rewards, next_obs, dones = replay_buffer.sample(batch_size)
        alpha = self.log_alpha.exp().detach() if self.alpha_auto_tune else self.alpha

        # ---- Critic Update ----
        with torch.no_grad():
            next_actions, next_log_probs = self.actor.sample(next_obs)
            q1_target = self.critic1_target(next_obs, next_actions)
            q2_target = self.critic2_target(next_obs, next_actions)
            q_target = torch.min(q1_target, q2_target)

            # Entropy-regularized target
            td_target = rewards + self.gamma * (1 - dones) * (
                q_target - alpha * next_log_probs
            )

        q1 = self.critic1(obs, actions)
        q2 = self.critic2(obs, actions)

        critic_loss = F.mse_loss(q1, td_target) + F.mse_loss(q2, td_target)

        self.critic_optimizer.zero_grad()
        critic_loss.backward()
        self.critic_optimizer.step()

        # ---- Actor Update ----
        new_actions, log_probs = self.actor.sample(obs)
        q1_new = self.critic1(obs, new_actions)
        q2_new = self.critic2(obs, new_actions)
        q_new = torch.min(q1_new, q2_new)

        actor_loss = (alpha * log_probs - q_new).mean()

        self.actor_optimizer.zero_grad()
        actor_loss.backward()
        self.actor_optimizer.step()

        # ---- Alpha (Temperature) Update ----
        alpha_loss = torch.tensor(0.0)
        if self.alpha_auto_tune:
            alpha_loss = -(
                self.log_alpha.exp() * (log_probs.detach() + self.target_entropy)
            ).mean()

            self.alpha_optimizer.zero_grad()
            alpha_loss.backward()
            self.alpha_optimizer.step()

            self.alpha = self.log_alpha.exp().detach()

        # Soft update target networks
        soft_update(self.critic1_target, self.critic1, self.tau)
        soft_update(self.critic2_target, self.critic2, self.tau)

        self.metrics = {
            "critic_loss": critic_loss.item(),
            "actor_loss": actor_loss.item(),
            "alpha_loss": alpha_loss.item() if alpha_loss.item() else 0.0,
            "alpha": self.alpha.item(),
            "q1_mean": q1.mean().item(),
            "q2_mean": q2.mean().item(),
            "entropy": -log_probs.mean().item(),
        }
        return self.metrics

    def save(self, path: str):
        save_dict = {
            "actor": self.actor.state_dict(),
            "critic1": self.critic1.state_dict(),
            "critic2": self.critic2.state_dict(),
            "critic1_target": self.critic1_target.state_dict(),
            "critic2_target": self.critic2_target.state_dict(),
            "actor_optimizer": self.actor_optimizer.state_dict(),
            "critic_optimizer": self.critic_optimizer.state_dict(),
            "log_alpha": self.log_alpha,
            "total_it": self.total_it,
        }
        if self.alpha_auto_tune:
            save_dict["alpha_optimizer"] = self.alpha_optimizer.state_dict()
        torch.save(save_dict, path)

    def load(self, path: str):
        ckpt = torch.load(path, map_location=self.device)
        self.actor.load_state_dict(ckpt["actor"])
        self.critic1.load_state_dict(ckpt["critic1"])
        self.critic2.load_state_dict(ckpt["critic2"])
        self.critic1_target.load_state_dict(ckpt["critic1_target"])
        self.critic2_target.load_state_dict(ckpt["critic2_target"])
        self.log_alpha = ckpt["log_alpha"]
        self.alpha = self.log_alpha.exp().detach()
        self.total_it = ckpt.get("total_it", 0)
