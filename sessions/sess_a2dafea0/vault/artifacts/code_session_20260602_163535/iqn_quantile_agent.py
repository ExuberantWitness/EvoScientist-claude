"""
IQN Quantile Agent — full IQN + heteroscedastic variance adaptive entropy.

Key idea: Replace SAC's scalar Q-networks with IQN-style QuantileQNetworks
(N=32 quantiles). Cross-quantile variance provides aleatoric uncertainty.
A separate var_net predicts epistemic (heteroscedastic) TD-error variance from
state-action features. The two signals are fused to produce per-state entropy
coefficient alpha(s).

alpha_effective = alpha_base * (1 + lambda_unc * sigmoid(combined_norm))
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from copy import deepcopy
from typing import Dict

from networks import StochasticActor, QuantileQNetwork, soft_update, hard_update


class HeteroscedasticVarNet(nn.Module):
    """Predicts log-variance of TD error from (s, a) features."""

    def __init__(self, input_dim: int = 14, hidden_dim: int = 128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim), nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )

    def forward(self, obs: torch.Tensor, action: torch.Tensor) -> torch.Tensor:
        x = torch.cat([obs, action], dim=-1)
        return self.net(x)  # (B, 1) — log-var


class IQNQuantileAgent:
    """SAC with IQN quantile variance + heteroscedastic var as per-state entropy."""

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
        lambda_unc: float = 0.3,
        lambda_hetero: float = 0.1,
        var_hidden: int = 128,
        var_lr: float = 5e-4,
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
        self.lambda_hetero = lambda_hetero
        self.huber_kappa = huber_kappa

        if target_entropy is None:
            self.target_entropy = -action_dim
        else:
            self.target_entropy = target_entropy

        self.actor = StochasticActor(
            obs_dim, action_dim, actor_hidden, max_action=max_action,
            log_std_min=-20, log_std_max=2
        ).to(device)

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

        self.var_net = HeteroscedasticVarNet(
            input_dim=obs_dim + action_dim, hidden_dim=var_hidden
        ).to(device)

        self.log_alpha = torch.tensor(np.log(alpha_init), requires_grad=True, device=device)

        self.actor_optimizer = torch.optim.Adam(self.actor.parameters(), lr=actor_lr)
        self.critic_optimizer = torch.optim.Adam(
            list(self.critic1.parameters()) + list(self.critic2.parameters()),
            lr=critic_lr
        )
        self.alpha_optimizer = torch.optim.Adam([self.log_alpha], lr=alpha_lr)
        self.var_optimizer = torch.optim.Adam(self.var_net.parameters(), lr=var_lr)

        self._step_count = 0

    def select_action(self, obs: np.ndarray, deterministic: bool = False) -> np.ndarray:
        obs_t = torch.FloatTensor(obs).unsqueeze(0).to(self.device)
        with torch.no_grad():
            action, _ = self.actor.sample(obs_t, deterministic=deterministic)
        return action.cpu().numpy().flatten()

    def _sample_taus(self, batch_size: int) -> torch.Tensor:
        return torch.rand(batch_size, self.n_quantiles, 1, device=self.device)

    def _quantile_huber_loss(
        self, td_error: torch.Tensor, taus: torch.Tensor
    ) -> torch.Tensor:
        k = self.huber_kappa
        huber = torch.where(
            td_error.abs() <= k,
            0.5 * td_error ** 2,
            k * (td_error.abs() - 0.5 * k)
        )
        weight = (taus - (td_error.detach() < 0).float()).abs()
        return (weight * huber).mean()

    def _compute_combined_uncertainty(
        self, obs: torch.Tensor, actions: torch.Tensor
    ) -> torch.Tensor:
        """Returns combined uncertainty (B, 1) for entropy modulation."""
        taus = self._sample_taus(obs.shape[0])

        with torch.no_grad():
            q1_q = self.critic1(obs, actions, taus)  # (B, N, 1)

        quantile_var = q1_q.var(dim=1)  # (B, 1) — aleatoric

        predicted_var = torch.exp(self.var_net(obs, actions)).clamp(max=100.0)  # (B, 1)

        combined = quantile_var + self.lambda_hetero * predicted_var
        combined = combined.clamp(max=100.0)
        combined_norm = (combined - combined.mean()) / (combined.std().clamp(min=1e-6))
        combined_norm = combined_norm.clamp(-5.0, 5.0)
        return combined_norm, quantile_var.detach(), predicted_var.detach()

    def train(self, replay_buffer, batch_size: int = 256) -> Dict[str, float]:
        self._step_count += 1

        obs, actions, rewards, next_obs, dones = replay_buffer.sample(batch_size)
        B = obs.shape[0]
        alpha = self.log_alpha.exp()

        taus = self._sample_taus(B)

        # --- Compute uncertainties ---
        combined_norm, quantile_var, predicted_var = self._compute_combined_uncertainty(
            obs, actions
        )

        # --- Next-state uncertainty ---
        taus_next = self._sample_taus(B)
        with torch.no_grad():
            next_actions, next_log_probs = self.actor.sample(next_obs)
            q1_next_q = self.critic1_target(next_obs, next_actions, taus_next)
            q1_next_var = q1_next_q.var(dim=1)

            # Compute next-state beta
            combined_next = q1_next_var + self.lambda_hetero * torch.exp(
                self.var_net(next_obs, next_actions)
            ).clamp(max=100.0)
            combined_next_norm = ((combined_next - combined_next.mean()) / (
                combined_next.std().clamp(min=1e-6)
            )).clamp(-5.0, 5.0)

            alpha_val = alpha.detach()
            beta_next = (alpha_val * (
                1.0 + self.lambda_unc * torch.sigmoid(combined_next_norm)
            )).clamp(0.001, 5.0)

        # --- Critic update ---
        with torch.no_grad():
            q1_next_all = self.critic1_target(next_obs, next_actions, taus_next)  # (B, N, 1)
            q2_next_all = self.critic2_target(next_obs, next_actions, taus_next)
            min_q_next = torch.min(q1_next_all, q2_next_all).mean(dim=1)  # (B, 1)

            target_q = rewards + self.gamma * (1 - dones) * (
                min_q_next - beta_next * next_log_probs
            )
            target_q = target_q.unsqueeze(1).expand(-1, self.n_quantiles, -1)  # (B, N, 1)

        q1_quantiles = self.critic1(obs, actions, taus)
        q2_quantiles = self.critic2(obs, actions, taus)

        td1 = target_q - q1_quantiles
        td2 = target_q - q2_quantiles
        critic_loss = self._quantile_huber_loss(td1, taus) + self._quantile_huber_loss(td2, taus)

        self.critic_optimizer.zero_grad()
        critic_loss.backward()
        torch.nn.utils.clip_grad_norm_(self.critic1.parameters(), 10.0)
        torch.nn.utils.clip_grad_norm_(self.critic2.parameters(), 10.0)
        self.critic_optimizer.step()

        # --- Variance network update ---
        td_error_sq = (td1.detach() + td2.detach()).pow(2) / 4.0  # (B, N, 1)
        td_error_mean = td_error_sq.mean(dim=1)  # (B, 1)
        predicted_logvar = self.var_net(obs, actions)
        var_loss = F.mse_loss(torch.exp(predicted_logvar), td_error_mean)

        self.var_optimizer.zero_grad()
        var_loss.backward()
        self.var_optimizer.step()

        # --- Actor update ---
        new_actions, log_probs = self.actor.sample(obs)
        taus_new = self._sample_taus(B)

        q1_new = self.critic1(obs, new_actions, taus_new)
        q2_new = self.critic2(obs, new_actions, taus_new)
        min_q_new = torch.min(q1_new, q2_new).mean(dim=1)

        beta_state = (alpha.detach() * (
            1.0 + self.lambda_unc * torch.sigmoid(combined_norm.detach())
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
            "var_loss": var_loss.item(),
            "alpha": alpha.item(),
            "quantile_var_mean": quantile_var.mean().item(),
            "predicted_var_mean": predicted_var.mean().item(),
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
            "var_net": self.var_net.state_dict(),
            "log_alpha": self.log_alpha.item(),
            "actor_optimizer": self.actor_optimizer.state_dict(),
            "critic_optimizer": self.critic_optimizer.state_dict(),
            "alpha_optimizer": self.alpha_optimizer.state_dict(),
            "var_optimizer": self.var_optimizer.state_dict(),
        }, path)

    def load(self, path: str):
        ckpt = torch.load(path, map_location=self.device)
        self.actor.load_state_dict(ckpt["actor"])
        self.critic1.load_state_dict(ckpt["critic1"])
        self.critic2.load_state_dict(ckpt["critic2"])
        self.critic1_target.load_state_dict(ckpt["critic1_target"])
        self.critic2_target.load_state_dict(ckpt["critic2_target"])
        self.var_net.load_state_dict(ckpt["var_net"])
        self.log_alpha.data = torch.tensor(ckpt["log_alpha"], device=self.device)
        self.actor_optimizer.load_state_dict(ckpt["actor_optimizer"])
        self.critic_optimizer.load_state_dict(ckpt["critic_optimizer"])
        self.alpha_optimizer.load_state_dict(ckpt["alpha_optimizer"])
        self.var_optimizer.load_state_dict(ckpt["var_optimizer"])
