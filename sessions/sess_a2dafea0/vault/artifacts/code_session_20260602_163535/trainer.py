"""
Training and evaluation infrastructure for Hopper-v4 experiments.

Provides:
  - Environment wrapper with normalization and diagnostics
  - Training loop with logging
  - Evaluation loop
  - Results collection
"""

import os
import sys
import json
import csv
import time
import numpy as np
import torch
from typing import Dict, Any, Optional, List, Tuple

import gymnasium as gym


# ---------------------------------------------------------------------------
# Environment wrapper with observation normalization
# ---------------------------------------------------------------------------

class NormalizedEnv:
    """Running normalization wrapper for observations."""

    def __init__(self, env: gym.Env, clip: float = 10.0):
        self.env = env
        self.clip = clip
        self.mean = np.zeros(env.observation_space.shape[0])
        self.var = np.ones(env.observation_space.shape[0])
        self.count = 0

    def normalize(self, obs: np.ndarray) -> np.ndarray:
        return np.clip((obs - self.mean) / (np.sqrt(self.var) + 1e-8),
                       -self.clip, self.clip)

    def update_stats(self, obs: np.ndarray):
        self.count += 1
        delta = obs - self.mean
        self.mean += delta / self.count
        delta2 = obs - self.mean
        self.var = (self.var * (self.count - 1) + delta * delta2) / self.count

    def reset(self, **kwargs):
        obs, info = self.env.reset(**kwargs)
        self.update_stats(obs)
        return self.normalize(obs), info

    def step(self, action):
        obs, reward, terminated, truncated, info = self.env.step(action)
        self.update_stats(obs)
        return self.normalize(obs), reward, terminated, truncated, info

    def __getattr__(self, name):
        return getattr(self.env, name)

    @property
    def unwrapped(self):
        return self.env.unwrapped


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------

class Trainer:
    """Handles training, evaluation, and logging for a single run."""

    def __init__(
        self,
        agent,
        env_name: str = "Hopper-v4",
        total_steps: int = 1_000_000,
        eval_freq: int = 10_000,
        eval_episodes: int = 10,
        save_freq: int = 100_000,
        log_freq: int = 1_000,
        warmup_steps: int = 25_000,
        seed: int = 0,
        output_dir: str = "./results",
        algorithm: str = "td3",
        use_normalization: bool = True,
        device: str = "cuda",
    ):
        self.agent = agent
        self.env_name = env_name
        self.total_steps = total_steps
        self.eval_freq = eval_freq
        self.eval_episodes = eval_episodes
        self.save_freq = save_freq
        self.log_freq = log_freq
        self.warmup_steps = warmup_steps
        self.seed = seed
        self.output_dir = output_dir
        self.algorithm = algorithm
        self.use_normalization = use_normalization
        self.device = device

        # Set random seeds
        np.random.seed(seed)
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)

        # Create environment
        self._make_env()

        # Metrics storage
        self.logs = {
            "step": [],
            "eval_return_mean": [],
            "eval_return_std": [],
            "eval_return_min": [],
            "eval_return_max": [],
            "eval_length_mean": [],
            "critic_loss": [],
            "actor_loss": [],
            "q_mean": [],
        }

    def _make_env(self, render_mode: Optional[str] = None):
        """Create training or evaluation environment."""
        if render_mode:
            env = gym.make(self.env_name, render_mode=render_mode)
        else:
            env = gym.make(self.env_name)

        if self.use_normalization:
            self.env = NormalizedEnv(env)
        else:
            self.env = env

    def _select_action(self, obs: np.ndarray, deterministic: bool = False) -> np.ndarray:
        """Select action with unified interface for all agent types."""
        import inspect

        if not hasattr(self.agent, 'select_action'):
            return self.agent.select_action(obs)

        sig = inspect.signature(self.agent.select_action)
        params = sig.parameters

        kwargs = {}
        if 'deterministic' in params:
            kwargs['deterministic'] = deterministic
        elif 'add_noise' in params:
            kwargs['add_noise'] = not deterministic
        elif 'add_noise' not in params and 'explore' in params:
            kwargs['explore'] = not deterministic

        return self.agent.select_action(obs, **kwargs)

    def evaluate(self, deterministic: bool = True) -> Dict[str, float]:
        """Run evaluation episodes."""
        eval_env = gym.make(self.env_name)
        returns = []
        lengths = []

        for ep in range(self.eval_episodes):
            obs, _ = eval_env.reset()
            if self.use_normalization:
                obs = np.clip(
                    (obs - self.env.mean) / (np.sqrt(self.env.var) + 1e-8),
                    -10.0, 10.0
                )

            ep_return = 0.0
            ep_length = 0

            while True:
                action = self._select_action(obs, deterministic=deterministic)

                obs, reward, terminated, truncated, _ = eval_env.step(action)
                if self.use_normalization:
                    obs = np.clip(
                        (obs - self.env.mean) / (np.sqrt(self.env.var) + 1e-8),
                        -10.0, 10.0
                    )

                ep_return += reward
                ep_length += 1

                if terminated or truncated:
                    break

            returns.append(ep_return)
            lengths.append(ep_length)

        eval_env.close()

        return {
            "return_mean": float(np.mean(returns)),
            "return_std": float(np.std(returns)),
            "return_min": float(np.min(returns)),
            "return_max": float(np.max(returns)),
            "length_mean": float(np.mean(lengths)),
        }

    def train(self) -> Dict:
        """Run the full training loop."""
        from buffer import ReplayBuffer, TrajectoryBuffer

        obs_dim = self.env.observation_space.shape[0]
        action_dim = self.env.action_space.shape[0]

        replay_buffer = ReplayBuffer(
            obs_dim, action_dim, capacity=1_000_000, device=self.device
        )

        # Create trajectory buffer for TCD (if needed)
        use_trajectory_buffer = hasattr(self.agent, 'trajectory_len')
        if use_trajectory_buffer:
            trajectory_buffer = TrajectoryBuffer(
                max_trajectories=200, min_trajectory_len=8
            )
        else:
            trajectory_buffer = None

        obs, _ = self.env.reset()
        episode_reward = 0.0
        episode_steps = 0

        print(f"[Alg={self.algorithm} Seed={self.seed}] Starting training, "
              f"total_steps={self.total_steps}, eval_freq={self.eval_freq}")

        start_time = time.time()

        for step in range(1, self.total_steps + 1):
            # Select action (with exploration noise during training)
            if step < self.warmup_steps:
                action = self.env.action_space.sample()
            else:
                action = self._select_action(obs, deterministic=False)

            # Environment step
            next_obs, reward, terminated, truncated, _ = self.env.step(action)
            done = terminated or truncated
            episode_reward += reward
            episode_steps += 1

            # Store transition
            replay_buffer.add(obs, action, reward, next_obs, float(done))

            # On-policy agent hook (PPO)
            if hasattr(self.agent, 'add_transition'):
                self.agent.add_transition(obs, action, reward, next_obs, float(done))

            # Store in trajectory buffer (for TCD)
            if trajectory_buffer is not None:
                trajectory_buffer.add_step(obs, action, reward, next_obs, done)

            obs = next_obs

            # Episode reset
            if done:
                if hasattr(self.agent, 'reset_phase'):
                    self.agent.reset_phase()
                obs, _ = self.env.reset()
                episode_reward = 0.0
                episode_steps = 0

            # Training
            if step >= self.warmup_steps:
                if trajectory_buffer is not None:
                    metrics = self.agent.train(replay_buffer, trajectory_buffer)
                else:
                    metrics = self.agent.train(replay_buffer)

            # Evaluation
            if step % self.eval_freq == 0:
                eval_results = self.evaluate()
                elapsed = time.time() - start_time
                print(f"[Step {step:7d}] Return: {eval_results['return_mean']:.1f} "
                      f"± {eval_results['return_std']:.0f} "
                      f"(min={eval_results['return_min']:.0f}, "
                      f"max={eval_results['return_max']:.0f}) "
                      f"[{elapsed:.0f}s]")

                self.logs["step"].append(step)
                self.logs["eval_return_mean"].append(eval_results["return_mean"])
                self.logs["eval_return_std"].append(eval_results["return_std"])
                self.logs["eval_return_min"].append(eval_results["return_min"])
                self.logs["eval_return_max"].append(eval_results["return_max"])
                self.logs["eval_length_mean"].append(eval_results["length_mean"])

                # Log training metrics
                if hasattr(self.agent, 'metrics'):
                    for k, v in self.agent.metrics.items():
                        if k not in self.logs:
                            self.logs[k] = []
                        self.logs[k].append(v)

            # Save checkpoint
            if step % self.save_freq == 0:
                save_path = os.path.join(
                    self.output_dir,
                    f"{self.algorithm}_seed{self.seed}_step{step}.pt"
                )
                if hasattr(self.agent, 'save'):
                    self.agent.save(save_path)

        # Final evaluation
        final_results = self.evaluate()
        total_time = time.time() - start_time

        # Save final agent
        save_path = os.path.join(
            self.output_dir,
            f"{self.algorithm}_seed{self.seed}_final.pt"
        )
        if hasattr(self.agent, 'save'):
            self.agent.save(save_path)

        # Save logs
        logs_path = os.path.join(
            self.output_dir,
            f"{self.algorithm}_seed{self.seed}_logs.csv"
        )
        self._save_logs(logs_path)

        return {
            "algorithm": self.algorithm,
            "seed": self.seed,
            "final_return_mean": final_results["return_mean"],
            "final_return_std": final_results["return_std"],
            "total_time": total_time,
            "total_steps": step,
        }

    def _save_logs(self, path: str):
        """Save training logs as CSV."""
        # Truncate all columns to same length
        min_len = min(len(v) for v in self.logs.values())
        rows = []
        for i in range(min_len):
            row = {}
            for k, v in self.logs.items():
                if i < len(v):
                    row[k] = v[i]
            rows.append(row)

        if rows:
            with open(path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)

        # Also save as JSON for programmatic access
        json_path = path.replace('.csv', '.json')
        with open(json_path, 'w') as f:
            json.dump({k: v for k, v in self.logs.items() if v}, f, indent=2)
