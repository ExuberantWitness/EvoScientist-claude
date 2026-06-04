#!/usr/bin/env python3
"""
Hyperparameter sweep at 50k steps per trial.
Finds the best hyperparameters for each algorithm before full comparison.

Usage:
    python hparam_sweep.py --algo sac --trials 16
    python hparam_sweep.py --algo all --trials 12
"""

import os, sys, json, argparse, time, itertools
import numpy as np
import torch
import gymnasium as gym

from config import ExperimentConfig
from trainer import Trainer

SEARCH_SPACE = {
    "sac": {
        "alpha_init": [0.05, 0.1, 0.2, 0.5, 1.0],
        "actor_lr": [1e-4, 3e-4, 1e-3],
        "critic_lr": [1e-4, 3e-4, 1e-3],
        "alpha_lr": [1e-4, 3e-4, 1e-3],
    },
    "td3": {
        "policy_noise": [0.1, 0.2, 0.3, 0.5],
        "noise_clip": [0.2, 0.5, 0.7],
        "policy_delay": [1, 2, 3],
        "exploration_noise": [0.05, 0.1, 0.2, 0.3],
        "actor_lr": [1e-4, 3e-4, 1e-3],
        "critic_lr": [1e-4, 3e-4, 1e-3],
    },
    "sme": {
        "n_critics": [3, 5, 7, 10],
        "mutation_rate": [0.001, 0.005, 0.01, 0.05],
        "mutation_freq": [50, 100, 200, 400],
        "elite_fraction": [0.2, 0.3, 0.4, 0.5, 0.6],
        "alpha_init": [0.05, 0.1, 0.2, 0.5],
        "actor_lr": [1e-4, 3e-4],
        "critic_lr": [1e-4, 3e-4],
    },
    "map": {
        "alpha_init": [0.05, 0.1, 0.2, 0.5],
        "adaptive_lr": [1e-4, 3e-4, 1e-3],
        "adaptive_hidden": [32, 64, 128, 256],
        "policy_noise": [0.1, 0.2, 0.3],
        "noise_clip": [0.2, 0.5, 0.7],
        "actor_lr": [1e-4, 3e-4, 1e-3],
        "critic_lr": [1e-4, 3e-4, 1e-3],
        "exploration_noise": [0.05, 0.1, 0.2],
    },
}


def sample_configs(search_space, n_trials):
    """Randomly sample n_trials configs from search space."""
    keys = list(search_space.keys())
    samples = []
    seen = set()
    # Also include the "default" config as first trial
    defaults = {
        "sac": {"alpha_init": 0.2, "actor_lr": 3e-4, "critic_lr": 3e-4,
                "alpha_lr": 3e-4},
        "td3": {"policy_noise": 0.2, "noise_clip": 0.5, "policy_delay": 2,
                "exploration_noise": 0.1, "actor_lr": 3e-4, "critic_lr": 3e-4},
        "sme": {"n_critics": 5, "mutation_rate": 0.01, "mutation_freq": 100,
                "elite_fraction": 0.4, "alpha_init": 0.2, "actor_lr": 3e-4,
                "critic_lr": 3e-4},
        "map": {"alpha_init": 0.2, "adaptive_lr": 3e-4, "adaptive_hidden": 64,
                "policy_noise": 0.2, "noise_clip": 0.5, "actor_lr": 3e-4,
                "critic_lr": 3e-4, "exploration_noise": 0.1},
    }
    default = defaults.get("", {})
    while len(samples) < n_trials:
        if len(samples) == 0 and default:
            cfg = default.copy()
        else:
            cfg = {}
            for k in keys:
                options = search_space[k]
                # Handle list-type values (multi-dim)
                if isinstance(options[0], list):
                    cfg[k] = options[np.random.randint(len(options))]
                else:
                    cfg[k] = options[np.random.randint(len(options))]
        key = str(sorted(cfg.items()))
        if key in seen:
            continue
        seen.add(key)
        samples.append(cfg)
    return samples


def build_sac_agent(config, obs_dim, action_dim, max_action, device, trial_cfg):
    from sac import SACAgent
    return SACAgent(
        obs_dim, action_dim, max_action,
        actor_hidden=[256, 256], critic_hidden=[256, 256],
        gamma=config.sac.gamma, tau=config.sac.tau,
        actor_lr=trial_cfg["actor_lr"], critic_lr=trial_cfg["critic_lr"],
        alpha_lr=trial_cfg["alpha_lr"], alpha_init=trial_cfg["alpha_init"],
        alpha_auto_tune=True, target_entropy=None, device=device,
    )


def build_td3_agent(config, obs_dim, action_dim, max_action, device, trial_cfg):
    from td3 import TD3Agent
    return TD3Agent(
        obs_dim, action_dim, max_action,
        actor_hidden=[256, 256], critic_hidden=[256, 256],
        gamma=config.td3.gamma, tau=config.td3.tau,
        policy_noise=trial_cfg["policy_noise"], noise_clip=trial_cfg["noise_clip"],
        policy_delay=trial_cfg["policy_delay"],
        actor_lr=trial_cfg["actor_lr"], critic_lr=trial_cfg["critic_lr"],
        exploration_noise=trial_cfg["exploration_noise"], device=device,
    )


def build_sme_agent(config, obs_dim, action_dim, max_action, device, trial_cfg):
    from sme import SMEAgent
    return SMEAgent(
        obs_dim, action_dim, max_action,
        actor_hidden=[256, 256], critic_hidden=[256, 256],
        gamma=config.sme.gamma, tau=config.sme.tau,
        actor_lr=trial_cfg["actor_lr"], critic_lr=trial_cfg["critic_lr"],
        alpha_lr=3e-4, alpha_init=trial_cfg["alpha_init"],
        alpha_auto_tune=True, target_entropy=None,
        n_critics=trial_cfg["n_critics"], mutation_rate=trial_cfg["mutation_rate"],
        mutation_freq=trial_cfg["mutation_freq"],
        elite_fraction=trial_cfg["elite_fraction"], device=device,
    )


def build_map_agent(config, obs_dim, action_dim, max_action, device, trial_cfg):
    from map import MAPAgent
    return MAPAgent(
        obs_dim, action_dim, max_action,
        actor_hidden=[256, 256], critic_hidden=[256, 256],
        gamma=config.map.gamma, tau=config.map.tau,
        policy_noise=trial_cfg["policy_noise"], noise_clip=trial_cfg["noise_clip"],
        policy_delay=2,
        actor_lr=trial_cfg["actor_lr"], critic_lr=trial_cfg["critic_lr"],
        alpha_lr=3e-4, adaptive_lr=trial_cfg["adaptive_lr"],
        alpha_init=trial_cfg["alpha_init"], alpha_auto_tune=True,
        target_entropy=None, adaptive_hidden=trial_cfg["adaptive_hidden"],
        exploration_noise=trial_cfg["exploration_noise"], device=device,
    )


BUILD_FN = {"sac": build_sac_agent, "td3": build_td3_agent,
            "sme": build_sme_agent, "map": build_map_agent}


def score_result(result):
    """Score based on final return and total training stability."""
    return result.get("final_return_mean", 0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--algo", nargs="+", default=["sac"],
                        choices=["sac", "td3", "sme", "map", "all"])
    parser.add_argument("--trials", type=int, default=12,
                        help="Number of random hyperparameter trials per algorithm")
    parser.add_argument("--steps", type=int, default=50000)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--output-dir", default="./hparam_sweep_results")
    args = parser.parse_args()

    if "all" in args.algo:
        args.algo = ["sac", "td3", "sme", "map"]

    device = args.device
    if device == "cuda" and not torch.cuda.is_available():
        device = "cpu"

    config = ExperimentConfig()

    # Get env info
    test_env = gym.make("Hopper-v4")
    obs_dim = test_env.observation_space.shape[0]
    action_dim = test_env.action_space.shape[0]
    max_action = float(test_env.action_space.high[0])
    test_env.close()

    os.makedirs(args.output_dir, exist_ok=True)
    all_best = {}

    for algo in args.algo:
        print(f"\n{'=' * 60}")
        print(f"HYPERPARAMETER SWEEP: {algo.upper()}")
        print(f"{'=' * 60}")

        space = SEARCH_SPACE[algo]
        n_possible = 1
        for v in space.values():
            n_possible *= len(v)
        n_trials = min(args.trials, n_possible)

        print(f"Search space: {len(space)} params, {n_possible} combos")
        print(f"Sampling {n_trials} configs...")

        trials = sample_configs(space, n_trials)
        results = []

        algo_dir = os.path.join(args.output_dir, algo)
        os.makedirs(algo_dir, exist_ok=True)

        for i, trial in enumerate(trials):
            t0 = time.time()
            print(f"\n[{i+1}/{n_trials}] ", end="")
            for k, v in trial.items():
                if isinstance(v, float):
                    print(f"{k}={v:.0e} ", end="")
                elif isinstance(v, list):
                    print(f"{k}={v} ", end="")
                else:
                    print(f"{k}={v} ", end="")
            print()

            agent = BUILD_FN[algo](config, obs_dim, action_dim, max_action, device, trial)

            trainer = Trainer(
                agent=agent, env_name="Hopper-v4",
                total_steps=args.steps, eval_freq=5000,
                eval_episodes=5, save_freq=1000000, log_freq=10000,
                warmup_steps=10000, seed=42,
                output_dir=algo_dir, algorithm=algo, device=device,
            )
            result = trainer.train()
            score = score_result(result)
            elapsed = time.time() - t0

            trial_result = {
                "trial": i, "config": {k: (v if not isinstance(v, list) else str(v))
                                       for k, v in trial.items()},
                "score": score, "final_return": result.get("final_return_mean", 0),
                "elapsed_s": elapsed,
            }
            results.append(trial_result)
            print(f"  Score={score:.0f} [{elapsed:.0f}s]")

            # Save intermediate results
            with open(os.path.join(algo_dir, "sweep_results.json"), "w") as f:
                json.dump(results, f, indent=2)

        # Rank and report
        results.sort(key=lambda r: r["score"], reverse=True)
        print(f"\n--- {algo.upper()} TOP 5 ---")
        for i, r in enumerate(results[:5]):
            cfg_str = "  ".join(f"{k}={v}" for k, v in r["config"].items())
            print(f"  #{i+1} score={r['score']:.0f} final={r['final_return']:.0f} | {cfg_str}")

        best = results[0]
        all_best[algo] = best
        print(f"\nBEST {algo}: score={best['score']:.0f}")
        for k, v in best["config"].items():
            print(f"  {k}: {v}")

    # Final summary
    print(f"\n{'=' * 60}")
    print("FINAL BEST CONFIGS")
    print(f"{'=' * 60}")
    for algo, best in all_best.items():
        cfg_str = " ".join(f"{k}={v}" for k, v in best["config"].items())
        print(f"{algo:6s}: score={best['score']:7.0f} | {cfg_str}")

    # Save final summary
    with open(os.path.join(args.output_dir, "best_configs.json"), "w") as f:
        json.dump(all_best, f, indent=2, default=str)
    print(f"\nSaved to {args.output_dir}/best_configs.json")


if __name__ == "__main__":
    main()
