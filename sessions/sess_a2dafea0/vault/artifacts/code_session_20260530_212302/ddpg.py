"""
DDPG (Deep Deterministic Policy Gradient) Agent.

Lillicrap et al., "Continuous control with deep reinforcement learning"
ICLR 2016. https://arxiv.org/abs/1509.02971

Simplified from TD3: single Q-network (no twin), no target policy smoothing,
no delayed policy updates.
"""

import torch
import torch.nn.functional as F
import numpy as np
from copy import deepcopy
from typing import Dict

from networks import DeterministicActor, QNetwork, soft_update, hard_update


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
        dx = -self.theta * x + self.sigma * np.random.randn(self.action_dim)
        self.state = x + dx
        return self.state


class DDPGAgent:
    """DDPG Agent with single critic and target networks."""

    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        max_action: float = 1.0,
        actor_hidden: list = None,
        critic_hidden: list = None,
        gamma: float = 0.99,
        tau: float = 0.005,
        actor_lr: float = 1e-4,
        critic_lr: float = 1e-3,
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
        self.exploration_noise = exploration_noise
        self.noise_type = noise_type

        self.actor = DeterministicActor(obs_dim, action_dim, actor_hidden,
                                         max_action=max_action).to(device)
        self.actor_target = deepcopy(self.actor)

        self.critic = QNetwork(obs_dim, action_dim, critic_hidden).to(device)
        self.critic_target = deepcopy(self.critic)

        self.actor_optimizer = torch.optim.Adam(self.actor.parameters(), lr=actor_lr)
        self.critic_optimizer = torch.optim.Adam(self.critic.parameters(), lr=critic_lr)

        self.noise = OUNoise(action_dim, theta=ou_theta, sigma=ou_sigma)

        self._step_count = 0

    def select_action(self, obs: np.ndarray, add_noise: bool = True) -> np.ndarray:
        obs_t = torch.FloatTensor(obs).unsqueeze(0).to(self.device)
        with torch.no_grad():
            action = self.actor(obs_t).cpu().numpy().flatten()

        if add_noise:
            if self.noise_type == "ou":
                noise = self.noise.sample()
            else:
                noise = np.random.normal(0, self.exploration_noise, size=self.action_dim)
            action = np.clip(action + noise, -self.max_action, self.max_action)

        return action

    def train(self, replay_buffer, batch_size: int = 256) -> Dict[str, float]:
        self._step_count += 1

        obs, actions, rewards, next_obs, dones = replay_buffer.sample(batch_size)

        # --- Critic update ---
        with torch.no_grad():
            next_actions = self.actor_target(next_obs)
            q_next = self.critic_target(next_obs, next_actions)
            q_target = rewards + self.gamma * (1 - dones) * q_next

        q_pred = self.critic(obs, actions)
        critic_loss = F.mse_loss(q_pred, q_target)

        self.critic_optimizer.zero_grad()
        critic_loss.backward()
        self.critic_optimizer.step()

        # --- Actor update (every step, unlike TD3) ---
        new_actions = self.actor(obs)
        actor_loss = -self.critic(obs, new_actions).mean()

        self.actor_optimizer.zero_grad()
        actor_loss.backward()
        self.actor_optimizer.step()

        # --- Soft target updates ---
        soft_update(self.critic_target, self.critic, self.tau)
        soft_update(self.actor_target, self.actor, self.tau)

        with torch.no_grad():
            q_mean = q_pred.mean().item()

        return {
            "critic_loss": critic_loss.item(),
            "actor_loss": actor_loss.item(),
            "q_mean": q_mean,
        }

    def save(self, path: str):
        torch.save({
            "actor": self.actor.state_dict(),
            "actor_target": self.actor_target.state_dict(),
            "critic": self.critic.state_dict(),
            "critic_target": self.critic_target.state_dict(),
            "actor_optimizer": self.actor_optimizer.state_dict(),
            "critic_optimizer": self.critic_optimizer.state_dict(),
        }, path)

    def load(self, path: str):
        ckpt = torch.load(path, map_location=self.device)
        self.actor.load_state_dict(ckpt["actor"])
        self.actor_target.load_state_dict(ckpt["actor_target"])
        self.critic.load_state_dict(ckpt["critic"])
        self.critic_target.load_state_dict(ckpt["critic_target"])
        self.actor_optimizer.load_state_dict(ckpt["actor_optimizer"])
        self.critic_optimizer.load_state_dict(ckpt["critic_optimizer"])
