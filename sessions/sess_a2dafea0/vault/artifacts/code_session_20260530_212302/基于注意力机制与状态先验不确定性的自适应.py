"""
Attention + State Prior Uncertainty Adaptive Entropy Agent (ELO #1).

Key idea: Use multi-head attention over learned key states (prototypes) to
capture which "regime" the current state belongs to. Physics priors (contact
flag, joint acceleration variance, phase signal) provide inductive bias about
Hopper dynamics. Combined representation drives per-state entropy coefficient
beta(s), replacing the fixed global alpha.

Architecture:
  - SAC backbone (stochastic actor, twin Q, auto-tune)
  - Learned key states (16 prototypes) + MultiheadAttention
  - Physics prior encoder: contact_flag, joint_acc_var, phase_signal
  - Beta network: attention_output + prior_feat -> beta(s) in [0.01, 0.61]
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from copy import deepcopy
from typing import Dict, Tuple

from networks import StochasticActor, QNetwork, MLP, soft_update, hard_update


class PhysicsPriorEncoder(nn.Module):
    """Encodes physics priors from raw Hopper-v4 observations (11-dim).

    Hopper-v4 obs layout:
      0: root height (z),   1: x velocity,      2: z velocity,
      3: root angle,        4: root angular vel,
      5: thigh joint angle, 6: leg joint angle,  7: foot joint angle,
      8: thigh joint vel,   9: leg joint vel,    10: foot joint vel
    """

    def __init__(self, prior_dim: int = 64):
        super().__init__()
        self.prior_net = nn.Sequential(
            nn.Linear(3, 32), nn.ReLU(),
            nn.Linear(32, prior_dim), nn.ReLU(),
        )

    def compute_raw_priors(self, obs: torch.Tensor, next_obs: torch.Tensor) -> torch.Tensor:
        """Compute raw physics priors from observation pairs. Returns (B, 3)."""
        contact_flag = torch.tanh(obs[:, 5:6] * 5.0)  # thigh angle -> contact proxy
        joint_vel = obs[:, 8:11]
        joint_vel_next = next_obs[:, 8:11]
        acc_var = ((joint_vel_next - joint_vel) ** 2).mean(dim=-1, keepdim=True)
        acc_var = torch.clamp(acc_var, 0, 10.0)  # clamp extreme values
        phase_signal = torch.sin(obs[:, 0:1] * np.pi / 0.8)  # root height -> phase
        priors = torch.cat([contact_flag, acc_var, phase_signal], dim=-1)
        return priors

    def forward(self, obs: torch.Tensor, next_obs: torch.Tensor) -> torch.Tensor:
        raw = self.compute_raw_priors(obs, next_obs)
        return self.prior_net(raw)


class AttentionStateEncoder(nn.Module):
    """Encodes state via attention over learnable key-state prototypes."""

    def __init__(self, obs_dim: int, embed_dim: int = 256, n_keys: int = 16, n_heads: int = 8):
        super().__init__()
        self.n_keys = n_keys
        self.embed_dim = embed_dim

        self.state_proj = nn.Linear(obs_dim, embed_dim)
        self.key_states = nn.Parameter(torch.randn(n_keys, embed_dim) * 0.1)
        self.attention = nn.MultiheadAttention(embed_dim=embed_dim, num_heads=n_heads,
                                                batch_first=True)

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        """Returns attention-pooled state representation (B, embed_dim)."""
        B = obs.shape[0]
        state_feat = F.relu(self.state_proj(obs))  # (B, embed_dim)

        q = state_feat.unsqueeze(1)  # (B, 1, embed_dim)
        k = self.key_states.unsqueeze(0).expand(B, -1, -1)  # (B, n_keys, embed_dim)
        v = k  # values = keys (prototype vectors)

        attn_out, _ = self.attention(q, k, v)  # attn_out: (B, 1, embed_dim)
        return attn_out.squeeze(1)  # (B, embed_dim)


class BetaNetwork(nn.Module):
    """MLP that maps attention + prior features to per-state beta(s)."""

    def __init__(self, attention_dim: int = 256, prior_dim: int = 64,
                 hidden_dim: int = 128, beta_min: float = 0.01, beta_max: float = 0.6):
        super().__init__()
        self.beta_min = beta_min
        self.beta_range = beta_max - beta_min

        self.net = nn.Sequential(
            nn.Linear(attention_dim + prior_dim, hidden_dim), nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim // 2), nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1), nn.Sigmoid(),
        )

    def forward(self, attn_feat: torch.Tensor, prior_feat: torch.Tensor) -> torch.Tensor:
        x = torch.cat([attn_feat, prior_feat], dim=-1)
        beta_raw = self.net(x)  # (B, 1), range [0, 1]
        return self.beta_min + self.beta_range * beta_raw  # (B, 1), range [beta_min, beta_max]


class AttentionPriorAgent:
    """SAC with attention-based state representation + physics priors for adaptive entropy."""

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
        # Attention-specific hyperparams
        embed_dim: int = 256,
        n_keys: int = 16,
        n_heads: int = 8,
        prior_dim: int = 64,
        beta_lr: float = 1e-4,
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

        if target_entropy is None:
            self.target_entropy = -action_dim
        else:
            self.target_entropy = target_entropy

        # SAC backbone
        self.actor = StochasticActor(
            obs_dim, action_dim, actor_hidden, max_action=max_action,
            log_std_min=-20, log_std_max=2
        ).to(device)

        self.critic1 = QNetwork(obs_dim, action_dim, critic_hidden).to(device)
        self.critic2 = QNetwork(obs_dim, action_dim, critic_hidden).to(device)
        self.critic1_target = deepcopy(self.critic1)
        self.critic2_target = deepcopy(self.critic2)

        # Attention + prior components
        self.prior_encoder = PhysicsPriorEncoder(prior_dim=prior_dim).to(device)
        self.attention_encoder = AttentionStateEncoder(
            obs_dim, embed_dim=embed_dim, n_keys=n_keys, n_heads=n_heads
        ).to(device)
        self.beta_network = BetaNetwork(
            attention_dim=embed_dim, prior_dim=prior_dim
        ).to(device)

        # Temperature (global baseline alpha)
        self.log_alpha = torch.tensor(np.log(alpha_init), requires_grad=True, device=device)

        # Optimizers
        self.actor_optimizer = torch.optim.Adam(self.actor.parameters(), lr=actor_lr)
        self.critic_optimizer = torch.optim.Adam(
            list(self.critic1.parameters()) + list(self.critic2.parameters()),
            lr=critic_lr
        )
        self.alpha_optimizer = torch.optim.Adam([self.log_alpha], lr=alpha_lr)
        self.beta_optimizer = torch.optim.Adam(
            list(self.prior_encoder.parameters()) +
            list(self.attention_encoder.parameters()) +
            list(self.beta_network.parameters()),
            lr=beta_lr
        )

        self._step_count = 0

    def _compute_beta(self, obs: torch.Tensor, next_obs: torch.Tensor) -> torch.Tensor:
        """Compute per-state beta(s) from attention + physics priors. Returns (B, 1)."""
        prior_feat = self.prior_encoder(obs, next_obs)  # (B, prior_dim)
        attn_feat = self.attention_encoder(obs)  # (B, embed_dim)
        beta = self.beta_network(attn_feat, prior_feat)  # (B, 1)
        return beta

    def select_action(self, obs: np.ndarray, deterministic: bool = False) -> np.ndarray:
        obs_t = torch.FloatTensor(obs).unsqueeze(0).to(self.device)
        with torch.no_grad():
            action, _ = self.actor.sample(obs_t, deterministic=deterministic)
        return action.cpu().numpy().flatten()

    def train(self, replay_buffer, batch_size: int = 256) -> Dict[str, float]:
        self._step_count += 1

        obs, actions, rewards, next_obs, dones = replay_buffer.sample(batch_size)

        # --- Compute per-state beta(s) and next_beta(s') ---
        beta_state = self._compute_beta(obs, next_obs).detach()  # (B, 1)
        beta_next = self._compute_beta(next_obs, obs).detach()  # (B, 1)

        # --- Critic update (with per-state beta in TD target) ---
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

        # --- Actor update (with per-state beta) ---
        new_actions, log_probs = self.actor.sample(obs)
        q1_new = self.critic1(obs, new_actions)
        q2_new = self.critic2(obs, new_actions)
        min_q_new = torch.min(q1_new, q2_new)

        actor_loss = (beta_state * log_probs - min_q_new).mean()

        self.actor_optimizer.zero_grad()
        actor_loss.backward()
        self.actor_optimizer.step()

        # --- Beta network update: regress beta toward entropy-aware target ---
        # Target: beta should be high when Q is confident (low TD variance), low otherwise
        with torch.no_grad():
            td_var_signal = ((q1_new - q2_new).abs() / (torch.abs(min_q_new) + 1e-6)).clamp(0, 1)
            beta_target = (self.log_alpha.exp() * (1.0 - 0.5 * td_var_signal)).clamp(0.01, 0.6)

        beta_current = self._compute_beta(obs, next_obs)
        beta_loss = F.mse_loss(beta_current, beta_target)

        self.beta_optimizer.zero_grad()
        beta_loss.backward()
        self.beta_optimizer.step()

        # --- Alpha auto-tune (SAC-style, for residual global temperature) ---
        alpha_loss_val = 0.0
        if self.alpha_auto_tune:
            alpha_loss = -(self.log_alpha.exp() * (log_probs.detach() + self.target_entropy)).mean()
            alpha_loss_val = alpha_loss.item()

            self.alpha_optimizer.zero_grad()
            alpha_loss.backward()
            self.alpha_optimizer.step()

        # --- Soft target updates ---
        soft_update(self.critic1_target, self.critic1, self.tau)
        soft_update(self.critic2_target, self.critic2, self.tau)

        alpha = self.log_alpha.exp().item()
        beta_mean = beta_state.mean().item()

        return {
            "critic_loss": critic_loss.item(),
            "actor_loss": actor_loss.item(),
            "alpha_loss": alpha_loss_val,
            "beta_loss": beta_loss.item(),
            "alpha": alpha,
            "beta_mean": beta_mean,
            "q1_mean": q1.mean().item(),
            "q2_mean": q2.mean().item(),
            "entropy": -log_probs.mean().item(),
        }

    def save(self, path: str):
        torch.save({
            "actor": self.actor.state_dict(),
            "critic1": self.critic1.state_dict(),
            "critic2": self.critic2.state_dict(),
            "critic1_target": self.critic1_target.state_dict(),
            "critic2_target": self.critic2_target.state_dict(),
            "prior_encoder": self.prior_encoder.state_dict(),
            "attention_encoder": self.attention_encoder.state_dict(),
            "beta_network": self.beta_network.state_dict(),
            "log_alpha": self.log_alpha.item(),
            "actor_optimizer": self.actor_optimizer.state_dict(),
            "critic_optimizer": self.critic_optimizer.state_dict(),
            "alpha_optimizer": self.alpha_optimizer.state_dict(),
            "beta_optimizer": self.beta_optimizer.state_dict(),
        }, path)

    def load(self, path: str):
        ckpt = torch.load(path, map_location=self.device)
        self.actor.load_state_dict(ckpt["actor"])
        self.critic1.load_state_dict(ckpt["critic1"])
        self.critic2.load_state_dict(ckpt["critic2"])
        self.critic1_target.load_state_dict(ckpt["critic1_target"])
        self.critic2_target.load_state_dict(ckpt["critic2_target"])
        self.prior_encoder.load_state_dict(ckpt["prior_encoder"])
        self.attention_encoder.load_state_dict(ckpt["attention_encoder"])
        self.beta_network.load_state_dict(ckpt["beta_network"])
        self.log_alpha.data = torch.tensor(ckpt["log_alpha"], device=self.device)
        self.actor_optimizer.load_state_dict(ckpt["actor_optimizer"])
        self.critic_optimizer.load_state_dict(ckpt["critic_optimizer"])
        self.alpha_optimizer.load_state_dict(ckpt["alpha_optimizer"])
        self.beta_optimizer.load_state_dict(ckpt["beta_optimizer"])
