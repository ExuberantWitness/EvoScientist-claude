"""
Replay buffer implementations for off-policy RL.

Supports:
  - Uniform replay buffer (standard)
  - Prioritized replay buffer (PER)
  - Trajectory buffer (for TCD — stores complete episodes)
"""

import numpy as np
import torch
from typing import Tuple, Optional, List, Dict


class ReplayBuffer:
    """Standard uniform replay buffer."""

    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        capacity: int = 1_000_000,
        device: str = "cuda",
    ):
        self.capacity = capacity
        self.device = device
        self.ptr = 0
        self.size = 0

        # Preallocate storage
        self.obs = np.zeros((capacity, obs_dim), dtype=np.float32)
        self.next_obs = np.zeros((capacity, obs_dim), dtype=np.float32)
        self.actions = np.zeros((capacity, action_dim), dtype=np.float32)
        self.rewards = np.zeros((capacity, 1), dtype=np.float32)
        self.dones = np.zeros((capacity, 1), dtype=np.float32)

    def add(
        self,
        obs: np.ndarray,
        action: np.ndarray,
        reward: float,
        next_obs: np.ndarray,
        done: bool,
    ):
        """Store a single transition."""
        idx = self.ptr
        self.obs[idx] = obs
        self.actions[idx] = action
        self.rewards[idx] = reward
        self.next_obs[idx] = next_obs
        self.dones[idx] = float(done)

        self.ptr = (self.ptr + 1) % self.capacity
        self.size = min(self.size + 1, self.capacity)

    def sample(self, batch_size: int) -> Tuple[torch.Tensor, ...]:
        """Sample a random batch of transitions."""
        idxs = np.random.randint(0, self.size, size=batch_size)

        return (
            torch.from_numpy(self.obs[idxs]).to(self.device),
            torch.from_numpy(self.actions[idxs]).to(self.device),
            torch.from_numpy(self.rewards[idxs]).to(self.device),
            torch.from_numpy(self.next_obs[idxs]).to(self.device),
            torch.from_numpy(self.dones[idxs]).to(self.device),
        )

    def __len__(self) -> int:
        return self.size


class PrioritizedReplayBuffer(ReplayBuffer):
    """Prioritized Experience Replay (Schaul et al., 2016)."""

    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        capacity: int = 1_000_000,
        alpha: float = 0.6,
        beta: float = 0.4,
        beta_increment: float = 1e-5,
        epsilon: float = 1e-6,
        device: str = "cuda",
    ):
        super().__init__(obs_dim, action_dim, capacity, device)
        self.alpha = alpha
        self.beta = beta
        self.beta_increment = beta_increment
        self.epsilon = epsilon

        # Sum-tree for efficient sampling
        tree_capacity = 1
        while tree_capacity < capacity:
            tree_capacity *= 2
        self.tree_capacity = tree_capacity
        self.tree = np.zeros(2 * tree_capacity, dtype=np.float64)
        self.max_priority = 1.0

    def add(self, obs, action, reward, next_obs, done):
        idx = self.ptr
        super().add(obs, action, reward, next_obs, done)
        # Set max priority for new experience
        self._set_priority(idx, self.max_priority)

    def _set_priority(self, idx: int, priority: float):
        tree_idx = idx + self.tree_capacity
        self.tree[tree_idx] = priority ** self.alpha
        # Update ancestors
        tree_idx //= 2
        while tree_idx > 0:
            self.tree[tree_idx] = self.tree[2 * tree_idx] + self.tree[2 * tree_idx + 1]
            tree_idx //= 2
        if priority > self.max_priority:
            self.max_priority = priority

    def _sample_from_tree(self, value: float) -> int:
        """Sample index proportional to priority."""
        idx = 1
        while idx < self.tree_capacity:
            left = 2 * idx
            if value <= self.tree[left]:
                idx = left
            else:
                value -= self.tree[left]
                idx = left + 1
        return idx - self.tree_capacity

    def sample(self, batch_size: int) -> Tuple:
        """Sample with importance weights."""
        batch_idxs = []
        segment = self.tree[1] / batch_size  # Total priority / batch

        for i in range(batch_size):
            a = segment * i
            b = segment * (i + 1)
            value = np.random.uniform(a, b)
            batch_idxs.append(self._sample_from_tree(value))

        # Importance sampling weights
        total = max(self.tree[1], 1e-10)
        probs = np.array([self.tree[idx + self.tree_capacity] / total
                          for idx in batch_idxs])
        weights = ((1.0 / (self.size * probs + 1e-10)) ** self.beta)
        weights /= weights.max()

        self.beta = min(1.0, self.beta + self.beta_increment)

        batch = (
            torch.from_numpy(self.obs[batch_idxs]).to(self.device),
            torch.from_numpy(self.actions[batch_idxs]).to(self.device),
            torch.from_numpy(self.rewards[batch_idxs]).to(self.device),
            torch.from_numpy(self.next_obs[batch_idxs]).to(self.device),
            torch.from_numpy(self.dones[batch_idxs]).to(self.device),
            torch.from_numpy(weights).to(self.device),
            batch_idxs,
        )
        return batch

    def update_priorities(self, idxs: List[int], priorities: np.ndarray):
        for idx, priority in zip(idxs, priorities):
            self._set_priority(idx, priority)


class PPOBuffer:
    """On-policy rollout buffer for PPO."""

    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        capacity: int = 2048,
        gamma: float = 0.99,
        gae_lambda: float = 0.95,
        device: str = "cuda",
    ):
        self.capacity = capacity
        self.gamma = gamma
        self.gae_lambda = gae_lambda
        self.device = device
        self.ptr = 0

        self.obs = np.zeros((capacity, obs_dim), dtype=np.float32)
        self.actions = np.zeros((capacity, action_dim), dtype=np.float32)
        self.rewards = np.zeros(capacity, dtype=np.float32)
        self.dones = np.zeros(capacity, dtype=np.float32)
        self.log_probs = np.zeros(capacity, dtype=np.float32)
        self.values = np.zeros(capacity, dtype=np.float32)

    def add(self, obs, action, reward, done, log_prob, value):
        if self.ptr >= self.capacity:
            return  # Buffer full, wait for train() to clear it
        self.obs[self.ptr] = obs
        self.actions[self.ptr] = action
        self.rewards[self.ptr] = reward
        self.dones[self.ptr] = float(done)
        self.log_probs[self.ptr] = log_prob
        self.values[self.ptr] = value
        self.ptr += 1

    def compute_gae(self, last_value: float) -> np.ndarray:
        advantages = np.zeros(self.ptr, dtype=np.float32)
        gae = 0.0
        for t in reversed(range(self.ptr)):
            next_value = 0.0 if self.dones[t] else (self.values[t + 1] if t + 1 < self.ptr else last_value)
            delta = self.rewards[t] + self.gamma * next_value - self.values[t]
            gae = delta + self.gamma * self.gae_lambda * (1 - self.dones[t]) * gae
            advantages[t] = gae
        return advantages

    def get(self):
        obs = torch.from_numpy(self.obs[:self.ptr]).to(self.device)
        actions = torch.from_numpy(self.actions[:self.ptr]).to(self.device)
        log_probs = torch.from_numpy(self.log_probs[:self.ptr]).to(self.device)
        advantages = torch.from_numpy(self.compute_gae(0.0)).to(self.device)
        returns = advantages + torch.from_numpy(self.values[:self.ptr]).to(self.device)
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
        return obs, actions, log_probs, returns, advantages

    def clear(self):
        self.ptr = 0

    @property
    def full(self):
        return self.ptr >= self.capacity

    def __len__(self):
        return self.ptr


class TrajectoryBuffer:
    """
    Buffer that stores complete trajectories for TCD.
    Used to train the temporal credit discriminator.
    """

    def __init__(
        self,
        max_trajectories: int = 1000,
        min_trajectory_len: int = 16,
    ):
        self.max_trajectories = max_trajectories
        self.min_trajectory_len = min_trajectory_len
        self.trajectories: List[Dict] = []
        self.current_trajectory: Dict = {
            "obs": [],
            "actions": [],
            "rewards": [],
            "next_obs": [],
            "dones": [],
        }
        self.current_return = 0.0

    def add_step(
        self,
        obs: np.ndarray,
        action: np.ndarray,
        reward: float,
        next_obs: np.ndarray,
        done: bool,
    ):
        self.current_trajectory["obs"].append(obs)
        self.current_trajectory["actions"].append(action)
        self.current_trajectory["rewards"].append(reward)
        self.current_trajectory["next_obs"].append(next_obs)
        self.current_trajectory["dones"].append(done)
        self.current_return += reward

        if done:
            if len(self.current_trajectory["obs"]) >= self.min_trajectory_len:
                self.current_trajectory["total_return"] = self.current_return
                self.current_trajectory["length"] = len(self.current_trajectory["obs"])
                self.trajectories.append(self.current_trajectory)
                if len(self.trajectories) > self.max_trajectories:
                    self.trajectories.pop(0)

            self.current_trajectory = {
                "obs": [],
                "actions": [],
                "rewards": [],
                "next_obs": [],
                "dones": [],
            }
            self.current_return = 0.0

    def sample_pairs(
        self, batch_size: int, chunk_len: int
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Sample paired high-return and low-return trajectory chunks for contrastive learning.

        Args:
            batch_size: number of pairs
            chunk_len: K, chunk length

        Returns:
            high_chunks: (batch, chunk_len, obs_dim+action_dim)
            low_chunks: (batch, chunk_len, obs_dim+action_dim)
        """
        if len(self.trajectories) < 2:
            return None, None

        # Sort trajectories by return and split into high/low
        returns = [t["total_return"] for t in self.trajectories]
        median = np.median(returns)

        high_trajs = [t for t in self.trajectories
                      if t["total_return"] >= median]
        low_trajs = [t for t in self.trajectories
                     if t["total_return"] < median]

        high_chunks_list = []
        low_chunks_list = []

        for _ in range(batch_size):
            # Sample a high-return trajectory and extract a chunk
            high_traj = high_trajs[np.random.randint(len(high_trajs))]
            start = np.random.randint(0, max(1, len(high_traj["obs"]) - chunk_len))
            chunk_h = []
            for i in range(start, min(start + chunk_len, len(high_traj["obs"]))):
                chunk_h.append(np.concatenate([
                    high_traj["obs"][i], high_traj["actions"][i]
                ]))
            # Pad if needed
            while len(chunk_h) < chunk_len:
                chunk_h.append(np.zeros_like(chunk_h[0]))
            high_chunks_list.append(chunk_h)

            # Sample a low-return trajectory and extract a chunk
            low_traj = low_trajs[np.random.randint(len(low_trajs))]
            start = np.random.randint(0, max(1, len(low_traj["obs"]) - chunk_len))
            chunk_l = []
            for i in range(start, min(start + chunk_len, len(low_traj["obs"]))):
                chunk_l.append(np.concatenate([
                    low_traj["obs"][i], low_traj["actions"][i]
                ]))
            while len(chunk_l) < chunk_len:
                chunk_l.append(np.zeros_like(chunk_l[0]))
            low_chunks_list.append(chunk_l)

        high_chunks = torch.from_numpy(np.array(high_chunks_list)).float()
        low_chunks = torch.from_numpy(np.array(low_chunks_list)).float()

        return high_chunks, low_chunks
