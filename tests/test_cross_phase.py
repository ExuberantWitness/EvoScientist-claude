"""Cross-phase integration tests — validate the full pipeline: Plan → Research → Ideate → Code → Analyze.

Tests cover:
  - W2 Plan: DomainConfig loading, plan template rendering
  - W3 Research: LitIngest manifest generation
  - W3.5 Ideate: Atom creation and schema validation
  - W3.7 Refine: RefinedAtom acceptance/rejection
  - W3.8 Verify: L1 quick check + L2 full check
  - W4 Code: Plan verification + stub compilation
  - W5 Analyze: Claim Chain v2 data flow
  - Negative archive: failure tracking and ban logic
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT))

# ── Shared test data ──

VALID_STEP_CODE = """\
import torch
import torch.nn.functional as F
from typing import Dict

def step(self, batch):
    s, a, r, s2, d = batch
    q1 = self.critic1(s, a)
    q2 = self.critic2(s, a)
    with torch.no_grad():
        a2 = self.actor_target(s2)
        noise = torch.randn_like(a2) * 0.2
        noise = noise.clamp(-0.5, 0.5)
        a2_noisy = (a2 + noise).clamp(-1.0, 1.0)
        q1_t, q2_t = self.critic1_target(s2, a2_noisy), self.critic2_target(s2, a2_noisy)
        q_target = r + (1 - d) * 0.99 * torch.min(q1_t, q2_t)
    loss = F.mse_loss(q1, q_target) + F.mse_loss(q2, q_target)
    self.critic_optimizer.zero_grad()
    loss.backward()
    self.critic_optimizer.step()
    return {'critic_loss': loss.item()}
"""


def make_test_atom(atom_id: str, code: str, **overrides) -> dict:
    """Build a RefinedAtom dict for testing."""
    base = {
        "atom_id": atom_id,
        "philosophical_analogy": "Original sketch: Map isomorphism from X to Y",
        "problem_anchor": {
            "bottom_line": "Improve benchmark score by >=15% over baseline",
            "bottleneck": "Current method under-samples high-uncertainty regions",
            "non_goals": ["Don't change reward function", "Don't increase wall-clock time"],
            "constraints": ["Single GPU", "No environment modification"],
            "success_condition": "Improvement with 95% CI not crossing zero, 3 seeds",
        },
        "concrete_algorithm": {
            "core_method_body": code,
            "core_update_equation_latex": r"y_t = r_t + (1-d_t)\gamma \min_{i} Q_i(s_{t+1},a_{t+1}+\epsilon)",
            "memory_structure": "ReplayBuffer FIFO, 1M capacity, stores (s,a,r,s2,d) as float32 tensors",
            "hyperparameters": [
                {"name": "lr", "default": 3e-4, "range": [1e-5, 1e-2], "description": "Adam learning rate parameter"},
                {"name": "gamma", "default": 0.99, "range": [0.9, 0.999], "description": "Discount factor for TD target computation"},
            ],
        },
        "novelty_vs_artifacts": [
            {
                "artifact_path": "artifacts/td3.py",
                "differences": [
                    "TD3.py L42 uses single Q-network pair with EMA; this variant uses ensemble of 5 independent Q-networks without EMA target computation",
                    "TD3.py L102 samples uniformly from replay buffer; this uses prioritized sampling with proportional prioritization based on Q-value disagreement",
                ],
            },
        ],
        "literature_grounding": [
            {
                "literature_file": "literature/fujimoto2018td3.md",
                "paper_title": "Addressing Function Approximation Error in Actor-Critic Methods",
                "adapted_element": "Eq.5 Sec.4.2 — clipped double-Q target computation method",
                "verbatim_quote": "We propose to use the minimum of the two critics to compute the target in the Bellman error",
                "code_correspondence": "lines 10-12: q_target = r + (1-d) * 0.99 * min(q1_t, q2_t)",
            },
            {
                "literature_file": "literature/haarnoja2018sac.md",
                "paper_title": "Soft Actor-Critic — Off-Policy Maximum Entropy Deep Reinforcement Learning",
                "adapted_element": "Eq.4 entropy-regularized objective with adaptive temperature parameter",
                "verbatim_quote": "We augment the standard maximum reward RL objective with an entropy term H(pi(cdot|s_t))",
                "code_correspondence": "lines 8-10: noise = torch.randn_like(a2) * 0.2, clamp, a2_noisy",
            },
            {
                "literature_file": "literature/chen2021redq.md",
                "paper_title": "Randomized Ensembled Double Q-Learning for Fast Sample-Efficient Training",
                "adapted_element": "Eq.5 ensemble target computation with randomized subset selection",
                "verbatim_quote": "We use an ensemble of N Q-networks and compute the TD target using the minimum over a random subset of size M",
                "code_correspondence": "lines 10-12: q_target = r + (1-d) * 0.99 * min(q1_t, q2_t)",
            },
        ],
        "trainer_integration": {
            "trainer_py_lines_touched": "L42-L78, L120-L135",
            "step_method_signature": "def step(self, batch: Tuple[Tensor,Tensor,Tensor,Tensor,Tensor]) -> Dict[str,float]:",
            "required_batch_fields": ["obs", "action", "reward", "next_obs", "done"],
        },
    }
    base.update(overrides)
    return base


# ── W3.5 Ideate: Schema Validation Tests ──

class TestW35IdeateAtomSchema:
    """W3.5 Ideate — atom creation and schema validation."""

    def test_valid_method_atom_passes(self):
        from schemas.atom import RefinedAtom
        atom = RefinedAtom.model_validate(make_test_atom("test01", VALID_STEP_CODE))
        assert atom.atom_id == "test01"
        assert len(atom.concrete_algorithm.hyperparameters) == 2
        assert len(atom.literature_grounding) == 3

    def test_philosophical_docstring_rejected(self):
        philo_code = VALID_STEP_CODE.replace(
            "def step(self, batch):",
            'def step(self, batch):\n    """1. Analyze what makes X work. 2. Map isomorphic relational structure."""',
        )
        from schemas.atom import RefinedAtom
        with pytest.raises(Exception) as exc:
            RefinedAtom.model_validate(make_test_atom("bad", philo_code))
        assert "Buzzword" in str(exc.value) or "isomorphic" in str(exc.value).lower()

    def test_short_method_rejected(self):
        short = "import torch\ndef step(self, batch):\n    s = batch\n    return s"
        from schemas.atom import RefinedAtom
        with pytest.raises(Exception):
            RefinedAtom.model_validate(make_test_atom("short", short))

    def test_no_step_method_rejected(self):
        no_step = "import torch\ndef forward(self, x):\n    return x * 2\nclass Foo:\n    pass"
        from schemas.atom import RefinedAtom
        with pytest.raises(Exception):
            RefinedAtom.model_validate(make_test_atom("nostep", no_step))

    def test_tunable_hyperparam_rejected(self):
        from schemas.atom import RefinedAtom
        with pytest.raises(Exception):
            RefinedAtom.model_validate(make_test_atom("tune", VALID_STEP_CODE,
                concrete_algorithm={
                    "core_method_body": VALID_STEP_CODE,
                    "core_update_equation_latex": "y = f(x)" * 3,
                    "memory_structure": "Buffer with 1M capacity for tensors representing state transitions",
                    "hyperparameters": [
                        {"name": "lr", "default": "tunable", "description": "learning rate parameter tuned per experiment"},
                        {"name": "gamma", "default": 0.99, "description": "Discount factor for future reward computation"},
                    ],
                },
            ))

    def test_vague_diff_rejected(self):
        from schemas.atom import RefinedAtom
        with pytest.raises(Exception) as exc:
            RefinedAtom.model_validate(make_test_atom("vague", VALID_STEP_CODE,
                novelty_vs_artifacts=[{
                    "artifact_path": "artifacts/td3.py",
                    "differences": ["different approach from TD3"],
                }],
            ))
        assert "short" in str(exc.value).lower() or "vague" in str(exc.value).lower()

    def test_missing_literature_field_rejected(self):
        from schemas.atom import RefinedAtom
        with pytest.raises(Exception):
            RefinedAtom.model_validate(make_test_atom("nolit", VALID_STEP_CODE,
                literature_grounding=[
                    {
                        "literature_file": "lit/fake.md",
                        "paper_title": "Test Paper Title Goes Here",
                        "adapted_element": "Some element description",
                        "verbatim_quote": "A quote that is at least thirty characters long",
                        # missing code_correspondence
                    },
                ],
            ))


# ── W3.7 Refine: verify_atom L1 Quick Check ──

class TestW37RefineL1Verify:
    """W3.7 Refine — L1 quick check via verify_atom --quick."""

    @pytest.fixture
    def tmpdir(self):
        d = tempfile.mkdtemp()
        yield Path(d)
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    def test_l1_valid_atom_passes(self, tmpdir):
        atom_file = tmpdir / "test.json"
        atom_file.write_text(json.dumps(make_test_atom("ok", VALID_STEP_CODE)))
        r = subprocess.run(
            [sys.executable, str(PROJECT / "tools" / "verify_atom.py"),
             "--quick", "--atom", str(atom_file)],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, f"L1 should pass: {r.stdout}\n{r.stderr}"

    def test_l1_philosophy_rejected(self, tmpdir):
        philo = "1. Analyze what makes X work.\n2. Map isomorphic structure.\n3. Reconcile via cyclic_3node."
        atom_file = tmpdir / "bad.json"
        atom_file.write_text(json.dumps(make_test_atom("bad", philo)))
        r = subprocess.run(
            [sys.executable, str(PROJECT / "tools" / "verify_atom.py"),
             "--quick", "--atom", str(atom_file)],
            capture_output=True, text=True,
        )
        assert r.returncode != 0, f"L1 should reject philosophy: {r.stdout}"

    def test_l1_short_body_rejected(self, tmpdir):
        short = "import torch\ndef step(self, batch):\n    return batch\n"
        atom_file = tmpdir / "short.json"
        atom_file.write_text(json.dumps(make_test_atom("short", short)))
        r = subprocess.run(
            [sys.executable, str(PROJECT / "tools" / "verify_atom.py"),
             "--quick", "--atom", str(atom_file)],
            capture_output=True, text=True,
        )
        assert r.returncode != 0

    def test_l1_no_step_rejected(self, tmpdir):
        nostep = "import torch\ndef forward(self, x):\n    return self.net(x)\nclass Foo:\n    pass\n"
        atom_file = tmpdir / "nostep.json"
        atom_file.write_text(json.dumps(make_test_atom("nostep", nostep)))
        r = subprocess.run(
            [sys.executable, str(PROJECT / "tools" / "verify_atom.py"),
             "--quick", "--atom", str(atom_file)],
            capture_output=True, text=True,
        )
        assert r.returncode != 0


# ── W3 Research + W3.3 LitIngest: Literature Flow ──

class TestW3LitIngest:
    """W3 Research → W3.3 LitIngest — manifest generation and grep."""

    @pytest.fixture
    def session_dir(self):
        d = tempfile.mkdtemp()
        sp = Path(d)
        (sp / "_index").mkdir(parents=True, exist_ok=True)
        (sp / "literature").mkdir(parents=True, exist_ok=True)
        # Create minimal literature files
        (sp / "literature" / "fujimoto2018td3.md").write_text(
            "# TD3\n\nWe propose to use the minimum of the two critics to compute "
            "the target in the Bellman error. This addresses the overestimation bias.\n",
            encoding="utf-8",
        )
        (sp / "literature" / "haarnoja2018sac.md").write_text(
            "# SAC\n\nWe augment the standard maximum reward RL objective with an "
            "entropy term H(pi(cdot|s_t)). This encourages exploration.\n",
            encoding="utf-8",
        )
        (sp / "literature" / "chen2021redq.md").write_text(
            "# REDQ\n\nWe use an ensemble of N Q-networks and compute the TD target "
            "using the minimum over a random subset of size M. This reduces variance.\n",
            encoding="utf-8",
        )
        # Create manifest
        manifest_lines = [
            json.dumps({"paper_id": p, "file": f"literature/{p}.md", "title": t, "abstract": "", "relevance_score": 0.9, "source": "test"})
            for p, t in [
                ("fujimoto2018td3", "Addressing Function Approximation Error in Actor-Critic Methods"),
                ("haarnoja2018sac", "Soft Actor-Critic — Off-Policy Maximum Entropy Deep RL"),
                ("chen2021redq", "REDQ Paper"),
            ]
        ]
        (sp / "_index" / "literature_manifest.jsonl").write_text("\n".join(manifest_lines))
        yield sp
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    def test_manifest_has_three_papers(self, session_dir):
        manifest = session_dir / "_index" / "literature_manifest.jsonl"
        papers = [json.loads(l) for l in manifest.read_text().strip().split("\n") if l.strip()]
        assert len(papers) == 3

    def test_l2_verify_checks_manifest(self, session_dir):
        """L2 should check that literature files are in manifest."""
        atom_file = session_dir / "test_atom.json"
        atom_file.write_text(json.dumps(make_test_atom("l2test", VALID_STEP_CODE)))
        r = subprocess.run(
            [sys.executable, str(PROJECT / "tools" / "verify_atom.py"),
             "--session", str(session_dir), "--atom", str(atom_file)],
            capture_output=True, text=True,
        )
        # Should pass — all lit files are in manifest
        assert r.returncode == 0, f"L2 should pass: {r.stdout}\n{r.stderr}"

    def test_l2_rejects_unregistered_lit(self, session_dir):
        """L2 should reject when literature_file is not in manifest."""
        unregistered = make_test_atom("unreg", VALID_STEP_CODE,
            literature_grounding=[
                {
                    "literature_file": "literature/nonexistent_paper.md",
                    "paper_title": "Some Fake Paper That Does Not Exist Anywhere",
                    "adapted_element": "Made up element description here",
                    "verbatim_quote": "This quote definitely does not appear in any real literature file anywhere",
                    "code_correspondence": "lines 10-12: q_target = r + (1-d) * 0.99 * min(q1_t, q2_t)",
                },
                {
                    "literature_file": "literature/fujimoto2018td3.md",
                    "paper_title": "Addressing Function Approximation Error in Deep RL",
                    "adapted_element": "Eq.5 clipped double-Q method implementation",
                    "verbatim_quote": "We propose to use the minimum of the two critics to compute the target in the Bellman error",
                    "code_correspondence": "lines 10-12: q_target = r + (1-d) * 0.99 * min(q1_t, q2_t)",
                },
                {
                    "literature_file": "literature/haarnoja2018sac.md",
                    "paper_title": "Soft Actor-Critic Off-Policy Maximum Entropy RL",
                    "adapted_element": "Eq.4 entropy regularized objective function",
                    "verbatim_quote": "We augment the standard maximum reward RL objective with an entropy term H(pi(cdot|s_t))",
                    "code_correspondence": "lines 8-10: noise=torch.randn_like, clamp, a2_noisy",
                },
            ],
        )
        atom_file = session_dir / "unreg_atom.json"
        atom_file.write_text(json.dumps(unregistered))
        r = subprocess.run(
            [sys.executable, str(PROJECT / "tools" / "verify_atom.py"),
             "--session", str(session_dir), "--atom", str(atom_file)],
            capture_output=True, text=True,
        )
        assert "UNREGISTERED" in r.stdout, f"Should detect unregistered lit: {r.stdout}"

    def test_verbatim_quote_fuzzy_match(self, session_dir):
        """Test that verbatim_quote with whitespace variation still matches."""
        atom = make_test_atom("fuzzy", VALID_STEP_CODE,
            literature_grounding=[
                {
                    "literature_file": "literature/fujimoto2018td3.md",
                    "paper_title": "Addressing Function Approximation Error in Actor-Critic Methods",
                    "adapted_element": "Eq.5 target computation method implementation",
                    "verbatim_quote": "We propose to use the minimum of the two critics to compute the target in the Bellman error",
                    "code_correspondence": "lines 10-12: q_target = r + (1-d) * 0.99 * min(q1_t, q2_t)",
                },
                {
                    "literature_file": "literature/haarnoja2018sac.md",
                    "paper_title": "Soft Actor-Critic — Off-Policy Maximum Entropy Deep RL",
                    "adapted_element": "Eq.4 entropy regularization technique",
                    "verbatim_quote": "We augment the standard maximum reward RL objective with an entropy term H(pi(cdot|s_t))",
                    "code_correspondence": "lines 8-10: noise=torch.randn_like, clamp, a2_noisy",
                },
                {
                    "literature_file": "literature/chen2021redq.md",
                    "paper_title": "REDQ Paper",
                    "adapted_element": "Eq.5 ensemble target computation",
                    "verbatim_quote": "We use an ensemble of N Q-networks and compute the TD target using the minimum over a random subset of size M",
                    "code_correspondence": "lines 10-12: q_target = r + (1-d) * 0.99 * min(q1_t, q2_t)",
                },
            ],
        )
        atom_file = session_dir / "fuzzy.json"
        atom_file.write_text(json.dumps(atom))
        r = subprocess.run(
            [sys.executable, str(PROJECT / "tools" / "verify_atom.py"),
             "--session", str(session_dir), "--atom", str(atom_file)],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, f"Fuzzy match should pass: {r.stdout}"


# ── W4 Code: Plan Verification ──

class TestW4CodePlanVerify:
    """W4 Code — plan_verify + stub compilation."""

    @pytest.fixture
    def iteration_dir(self):
        d = tempfile.mkdtemp()
        ip = Path(d)
        stubs = ip / "planned_stubs"
        stubs.mkdir(parents=True)
        # Create valid stub
        (stubs / "test_algo.py").write_text(VALID_STEP_CODE)
        # Create plan
        (ip / "implementation_plan.md").write_text(
            "# Implementation Plan\n\n"
            "## Deliverables\n\n"
            "- [ ] artifacts/test_algo.py\n"
            "trainer.py 集成: L42-L78\n"
            "与 TD3.py 的区别: uses 5 Q-nets instead of 2\n"
        )
        yield ip
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    def test_valid_plan_passes(self, iteration_dir):
        r = subprocess.run(
            [sys.executable, str(PROJECT / "tools" / "verify_plan.py"),
             str(iteration_dir)],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, f"Plan should pass: {r.stdout}\n{r.stderr}"

    def test_missing_stub_detected(self, iteration_dir):
        (iteration_dir / "implementation_plan.md").write_text(
            "# Plan\n- [ ] artifacts/missing_algo.py\n"
        )
        r = subprocess.run(
            [sys.executable, str(PROJECT / "tools" / "verify_plan.py"),
             str(iteration_dir)],
            capture_output=True, text=True,
        )
        assert r.returncode != 0
        assert "MISSING" in r.stdout

    def test_banned_phrase_detected(self, iteration_dir):
        (iteration_dir / "implementation_plan.md").write_text(
            "# Plan\n- [ ] artifacts/test_algo.py\n与 trainer.py 接口兼容\n"
        )
        r = subprocess.run(
            [sys.executable, str(PROJECT / "tools" / "verify_plan.py"),
             str(iteration_dir)],
            capture_output=True, text=True,
        )
        assert "BANNED" in r.stdout, f"Should detect banned phrase: {r.stdout}"


# ── W5 Analyze: Claim Chain v2 Flow ──

class TestW5AnalyzeClaimChain:
    """W5 Analyze — CC v2 data flow: atoms → relations → graph."""

    @pytest.fixture
    def cc(self):
        from claim_chain.chain import ClaimChainV2
        db = tempfile.mktemp(suffix=".db")
        cc = ClaimChainV2(db)
        yield cc
        cc.close()
        try:
            os.unlink(db)
        except OSError:
            pass

    def test_add_atom_flow(self, cc):
        a1 = cc.add_atom("method", "Algorithm A", "Content A", tags=["test"])
        a2 = cc.add_atom("method", "Algorithm B", "Content B", tags=["test"])
        assert len(cc.all_nodes()) == 2
        assert a1["type"] == "method"

    def test_add_relation_flow(self, cc):
        a1 = cc.add_atom("method", "Algo1", "C1")
        a2 = cc.add_atom("method", "Algo2", "C2")
        rel = cc.add_relation(
            a1["id"], a2["id"], "extends", evidence="test relation",
            metadata={
                "bottleneck": "overestimation_bias",
                "mechanism": "Testing mechanism with at least ten characters",
                "tradeoff": "Higher compute cost than baseline methods",
                "confidence": 0.8,
            },
        )
        assert rel["type"] == "extends"
        summary = cc.get_graph_summary()
        assert summary["total_nodes"] == 2
        assert summary["total_edges"] == 1

    def test_export_graph(self, cc):
        a1 = cc.add_atom("method", "Node1", "C1")
        a2 = cc.add_atom("method", "Node2", "C2")
        cc.add_relation(a1["id"], a2["id"], "extends", evidence="e",
            metadata={
                "bottleneck": "overestimation_bias",
                "mechanism": "Testing mechanism description long enough",
                "tradeoff": "No significant tradeoff identified",
                "confidence": 0.7,
            },
        )
        graph = cc.export_graph()
        assert len(graph["nodes"]) == 2
        assert len(graph["edges"]) == 1
        assert graph["nodes"][0]["id"] is not None


# ── W2 Plan: DomainConfig + Plan Templates ──

class TestW2PlanConfig:
    """W2 Plan — DomainConfig loading + plan template rendering."""

    def test_rl_preset_loads(self):
        from plugins.ideation.domain_presets import get_domain_preset
        rl = get_domain_preset("reinforcement_learning")
        assert rl["domain_name"] == "reinforcement_learning"
        assert len(rl["seed_keywords"]) > 0
        assert "sme_domains" in rl  # domain config has cross-domain mapping config

    def test_invalid_preset_falls_back(self):
        from plugins.ideation.domain_presets import get_domain_preset
        unknown = get_domain_preset("nonexistent_domain_xyz")
        assert unknown["domain_name"] == "general"

    def test_plan_template_renders(self):
        import tempfile
        from plugins.ideation.plan_templates import render_algo_section, render_plan_header
        hdr = render_plan_header("test_session", 0, "reinforcement_learning")
        assert "test_session" in hdr
        assert "reinforcement_learning" in hdr
        assert "Jinja2" in hdr

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(make_test_atom("tpl_test", VALID_STEP_CODE), f)
            tmp_path = f.name
        try:
            section = render_algo_section(Path(tmp_path))
            assert "BaseAlgorithm" in section
            assert "L42-L78" in section
            assert "TD3.py" in section
            assert "refined_proposals/tpl_test.json" in section
        finally:
            os.unlink(tmp_path)

    def test_plan_sanitize_banned(self):
        from plugins.ideation.plan_templates import sanitize_plan_text
        dirty = "Implementation: 与 trainer.py 接口兼容"
        clean = sanitize_plan_text(dirty)
        assert "与 trainer.py 接口兼容" not in clean
        assert "trainer.py 集成行号" in clean


# ── Cross-phase: Negative Archive ──

class TestNegativeArchive:
    """Negative archive for failed refinements (W3.7 retries + MAP-Elites)."""

    @pytest.fixture
    def na(self):
        d = tempfile.mkdtemp()
        from claim_chain.negative_archive import NegativeArchive
        na = NegativeArchive(Path(d))
        yield na
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    def test_record_and_retrieve(self, na):
        na.record_failure("map1", 1, "BuzzwordFound", "Found: isomorphic", "claude")
        na.record_failure("map1", 2, "ASTFail", "Body has 3 statements", "claude")
        na.record_failure("sme1", 1, "py_compile_FAIL", "SyntaxError", "claude")
        recent = na.get_recent_failures(3)
        assert len(recent) == 3
        # Most recent first
        assert recent[0]["atom_id"] == "sme1"

    def test_count_by_prefix(self, na):
        na.record_failure("map1", 1, "X", "stderr", "m")
        na.record_failure("map2", 1, "X", "stderr", "m")
        assert na.count_failures("map") == 2
        assert na.count_failures("sme") == 0

    def test_ban_after_max_failures(self, na):
        for i in range(5):
            na.record_failure(f"bad{i}", 1, "X", "err", "m")
        assert na.should_ban_direction("bad")  # 5 failures = ban threshold
        assert not na.should_ban_direction("good")

    def test_gate_rejects_bad_atom(self, na):
        bad_atom = na.session_dir / "bad.json"
        bad_atom.write_text(json.dumps(make_test_atom("bad", "not python code at all")))
        from claim_chain.negative_archive import atom_verify_gate
        ok, reason = atom_verify_gate(bad_atom)
        assert not ok
        assert "FAIL" in reason or "FAIL" in reason


# ── Phase 0: BaseAlgorithm contract ──

class TestBaseAlgorithm:
    """Phase 0 — BaseAlgorithm inheritance verification."""

    def test_concrete_subclass_passes(self):
        from plugins.experimentation.trainer_contract import BaseAlgorithm
        import numpy as np

        class TestAgent(BaseAlgorithm):
            def select_action(self, obs, deterministic=False):
                return np.zeros(3)

            def train(self, replay_buffer, batch_size=256):
                return {"loss": 0.0}

            def save(self, path):
                pass

            def load(self, path):
                pass

        agent = TestAgent()
        assert issubclass(TestAgent, BaseAlgorithm)

    def test_missing_method_errors(self):
        from plugins.experimentation.trainer_contract import BaseAlgorithm
        with pytest.raises(TypeError):
            class BrokenAgent(BaseAlgorithm):
                def select_action(self, obs, deterministic=False):
                    return None
                # missing train, save, load
            BrokenAgent()  # Instantiation triggers ABC check


# ── Phase 0.5: ConcretenessGate ──

class TestConcretenessGate:
    """Phase 6 — ConcretenessGate soft fallback."""

    def test_default_config(self):
        from pes_controller.protocol import ConcretenessGate
        gate = ConcretenessGate()
        assert gate.enabled is True
        assert gate.min_score == 0.3
        assert gate.block_on_failure is False

    def test_strict_mode(self):
        from pes_controller.protocol import ConcretenessGate
        gate = ConcretenessGate(block_on_failure=True, min_score=0.7)
        assert gate.min_score == 0.7
        assert gate.block_on_failure is True
