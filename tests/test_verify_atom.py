"""Tests for verify_atom.py — 8 bad fixtures → exit 1, 2 good fixtures → exit 0."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
VERIFY_ATOM = Path(__file__).parent.parent / "tools" / "verify_atom.py"

# ── Helper: valid base atom ──

VALID_CODE = """\
import torch
import torch.nn.functional as F

def step(self, batch):
    s, a, r, s2, d = batch
    q1 = self.critic1(s, a)
    q2 = self.critic2(s, a)
    with torch.no_grad():
        a2 = self.actor_target(s2)
        noise = torch.randn_like(a2) * self.policy_noise
        noise = noise.clamp(-self.noise_clip, self.noise_clip)
        a2_noisy = (a2 + noise).clamp(-self.max_action, self.max_action)
        q1_t, q2_t = self.critic1_target(s2, a2_noisy), self.critic2_target(s2, a2_noisy)
        q_target = r + (1 - d) * self.gamma * torch.min(q1_t, q2_t)
    critic_loss = F.mse_loss(q1, q_target) + F.mse_loss(q2, q_target)
    self.critic_optimizer.zero_grad()
    critic_loss.backward()
    self.critic_optimizer.step()
    return {'critic_loss': critic_loss.item()}
"""


def _make_atom(core_method_body: str, **overrides) -> dict:
    """Build a valid RefinedAtom dict, override specific fields."""
    base = {
        "atom_id": "test01",
        "philosophical_analogy": "Original analogy text (retained for traceability)",
        "problem_anchor": {
            "bottom_line": "Improve sample efficiency on benchmark by >=15%",
            "bottleneck": "Current method under-samples high-uncertainty regions",
            "non_goals": ["Not targeting wall-clock speedup", "Not changing reward shaping"],
            "constraints": ["Single GPU", "Fits in existing trainer API"],
            "success_condition": "AUC delta >= 0.15 with 95% CI not crossing zero, 3 seeds",
        },
        "concrete_algorithm": {
            "core_method_body": core_method_body,
            "core_update_equation_latex": "y_t = r_t + (1-d_t) \\gamma \\min_i Q_i(s_{t+1}, a_{t+1})",
            "memory_structure": "ReplayBuffer[Tensor] FIFO, capacity 1M, stores (s,a,r,s2,d) as float32",
            "hyperparameters": [
                {"name": "lr", "default": 3e-4, "range": [1e-5, 1e-2], "description": "Adam learning rate"},
                {"name": "gamma", "default": 0.99, "range": [0.9, 0.999], "description": "Discount factor"},
            ],
        },
        "novelty_vs_artifacts": [
            {
                "artifact_path": "artifacts/td3.py",
                "differences": [
                    "TD3.py L47 uses a single Q-network pair with EMA target; this uses K=5 independent Q-nets with per-ensemble min target",
                    "TD3.py L102 samples uniformly from replay buffer; this prioritizes high-q-std samples via PER with alpha=0.6",
                ],
            },
        ],
        "literature_grounding": [
            {
                "literature_file": "literature/fujimoto2018td3.md",
                "paper_title": "TD3: Addressing Function Approximation Error in Actor-Critic Methods",
                "adapted_element": "Eq.5 of Sec.4.2 — clipped double-Q target computation",
                "verbatim_quote": "We propose to use the minimum of the two critics to compute the target in the Bellman error",
                "code_correspondence": "lines 10-12: q_target = r + (1-d) * gamma * min(q1_t, q2_t)",
            },
            {
                "literature_file": "literature/haarnoja2018sac.md",
                "paper_title": "SAC: Soft Actor-Critic — Off-Policy Maximum Entropy Deep RL",
                "adapted_element": "Eq.4 entropy-regularized objective with auto-tuned alpha",
                "verbatim_quote": "We augment the standard maximum reward RL objective with an entropy term H(pi(cdot|s_t))",
                "code_correspondence": "lines 5-7: noise generation and clamping for target policy smoothing",
            },
            {
                "literature_file": "literature/chen2021redq.md",
                "paper_title": "REDQ: Randomized Ensembled Double Q-Learning",
                "adapted_element": "Eq.5 of Sec.3.2 — ensemble target with min-over-subset",
                "verbatim_quote": "We use an ensemble of N Q-networks and compute the TD target using the minimum over a random subset of size M",
                "code_correspondence": "lines 10-12: q_target = r + (1-d) * gamma * min(q1_t, q2_t)",
            },
        ],
        "trainer_integration": {
            "trainer_py_lines_touched": "L42-L78, L120-L135",
            "step_method_signature": "def step(self, batch: Tuple[Tensor, ...]) -> Dict[str, float]:",
            "required_batch_fields": ["obs", "action", "reward", "next_obs", "done"],
        },
    }
    base.update(overrides)
    return base


def _run_verify(atom_dict: dict, quick: bool = True) -> subprocess.CompletedProcess:
    """Run verify_atom.py on a dict. Write temp file, run, return result."""
    tmp = FIXTURES_DIR / "_tmp_test.json"
    tmp.write_text(json.dumps(atom_dict, indent=2), encoding="utf-8")
    args = [sys.executable, str(VERIFY_ATOM), "--atom", str(tmp)]
    if quick:
        args.append("--quick")
    return subprocess.run(args, capture_output=True, text=True)


# ── Bad fixtures (expect exit != 0) ──

PHILOSOPHY_IN_DOCSTRING = '''\
import torch
def step(self, batch):
    """1. Analyze what makes X work. 2. Map isomorphic relational structure.
    3. Reconcile via cyclic_3node. 4. Test whether the structural analogy transfers."""
    s, a, r, s2, d = batch
    q1 = self.q(s, a)
    q2 = self.q2(s, a)
    q_target = r + (1 - d) * self.gamma * q1
    loss = ((q1 - q_target)**2).mean()
    self.opt.zero_grad()
    loss.backward()
    self.opt.step()
    return {'loss': loss.item()}
'''

SHORT_METHOD = '''\
import torch
def step(self, batch):
    s, a, r, s2, d = batch
    return s.mean()
'''

NO_STEP_METHOD = '''\
import torch
def forward(self, x):
    return self.net(x)

class DummyAgent:
    def __init__(self):
        self.net = torch.nn.Linear(10, 1)
'''

TUNABLE_HPARAM = VALID_CODE  # reuse valid code, but override hyperparams below

BAD_FIXTURES = [
    ("atom_bad_docstring_philosophy", _make_atom(PHILOSOPHY_IN_DOCSTRING), True),
    ("atom_bad_short_method", _make_atom(SHORT_METHOD), True),
    ("atom_bad_no_step_method", _make_atom(NO_STEP_METHOD), True),
    ("atom_bad_tunable_hparam", _make_atom(
        VALID_CODE,
        concrete_algorithm={
            "core_method_body": VALID_CODE,
            "core_update_equation_latex": "y = f(x)" * 3,
            "memory_structure": "Simple buffer with 1M capacity for (s,a,r,s2,d) tuples stored as torch tensors",
            "hyperparameters": [
                {"name": "lr", "default": "tunable", "description": "learning rate parameter that is tuned"},
                {"name": "gamma", "default": 0.99, "description": "Discount factor for future rewards"},
            ],
        },
    ), True),
    ("atom_bad_vague_diff", _make_atom(
        VALID_CODE,
        novelty_vs_artifacts=[
            {
                "artifact_path": "artifacts/td3.py",
                "differences": ["different approach from TD3", "similar to MAP"],
            },
        ],
    ), True),
]


@pytest.mark.parametrize("name,atom,quick", BAD_FIXTURES)
def test_bad_atom_rejected(name, atom, quick):
    """Bad atoms must be rejected (exit != 0)."""
    r = _run_verify(atom, quick=quick)
    assert r.returncode != 0, (
        f"FAIL: {name} was ACCEPTED but should be REJECTED\n"
        f"stdout: {r.stdout[:300]}"
    )


# ── Good fixtures (expect exit == 0) ──

GOOD_FIXTURES = [
    ("atom_good_concrete", _make_atom(VALID_CODE), True),
    ("atom_good_minimal", _make_atom(
        VALID_CODE.replace("K=5 independent Q-nets", "K=3 independent Q-nets"),
        hyperparameters=[
            {"name": "lr", "default": 3e-4, "range": [1e-5, 1e-2], "description": "Adam learning rate"},
            {"name": "gamma", "default": 0.99, "range": [0.9, 0.999], "description": "Discount factor"},
        ],
        atom_id="t02",
    ), True),
]


@pytest.mark.parametrize("name,atom,quick", GOOD_FIXTURES)
def test_good_atom_accepted(name, atom, quick):
    """Good atoms must be accepted (exit == 0)."""
    r = _run_verify(atom, quick=quick)
    assert r.returncode == 0, (
        f"FAIL: {name} was REJECTED but should be ACCEPTED\n"
        f"stderr: {r.stderr[:300]}\nstdout: {r.stdout[:300]}"
    )


# ── Save fixtures to disk ──

def test_save_fixtures():
    """Save all fixtures to tests/fixtures/ for manual inspection."""
    for name, atom, _ in BAD_FIXTURES + GOOD_FIXTURES:
        path = FIXTURES_DIR / f"{name}.json"
        path.write_text(json.dumps(atom, indent=2, ensure_ascii=False), encoding="utf-8")
        assert path.exists(), f"Failed to write {path}"
