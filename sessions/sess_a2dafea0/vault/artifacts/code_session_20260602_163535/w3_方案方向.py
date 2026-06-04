"""
State Novelty / DP Depth Adaptive Entropy Agent.

Key idea: Use autoencoder reconstruction error as a proxy for state novelty.
States visited less frequently (higher novelty) get higher entropy coefficients
to encourage exploration. States that are well-known get lower entropy.

This approximates the "dynamic programming depth" concept: states with many
Bellman backups have low reconstruction error. beta(s) = alpha * (1 + lambda * recon_error)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from copy import deepcopy
from typing import Dict, Tuple

from networks import StochasticActor, QNetwork, soft_update, hard_update


class StateAutoencoder(nn.Module):
    """Simple autoencoder for state novelty detection."""

    def __init__(self, obs_dim: int, latent_dim: int = 64):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(obs_dim, 128), nn.ReLU(),
            nn.Linear(128, latent_dim), nn.ReLU(),
        )
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 128), nn.ReLU(),
            nn.Linear(128, obs_dim),
        )

    def forward(self, obs: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Returns: (reconstructed_obs, latent)."""
        latent = self.encoder(obs)
        recon = self.decoder(latent)
        return recon, latent

    def reconstruction_error(self, obs: torch.Tensor) -> torch.Tensor:
        """Returns per-sample reconstruction error (B, 1)."""
        recon, _ = self.forward(obs)
        error = ((obs - recon) ** 2).mean(dim=-1, keepdim=True)
        return error


class DPDepthAgent:
    """SAC with state novelty (autoencoder recon error) as per-state entropy modulation."""

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
        # State novelty specific
        novelty_latent: int = 64,
        novelty_lr: float = 1e-4,
        lambda_novelty: float = 2.0,
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
        self.lambda_novelty = lambda_novelty

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

        # State novelty autoencoder
        self.autoencoder = StateAutoencoder(obs_dim, latent_dim=novelty_latent).to(device)

        self.log_alpha = torch.tensor(np.log(alpha_init), requires_grad=True, device=device)

        self.actor_optimizer = torch.optim.Adam(self.actor.parameters(), lr=actor_lr)
        self.critic_optimizer = torch.optim.Adam(
            list(self.critic1.parameters()) + list(self.critic2.parameters()),
            lr=critic_lr
        )
        self.alpha_optimizer = torch.optim.Adam([self.log_alpha], lr=alpha_lr)
        self.autoencoder_optimizer = torch.optim.Adam(
            self.autoencoder.parameters(), lr=novelty_lr
        )

        self._step_count = 0

    def _compute_novelty(self, obs: torch.Tensor) -> torch.Tensor:
        """Returns per-state novelty score (B, 1)."""
        return self.autoencoder.reconstruction_error(obs)

    def select_action(self, obs: np.ndarray, deterministic: bool = False) -> np.ndarray:
        obs_t = torch.FloatTensor(obs).unsqueeze(0).to(self.device)
        with torch.no_grad():
            action, _ = self.actor.sample(obs_t, deterministic=deterministic)
        return action.cpu().numpy().flatten()

    def train(self, replay_buffer, batch_size: int = 256) -> Dict[str, float]:
        self._step_count += 1

        obs, actions, rewards, next_obs, dones = replay_buffer.sample(batch_size)
        alpha = self.log_alpha.exp()

        # --- Update autoencoder (reconstruct observations) ---
        recon, _ = self.autoencoder(obs)
        ae_loss = F.mse_loss(recon, obs)

        self.autoencoder_optimizer.zero_grad()
        ae_loss.backward()
        self.autoencoder_optimizer.step()

        # --- Compute per-state novelty ---
        novelty = self._compute_novelty(obs).detach()  # (B, 1)
        novelty_next = self._compute_novelty(next_obs).detach()  # (B, 1)

        # Per-state beta: higher novelty → higher entropy
        # Detach alpha so it's only optimized via alpha_loss (standard SAC pattern)
        alpha_val = alpha.detach()
        beta_state = alpha_val * (1.0 + self.lambda_novelty * novelty)  # (B, 1)
        beta_next = alpha_val * (1.0 + self.lambda_novelty * novelty_next)  # (B, 1)

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
            "ae_loss": ae_loss.item(),
            "alpha": alpha.item(),
            "novelty_mean": novelty.mean().item(),
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
            "autoencoder": self.autoencoder.state_dict(),
            "log_alpha": self.log_alpha.item(),
            "actor_optimizer": self.actor_optimizer.state_dict(),
            "critic_optimizer": self.critic_optimizer.state_dict(),
            "alpha_optimizer": self.alpha_optimizer.state_dict(),
            "autoencoder_optimizer": self.autoencoder_optimizer.state_dict(),
        }, path)

    def load(self, path: str):
        ckpt = torch.load(path, map_location=self.device)
        self.actor.load_state_dict(ckpt["actor"])
        self.critic1.load_state_dict(ckpt["critic1"])
        self.critic2.load_state_dict(ckpt["critic2"])
        self.critic1_target.load_state_dict(ckpt["critic1_target"])
        self.critic2_target.load_state_dict(ckpt["critic2_target"])
        self.autoencoder.load_state_dict(ckpt["autoencoder"])
        self.log_alpha.data = torch.tensor(ckpt["log_alpha"], device=self.device)
        self.actor_optimizer.load_state_dict(ckpt["actor_optimizer"])
        self.critic_optimizer.load_state_dict(ckpt["critic_optimizer"])
        self.alpha_optimizer.load_state_dict(ckpt["alpha_optimizer"])
        self.autoencoder_optimizer.load_state_dict(ckpt["autoencoder_optimizer"])
