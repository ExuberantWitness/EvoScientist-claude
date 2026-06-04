"""
Gait Phase Adaptive Entropy Agent.

Key idea: Hopper-v4 has a periodic gait cycle. Different gait phases (takeoff,
flight, landing, support) need different exploration levels. Use PhaseEncoder
(from networks.py) to extract phase from observations, then modulate the entropy
coefficient based on the current gait phase.

beta(s) = alpha + beta_scale * phase_offset(s)
where phase_offset is learned from the phase encoding via a small MLP.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from copy import deepcopy
from typing import Dict

from networks import StochasticActor, QNetwork, PhaseEncoder, soft_update, hard_update


class PhaseBetaModulator(nn.Module):
    """Maps phase encoding to entropy modulation offset."""

    def __init__(self, phase_dim: int = 2, hidden_dim: int = 32):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(phase_dim, hidden_dim), nn.ReLU(),
            nn.Linear(hidden_dim, 1), nn.Tanh(),  # output in [-1, 1]
        )

    def forward(self, phase: torch.Tensor) -> torch.Tensor:
        """Returns beta offset in [-1, 1]."""
        return self.net(phase)


class GaitPhaseAgent:
    """SAC with gait-phase-conditioned entropy modulation."""

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
        # Gait phase specific
        phase_hidden: int = 64,
        beta_scale: float = 0.15,
        phase_lr: float = 1e-4,
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
        self.beta_scale = beta_scale

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

        # Phase encoder (reuse from networks.py) + beta modulator
        self.phase_encoder = PhaseEncoder(obs_dim, hidden_dim=phase_hidden, phase_dim=2).to(device)
        self.phase_modulator = PhaseBetaModulator(phase_dim=2, hidden_dim=32).to(device)

        self.log_alpha = torch.tensor(np.log(alpha_init), requires_grad=True, device=device)

        self.actor_optimizer = torch.optim.Adam(self.actor.parameters(), lr=actor_lr)
        self.critic_optimizer = torch.optim.Adam(
            list(self.critic1.parameters()) + list(self.critic2.parameters()),
            lr=critic_lr
        )
        self.alpha_optimizer = torch.optim.Adam([self.log_alpha], lr=alpha_lr)
        self.phase_optimizer = torch.optim.Adam(
            list(self.phase_encoder.parameters()) + list(self.phase_modulator.parameters()),
            lr=phase_lr
        )

        self._step_count = 0

    def _compute_beta(self, obs: torch.Tensor) -> torch.Tensor:
        """Compute per-state beta(s) from gait phase. Returns (B, 1)."""
        alpha = self.log_alpha.exp()
        phase, _ = self.phase_encoder(obs)  # phase: (B, 2) = [sin(theta), cos(theta)]
        phase_offset = self.phase_modulator(phase)  # (B, 1), range [-1, 1]
        beta = alpha + self.beta_scale * phase_offset  # (B, 1)
        beta = torch.clamp(beta, 0.01, 1.0)  # stable range
        return beta

    def select_action(self, obs: np.ndarray, deterministic: bool = False) -> np.ndarray:
        obs_t = torch.FloatTensor(obs).unsqueeze(0).to(self.device)
        with torch.no_grad():
            action, _ = self.actor.sample(obs_t, deterministic=deterministic)
        return action.cpu().numpy().flatten()

    def train(self, replay_buffer, batch_size: int = 256) -> Dict[str, float]:
        self._step_count += 1

        obs, actions, rewards, next_obs, dones = replay_buffer.sample(batch_size)

        # Compute per-state beta
        beta_state = self._compute_beta(obs).detach()
        beta_next = self._compute_beta(next_obs).detach()
        alpha = self.log_alpha.exp()

        # --- Critic update ---
        with torch.no_grad():
            next_actions, next_log_probs = self.actor.sample(next_obs)
            q1_next = self.critic1_target(next_obs, next_actions)
            q2_next = self.critic2_target(next_obs, next_actions)
            min_q_next = torch.min(q1_next, q2_next)
            target_q = rewards + self.gamma * (1 - dones) * (min_q_next - beta_next * next_log_probs)

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

        actor_loss = (beta_state * log_probs - min_q_new).mean()

        self.actor_optimizer.zero_grad()
        actor_loss.backward()
        self.actor_optimizer.step()

        # --- Phase network update: encourage phase to be predictive of Q-difference ---
        with torch.no_grad():
            q_diff = (q1_new - q2_new).abs() / (torch.abs(min_q_new) + 1e-6)
            q_diff = torch.clamp(q_diff, 0, 1)
            beta_target = (alpha * (1.0 - 0.3 * q_diff)).detach()

        beta_live = self._compute_beta(obs)
        phase_loss = F.mse_loss(beta_live, beta_target)
        # This encourages: high Q disagreement → lower beta (more cautious)

        self.phase_optimizer.zero_grad()
        phase_loss.backward()
        self.phase_optimizer.step()

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
            "phase_loss": phase_loss.item(),
            "alpha": alpha.item(),
            "beta_mean": beta_state.mean().item(),
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
            "phase_encoder": self.phase_encoder.state_dict(),
            "phase_modulator": self.phase_modulator.state_dict(),
            "log_alpha": self.log_alpha.item(),
            "actor_optimizer": self.actor_optimizer.state_dict(),
            "critic_optimizer": self.critic_optimizer.state_dict(),
            "alpha_optimizer": self.alpha_optimizer.state_dict(),
            "phase_optimizer": self.phase_optimizer.state_dict(),
        }, path)

    def load(self, path: str):
        ckpt = torch.load(path, map_location=self.device)
        self.actor.load_state_dict(ckpt["actor"])
        self.critic1.load_state_dict(ckpt["critic1"])
        self.critic2.load_state_dict(ckpt["critic2"])
        self.critic1_target.load_state_dict(ckpt["critic1_target"])
        self.critic2_target.load_state_dict(ckpt["critic2_target"])
        self.phase_encoder.load_state_dict(ckpt["phase_encoder"])
        self.phase_modulator.load_state_dict(ckpt["phase_modulator"])
        self.log_alpha.data = torch.tensor(ckpt["log_alpha"], device=self.device)
        self.actor_optimizer.load_state_dict(ckpt["actor_optimizer"])
        self.critic_optimizer.load_state_dict(ckpt["critic_optimizer"])
        self.alpha_optimizer.load_state_dict(ckpt["alpha_optimizer"])
        self.phase_optimizer.load_state_dict(ckpt["phase_optimizer"])
