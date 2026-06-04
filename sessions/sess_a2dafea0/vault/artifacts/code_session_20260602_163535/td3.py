"""
TD3 (Twin Delayed DDPG) Agent.

Fujimoto et al., "Addressing Function Approximation Error in Actor-Critic Methods"
ICML 2018. https://arxiv.org/abs/1802.09477

Key features:
  - Clipped Double Q-learning (twin critics, take min)
  - Delayed policy updates (actor updated every d=2 steps)
  - Target policy smoothing (add clipped noise to target actions)
"""

import torch
import torch.nn.functional as F
import numpy as np
from typing import Tuple, Dict, Optional

from networks import (
    DeterministicActor, QNetwork, soft_update, hard_update
)


class OUNoise:
    """Ornstein-Uhlenbeck process for temporally-correlated exploration."""

    def __init__(self, action_dim: int, theta: float = 0.15, sigma: float = 0.2):
        self.action_dim = action_dim
        self.theta = theta
        self.sigma = sigma
        self.reset()

    def reset(self):
        self.state = np.zeros(self.action_dim)

    def sample(self) -> np.ndarray:
        x = self.state
        dx = self.theta * (-x) + self.sigma * np.random.randn(self.action_dim)
        self.state = x + dx
        return self.state


class TD3Agent:
    """TD3 Agent."""

    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        max_action: float = 1.0,
        actor_hidden: list = None,
        critic_hidden: list = None,
        gamma: float = 0.99,
        tau: float = 0.005,
        policy_noise: float = 0.2,
        noise_clip: float = 0.5,
        policy_delay: int = 2,
        actor_lr: float = 3e-4,
        critic_lr: float = 3e-4,
        exploration_noise: float = 0.1,
        noise_type: str = "gaussian",
        ou_theta: float = 0.15,
        ou_sigma: float = 0.2,
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
        self.policy_noise = policy_noise
        self.noise_clip = noise_clip
        self.policy_delay = policy_delay
        self.exploration_noise = exploration_noise
        self.noise_type = noise_type

        # Networks
        self.actor = DeterministicActor(
            obs_dim, action_dim, actor_hidden, max_action
        ).to(device)
        self.actor_target = DeterministicActor(
            obs_dim, action_dim, actor_hidden, max_action
        ).to(device)
        self.critic1 = QNetwork(obs_dim, action_dim, critic_hidden).to(device)
        self.critic2 = QNetwork(obs_dim, action_dim, critic_hidden).to(device)
        self.critic1_target = QNetwork(obs_dim, action_dim, critic_hidden).to(device)
        self.critic2_target = QNetwork(obs_dim, action_dim, critic_hidden).to(device)

        # Initialize targets with same weights
        hard_update(self.actor_target, self.actor)
        hard_update(self.critic1_target, self.critic1)
        hard_update(self.critic2_target, self.critic2)

        # Optimizers
        self.actor_optimizer = torch.optim.Adam(self.actor.parameters(), lr=actor_lr)
        self.critic_optimizer = torch.optim.Adam(
            list(self.critic1.parameters()) + list(self.critic2.parameters()),
            lr=critic_lr,
        )

        # Exploration noise
        self.ou_noise = OUNoise(action_dim, ou_theta, ou_sigma) if noise_type == "ou" else None

        self.total_it = 0
        self.metrics = {}

    def select_action(
        self, obs: np.ndarray, add_noise: bool = True
    ) -> np.ndarray:
        """Select action, optionally with exploration noise."""
        obs_t = torch.from_numpy(obs).float().unsqueeze(0).to(self.device)
        with torch.no_grad():
            action = self.actor(obs_t).cpu().numpy().flatten()

        if add_noise:
            if self.noise_type == "ou" and self.ou_noise is not None:
                noise = self.ou_noise.sample()
            else:
                noise = np.random.normal(0, self.exploration_noise, size=self.action_dim)
            action = action + noise
            action = np.clip(action, -self.max_action, self.max_action)

        return action

    def train(self, replay_buffer, batch_size: int = 256) -> Dict:
        """Perform one TD3 training step."""
        self.total_it += 1

        # Sample batch
        obs, actions, rewards, next_obs, dones = replay_buffer.sample(batch_size)

        # ---- Critic Update ----
        with torch.no_grad():
            # Target policy smoothing
            noise = (torch.randn_like(actions) * self.policy_noise).clamp(
                -self.noise_clip, self.noise_clip
            )
            next_actions = (self.actor_target(next_obs) + noise).clamp(
                -self.max_action, self.max_action
            )

            # Clipped Double Q
            q1_target = self.critic1_target(next_obs, next_actions)
            q2_target = self.critic2_target(next_obs, next_actions)
            q_target = torch.min(q1_target, q2_target)

            td_target = rewards + self.gamma * (1 - dones) * q_target

        # Current Q estimates
        q1 = self.critic1(obs, actions)
        q2 = self.critic2(obs, actions)

        critic_loss = F.mse_loss(q1, td_target) + F.mse_loss(q2, td_target)

        self.critic_optimizer.zero_grad()
        critic_loss.backward()
        self.critic_optimizer.step()

        # ---- Delayed Actor Update ----
        actor_loss = torch.tensor(0.0)
        if self.total_it % self.policy_delay == 0:
            actor_actions = self.actor(obs)
            actor_loss = -self.critic1(obs, actor_actions).mean()

            self.actor_optimizer.zero_grad()
            actor_loss.backward()
            self.actor_optimizer.step()

            # Soft update target networks
            soft_update(self.actor_target, self.actor, self.tau)
            soft_update(self.critic1_target, self.critic1, self.tau)
            soft_update(self.critic2_target, self.critic2, self.tau)

        self.metrics = {
            "critic_loss": critic_loss.item(),
            "actor_loss": actor_loss.item() if isinstance(actor_loss.item, float) or not actor_loss.item else 0.0,
            "q1_mean": q1.mean().item(),
            "q2_mean": q2.mean().item(),
        }
        return self.metrics

    def save(self, path: str):
        torch.save({
            "actor": self.actor.state_dict(),
            "actor_target": self.actor_target.state_dict(),
            "critic1": self.critic1.state_dict(),
            "critic2": self.critic2.state_dict(),
            "critic1_target": self.critic1_target.state_dict(),
            "critic2_target": self.critic2_target.state_dict(),
            "actor_optimizer": self.actor_optimizer.state_dict(),
            "critic_optimizer": self.critic_optimizer.state_dict(),
            "total_it": self.total_it,
        }, path)

    def load(self, path: str):
        ckpt = torch.load(path, map_location=self.device)
        self.actor.load_state_dict(ckpt["actor"])
        self.actor_target.load_state_dict(ckpt["actor_target"])
        self.critic1.load_state_dict(ckpt["critic1"])
        self.critic2.load_state_dict(ckpt["critic2"])
        self.critic1_target.load_state_dict(ckpt["critic1_target"])
        self.critic2_target.load_state_dict(ckpt["critic2_target"])
        self.total_it = ckpt.get("total_it", 0)
