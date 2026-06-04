"""
QVGN-SAC: Quantile-Variance Gradient-Norm SAC.

Fuses two complementary uncertainty signals:
  1. Quantile variance (aleatoric) — cross-quantile spread from N_qvar=64
  2. Gradient norm (epistemic) — ||nabla_a Q(s,a)|| local Lipschitz sensitivity

A learned Modulator maps [obs || norm_qvar || norm_gnorm] to per-dimension
sigma_scale(s), which multiplies the actor's log_std for fine-grained
exploration modulation.

beta(s) is computed via a direct formula from the fused normalized signals
(NOT learned), avoiding the NaN instability of the heteroscedastic var_net.

Key anti-crash difference vs iqn_quantile:
  Modulator is trained end-to-end through policy gradient, NOT by fitting
  TD errors. No feedback loop between predicted variance and critic targets.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from copy import deepcopy
from typing import Dict, Tuple

from networks import (
    StochasticActor, QuantileQNetwork, Modulator, RunningStats,
    soft_update, hard_update,
)


class QVGNSACAgent:
    """Quantile-Variance Gradient-Norm SAC with per-dim exploration modulation."""

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
        modulator_lr: float = 1e-4,
        alpha_init: float = 0.2,
        alpha_auto_tune: bool = True,
        target_entropy: float = None,
        device: str = "cuda",
        # IQN
        n_quantiles: int = 32,
        n_qvar: int = 64,
        embedding_dim: int = 64,
        huber_kappa: float = 1.0,
        # Modulator
        modulator_hidden: int = 64,
        sigma_min: float = 0.5,
        sigma_max: float = 2.0,
        # Uncertainty fusion
        lambda_qvar: float = 0.5,
        lambda_gnorm: float = 0.5,
        lambda_unc: float = 0.3,
        unc_threshold: float = 0.0,
        unc_temperature: float = 0.1,
        # RunningStats
        stats_momentum: float = 0.001,
        stats_clip: float = 5.0,
        # Stability
        max_grad_norm: float = 10.0,
        beta_min: float = 0.001,
        beta_max: float = 5.0,
    ):
        if actor_hidden is None:
            actor_hidden = [256, 256]
        if critic_hidden is None:
            critic_hidden = [256, 256]

        self.device = device
        self.max_action = max_action
        self.action_dim = action_dim
        self.obs_dim = obs_dim
        self.gamma = gamma
        self.tau = tau
        self.alpha_auto_tune = alpha_auto_tune
        self.n_quantiles = n_quantiles
        self.n_qvar = n_qvar
        self.huber_kappa = huber_kappa
        self.lambda_qvar = lambda_qvar
        self.lambda_gnorm = lambda_gnorm
        self.lambda_unc = lambda_unc
        self.unc_threshold = unc_threshold
        self.unc_temperature = unc_temperature
        self.max_grad_norm = max_grad_norm
        self.beta_min = beta_min
        self.beta_max = beta_max

        if target_entropy is None:
            self.target_entropy = -action_dim
        else:
            self.target_entropy = target_entropy

        # Actor
        self.actor = StochasticActor(
            obs_dim, action_dim, actor_hidden, max_action=max_action,
            log_std_min=-20, log_std_max=2
        ).to(device)

        # Twin quantile Q-networks (N=32 for critic loss)
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

        # Modulator: state + uncertainty features → per-dim sigma_scale
        modulator_input_dim = obs_dim + 2  # obs(11) + norm_qvar(1) + norm_gnorm(1)
        self.modulator = Modulator(
            input_dim=modulator_input_dim,
            hidden_dim=modulator_hidden,
            action_dim=action_dim,
            output_min=sigma_min,
            output_max=sigma_max,
        ).to(device)

        # Running statistics for uncertainty normalization
        self.qvar_stats = RunningStats(momentum=stats_momentum, clip=stats_clip)
        self.gnorm_stats = RunningStats(momentum=stats_momentum, clip=stats_clip)

        # Global temperature (auto-tuned SAC style)
        self.log_alpha = torch.tensor(np.log(alpha_init), requires_grad=True, device=device)

        # Optimizers
        self.actor_optimizer = torch.optim.Adam(self.actor.parameters(), lr=actor_lr)
        self.critic_optimizer = torch.optim.Adam(
            list(self.critic1.parameters()) + list(self.critic2.parameters()),
            lr=critic_lr
        )
        self.modulator_optimizer = torch.optim.Adam(
            self.modulator.parameters(), lr=modulator_lr
        )
        self.alpha_optimizer = torch.optim.Adam([self.log_alpha], lr=alpha_lr)

        self._step_count = 0

    # ------------------------------------------------------------------
    # Action selection
    # ------------------------------------------------------------------

    def select_action(self, obs: np.ndarray, deterministic: bool = False) -> np.ndarray:
        obs_t = torch.FloatTensor(obs).unsqueeze(0).to(self.device)
        with torch.no_grad():
            action, _ = self.actor.sample(obs_t, deterministic=deterministic)
        return action.cpu().numpy().flatten()

    # ------------------------------------------------------------------
    # Sampling helpers
    # ------------------------------------------------------------------

    def _sample_taus(self, batch_size: int, n: int = None) -> torch.Tensor:
        """Sample N random quantile fractions. Returns: (B, N, 1)."""
        n_use = n if n is not None else self.n_quantiles
        return torch.rand(batch_size, n_use, 1, device=self.device)

    def _sample_modulated(
        self, obs: torch.Tensor, sigma_scale: torch.Tensor,
        deterministic: bool = False
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """Sample actions with Modulator-controlled per-dimension std.

        effective_log_std = log_std + log(sigma_scale)
        log_prob is computed with the modulated std for unbiased policy gradient.
        """
        mean, log_std = self.actor(obs)  # (B, act_dim), (B, act_dim)

        if deterministic:
            action = torch.tanh(mean) * self.max_action
            log_prob = torch.zeros(obs.shape[0], 1, device=self.device)
            return action, log_prob

        effective_log_std = log_std + torch.log(sigma_scale.clamp(min=1e-6))
        effective_log_std = effective_log_std.clamp(-20.0, 2.0)
        std = effective_log_std.exp()

        normal = torch.distributions.Normal(mean, std)
        z = normal.rsample()
        action = torch.tanh(z) * self.max_action

        # Log prob with tanh correction (uses modulated std)
        log_prob = normal.log_prob(z)
        log_prob -= torch.log(1 - action.pow(2) / self.max_action**2 + 1e-6)
        log_prob = log_prob.sum(dim=-1, keepdim=True)

        return action, log_prob

    # ------------------------------------------------------------------
    # Quantile Huber loss
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Uncertainty signals
    # ------------------------------------------------------------------

    def _compute_raw_uncertainty(
        self, obs: torch.Tensor, actions: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """Compute raw (unnormalized) quantile variance and gradient norm.

        Returns:
            raw_qvar: (B, 1) — inter-quantile variance from both critics
            raw_gnorm: (B, 1) — gradient norm of Q wrt actions
        """
        with torch.no_grad():
            # Quantile variance using N_qvar samples (finer resolution)
            taus_var = torch.rand(obs.shape[0], self.n_qvar, 1, device=self.device)
            q1_var = self.critic1(obs, actions, taus_var)  # (B, n_qvar, 1)
            q2_var = self.critic2(obs, actions, taus_var)  # (B, n_qvar, 1)

            qvar_1 = q1_var.var(dim=1)  # (B, 1) — intra-critic1 spread
            qvar_2 = q2_var.var(dim=1)  # (B, 1) — intra-critic2 spread
            # Inter-critic disagreement at the mean
            qvar_inter = (q1_var.mean(dim=1) - q2_var.mean(dim=1)).pow(2)  # (B, 1)

            raw_qvar = qvar_1 + qvar_2 + 0.5 * qvar_inter

        # Gradient norm using autograd through critic1.
        # Must be inside enable_grad() because _compute_beta may be called
        # from within torch.no_grad() (e.g., critic target computation).
        with torch.enable_grad():
            actions_grad = actions.detach().clone().requires_grad_(True)
            taus_grad = torch.rand(obs.shape[0], self.n_quantiles, 1, device=self.device)
            q_grad = self.critic1(obs.detach(), actions_grad, taus_grad)  # (B, N, 1)
            grad_q, = torch.autograd.grad(
                q_grad.mean(), actions_grad,
                create_graph=False, retain_graph=False
            )
            raw_gnorm = grad_q.detach().norm(p=2, dim=-1, keepdim=True)  # (B, 1)

        return raw_qvar.detach(), raw_gnorm.detach()

    # ------------------------------------------------------------------
    # Beta computation (direct formula, NOT learned)
    # ------------------------------------------------------------------

    def _compute_beta(
        self, obs: torch.Tensor, actions: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """Compute per-state beta(s) from fused normalized uncertainty signals.

        Returns:
            beta_state: (B, 1) — effective entropy coefficient
            norm_qvar: (B, 1) — normalized quantile variance (for Modulator input)
            norm_gnorm: (B, 1) — normalized gradient norm (for Modulator input)
            combined: (B, 1) — fused uncertainty (before sigmoid, for logging)
        """
        raw_qvar, raw_gnorm = self._compute_raw_uncertainty(obs, actions)

        # Update running stats
        self.qvar_stats.update(raw_qvar)
        self.gnorm_stats.update(raw_gnorm)

        # Normalize
        norm_qvar = self.qvar_stats.normalize(raw_qvar)
        norm_gnorm = self.gnorm_stats.normalize(raw_gnorm)

        # Fuse
        combined = self.lambda_qvar * norm_qvar + self.lambda_gnorm * norm_gnorm
        combined = combined.clamp(-5.0, 5.0)

        # Map to beta multiplier
        alpha = self.log_alpha.exp().detach()
        beta_multiplier = (
            1.0 + self.lambda_unc * torch.sigmoid(
                (combined - self.unc_threshold) / self.unc_temperature
            )
        ).clamp(0.5, 2.0)

        beta_state = (alpha * beta_multiplier).clamp(self.beta_min, self.beta_max)

        return beta_state, norm_qvar, norm_gnorm, combined

    # ------------------------------------------------------------------
    # Training step
    # ------------------------------------------------------------------

    def train(self, replay_buffer, batch_size: int = 256) -> Dict[str, float]:
        self._step_count += 1

        obs, actions, rewards, next_obs, dones = replay_buffer.sample(batch_size)
        B = obs.shape[0]

        # Sample quantile fractions
        taus = self._sample_taus(B, n=self.n_quantiles)
        taus_next = self._sample_taus(B, n=self.n_quantiles)

        # --- Next-state beta for critic target ---
        with torch.no_grad():
            next_actions, next_log_probs = self.actor.sample(next_obs)
            beta_next, _, _, _ = self._compute_beta(next_obs, next_actions)

        # --- Critic update (Quantile Huber loss) ---
        with torch.no_grad():
            q1_next = self.critic1_target(next_obs, next_actions, taus_next)
            q2_next = self.critic2_target(next_obs, next_actions, taus_next)
            min_q_next = torch.min(q1_next, q2_next).mean(dim=1)  # (B, 1)

            target_q = rewards + self.gamma * (1 - dones) * (
                min_q_next - beta_next * next_log_probs
            )
            target_q = target_q.unsqueeze(1).expand(-1, self.n_quantiles, -1)

        q1_q = self.critic1(obs, actions, taus)
        q2_q = self.critic2(obs, actions, taus)

        td1 = target_q - q1_q
        td2 = target_q - q2_q
        critic_loss = self._quantile_huber_loss(td1, taus) + self._quantile_huber_loss(td2, taus)

        self.critic_optimizer.zero_grad()
        critic_loss.backward()
        torch.nn.utils.clip_grad_norm_(self.critic1.parameters(), self.max_grad_norm)
        torch.nn.utils.clip_grad_norm_(self.critic2.parameters(), self.max_grad_norm)
        self.critic_optimizer.step()

        # --- Compute beta + uncertainty signals (DETACHED for Modulator input) ---
        beta_state, norm_qvar, norm_gnorm, combined = self._compute_beta(obs, actions)

        # --- Build Modulator input ---
        modulator_input = torch.cat([obs, norm_qvar.detach(), norm_gnorm.detach()], dim=-1)

        # --- Modulator forward: per-dim sigma_scale ---
        sigma_scale = self.modulator(modulator_input)  # (B, action_dim)

        # --- Actor sample with modulated std ---
        new_actions, log_probs = self._sample_modulated(obs, sigma_scale)

        # --- Actor + Modulator update ---
        taus_actor = self._sample_taus(B, n=self.n_quantiles)
        q1_actor = self.critic1(obs, new_actions, taus_actor)
        q2_actor = self.critic2(obs, new_actions, taus_actor)
        min_q_actor = torch.min(q1_actor, q2_actor).mean(dim=1)  # (B, 1)

        # beta_state is DETACHED (not trained through this loss)
        actor_loss = (beta_state.detach() * log_probs - min_q_actor).mean()

        self.actor_optimizer.zero_grad()
        self.modulator_optimizer.zero_grad()
        actor_loss.backward()
        torch.nn.utils.clip_grad_norm_(self.actor.parameters(), self.max_grad_norm)
        torch.nn.utils.clip_grad_norm_(self.modulator.parameters(), self.max_grad_norm)
        self.actor_optimizer.step()
        self.modulator_optimizer.step()

        # --- Alpha auto-tune (standard SAC) ---
        alpha = self.log_alpha.exp()
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
            "qvar_mean": norm_qvar.mean().item(),
            "gnorm_mean": norm_gnorm.mean().item(),
            "sigma_scale_mean": sigma_scale.mean().item(),
            "sigma_scale_std": sigma_scale.std().item(),
            "beta_mean": beta_state.mean().item(),
            "combined_mean": combined.mean().item(),
            "q_mean": min_q_actor.mean().item(),
            "entropy": -log_probs.mean().item(),
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str):
        torch.save({
            "actor": self.actor.state_dict(),
            "critic1": self.critic1.state_dict(),
            "critic2": self.critic2.state_dict(),
            "critic1_target": self.critic1_target.state_dict(),
            "critic2_target": self.critic2_target.state_dict(),
            "modulator": self.modulator.state_dict(),
            "log_alpha": self.log_alpha.item(),
            "actor_optimizer": self.actor_optimizer.state_dict(),
            "critic_optimizer": self.critic_optimizer.state_dict(),
            "modulator_optimizer": self.modulator_optimizer.state_dict(),
            "alpha_optimizer": self.alpha_optimizer.state_dict(),
            # Running stats (for resuming training — stored as CPU tensors)
            "qvar_mean": self.qvar_stats.mean.cpu() if self.qvar_stats.mean is not None else None,
            "qvar_var": self.qvar_stats.var.cpu() if self.qvar_stats.var is not None else None,
            "gnorm_mean": self.gnorm_stats.mean.cpu() if self.gnorm_stats.mean is not None else None,
            "gnorm_var": self.gnorm_stats.var.cpu() if self.gnorm_stats.var is not None else None,
        }, path)

    def load(self, path: str):
        ckpt = torch.load(path, map_location=self.device)
        self.actor.load_state_dict(ckpt["actor"])
        self.critic1.load_state_dict(ckpt["critic1"])
        self.critic2.load_state_dict(ckpt["critic2"])
        self.critic1_target.load_state_dict(ckpt["critic1_target"])
        self.critic2_target.load_state_dict(ckpt["critic2_target"])
        self.modulator.load_state_dict(ckpt["modulator"])
        self.log_alpha.data = torch.tensor(ckpt["log_alpha"], device=self.device)
        self.actor_optimizer.load_state_dict(ckpt["actor_optimizer"])
        self.critic_optimizer.load_state_dict(ckpt["critic_optimizer"])
        self.modulator_optimizer.load_state_dict(ckpt["modulator_optimizer"])
        self.alpha_optimizer.load_state_dict(ckpt["alpha_optimizer"])
        # Restore running stats
        for name in ["qvar", "gnorm"]:
            stats = getattr(self, f"{name}_stats")
            m = ckpt.get(f"{name}_mean")
            v = ckpt.get(f"{name}_var")
            if m is not None:
                stats.mean = m.to(self.device)
                stats.var = v.to(self.device)
                stats.initialized = True
