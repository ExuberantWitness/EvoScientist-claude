"""
Taylor Expansion Local Entropy Curvature Adaptive Agent.

Key idea: Use the gradient norm of policy entropy with respect to state as
a local curvature measure. High curvature = entropy changes rapidly = needs
fine-grained control. Low curvature = flat entropy landscape = any entropy works.

beta(s) = alpha * (1 + lambda_curv * ||grad_s H(pi(.|s))||)

Computational note: Gradients are computed only every K steps to reduce overhead.
"""

import torch
import torch.nn.functional as F
import numpy as np
from copy import deepcopy
from typing import Dict

from networks import StochasticActor, QNetwork, soft_update, hard_update


class TaylorCurvatureAgent:
    """SAC with policy entropy curvature (gradient norm) as entropy modulation."""

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
        # Taylor curvature specific
        lambda_curv: float = 1.0,
        curvature_freq: int = 4,
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
        self.lambda_curv = lambda_curv
        self.curvature_freq = curvature_freq

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

        self.log_alpha = torch.tensor(np.log(alpha_init), requires_grad=True, device=device)

        self.actor_optimizer = torch.optim.Adam(self.actor.parameters(), lr=actor_lr)
        self.critic_optimizer = torch.optim.Adam(
            list(self.critic1.parameters()) + list(self.critic2.parameters()),
            lr=critic_lr
        )
        self.alpha_optimizer = torch.optim.Adam([self.log_alpha], lr=alpha_lr)

        self._step_count = 0
        self._cached_curvature = None

    def _compute_curvature(self, obs: torch.Tensor) -> torch.Tensor:
        """Compute entropy gradient norm ||grad_s H|| as curvature proxy. Returns (B, 1)."""
        obs_grad = obs.clone().detach().requires_grad_(True)
        mean, log_std = self.actor(obs_grad)
        # Gaussian entropy per dimension: 0.5 * log(2*pi*e*sigma^2) = 0.5 + 0.5*log(2*pi) + log_std
        entropy_dims = 0.5 * (1.0 + np.log(2 * np.pi)) + log_std  # (B, action_dim)
        entropy = entropy_dims.sum(dim=-1)  # (B,)

        grad_entropy = torch.autograd.grad(
            entropy.sum(), obs_grad, create_graph=False, retain_graph=False
        )[0]  # (B, obs_dim)
        curvature = grad_entropy.norm(dim=-1, keepdim=True)  # (B, 1)
        return curvature.detach()

    def _get_beta(self, obs: torch.Tensor) -> torch.Tensor:
        """Compute per-state beta with cached curvature. Returns (B, 1)."""
        alpha = self.log_alpha.exp()
        if self._step_count % self.curvature_freq == 0 or self._cached_curvature is None:
            self._cached_curvature = self._compute_curvature(obs)

        # Clamp curvature to avoid extreme beta values
        curv = torch.clamp(self._cached_curvature, 0, 5.0)
        beta = alpha * (1.0 + self.lambda_curv * curv)
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
        beta_state = self._get_beta(obs).detach()
        beta_next = self._get_beta(next_obs).detach()
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

        curv_mean = self._cached_curvature.mean().item() if self._cached_curvature is not None else 0.0

        return {
            "critic_loss": critic_loss.item(),
            "actor_loss": actor_loss.item(),
            "alpha_loss": alpha_loss_val,
            "alpha": alpha.item(),
            "curvature_mean": curv_mean,
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
