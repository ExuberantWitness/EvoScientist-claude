"""
Neural network architectures for actor-critic RL algorithms.

Includes:
  - MLP (shared backbone)
  - Actor (deterministic and stochastic)
  - Critic (single and ensemble)
  - Phase encoder (for PSAC)
  - Temporal discriminator (Transformer-based, for TCD)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import math
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Weight initialization
# ---------------------------------------------------------------------------

def orthogonal_init(layer: nn.Linear, gain: float = 1.0):
    """Orthogonal weight initialization."""
    nn.init.orthogonal_(layer.weight, gain=gain)
    if layer.bias is not None:
        nn.init.constant_(layer.bias, 0.0)


def xavier_init(layer: nn.Linear, gain: float = 1.0):
    """Xavier uniform initialization."""
    nn.init.xavier_uniform_(layer.weight, gain=gain)
    if layer.bias is not None:
        nn.init.constant_(layer.bias, 0.0)


# ---------------------------------------------------------------------------
# MLP backbone
# ---------------------------------------------------------------------------

class MLP(nn.Module):
    """Multi-layer perceptron with configurable norm and activation."""

    def __init__(
        self,
        input_dim: int,
        hidden_dims: List[int],
        output_dim: int,
        activation: str = "relu",
        final_activation: Optional[str] = None,
        layer_norm: bool = False,
        batch_norm: bool = False,
    ):
        super().__init__()
        layers = []
        prev_dim = input_dim

        act_fn = {"relu": nn.ReLU(), "tanh": nn.Tanh(),
                   "leaky_relu": nn.LeakyReLU(0.01), "elu": nn.ELU()}[activation]

        for h in hidden_dims:
            layers.append(nn.Linear(prev_dim, h))
            if layer_norm:
                layers.append(nn.LayerNorm(h))
            if batch_norm:
                layers.append(nn.BatchNorm1d(h))
            layers.append(act_fn)
            prev_dim = h

        layers.append(nn.Linear(prev_dim, output_dim))
        if final_activation is not None:
            fa = {"tanh": nn.Tanh(), "sigmoid": nn.Sigmoid(), "relu": nn.ReLU()}[final_activation]
            layers.append(fa)

        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


# ---------------------------------------------------------------------------
# Deterministic Actor (for TD3 family)
# ---------------------------------------------------------------------------

class DeterministicActor(nn.Module):
    """Deterministic policy: s → a = tanh(MLP(s))."""

    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        hidden_dims: List[int],
        max_action: float = 1.0,
        init_scale: float = 3e-3,
    ):
        super().__init__()
        self.max_action = max_action
        self.net = MLP(obs_dim, hidden_dims, action_dim,
                       activation="relu", final_activation="tanh")

        # Small final layer init for stability
        last_layer = list(self.net.net.children())[-1]
        if isinstance(last_layer, nn.Linear):
            nn.init.uniform_(last_layer.weight, -init_scale, init_scale)
            nn.init.uniform_(last_layer.bias, -init_scale, init_scale)

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        return self.max_action * self.net(obs)


# ---------------------------------------------------------------------------
# Stochastic Actor (for SAC)
# ---------------------------------------------------------------------------

class StochasticActor(nn.Module):
    """Stochastic policy: s → (μ, log_σ) → a ~ N(μ, σ) → tanh(a)."""

    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        hidden_dims: List[int],
        max_action: float = 1.0,
        log_std_min: float = -20.0,
        log_std_max: float = 2.0,
    ):
        super().__init__()
        self.max_action = max_action
        self.log_std_min = log_std_min
        self.log_std_max = log_std_max

        # Shared backbone
        self.backbone = MLP(obs_dim, hidden_dims, hidden_dims[-1],
                            activation="relu")

        # Separate heads for mean and log_std
        self.mean_head = nn.Linear(hidden_dims[-1], action_dim)
        self.log_std_head = nn.Linear(hidden_dims[-1], action_dim)

        self._init_weights()

    def _init_weights(self):
        nn.init.uniform_(self.mean_head.weight, -3e-3, 3e-3)
        nn.init.uniform_(self.mean_head.bias, -3e-3, 3e-3)
        nn.init.uniform_(self.log_std_head.weight, -3e-3, 3e-3)
        nn.init.uniform_(self.log_std_head.bias, -3e-3, 3e-3)

    def forward(self, obs: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Returns: mean, log_std."""
        h = self.backbone(obs)
        mean = self.mean_head(h)
        log_std = torch.clamp(self.log_std_head(h),
                              self.log_std_min, self.log_std_max)
        return mean, log_std

    def sample(
        self, obs: torch.Tensor, deterministic: bool = False
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """Sample action. Returns: action, log_prob."""
        mean, log_std = self.forward(obs)

        if deterministic:
            action = torch.tanh(mean) * self.max_action
            log_prob = None
            return action, log_prob

        std = log_std.exp()
        # Reparameterization trick
        normal = torch.distributions.Normal(mean, std)
        z = normal.rsample()
        action = torch.tanh(z) * self.max_action

        # Log probability with tanh squashing correction
        log_prob = normal.log_prob(z)
        # Correct for tanh transformation: log(1 - tanh(z)^2)
        log_prob -= torch.log(1 - action.pow(2) / self.max_action**2 + 1e-6)
        log_prob = log_prob.sum(dim=-1, keepdim=True)

        return action, log_prob


# ---------------------------------------------------------------------------
# Q-Network (Critic)
# ---------------------------------------------------------------------------

class VNetwork(nn.Module):
    """State-value function: s → V(s). Used by PPO."""

    def __init__(
        self,
        obs_dim: int,
        hidden_dims: List[int],
    ):
        super().__init__()
        self.net = MLP(obs_dim, hidden_dims, 1, activation="relu")
        self._init_weights()

    def _init_weights(self):
        last_layer = list(self.net.net.children())[-1]
        if isinstance(last_layer, nn.Linear):
            nn.init.orthogonal_(last_layer.weight, gain=1.0)
            nn.init.constant_(last_layer.bias, 0.0)

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        return self.net(obs)


class QNetwork(nn.Module):
    """Q-value function: (s, a) → Q(s, a)."""

    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        hidden_dims: List[int],
    ):
        super().__init__()
        self.net = MLP(obs_dim + action_dim, hidden_dims, 1,
                       activation="relu")
        self._init_weights()

    def _init_weights(self):
        last_layer = list(self.net.net.children())[-1]
        if isinstance(last_layer, nn.Linear):
            nn.init.uniform_(last_layer.weight, -3e-3, 3e-3)
            nn.init.uniform_(last_layer.bias, -3e-3, 3e-3)

    def forward(self, obs: torch.Tensor, action: torch.Tensor) -> torch.Tensor:
        x = torch.cat([obs, action], dim=-1)
        return self.net(x)


class QuantileQNetwork(nn.Module):
    """IQN-style quantile Q-network.

    Given (obs, action) and N random tau values in [0,1], outputs N quantile
    values. Uses cosine embedding of tau followed by Hadamard-product fusion
    with the state-action encoding.
    """

    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        n_quantiles: int = 32,
        hidden_dims: list = None,
        embedding_dim: int = 64,
    ):
        super().__init__()
        if hidden_dims is None:
            hidden_dims = [256, 256]
        self.n_quantiles = n_quantiles
        self.embedding_dim = embedding_dim

        # State-action encoder → embedding_dim features
        self.sa_fc = MLP(obs_dim + action_dim, hidden_dims, embedding_dim,
                         activation="relu")

        # Cosine embedding coefficients: i * pi for i=1..embedding_dim
        self.register_buffer(
            'cos_coeffs',
            torch.arange(1, embedding_dim + 1).float() * math.pi
        )

        # Tau embedding: cos-embedded tau → embedding_dim
        self.tau_fc = nn.Sequential(
            nn.Linear(embedding_dim, hidden_dims[0]),
            nn.ReLU(),
            nn.Linear(hidden_dims[0], embedding_dim),
            nn.ReLU(),
        )

        # Output head: embedding_dim → 1 (scalar quantile value)
        self.output_fc = nn.Linear(embedding_dim, 1)

        self._init_weights()

    def _init_weights(self):
        nn.init.uniform_(self.output_fc.weight, -3e-3, 3e-3)
        nn.init.uniform_(self.output_fc.bias, -3e-3, 3e-3)

    def forward(
        self,
        obs: torch.Tensor,
        action: torch.Tensor,
        taus: torch.Tensor,
    ) -> torch.Tensor:
        """
        Args:
            obs: (B, obs_dim)
            action: (B, action_dim)
            taus: (B, N, 1) — random quantile fractions in [0, 1]
        Returns:
            quantiles: (B, N, 1)
        """
        B, N, _ = taus.shape

        # State-action encoding: (B, embedding_dim)
        x = torch.cat([obs, action], dim=-1)
        sa_feat = self.sa_fc(x)  # (B, E)

        # Cosine embedding of tau values
        tau_flat = taus.view(B * N, 1)  # (B*N, 1)
        tau_cos = torch.cos(tau_flat * self.cos_coeffs)  # (B*N, E)
        tau_feat = self.tau_fc(tau_cos)  # (B*N, E)
        tau_feat = tau_feat.view(B, N, self.embedding_dim)  # (B, N, E)

        # Hadamard product fusion
        sa_feat_exp = sa_feat.unsqueeze(1)  # (B, 1, E)
        fused = tau_feat * sa_feat_exp  # (B, N, E)

        # Output scalar quantile per (obs, action, tau)
        fused_flat = fused.reshape(B * N, self.embedding_dim)
        q_values = self.output_fc(fused_flat)  # (B*N, 1)
        return q_values.view(B, N, 1)


class CriticEnsemble(nn.Module):
    """Ensemble of Q-networks."""
    def __init__(
        self,
        n_critics: int,
        obs_dim: int,
        action_dim: int,
        hidden_dims: List[int],
    ):
        super().__init__()
        self.critics = nn.ModuleList([
            QNetwork(obs_dim, action_dim, hidden_dims) for _ in range(n_critics)
        ])

    def forward_all(self, obs: torch.Tensor, action: torch.Tensor) -> torch.Tensor:
        """Returns: (n_critics, batch, 1)"""
        return torch.stack([c(obs, action) for c in self.critics], dim=0)

    def sample(self, obs: torch.Tensor, action: torch.Tensor,
               n_sample: int = 2) -> torch.Tensor:
        """Sample a random subset of critics. Returns: (n_sample, batch, 1)."""
        idxs = torch.randperm(len(self.critics))[:n_sample]
        return torch.stack([self.critics[i](obs, action) for i in idxs], dim=0)


# ---------------------------------------------------------------------------
# Phase Encoder (for PSAC)
# ---------------------------------------------------------------------------

class PhaseEncoder(nn.Module):
    """
    Encodes observation into a cyclic phase representation.
    Output: [sin(θ), cos(θ)] ∈ S^1 (unit circle).
    """

    def __init__(
        self,
        obs_dim: int,
        hidden_dim: int = 64,
        phase_dim: int = 2,
    ):
        super().__init__()
        self.phase_dim = phase_dim  # Should be 2 for [sin, cos]
        self.encoder = nn.Sequential(
            nn.Linear(obs_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),  # Raw angle θ
        )
        self.omega_net = nn.Sequential(
            nn.Linear(obs_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),  # Raw omega
        )

    def forward(self, obs: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            obs: (batch, obs_dim)
        Returns:
            phase: (batch, 2) → [sin(θ), cos(θ)]
            omega: (batch, 1) → raw angular velocity (passed through softplus)
        """
        theta = self.encoder(obs)  # (batch, 1)
        phase = torch.cat([torch.sin(theta), torch.cos(theta)], dim=-1)
        omega_raw = self.omega_net(obs)
        omega = F.softplus(omega_raw)  # Positive frequency
        return phase, omega


# ---------------------------------------------------------------------------
# Conditional Actor/Critic (for PSAC — phase-aware)
# ---------------------------------------------------------------------------

class PhaseConditionalActor(nn.Module):
    """Actor that conditions on both observation and phase."""

    def __init__(
        self,
        obs_dim: int,
        phase_dim: int,
        action_dim: int,
        hidden_dims: List[int],
        max_action: float = 1.0,
        init_scale: float = 3e-3,
    ):
        super().__init__()
        self.max_action = max_action
        self.net = MLP(obs_dim + phase_dim, hidden_dims, action_dim,
                       activation="relu", final_activation="tanh")

        last_layer = list(self.net.net.children())[-1]
        if isinstance(last_layer, nn.Linear):
            nn.init.uniform_(last_layer.weight, -init_scale, init_scale)
            nn.init.uniform_(last_layer.bias, -init_scale, init_scale)

    def forward(self, obs: torch.Tensor, phase: torch.Tensor) -> torch.Tensor:
        x = torch.cat([obs, phase], dim=-1)
        return self.max_action * self.net(x)


class PhaseConditionalCritic(nn.Module):
    """Twin critic conditioned on obs, action, and phase."""

    def __init__(
        self,
        obs_dim: int,
        phase_dim: int,
        action_dim: int,
        hidden_dims: List[int],
    ):
        super().__init__()
        input_dim = obs_dim + phase_dim + action_dim
        self.q1 = QNetwork(obs_dim + phase_dim, action_dim, hidden_dims)
        self.q2 = QNetwork(obs_dim + phase_dim, action_dim, hidden_dims)

    def forward(self, obs: torch.Tensor, phase: torch.Tensor,
                action: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Returns: (q1, q2)."""
        aug_obs = torch.cat([obs, phase], dim=-1)
        return self.q1(aug_obs, action), self.q2(aug_obs, action)

    def q_min(self, obs: torch.Tensor, phase: torch.Tensor,
              action: torch.Tensor) -> torch.Tensor:
        """Returns min(q1, q2) for conservative updates."""
        q1, q2 = self.forward(obs, phase, action)
        return torch.min(q1, q2)


# ---------------------------------------------------------------------------
# Temporal Credit Discriminator (for TCD)
# ---------------------------------------------------------------------------

class PositionalEncoding(nn.Module):
    """Sinusoidal positional encoding for Transformer."""

    def __init__(self, d_model: int, max_len: int = 5000):
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        self.register_buffer('pe', pe.unsqueeze(0))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (batch, seq_len, d_model)."""
        return x + self.pe[:, :x.size(1)]


class CausalTransformerDiscriminator(nn.Module):
    """
    Causal Transformer for temporal credit assignment.
    Input: trajectory of (s_t, a_t) pairs
    Output: per-step credit weights w_t
    """

    def __init__(
        self,
        input_dim: int,       # obs_dim + action_dim
        d_model: int = 64,
        n_layers: int = 2,
        n_heads: int = 2,
        max_len: int = 64,
    ):
        super().__init__()
        self.input_proj = nn.Linear(input_dim, d_model)
        self.pos_encoder = PositionalEncoding(d_model, max_len)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=n_heads,
            dim_feedforward=d_model * 4,
            dropout=0.1,
            batch_first=True,
        )
        # Causal mask: can only attend to past
        self.causal_mask = torch.triu(
            torch.ones(max_len, max_len), diagonal=1
        ).bool()
        self.transformer = nn.TransformerEncoder(encoder_layer, n_layers)

        # Output per-step weight
        self.weight_head = nn.Sequential(
            nn.Linear(d_model, d_model),
            nn.ReLU(),
            nn.Linear(d_model, 1),
            nn.Sigmoid(),  # Weights in [0, 1]
        )

        # Global trajectory classifier (for contrastive loss)
        self.global_proj = nn.Sequential(
            nn.Linear(d_model, d_model),
            nn.ReLU(),
            nn.Linear(d_model, 1),
            nn.Sigmoid(),
        )

    def forward(
        self, x: torch.Tensor, mask: Optional[torch.Tensor] = None
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            x: (batch, seq_len, input_dim)
            mask: (batch, seq_len) optional padding mask
        Returns:
            weights: (batch, seq_len, 1) per-step credit weights
            global_score: (batch, 1) trajectory-level score
        """
        batch, seq_len, _ = x.shape
        h = self.input_proj(x)  # (batch, seq_len, d_model)
        h = self.pos_encoder(h)

        # Build causal mask
        causal_mask = self.causal_mask[:seq_len, :seq_len].to(x.device)

        h = self.transformer(h, mask=causal_mask, src_key_padding_mask=mask)
        # (batch, seq_len, d_model)

        weights = self.weight_head(h)  # (batch, seq_len, 1)

        # Global pooling (mean over sequence)
        if mask is not None:
            valid_mask = (~mask).float().unsqueeze(-1)
            h_pooled = (h * valid_mask).sum(dim=1) / valid_mask.sum(dim=1).clamp(min=1)
        else:
            h_pooled = h.mean(dim=1)

        global_score = self.global_proj(h_pooled)  # (batch, 1)

        return weights, global_score


class GRUDiscriminator(nn.Module):
    """GRU-based discriminator as ablation alternative to Transformer."""

    def __init__(
        self,
        input_dim: int,
        hidden_dim: int = 128,
        n_layers: int = 2,
    ):
        super().__init__()
        self.gru = nn.GRU(input_dim, hidden_dim, n_layers,
                          batch_first=True, bidirectional=False)
        self.weight_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
            nn.Sigmoid(),
        )
        self.global_proj = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
            nn.Sigmoid(),
        )

    def forward(
        self, x: torch.Tensor, mask: Optional[torch.Tensor] = None
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        h, _ = self.gru(x)  # (batch, seq_len, hidden_dim)
        weights = self.weight_head(h)

        if mask is not None:
            valid_mask = (~mask).float().unsqueeze(-1)
            h_pooled = (h * valid_mask).sum(dim=1) / valid_mask.sum(dim=1).clamp(min=1)
        else:
            h_pooled = h.mean(dim=1)

        global_score = self.global_proj(h_pooled)
        return weights, global_score


# ---------------------------------------------------------------------------
# Utility: soft target update
# ---------------------------------------------------------------------------

def soft_update(target: nn.Module, source: nn.Module, tau: float):
    """Polyak averaging: target = tau * source + (1-tau) * target."""
    for tp, sp in zip(target.parameters(), source.parameters()):
        tp.data.copy_(tau * sp.data + (1.0 - tau) * tp.data)


def hard_update(target: nn.Module, source: nn.Module):
    """Copy source parameters to target."""
    for tp, sp in zip(target.parameters(), source.parameters()):
        tp.data.copy_(sp.data)


# ---------------------------------------------------------------------------
# QVGN-SAC: Modulator + RunningStats
# ---------------------------------------------------------------------------

class RunningStats:
    """EMA-updated running statistics for uncertainty signal normalization.

    Uses exponential moving average to track mean and std of streaming
    uncertainty signals (quantile variance, gradient norm). Normalized
    values are clamped to [-clip, clip] to prevent outlier batches from
    destabilizing the Modulator.
    """

    def __init__(self, momentum: float = 0.001, clip: float = 5.0):
        self.momentum = momentum
        self.clip = clip
        self.mean = None
        self.var = None
        self.initialized = False

    def update(self, x: torch.Tensor):
        """Update running statistics with batch data (EMA)."""
        batch_mean = x.mean().detach()
        batch_var = x.var(unbiased=False).detach()

        if not self.initialized:
            self.mean = batch_mean
            self.var = batch_var
            self.initialized = True
        else:
            self.mean = (1 - self.momentum) * self.mean + self.momentum * batch_mean
            self.var = (1 - self.momentum) * self.var + self.momentum * batch_var

    def normalize(self, x: torch.Tensor) -> torch.Tensor:
        """Z-score normalize and clamp."""
        if not self.initialized:
            self.update(x)
        return ((x - self.mean) / (self.var.sqrt() + 1e-8)).clamp(-self.clip, self.clip)


class Modulator(nn.Module):
    """Maps state + uncertainty features to per-dimension exploration scaling.

    Input:  [obs (11) || norm_quantile_var (1) || norm_gradient_norm (1)] = 13
    Output: sigma_scale per action dimension, constrained to [sigma_min, sigma_max]
            via sigmoid. Default (no modulation) = 1.0.
    """

    def __init__(
        self,
        input_dim: int = 13,
        hidden_dim: int = 64,
        action_dim: int = 3,
        output_min: float = 0.5,
        output_max: float = 2.0,
    ):
        super().__init__()
        self.output_min = output_min
        self.output_max = output_max
        self.shared = nn.Sequential(
            nn.Linear(input_dim, hidden_dim), nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim), nn.ReLU(),
        )
        self.sigma_head = nn.Linear(hidden_dim, action_dim)

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        """Returns sigma_scale in [output_min, output_max] per action dim."""
        h = self.shared(features)
        raw = self.sigma_head(h)
        return self.output_min + (self.output_max - self.output_min) * torch.sigmoid(raw)
