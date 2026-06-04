#!/usr/bin/env python3
"""
Master training script -- runs all baselines and proposals on Hopper-v4.

Usage:
    python train_all.py                              # Full training (1M steps, 3 seeds)
    python train_all.py --quick                      # Quick smoke (5k steps, 1 seed)
    python train_all.py --algo sac td3 ddpg          # Specific algorithms
    python train_all.py --device cpu                 # CPU mode
"""

import os
import sys
import json
import argparse
import time
import numpy as np
import torch

from config import ExperimentConfig
from trainer import Trainer

# Baselines (always available)
from td3 import TD3Agent
from sac import SACAgent
from ddpg import DDPGAgent

# Proposals (imported as they are implemented)
_proposal_agents = {}
_proposal_names = [
    "attention_prior",
    "td_variance",
    "value_uncertainty",
    "dp_depth",
    "taylor_curvature",
    "gait_phase",
    "iqn_quantile",
    "iqn_quantile_simple",
    "dual_critic_attention",
]

try:
    from 基于注意力机制与状态先验不确定性的自适应 import AttentionPriorAgent
    _proposal_agents["attention_prior"] = AttentionPriorAgent
except ImportError:
    pass

try:
    from 基于td误差方差异方差感知的自适应熵调节 import TDVarianceAgent
    _proposal_agents["td_variance"] = TDVarianceAgent
except ImportError:
    pass

try:
    from 基于值函数不确定性量化的自适应熵调节ac算法 import ValueUncertaintyAgent
    _proposal_agents["value_uncertainty"] = ValueUncertaintyAgent
except ImportError:
    pass

try:
    from w3_方案方向 import DPDepthAgent
    _proposal_agents["dp_depth"] = DPDepthAgent
except ImportError:
    pass

try:
    from 基于taylor展开的局部熵曲率自适应ac算法 import TaylorCurvatureAgent
    _proposal_agents["taylor_curvature"] = TaylorCurvatureAgent
except ImportError:
    pass

try:
    from 跨步态相位时序差分噪声驱动的动态熵调节ac算法 import GaitPhaseAgent
    _proposal_agents["gait_phase"] = GaitPhaseAgent
except ImportError:
    pass

try:
    from iqn_quantile_agent import IQNQuantileAgent
    _proposal_agents["iqn_quantile"] = IQNQuantileAgent
except ImportError:
    pass

try:
    from iqn_quantile_simple_agent import IQNQuantileSimpleAgent
    _proposal_agents["iqn_quantile_simple"] = IQNQuantileSimpleAgent
except ImportError:
    pass

try:
    from dual_critic_attention_agent import DualCriticAttentionAgent
    _proposal_agents["dual_critic_attention"] = DualCriticAttentionAgent
except ImportError:
    pass

ALL_ALGOS = ["td3", "sac", "ddpg"] + _proposal_names


def build_agent(algo, config, obs_dim, action_dim, max_action, device):
    if algo == "td3":
        c = config.td3
        return TD3Agent(obs_dim, action_dim, max_action,
                        actor_hidden=config.network.actor_hidden,
                        critic_hidden=config.network.critic_hidden,
                        gamma=c.gamma, tau=c.tau, policy_noise=c.policy_noise,
                        noise_clip=c.noise_clip, policy_delay=c.policy_delay,
                        actor_lr=c.actor_lr, critic_lr=c.critic_lr,
                        exploration_noise=c.exploration_noise, noise_type=c.noise_type,
                        device=device)
    elif algo == "sac":
        c = config.sac
        return SACAgent(obs_dim, action_dim, max_action,
                        actor_hidden=config.network.actor_hidden,
                        critic_hidden=config.network.critic_hidden,
                        gamma=c.gamma, tau=c.tau, actor_lr=c.actor_lr,
                        critic_lr=c.critic_lr, alpha_lr=c.alpha_lr,
                        alpha_init=c.alpha_init, alpha_auto_tune=c.alpha_auto_tune,
                        target_entropy=c.target_entropy, device=device)
    elif algo == "ddpg":
        c = config.ddpg
        return DDPGAgent(obs_dim, action_dim, max_action,
                         actor_hidden=config.network.actor_hidden,
                         critic_hidden=config.network.critic_hidden,
                         gamma=c.gamma, tau=c.tau, actor_lr=c.actor_lr,
                         critic_lr=c.critic_lr, exploration_noise=c.exploration_noise,
                         noise_type=c.noise_type, device=device)
    elif algo in _proposal_agents:
        AgentClass = _proposal_agents[algo]
        return AgentClass(obs_dim, action_dim, max_action, device=device)
    else:
        raise ValueError(f"Unknown algorithm: {algo}")


def main():
    parser = argparse.ArgumentParser(description="Train all algorithms on Hopper-v4")
    parser.add_argument("--algo", nargs="+", default=ALL_ALGOS,
                        choices=ALL_ALGOS, help="Algorithms to train")
    parser.add_argument("--quick", action="store_true",
                        help="Quick mode: 5k steps, 1 seed")
    parser.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2],
                        help="Random seeds")
    parser.add_argument("--steps", type=int, default=1_000_000,
                        help="Total environment steps")
    parser.add_argument("--device", type=str, default="cuda",
                        help="Device (cuda/cpu)")
    parser.add_argument("--output-dir", type=str,
                        default="./hopper_experiments",
                        help="Output directory")
    parser.add_argument("--eval-freq", type=int, default=10_000,
                        help="Evaluation frequency")
    args = parser.parse_args()

    if args.quick:
        args.steps = 5_000
        args.seeds = [0]
        args.eval_freq = 1_000

    device = args.device
    if device == "cuda" and not torch.cuda.is_available():
        print("CUDA not available, falling back to CPU")
        device = "cpu"

    print(f"Device: {device}")
    print(f"Algorithms: {args.algo}")
    print(f"Seeds: {args.seeds}")
    print(f"Steps: {args.steps}")

    # Filter out proposals that haven't been implemented yet
    available = [a for a in args.algo if a in ALL_ALGOS]
    missing = [a for a in args.algo if a not in ALL_ALGOS]
    if missing:
        print(f"WARNING: skipping unimplemented algorithms: {missing}")
    args.algo = available

    if not args.algo:
        print("ERROR: No algorithms available to run.")
        sys.exit(1)

    config = ExperimentConfig()

    import gymnasium as gym
    test_env = gym.make(config.env.env_name)
    obs_dim = test_env.observation_space.shape[0]
    action_dim = test_env.action_space.shape[0]
    max_action = float(test_env.action_space.high[0])
    test_env.close()

    print(f"Env: {config.env.env_name} (obs={obs_dim}, act={action_dim})")

    os.makedirs(args.output_dir, exist_ok=True)

    all_results = []
    total_start = time.time()

    for algo in args.algo:
        print(f"\n{'=' * 60}")
        print(f"Training {algo.upper()}")
        print(f"{'=' * 60}")

        algo_dir = os.path.join(args.output_dir, algo)
        os.makedirs(algo_dir, exist_ok=True)

        algo_results = []
        for seed in args.seeds:
            print(f"\n--- {algo} | Seed {seed} ---")
            agent = build_agent(algo, config, obs_dim, action_dim, max_action, device)

            trainer = Trainer(
                agent=agent, env_name=config.env.env_name,
                total_steps=args.steps, eval_freq=args.eval_freq,
                eval_episodes=config.training.eval_episodes,
                save_freq=config.training.save_freq,
                log_freq=config.training.log_freq,
                warmup_steps=config.td3.warmup_steps,
                seed=seed, output_dir=algo_dir, algorithm=algo, device=device,
            )

            result = trainer.train()
            algo_results.append(result)
            all_results.append(result)

            print(f"  Final return: {result['final_return_mean']:.1f} "
                  f"+/- {result['final_return_std']:.0f}")

        returns = [r["final_return_mean"] for r in algo_results]
        print(f"\n{algo} Summary: {np.mean(returns):.1f} +/- {np.std(returns):.1f}")

    total_time = time.time() - total_start
    results_path = os.path.join(args.output_dir, "all_results.json")
    with open(results_path, 'w') as f:
        json.dump(all_results, f, indent=2)

    print(f"\n{'=' * 60}")
    print(f"DONE in {total_time:.0f}s. Results saved to {results_path}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
