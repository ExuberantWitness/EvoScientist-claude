"""
Configuration for Hopper-v4 Actor-Critic Experiments.

Based on the experimental plan:
  - Stage 1: Baselines (TD3, SAC, REDQ) + diagnostics
  - Stage 2A: PSAC (Phase-Space Actor-Critic)
  - Stage 2B: TCD (Temporal Credit Discriminator)
  - Stage 2C: VUMG (Value-Uncertainty Meta-Gradient)
  - Stage 3: Integration & Analysis

All values can be overridden via command line arguments.
"""

from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class EnvConfig:
    """Environment configuration."""
    env_name: str = "Hopper-v4"
    max_episode_steps: int = 1000
    obs_dim: int = 11          # Hopper-v4 observation space
    action_dim: int = 3        # Hopper-v4 action space
    max_action: float = 1.0    # Hopper action space is [-1, 1]


@dataclass
class NetworkConfig:
    """Neural network architecture configuration."""
    actor_hidden: List[int] = field(default_factory=lambda: [256, 256])
    critic_hidden: List[int] = field(default_factory=lambda: [256, 256])
    activation: str = "relu"
    init_scale: float = 3e-3    # Final layer init for actor
    layer_norm: bool = False


@dataclass
class TD3Config:
    """TD3-specific hyperparameters."""
    gamma: float = 0.99
    tau: float = 0.005           # Target network soft update
    policy_noise: float = 0.2    # Noise for target policy smoothing
    noise_clip: float = 0.5      # Clipped noise range
    policy_delay: int = 2        # Delayed actor updates
    actor_lr: float = 3e-4
    critic_lr: float = 3e-4
    batch_size: int = 256
    exploration_noise: float = 0.1  # OU or Gaussian noise for exploration
    noise_type: str = "gaussian"    # "gaussian" or "ou"
    ou_theta: float = 0.15
    ou_sigma: float = 0.2
    warmup_steps: int = 25000    # Random exploration before learning


@dataclass
class SACConfig:
    """SAC-specific hyperparameters."""
    gamma: float = 0.99
    tau: float = 0.005
    actor_lr: float = 3e-4
    critic_lr: float = 3e-4
    alpha_lr: float = 3e-4       # Temperature auto-tuning
    batch_size: int = 256
    alpha_init: float = 0.2      # Initial entropy coefficient
    alpha_auto_tune: bool = True  # Auto-tune entropy temperature
    target_entropy: Optional[float] = None  # -action_dim if None
    warmup_steps: int = 25000
    log_std_min: float = -20.0
    log_std_max: float = 2.0


@dataclass
class REDQConfig:
    """REDQ-specific hyperparameters."""
    gamma: float = 0.99
    tau: float = 0.005
    actor_lr: float = 3e-4
    critic_lr: float = 3e-4
    batch_size: int = 256
    n_critics: int = 5             # Ensemble size K
    sample_critics: int = 2        # M: number of critics sampled per update (UTD = G = K/M)
    exploration_noise: float = 0.1
    policy_noise: float = 0.2
    noise_clip: float = 0.5
    policy_delay: int = 1          # REDQ updates actor every step (not delayed)
    warmup_steps: int = 25000


@dataclass
class PSACConfig:
    """Phase-Space Actor-Critic configuration (Proposal A)."""
    gamma: float = 0.99
    tau: float = 0.005
    actor_lr: float = 3e-4
    critic_lr: float = 3e-4
    phase_lr: float = 3e-4         # Phase encoder + ω learning rate
    batch_size: int = 256
    policy_noise: float = 0.2
    noise_clip: float = 0.5
    policy_delay: int = 2
    exploration_noise: float = 0.1
    warmup_steps: int = 25000

    # Phase-specific
    phase_dim: int = 2             # [sin(θ), cos(θ)] output
    phase_hidden: int = 64         # Phase encoder hidden dim
    omega_init: float = 1.0        # Initial ω (phase velocity)
    omega_lr: float = 1e-3         # Separate learning rate for ω
    use_phase_for_critic: bool = True
    learn_omega: bool = True       # Learn ω vs fixed ω
    phase_for: str = "both"        # "actor", "critic", "both"


@dataclass
class TCDConfig:
    """Temporal Credit Discriminator configuration (Proposal B)."""
    gamma: float = 0.99
    tau: float = 0.005
    actor_lr: float = 3e-4
    critic_lr: float = 3e-4
    discriminator_lr: float = 3e-4
    batch_size: int = 256
    policy_noise: float = 0.2
    noise_clip: float = 0.5
    policy_delay: int = 2
    exploration_noise: float = 0.1
    warmup_steps: int = 25000

    # TCD-specific
    trajectory_len: int = 32       # K: trajectory chunk length
    d_model: int = 64              # Transformer hidden dim
    n_layers: int = 2              # Transformer layers
    n_heads: int = 2               # Attention heads
    discrim_type: str = "transformer"  # "transformer" or "gru"
    grad_penalty: float = 10.0     # For WGAN-style training
    discrim_update_freq: int = 1   # Discriminator updates per critic update


@dataclass
class VUMGConfig:
    """Value-Uncertainty Meta-Gradient configuration (Proposal C)."""
    gamma: float = 0.99
    tau: float = 0.005
    actor_lr: float = 3e-4
    critic_lr: float = 3e-4
    lambda_lr: float = 3e-4        # For adaptive λ
    batch_size: int = 256
    policy_noise: float = 0.2
    noise_clip: float = 0.5
    policy_delay: int = 2
    exploration_noise: float = 0.1
    warmup_steps: int = 25000

    # VUMG-specific
    n_critics: int = 5             # K: ensemble size
    lambda_init: float = 0.1       # Initial exploration coefficient λ
    adaptive_lambda: bool = True   # Self-adapt λ
    lambda_lower_bound: float = 0.01
    lambda_upper_bound: float = 1.0
    use_meta_gradient: bool = True  # True=meta-gradient, False=reward-bonus


@dataclass
class DDPGConfig:
    """DDPG-specific hyperparameters."""
    gamma: float = 0.99
    tau: float = 0.005
    actor_lr: float = 3e-4
    critic_lr: float = 3e-4
    batch_size: int = 256
    exploration_noise: float = 0.1
    noise_type: str = "gaussian"
    ou_theta: float = 0.15
    ou_sigma: float = 0.2
    warmup_steps: int = 25000


@dataclass
class PPOConfig:
    """PPO-specific hyperparameters."""
    gamma: float = 0.99
    gae_lambda: float = 0.95
    actor_lr: float = 3e-4
    critic_lr: float = 3e-4
    batch_size: int = 256
    clip_eps: float = 0.2
    n_epochs: int = 10
    mini_batch_size: int = 64
    entropy_coef: float = 0.01
    value_coef: float = 0.5
    max_grad_norm: float = 0.5
    rollout_steps: int = 2048      # Steps to collect before each update
    normalize_advantage: bool = True
    warmup_steps: int = 0          # PPO doesn't need random warmup


@dataclass
class EMTD3Config:
    """EMTD3 (Entropy-Maximizing TD3) hyperparameters."""
    gamma: float = 0.99
    tau: float = 0.005
    policy_noise: float = 0.2
    noise_clip: float = 0.5
    policy_delay: int = 2
    actor_lr: float = 3e-4
    critic_lr: float = 3e-4
    alpha_lr: float = 3e-4
    batch_size: int = 256
    exploration_noise: float = 0.1    # Exploration noise on top of stochastic actor
    noise_type: str = "gaussian"
    ou_theta: float = 0.15
    ou_sigma: float = 0.2
    alpha_init: float = 0.2
    alpha_auto_tune: bool = True
    target_entropy: Optional[float] = None
    log_std_min: float = -20.0
    log_std_max: float = 2.0
    warmup_steps: int = 25000


@dataclass
class ACEConfig:
    """ACE (Causality-Aware Entropy Regularization) hyperparameters."""
    gamma: float = 0.99
    tau: float = 0.005
    actor_lr: float = 3e-4
    critic_lr: float = 3e-4
    causal_lr: float = 3e-4
    alpha_lr: float = 3e-4
    batch_size: int = 256
    alpha_init: float = 0.2
    alpha_auto_tune: bool = True
    target_entropy: Optional[float] = None
    log_std_min: float = -20.0
    log_std_max: float = 2.0
    causal_hidden: int = 64
    causal_layers: int = 2
    entropy_scale: float = 1.0      # Scale factor for causal entropy weights
    warmup_steps: int = 25000


@dataclass
class CrossQConfig:
    """CrossQ hyperparameters (LayerNorm default, BatchNorm opt-in, UTD=1)."""
    gamma: float = 0.99
    tau: float = 0.005
    actor_lr: float = 3e-4
    critic_lr: float = 3e-4
    batch_size: int = 256
    policy_noise: float = 0.2
    noise_clip: float = 0.5
    policy_delay: int = 2
    utd: int = 1                    # Update-To-Data ratio
    exploration_noise: float = 0.1
    alpha_init: float = 0.2         # For potential reward shaping
    use_potential_shaping: bool = True
    batch_norm: bool = False        # Use BatchNorm (original) vs LayerNorm (stable)
    warmup_steps: int = 25000


@dataclass
class BSRSConfig:
    """BSRS (Bootstrapped Self-Rescaling Reward Shaping) hyperparameters."""
    gamma: float = 0.99
    shaping_scale: float = 1.0      # Scale factor for shaped reward
    vf_lr: float = 3e-4             # Learning rate for V(s) estimator
    vf_hidden: List[int] = field(default_factory=lambda: [128, 128])
    vf_update_freq: int = 1         # Update V(s) every N steps
    warmup_steps: int = 25000       # Don't shape reward before V(s) is stable


@dataclass
class MAPConfig:
    """Meta-Adaptive Policy (MAP) hyperparameters.

    MAP adds a state-conditioned entropy coefficient alpha(s) on top of a
    TD3-style backbone. A small MLP maps observation -> entropy multiplier,
    making the exploration/exploitation trade-off per-state adaptive.
    """
    gamma: float = 0.99
    tau: float = 0.005
    policy_noise: float = 0.2
    noise_clip: float = 0.5
    policy_delay: int = 2
    actor_lr: float = 3e-4
    critic_lr: float = 3e-4
    alpha_lr: float = 3e-4
    adaptive_lr: float = 3e-4       # State-conditional alpha network LR
    batch_size: int = 256
    exploration_noise: float = 0.1    # Exploration noise on top of stochastic actor
    noise_type: str = "gaussian"
    ou_theta: float = 0.15
    ou_sigma: float = 0.2
    alpha_init: float = 0.2
    alpha_auto_tune: bool = True
    target_entropy: Optional[float] = None
    log_std_min: float = -20.0
    log_std_max: float = 2.0
    adaptive_hidden: int = 64        # Hidden dim for alpha(s) network
    warmup_steps: int = 25000


@dataclass
class SMEConfig:
    """Stochastic Mutation Engine (SME) hyperparameters.

    SME maintains a population of N critics. Periodically mutates critic
    weights (Gaussian noise) and selects the top-K by TD error. Maps the
    evolutionary algorithm mutation/selection loop to critic ensemble management.
    """
    gamma: float = 0.99
    tau: float = 0.005
    actor_lr: float = 3e-4
    critic_lr: float = 3e-4
    alpha_lr: float = 3e-4
    batch_size: int = 256
    alpha_init: float = 0.2
    alpha_auto_tune: bool = True
    target_entropy: Optional[float] = None
    log_std_min: float = -20.0
    log_std_max: float = 2.0
    n_critics: int = 5               # Population size (original: 5)
    mutation_rate: float = 0.01      # Gaussian noise std for mutation
    mutation_freq: int = 100         # Steps between mutations
    elite_fraction: float = 0.4      # Top fraction retained (original: 0.4)
    warmup_steps: int = 25000


@dataclass
class SMEv2Config:
    """SME-v2 hyperparameters.

    Improved SME with TD3-style target policy smoothing, delayed actor updates,
    adaptive mutation rate decay, and larger critic population.
    """
    gamma: float = 0.99
    tau: float = 0.005
    actor_lr: float = 3e-4
    critic_lr: float = 3e-4
    alpha_lr: float = 3e-4
    batch_size: int = 256
    alpha_init: float = 0.2
    alpha_auto_tune: bool = True
    target_entropy: Optional[float] = None
    log_std_min: float = -20.0
    log_std_max: float = 2.0
    n_critics: int = 8                # Larger population (original: 5)
    mutation_rate: float = 0.05       # Initial mutation rate (higher start)
    mutation_rate_min: float = 0.001  # Minimum mutation rate
    mutation_freq: int = 200          # Less frequent mutation (original: 100)
    elite_fraction: float = 0.5       # Half are elite (original: 0.4)
    policy_noise: float = 0.2         # TD3-style target smoothing
    noise_clip: float = 0.5           # Noise clip for target smoothing
    policy_delay: int = 2             # Delayed actor updates
    warmup_steps: int = 25000


@dataclass
class MAPv2Config:
    """MAP-v2 hyperparameters.

    Redesigned MAP: removes global alpha, uses per-state alpha(s) as sole
    entropy coefficient. Alpha(s) trained to match Q-uncertainty signal
    with warmup delay for stable Q estimates.
    """
    gamma: float = 0.99
    tau: float = 0.005
    policy_noise: float = 0.2
    noise_clip: float = 0.5
    policy_delay: int = 2
    actor_lr: float = 3e-4
    critic_lr: float = 3e-4
    adaptive_lr: float = 1e-4         # Slower LR for stability
    batch_size: int = 256
    log_std_min: float = -20.0
    log_std_max: float = 2.0
    adaptive_hidden: int = 128        # Larger network (original: 64)
    adaptive_warmup: int = 50000      # Freeze alpha(s) until Q-values stabilize
    exploration_noise: float = 0.1
    noise_type: str = "gaussian"
    ou_theta: float = 0.15
    ou_sigma: float = 0.2
    warmup_steps: int = 25000


@dataclass
class GraftConfig:
    """Graft hyperparameters: TD3 + BSRS reward shaping + entropy regularization."""
    gamma: float = 0.99
    tau: float = 0.005
    policy_noise: float = 0.2
    noise_clip: float = 0.5
    policy_delay: int = 2
    actor_lr: float = 3e-4
    critic_lr: float = 3e-4
    alpha_lr: float = 3e-4
    potential_lr: float = 3e-4
    alpha_init: float = 0.2
    alpha_auto_tune: bool = True
    target_entropy: Optional[float] = None
    log_std_min: float = -20.0
    log_std_max: float = 2.0
    exploration_noise: float = 0.1
    noise_type: str = "gaussian"
    ou_theta: float = 0.15
    ou_sigma: float = 0.2
    batch_size: int = 256
    shaping_scale: float = 1.0
    potential_update_freq: int = 1
    warmup_steps: int = 25000


@dataclass
class TrainingConfig:
    """Training loop configuration."""
    total_steps: int = 1_000_000   # 1M environment steps
    eval_freq: int = 10_000        # Evaluate every 10k steps
    eval_episodes: int = 10        # Number of eval episodes
    save_freq: int = 100_000       # Checkpoint frequency
    log_freq: int = 1_000          # Console logging frequency
    n_seeds: int = 10
    seeds: List[int] = field(default_factory=lambda: list(range(10)))
    device: str = "cuda"
    use_wandb: bool = False
    wandb_project: str = "hopper-actor-critic"
    wandb_entity: Optional[str] = None
    output_dir: str = "./hopper_experiments"
    deterministic_eval: bool = True
    track_grad_norm: bool = True   # For gradient health monitoring
    grad_norm_threshold: float = 10.0  # Reject if grad norm > 10x running mean


@dataclass
class ExperimentConfig:
    """Master configuration combining all sub-configs."""
    env: EnvConfig = field(default_factory=EnvConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    td3: TD3Config = field(default_factory=TD3Config)
    sac: SACConfig = field(default_factory=SACConfig)
    redq: REDQConfig = field(default_factory=REDQConfig)
    ddpg: DDPGConfig = field(default_factory=DDPGConfig)
    ppo: PPOConfig = field(default_factory=PPOConfig)
    emtd3: EMTD3Config = field(default_factory=EMTD3Config)
    ace: ACEConfig = field(default_factory=ACEConfig)
    crossq: CrossQConfig = field(default_factory=CrossQConfig)
    bsrs: BSRSConfig = field(default_factory=BSRSConfig)
    map: MAPConfig = field(default_factory=MAPConfig)
    graft: GraftConfig = field(default_factory=GraftConfig)
    sme: SMEConfig = field(default_factory=SMEConfig)
    sme_v2: SMEv2Config = field(default_factory=SMEv2Config)
    map_v2: MAPv2Config = field(default_factory=MAPv2Config)
    psac: PSACConfig = field(default_factory=PSACConfig)
    tcd: TCDConfig = field(default_factory=TCDConfig)
    vumg: VUMGConfig = field(default_factory=VUMGConfig)
    training: TrainingConfig = field(default_factory=TrainingConfig)


def get_config(algorithm: str) -> ExperimentConfig:
    """Get a configuration object with algorithm-specific defaults."""
    config = ExperimentConfig()
    return config


def override_from_args(config: ExperimentConfig, args: dict):
    """Override config fields from command-line arguments."""
    for key, value in args.items():
        if value is None:
            continue
        parts = key.split(".")
        obj = config
        for part in parts[:-1]:
            if hasattr(obj, part):
                obj = getattr(obj, part)
            else:
                break
        else:
            if hasattr(obj, parts[-1]):
                setattr(obj, parts[-1], value)
