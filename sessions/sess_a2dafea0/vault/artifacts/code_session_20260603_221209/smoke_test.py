#!/usr/bin/env python3
"""
Quick smoke test: verify that all algorithms can be instantiated and run training steps.

Usage:
    python smoke_test.py
    python smoke_test.py --device cpu
    python smoke_test.py --algo sac td3 ddpg
"""

import os
import sys
import argparse
import numpy as np
import torch

sys.path.insert(0, os.path.dirname(__file__))


def test_environment():
    print("[ENV] Testing Hopper-v4...")
    import gymnasium as gym
    env = gym.make("Hopper-v4")
    obs, _ = env.reset()
    print(f"  obs shape: {obs.shape}, action space: {env.action_space}")
    action = env.action_space.sample()
    obs, reward, terminated, truncated, _ = env.step(action)
    print(f"  reward: {reward:.3f}")
    env.close()
    print("  OK")
    return obs.shape[0], env.action_space.shape[0], float(env.action_space.high[0])


def fill_buffer(buffer, obs_dim, action_dim, n=1000):
    obs = np.random.randn(obs_dim).astype(np.float32)
    for _ in range(n):
        a = np.random.randn(action_dim).astype(np.float32)
        buffer.add(obs, a, np.random.randn(),
                   np.random.randn(obs_dim).astype(np.float32), False)


# ---- Baselines ----

def test_td3(obs_dim, action_dim, max_action, device):
    print("[TD3] Testing...")
    from td3 import TD3Agent
    from buffer import ReplayBuffer
    agent = TD3Agent(obs_dim, action_dim, max_action, device=device)
    obs = np.random.randn(obs_dim).astype(np.float32)
    action = agent.select_action(obs)
    print(f"  action shape: {action.shape}, range: [{action.min():.2f}, {action.max():.2f}]")
    buffer = ReplayBuffer(obs_dim, action_dim, capacity=10000, device=device)
    fill_buffer(buffer, obs_dim, action_dim)
    metrics = agent.train(buffer, batch_size=64)
    print(f"  metrics: q1={metrics['q1_mean']:.3f}, critic_loss={metrics['critic_loss']:.3f}")
    print("  OK")


def test_sac(obs_dim, action_dim, max_action, device):
    print("[SAC] Testing...")
    from sac import SACAgent
    from buffer import ReplayBuffer
    agent = SACAgent(obs_dim, action_dim, max_action, device=device)
    obs = np.random.randn(obs_dim).astype(np.float32)
    action = agent.select_action(obs)
    print(f"  action shape: {action.shape}")
    buffer = ReplayBuffer(obs_dim, action_dim, capacity=10000, device=device)
    fill_buffer(buffer, obs_dim, action_dim)
    metrics = agent.train(buffer, batch_size=64)
    print(f"  metrics: q1={metrics['q1_mean']:.3f}, alpha={metrics['alpha']:.3f}, entropy={metrics['entropy']:.3f}")
    print("  OK")


def test_ddpg(obs_dim, action_dim, max_action, device):
    print("[DDPG] Testing...")
    from ddpg import DDPGAgent
    from buffer import ReplayBuffer
    agent = DDPGAgent(obs_dim, action_dim, max_action, device=device)
    obs = np.random.randn(obs_dim).astype(np.float32)
    action = agent.select_action(obs)
    print(f"  action shape: {action.shape}, range: [{action.min():.2f}, {action.max():.2f}]")
    buffer = ReplayBuffer(obs_dim, action_dim, capacity=10000, device=device)
    fill_buffer(buffer, obs_dim, action_dim)
    metrics = agent.train(buffer, batch_size=64)
    print(f"  metrics: q={metrics['q_mean']:.3f}, critic_loss={metrics['critic_loss']:.3f}")
    print("  OK")


# ---- Proposals ----

def test_attention_prior(obs_dim, action_dim, max_action, device):
    print("[AttentionPrior] Testing...")
    from 基于注意力机制与状态先验不确定性的自适应 import AttentionPriorAgent
    from buffer import ReplayBuffer
    agent = AttentionPriorAgent(obs_dim, action_dim, max_action, device=device)
    obs = np.random.randn(obs_dim).astype(np.float32)
    action = agent.select_action(obs)
    print(f"  action shape: {action.shape}")
    buffer = ReplayBuffer(obs_dim, action_dim, capacity=10000, device=device)
    fill_buffer(buffer, obs_dim, action_dim)
    metrics = agent.train(buffer, batch_size=64)
    print(f"  metrics: q1={metrics['q1_mean']:.3f}, alpha={metrics['alpha']:.3f}, entropy={metrics['entropy']:.3f}")
    print("  OK")


def test_td_variance(obs_dim, action_dim, max_action, device):
    print("[TDVariance] Testing...")
    from 基于td误差方差异方差感知的自适应熵调节 import TDVarianceAgent
    from buffer import ReplayBuffer
    agent = TDVarianceAgent(obs_dim, action_dim, max_action, device=device)
    obs = np.random.randn(obs_dim).astype(np.float32)
    action = agent.select_action(obs)
    print(f"  action shape: {action.shape}")
    buffer = ReplayBuffer(obs_dim, action_dim, capacity=10000, device=device)
    fill_buffer(buffer, obs_dim, action_dim)
    metrics = agent.train(buffer, batch_size=64)
    print(f"  metrics: q1={metrics['q1_mean']:.3f}, alpha={metrics['alpha']:.3f}, entropy={metrics['entropy']:.3f}")
    print("  OK")


def test_value_uncertainty(obs_dim, action_dim, max_action, device):
    print("[ValueUncertainty] Testing...")
    from 基于值函数不确定性量化的自适应熵调节ac算法 import ValueUncertaintyAgent
    from buffer import ReplayBuffer
    agent = ValueUncertaintyAgent(obs_dim, action_dim, max_action, device=device)
    obs = np.random.randn(obs_dim).astype(np.float32)
    action = agent.select_action(obs)
    print(f"  action shape: {action.shape}")
    buffer = ReplayBuffer(obs_dim, action_dim, capacity=10000, device=device)
    fill_buffer(buffer, obs_dim, action_dim)
    metrics = agent.train(buffer, batch_size=64)
    print(f"  metrics: q={metrics['q_mean']:.3f}, alpha={metrics['alpha']:.3f}, "
          f"sigma_q={metrics['sigma_q_mean']:.3f}, entropy={metrics['entropy']:.3f}")
    print("  OK")


def test_dp_depth(obs_dim, action_dim, max_action, device):
    print("[DPDepth] Testing...")
    from w3_方案方向 import DPDepthAgent
    from buffer import ReplayBuffer
    agent = DPDepthAgent(obs_dim, action_dim, max_action, device=device)
    obs = np.random.randn(obs_dim).astype(np.float32)
    action = agent.select_action(obs)
    print(f"  action shape: {action.shape}")
    buffer = ReplayBuffer(obs_dim, action_dim, capacity=10000, device=device)
    fill_buffer(buffer, obs_dim, action_dim)
    metrics = agent.train(buffer, batch_size=64)
    print(f"  metrics: q1={metrics['q1_mean']:.3f}, alpha={metrics['alpha']:.3f}, entropy={metrics['entropy']:.3f}")
    print("  OK")


def test_taylor_curvature(obs_dim, action_dim, max_action, device):
    print("[TaylorCurvature] Testing...")
    from 基于taylor展开的局部熵曲率自适应ac算法 import TaylorCurvatureAgent
    from buffer import ReplayBuffer
    agent = TaylorCurvatureAgent(obs_dim, action_dim, max_action, device=device)
    obs = np.random.randn(obs_dim).astype(np.float32)
    action = agent.select_action(obs)
    print(f"  action shape: {action.shape}")
    buffer = ReplayBuffer(obs_dim, action_dim, capacity=10000, device=device)
    fill_buffer(buffer, obs_dim, action_dim)
    metrics = agent.train(buffer, batch_size=64)
    print(f"  metrics: q1={metrics['q1_mean']:.3f}, alpha={metrics['alpha']:.3f}, entropy={metrics['entropy']:.3f}")
    print("  OK")


def test_gait_phase(obs_dim, action_dim, max_action, device):
    print("[GaitPhase] Testing...")
    from 跨步态相位时序差分噪声驱动的动态熵调节ac算法 import GaitPhaseAgent
    from buffer import ReplayBuffer
    agent = GaitPhaseAgent(obs_dim, action_dim, max_action, device=device)
    obs = np.random.randn(obs_dim).astype(np.float32)
    action = agent.select_action(obs)
    print(f"  action shape: {action.shape}")
    buffer = ReplayBuffer(obs_dim, action_dim, capacity=10000, device=device)
    fill_buffer(buffer, obs_dim, action_dim)
    metrics = agent.train(buffer, batch_size=64)
    print(f"  metrics: q1={metrics['q1_mean']:.3f}, alpha={metrics['alpha']:.3f}, entropy={metrics['entropy']:.3f}")
    print("  OK")


def test_iqn_quantile(obs_dim, action_dim, max_action, device):
    print("[IQN_QUANTILE] Testing...")
    from iqn_quantile_agent import IQNQuantileAgent
    from buffer import ReplayBuffer
    agent = IQNQuantileAgent(obs_dim, action_dim, max_action, device=device)
    obs = np.random.randn(obs_dim).astype(np.float32)
    action = agent.select_action(obs)
    print(f"  select_action shape: {action.shape}, range: [{action.min():.3f}, {action.max():.3f}]")
    buffer = ReplayBuffer(obs_dim, action_dim, capacity=2000)
    fill_buffer(buffer, obs_dim, action_dim, n=256)
    metrics = agent.train(buffer, batch_size=64)
    print(f"  metrics: {[(k, f'{v:.3f}') for k, v in sorted(metrics.items()) if not k.endswith('_loss')]}")
    assert not any(np.isnan(v) for v in metrics.values()), "NaN detected in metrics"
    assert "q_mean" in metrics, "Missing q_mean"
    print("  OK")


def test_iqn_quantile_simple(obs_dim, action_dim, max_action, device):
    print("[IQN_QUANTILE_SIMPLE] Testing...")
    from iqn_quantile_simple_agent import IQNQuantileSimpleAgent
    from buffer import ReplayBuffer
    agent = IQNQuantileSimpleAgent(obs_dim, action_dim, max_action, device=device)
    obs = np.random.randn(obs_dim).astype(np.float32)
    action = agent.select_action(obs)
    print(f"  select_action shape: {action.shape}, range: [{action.min():.3f}, {action.max():.3f}]")
    buffer = ReplayBuffer(obs_dim, action_dim, capacity=2000)
    fill_buffer(buffer, obs_dim, action_dim, n=256)
    metrics = agent.train(buffer, batch_size=64)
    print(f"  metrics: {[(k, f'{v:.3f}') for k, v in sorted(metrics.items()) if not k.endswith('_loss')]}")
    assert not any(np.isnan(v) for v in metrics.values()), "NaN detected in metrics"
    assert "q_mean" in metrics, "Missing q_mean"
    print("  OK")


def test_dual_critic_attention(obs_dim, action_dim, max_action, device):
    print("[DUAL_CRITIC_ATTENTION] Testing...")
    from dual_critic_attention_agent import DualCriticAttentionAgent
    from buffer import ReplayBuffer
    agent = DualCriticAttentionAgent(obs_dim, action_dim, max_action, device=device)
    obs = np.random.randn(obs_dim).astype(np.float32)
    action = agent.select_action(obs)
    print(f"  select_action shape: {action.shape}, range: [{action.min():.3f}, {action.max():.3f}]")
    buffer = ReplayBuffer(obs_dim, action_dim, capacity=2000)
    fill_buffer(buffer, obs_dim, action_dim, n=256)
    metrics = agent.train(buffer, batch_size=64)
    print(f"  metrics: {[(k, f'{v:.3f}') for k, v in sorted(metrics.items()) if not k.endswith('_loss')]}")
    assert not any(np.isnan(v) for v in metrics.values()), "NaN detected in metrics"
    assert "q1_mean" in metrics, "Missing q1_mean"
    print("  OK")


def test_qvgn_sac(obs_dim, action_dim, max_action, device):
    print("[QVGN_SAC] Testing...")
    from qvgn_sac_agent import QVGNSACAgent
    from buffer import ReplayBuffer
    agent = QVGNSACAgent(obs_dim, action_dim, max_action, device=device)
    obs = np.random.randn(obs_dim).astype(np.float32)
    action = agent.select_action(obs)
    print(f"  select_action shape: {action.shape}, range: [{action.min():.3f}, {action.max():.3f}]")
    buffer = ReplayBuffer(obs_dim, action_dim, capacity=2000, device=device)
    fill_buffer(buffer, obs_dim, action_dim, n=256)
    metrics = agent.train(buffer, batch_size=64)
    print(f"  metrics: {[(k, f'{v:.3f}') for k, v in sorted(metrics.items()) if not k.endswith('_loss')]}")
    assert not any(np.isnan(v) for v in metrics.values()), "NaN detected in metrics"
    assert "q_mean" in metrics, "Missing q_mean"
    # Verify save/load roundtrip
    agent.save("/tmp/test_qvgn_sac.pt")
    agent2 = QVGNSACAgent(obs_dim, action_dim, max_action, device=device)
    agent2.load("/tmp/test_qvgn_sac.pt")
    action2 = agent2.select_action(obs)
    print(f"  load+select OK, shape: {action2.shape}")
    print("  OK")


TEST_MAP = {
    # Baselines
    "td3": test_td3,
    "sac": test_sac,
    "ddpg": test_ddpg,
    # Proposals
    "attention_prior": test_attention_prior,
    "td_variance": test_td_variance,
    "value_uncertainty": test_value_uncertainty,
    "dp_depth": test_dp_depth,
    "taylor_curvature": test_taylor_curvature,
    "gait_phase": test_gait_phase,
    "iqn_quantile": test_iqn_quantile,
    "iqn_quantile_simple": test_iqn_quantile_simple,
    "dual_critic_attention": test_dual_critic_attention,
    "qvgn_sac": test_qvgn_sac,
}


def main():
    parser = argparse.ArgumentParser(description="Smoke test for all algorithms")
    parser.add_argument("--device", type=str, default="cuda", help="Device (cuda/cpu)")
    parser.add_argument("--algo", nargs="+", default=None, help="Specific algorithms to test")
    args = parser.parse_args()

    device = args.device
    if device == "cuda" and not torch.cuda.is_available():
        print("CUDA not available, using CPU")
        device = "cpu"

    print(f"Device: {device}")
    print("=" * 60)

    obs_dim, action_dim, max_action = test_environment()

    algos = args.algo if args.algo else list(TEST_MAP.keys())

    failed = []
    for algo in algos:
        if algo not in TEST_MAP:
            print(f"[SKIP] Unknown algorithm: {algo}")
            continue
        try:
            TEST_MAP[algo](obs_dim, action_dim, max_action, device)
        except ImportError as e:
            print(f"  NOT YET IMPLEMENTED: {e}")
        except Exception as e:
            print(f"  FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed.append(algo)

    if failed:
        print(f"\n{'=' * 60}")
        print(f"FAILURES: {', '.join(failed)}")
        sys.exit(1)
    else:
        print(f"\n{'=' * 60}")
        print(f"ALL SMOKE TESTS PASSED!")
        print("=" * 60)


if __name__ == "__main__":
    main()
