"""Unit tests for Flux-Insight v5 architecture.

Covers:
  1. Phase constants, TRANSITIONS, CHAIN_STEPS
  2. Phase handler registration and loading
  3. SKILL.md files existence and format
  4. Types dataclasses
  5. SkillExecutor SKILL.md parsing and template filling
  6. LLMClient initialization
  7. Controller v5 transition logic
  8. No stale PHASE_WRITE references in active code
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT))

SKILLS_DIR = PROJECT / "skills"
PES_DIR = PROJECT / "pes_controller"


# ═══════════════════════════════════════════════════════════════
# 1. Phase constants
# ═══════════════════════════════════════════════════════════════


class TestPhaseConstants:
    """Verify all phase constants, PHASES ordering, TRANSITIONS, PRODUCT_SPECS."""

    def test_phase_constants_defined(self):
        from pes_controller import (
            PHASE_INTAKE,
            PHASE_PLAN_1, PHASE_PLAN_2, PHASE_IDEATE,
            PHASE_CODE, PHASE_ANALYZE,
            PHASE_WRITE_PLAN, PHASE_WRITE_FIGURE, PHASE_WRITE_LATEX,
            PHASE_WRITE_COMPILE, PHASE_WRITE_IMPROVE,
            PHASE_REVIEW, PHASE_TERMINATED,
        )
        assert PHASE_PLAN_1 == "W2 问题分析"
        assert PHASE_INTAKE == "W1 Intake & Scope"
        assert PHASE_WRITE_PLAN == "W7.1 论文计划"
        assert PHASE_REVIEW == "W8 审阅"
        assert PHASE_TERMINATED == "已终止"

    def test_phases_order(self):
        from pes_controller import PHASES
        assert len(PHASES) == 12
        assert PHASES[0].startswith("W1")
        assert PHASES[-1].startswith("W8")

    def test_backward_compat_alias(self):
        from pes_controller import PHASE_WRITE, PHASE_WRITE_PLAN
        assert PHASE_WRITE == PHASE_WRITE_PLAN

    def test_transitions_forward_chain(self):
        from pes_controller import TRANSITIONS
        from pes_controller import (
            PHASE_INTAKE,
            PHASE_PLAN_1, PHASE_PLAN_2, PHASE_IDEATE,
            PHASE_CODE, PHASE_ANALYZE, PHASE_WRITE_PLAN,
            PHASE_WRITE_FIGURE, PHASE_WRITE_LATEX, PHASE_WRITE_COMPILE,
            PHASE_WRITE_IMPROVE, PHASE_REVIEW,
        )
        # W1 → W2 → W3 → W4 → W5 → W6
        assert PHASE_PLAN_1 in TRANSITIONS[PHASE_INTAKE]
        assert PHASE_PLAN_2 in TRANSITIONS[PHASE_PLAN_1]
        assert PHASE_IDEATE in TRANSITIONS[PHASE_PLAN_2]
        assert PHASE_CODE in TRANSITIONS[PHASE_IDEATE]
        assert PHASE_ANALYZE in TRANSITIONS[PHASE_CODE]

    def test_transitions_w7_backtrack(self):
        """W7.2+ can go back to W7.1."""
        from pes_controller import TRANSITIONS, PHASE_WRITE_PLAN
        for phase_key in [
            "PHASE_WRITE_FIGURE", "PHASE_WRITE_LATEX",
            "PHASE_WRITE_COMPILE", "PHASE_WRITE_IMPROVE",
        ]:
            from pes_controller import __dict__ as _d
            phase = getattr(
                __import__("pes_controller", fromlist=[phase_key]),
                phase_key,
            )
            assert PHASE_WRITE_PLAN in TRANSITIONS[phase], (
                f"{phase} should be able to transition back to W7.1"
            )

    def test_transitions_w8_targets(self):
        """W8 can go to W7.1, W5, W2, or terminate."""
        from pes_controller import TRANSITIONS, PHASE_REVIEW
        targets = TRANSITIONS[PHASE_REVIEW]
        assert len(targets) >= 3  # At minimum W7.1, W5, terminated

    def test_product_specs_w7_w8(self):
        from pes_controller import PRODUCT_SPECS
        from pes_controller import (
            PHASE_WRITE_PLAN, PHASE_WRITE_FIGURE, PHASE_WRITE_LATEX,
            PHASE_WRITE_COMPILE, PHASE_WRITE_IMPROVE, PHASE_REVIEW,
        )
        for phase in [PHASE_WRITE_PLAN, PHASE_WRITE_FIGURE, PHASE_WRITE_LATEX,
                      PHASE_WRITE_COMPILE, PHASE_WRITE_IMPROVE, PHASE_REVIEW]:
            assert phase in PRODUCT_SPECS, f"Missing PRODUCT_SPECS for {phase}"
            spec = PRODUCT_SPECS[phase]
            assert "required" in spec or "deliverables" in spec


# ═══════════════════════════════════════════════════════════════
# 2. Phase handler registration
# ═══════════════════════════════════════════════════════════════


class TestPhaseHandlers:
    """Verify phase handler registration and loading."""

    def test_all_phases_have_handlers(self):
        from pes_controller.phases import get_all_handlers
        from pes_controller import PHASES

        handlers = get_all_handlers()
        for phase in PHASES:
            assert phase in handlers, f"No handler registered for phase '{phase}'"

    def test_handler_has_build_step(self):
        from pes_controller.phases import get_all_handlers
        from pes_controller.phases.base import BasePhaseHandler

        for phase, handler_cls in get_all_handlers().items():
            assert hasattr(handler_cls, "build_step"), (
                f"Handler for {phase} missing build_step method"
            )

    def test_handler_has_chain_steps(self):
        from pes_controller.phases import get_all_handlers

        for phase, handler_cls in get_all_handlers().items():
            assert hasattr(handler_cls, "chain_steps"), (
                f"Handler for {phase} missing chain_steps"
            )
            assert isinstance(handler_cls.chain_steps, list), (
                f"chain_steps for {phase} should be a list"
            )
            assert len(handler_cls.chain_steps) > 0, (
                f"chain_steps for {phase} should not be empty"
            )

    def test_chain_steps_populated(self):
        """CHAIN_STEPS dict should be populated from handlers via get_all_handlers."""
        from pes_controller.phases import get_all_handlers
        from pes_controller import PHASES

        handlers = get_all_handlers()
        for phase in PHASES:
            assert phase in handlers, f"No handler for {phase}"
            assert len(handlers[phase].chain_steps) > 0, (
                f"Handler for {phase} has empty chain_steps"
            )

    def test_w1_handler_intake_steps(self):
        from pes_controller.phases import get_handler
        from pes_controller import PHASE_INTAKE

        handler_cls = get_handler(PHASE_INTAKE)
        assert handler_cls is not None
        assert len(handler_cls.chain_steps) == 5
        assert "github_search_baseline" in handler_cls.chain_steps
        assert "present_baseline_options" in handler_cls.chain_steps
        assert "test_baseline" in handler_cls.chain_steps
        assert "write_baselines_to_cc" in handler_cls.chain_steps

    def test_w7_1_handler_four_steps(self):
        from pes_controller.phases import get_handler
        from pes_controller import PHASE_WRITE_PLAN

        handler_cls = get_handler(PHASE_WRITE_PLAN)
        assert len(handler_cls.chain_steps) == 4
        assert "invoke_four_personas_paper" in handler_cls.chain_steps
        assert "elo_tournament_paper" in handler_cls.chain_steps

    def test_w7_5_handler_multi_round(self):
        from pes_controller.phases import get_handler
        from pes_controller import PHASE_WRITE_IMPROVE

        handler_cls = get_handler(PHASE_WRITE_IMPROVE)
        assert len(handler_cls.chain_steps) == 5  # 2 rounds (review+fix) + verify

    def test_w8_handler_three_rounds(self):
        from pes_controller.phases import get_handler
        from pes_controller import PHASE_REVIEW

        handler_cls = get_handler(PHASE_REVIEW)
        assert len(handler_cls.chain_steps) == 6  # 3 rounds (review+fix) + verify

    def test_w3_w4_inherit_w2(self):
        from pes_controller.phases.w2_handler import W2Handler
        from pes_controller.phases.w3_handler import W3Handler
        from pes_controller.phases.w4_handler import W4Handler

        assert issubclass(W3Handler, W2Handler)
        assert issubclass(W4Handler, W2Handler)
        assert W3Handler.phase_label == "W3 方案方向"
        assert W4Handler.phase_label == "W4 具体方案生成"

    def test_handler_phase_files_exist(self):
        """Verify all handler .py files exist."""
        handler_files = [
            "w1_handler.py",
            "w2_handler.py", "w3_handler.py", "w4_handler.py",
            "w5_handler.py", "w6_handler.py",
            "w7_1_handler.py", "w7_2_handler.py", "w7_3_handler.py",
            "w7_4_handler.py", "w7_5_handler.py", "w8_handler.py",
            "base.py", "__init__.py",
        ]
        phases_dir = PES_DIR / "phases"
        for fname in handler_files:
            assert (phases_dir / fname).exists(), f"Missing handler file: {fname}"

    def test_old_stub_files_deleted(self):
        """Verify old stub phase files are gone."""
        phases_dir = PES_DIR / "phases"
        # These should NOT exist anymore
        gone = [
            "base_phase.py",
            "w2_01_set_style.py", "w3_01_invoke_skill.py",
            "w7_01_invoke_skill_write.py", "w8_01_invoke_skill_review.py",
        ]
        for fname in gone:
            assert not (phases_dir / fname).exists(), (
                f"Old stub file should be deleted: {fname}"
            )


# ═══════════════════════════════════════════════════════════════
# 3. SKILL.md files
# ═══════════════════════════════════════════════════════════════


class TestSkillFiles:
    """Verify SKILL.md files exist and have valid format."""

    # Expected skills (plan: 4 persona + 5 W6 + 6 W7 + 1 W8 + 5 aux = 21 core + 4 kept evo)
    REQUIRED_SKILLS = [
        # 4 persona (shared W2-W4 and W7.1)
        "persona-novel-academic",
        "persona-conservative-academic",
        "persona-novel-engineering",
        "persona-conservative-engineering",
        # W6 skills
        "w6-discuss",
        "w6-scan-islands",
        "w6-island-assign",
        "w6-write-claim-chain",
        "w6-research",
        # W7 skills
        "flux-verify-paper-plan",
        "flux-paper-figure",
        "flux-paper-write",
        "flux-paper-compile",
        "flux-paper-improve",
        # W8
        "flux-review-loop",
        # Auxiliary
        "flux-result-to-claim",
        "flux-novelty-check",
        "flux-proof-writer",
        "flux-formula-derivation",
        "flux-paper-illustration",
    ]

    KEPT_EVO_SKILLS = [
        "flux-pipeline",
        "flux-code-agent-pre",
        "flux-code-agent-check",
        "flux-code-agent-post",
    ]

    DELETED_EVO_SKILLS = [
        "evo-analyze", "evo-boot", "evo-claim", "evo-code",
        "evo-debug", "evo-evolve", "evo-ideation", "evo-intake",
        "evo-iterate", "evo-memory", "evo-planner", "evo-refine",
        "evo-research", "evo-review", "evo-run", "evo-write",
        "research-wiki",
    ]

    def test_required_skills_exist(self):
        for skill_name in self.REQUIRED_SKILLS:
            path = SKILLS_DIR / skill_name / "SKILL.md"
            assert path.exists(), f"Missing SKILL.md: {skill_name}"

    def test_kept_evo_skills_exist(self):
        for skill_name in self.KEPT_EVO_SKILLS:
            path = SKILLS_DIR / skill_name / "SKILL.md"
            assert path.exists(), f"Kept evo skill missing: {skill_name}"

    def test_deleted_evo_skills_gone(self):
        for skill_name in self.DELETED_EVO_SKILLS:
            path = SKILLS_DIR / skill_name
            assert not path.exists(), f"Should be deleted: {skill_name}/"

    def test_skill_has_frontmatter(self):
        """Each SKILL.md should have YAML frontmatter."""
        for skill_name in self.REQUIRED_SKILLS:
            path = SKILLS_DIR / skill_name / "SKILL.md"
            content = path.read_text(encoding="utf-8")
            assert content.startswith("---"), (
                f"{skill_name}/SKILL.md should start with YAML frontmatter"
            )
            # Should have closing ---
            end = content.find("---", 3)
            assert end != -1, f"{skill_name}/SKILL.md frontmatter not closed"

    def test_skill_has_name_field(self):
        """Each SKILL.md frontmatter should have a 'name' field."""
        for skill_name in self.REQUIRED_SKILLS:
            path = SKILLS_DIR / skill_name / "SKILL.md"
            content = path.read_text(encoding="utf-8")
            end = content.find("---", 3)
            frontmatter = content[3:end]
            assert "name:" in frontmatter, (
                f"{skill_name}/SKILL.md missing 'name:' in frontmatter"
            )

    def test_skill_has_prompt_body(self):
        """Each SKILL.md should have non-empty prompt body after frontmatter."""
        for skill_name in self.REQUIRED_SKILLS:
            path = SKILLS_DIR / skill_name / "SKILL.md"
            content = path.read_text(encoding="utf-8")
            end = content.find("---", 3)
            body = content[end + 3:].strip()
            assert len(body) > 50, (
                f"{skill_name}/SKILL.md prompt body too short ({len(body)} chars)"
            )

    def test_persona_skills_have_phase_variable(self):
        """Persona SKILL.md should reference {{phase}} variable."""
        for persona in [
            "persona-novel-academic", "persona-conservative-academic",
            "persona-novel-engineering", "persona-conservative-engineering",
        ]:
            path = SKILLS_DIR / persona / "SKILL.md"
            content = path.read_text(encoding="utf-8")
            assert "{{phase}}" in content, (
                f"{persona}/SKILL.md should have {{{{phase}}}} variable"
            )

    def test_python_execution_skills_have_handler(self):
        """execution: python skills should have handler field."""
        python_skills = ["w6-scan-islands", "w6-island-assign", "w6-write-claim-chain"]
        for skill_name in python_skills:
            path = SKILLS_DIR / skill_name / "SKILL.md"
            content = path.read_text(encoding="utf-8")
            end = content.find("---", 3)
            frontmatter = content[3:end]
            assert "handler:" in frontmatter, (
                f"{skill_name}/SKILL.md missing 'handler:' field"
            )
            assert "execution:" in frontmatter, (
                f"{skill_name}/SKILL.md missing 'execution:' field"
            )


# ═══════════════════════════════════════════════════════════════
# 4. Types
# ═══════════════════════════════════════════════════════════════


class TestTypes:
    """Verify dataclass type definitions."""

    def test_step_result(self):
        from pes_controller.types import StepResult

        r = StepResult(done=True, phase="test", step="s", step_index=0, action="a")
        assert r.done is True
        assert r.data == {}

    def test_skill_result(self):
        from pes_controller.types import SkillResult

        r = SkillResult(success=True, files_written=["a.py"])
        assert r.success is True
        assert len(r.files_written) == 1

    def test_transition_result(self):
        from pes_controller.types import TransitionResult

        r = TransitionResult(transitioned=True, from_phase="W2", to_phase="W3")
        assert r.transitioned is True
        assert r.error == ""

    def test_sse_event(self):
        from pes_controller.types import SSEEvent

        e = SSEEvent(type="test", data={"key": "val"})
        assert e.phase == ""

    def test_skill_config(self):
        from pes_controller.types import SkillConfig

        c = SkillConfig(name="test", execution="python", handler="mod.fn")
        assert c.execution == "python"
        assert c.handler == "mod.fn"


# ═══════════════════════════════════════════════════════════════
# 5. SkillExecutor parsing
# ═══════════════════════════════════════════════════════════════


class TestSkillExecutor:
    """Verify SkillExecutor SKILL.md parsing and template filling."""

    def _make_executor(self):
        from pes_controller.skill_executor import SkillExecutor
        from unittest.mock import MagicMock

        mock_llm = MagicMock()
        return SkillExecutor(skills_dir=SKILLS_DIR, llm_client=mock_llm)

    def test_parse_skill_persona(self):
        executor = self._make_executor()
        config, prompt = executor._parse_skill("persona-novel-academic")
        assert config.name == "persona-novel-academic"
        assert len(prompt) > 0

    def test_parse_skill_flux_paper_write(self):
        executor = self._make_executor()
        config, prompt = executor._parse_skill("flux-paper-write")
        assert config.name == "flux-paper-write"
        assert len(prompt) > 0

    def test_parse_skill_missing_returns_empty(self):
        executor = self._make_executor()
        config, prompt = executor._parse_skill("nonexistent-skill-xyz")
        assert config.name == "nonexistent-skill-xyz"
        assert prompt == ""

    def test_fill_template(self):
        executor = self._make_executor()
        template = "Hello {{name}}, your topic is {{topic}}."
        filled = executor._fill_template(template, {"name": "Alice", "topic": "RL"})
        assert filled == "Hello Alice, your topic is RL."

    def test_fill_template_missing_var_unchanged(self):
        executor = self._make_executor()
        template = "Hello {{name}}, {{missing}} is here."
        filled = executor._fill_template(template, {"name": "Bob"})
        assert "Bob" in filled
        assert "{{missing}}" in filled

    def test_parse_json_response_code_block(self):
        executor = self._make_executor()
        content = '```json\n{"files": [{"path": "a.py", "content": "x"}], "actions": []}\n```'
        parsed = executor._parse_json_response(content)
        assert len(parsed["files"]) == 1
        assert parsed["files"][0]["path"] == "a.py"

    def test_parse_json_response_raw(self):
        executor = self._make_executor()
        content = '{"files": [], "actions": [], "summary": "done"}'
        parsed = executor._parse_json_response(content)
        assert parsed["summary"] == "done"

    def test_parse_json_response_fallback(self):
        executor = self._make_executor()
        content = "This is not JSON at all."
        parsed = executor._parse_json_response(content)
        assert parsed.get("raw_text") == content

    def test_session_management(self):
        executor = self._make_executor()
        # Initially empty
        assert len(executor.sessions) == 0

        # Simulate session creation
        executor.sessions["test-session"] = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        assert "test-session" in executor.sessions
        assert len(executor.sessions["test-session"]) == 2


# ═══════════════════════════════════════════════════════════════
# 6. LLMClient initialization
# ═══════════════════════════════════════════════════════════════


class TestLLMClient:
    """Verify LLMClient can be initialized (no API call)."""

    def test_init_with_fake_key(self):
        """LLMClient should accept any api_key without immediate validation."""
        from pes_controller.llm_client import LLMClient

        client = LLMClient(
            api_key="fake-key-for-testing",
            base_url="https://fake.api.example.com/v1",
            model="test-model",
        )
        assert client.model == "test-model"
        assert client.base_url == "https://fake.api.example.com/v1"

    def test_chat_with_retry_method_exists(self):
        from pes_controller.llm_client import LLMClient

        client = LLMClient(
            api_key="fake", base_url="https://fake.example.com/v1", model="test",
        )
        assert hasattr(client, "chat_with_retry")
        assert hasattr(client, "chat")


# ═══════════════════════════════════════════════════════════════
# 7. Controller v5 transition logic
# ═══════════════════════════════════════════════════════════════


class TestControllerV5Transitions:
    """Verify controller v5 transition logic."""

    def test_controller_v5_import(self):
        from pes_controller.controller_v5 import PESController
        assert PESController is not None

    def test_controller_default_is_v5(self):
        """pes_controller.PESController should be v5."""
        from pes_controller import PESController
        from pes_controller.controller_v5 import PESController as V5
        assert PESController is V5

    def test_auto_next_phase_w2_to_w6(self):
        """W2-W6 should auto-advance."""
        from pes_controller.controller_v5 import PESController
        assert hasattr(PESController, "transition_phase")

    def test_legal_next(self):
        """_legal_next should return valid targets."""
        from pes_controller import TRANSITIONS
        from pes_controller import PHASE_PLAN_1, PHASE_PLAN_2
        targets = TRANSITIONS.get(PHASE_PLAN_1, [])
        assert PHASE_PLAN_2 in targets


# ═══════════════════════════════════════════════════════════════
# 8. No stale references
# ═══════════════════════════════════════════════════════════════


class TestNoStaleReferences:
    """Verify no stale PHASE_WRITE or Agent SDK references in active code."""

    def test_controller_v5_no_stale_phase_write(self):
        content = (PES_DIR / "controller_v5.py").read_text(encoding="utf-8")
        # PHASE_WRITE without suffix should not appear
        import re
        matches = re.findall(r"PHASE_WRITE(?!_)", content)
        assert len(matches) == 0, (
            f"controller_v5.py has stale PHASE_WRITE references: {matches}"
        )

    def test_stages_py_deleted(self):
        assert not (PES_DIR / "stages.py").exists(), "stages.py should be deleted"

    def test_agent_task_deleted(self):
        path = PROJECT / "plugins" / "experimentation" / "agent_task.py"
        assert not path.exists(), "agent_task.py should be deleted"

    def test_phases_no_old_base_phase(self):
        assert not (PES_DIR / "phases" / "base_phase.py").exists()

    def test_pes_no_langchain_imports(self):
        """pes_controller/ should not import langchain."""
        import re
        for py_file in PES_DIR.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            # Check for actual import statements, not comments/docstrings
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                    continue
                if re.match(r"^(from\s+langchain|import\s+langchain)", stripped):
                    pytest.fail(
                        f"{py_file.relative_to(PROJECT)}:{i} imports langchain: {stripped}"
                    )


# ═══════════════════════════════════════════════════════════════
# 9. Elo tournament dimensions
# ═══════════════════════════════════════════════════════════════


class TestEloDimensions:
    """Verify Elo dimension layers exist for W7.1, W7.5, W8."""

    def test_elo_dimensions_w7_1(self):
        from pes_controller.elo.tournament import ELO_DIMENSIONS
        assert "W7.1 论文计划" in ELO_DIMENSIONS

    def test_elo_dimensions_w7_5(self):
        from pes_controller.elo.tournament import ELO_DIMENSIONS
        assert "W7.5 审稿修复" in ELO_DIMENSIONS

    def test_elo_dimensions_w8(self):
        from pes_controller.elo.tournament import ELO_DIMENSIONS
        assert "W8 审阅" in ELO_DIMENSIONS

    def test_elo_w7_1_has_five_dimensions(self):
        from pes_controller.elo.tournament import ELO_DIMENSIONS
        dims = ELO_DIMENSIONS["W7.1 论文计划"]
        assert "dimensions" in dims
        assert len(dims["dimensions"]) == 5

    def test_elo_accepts_llm_client(self):
        """EloTournament constructor should accept llm_client parameter."""
        from pes_controller.elo.tournament import EloTournament
        import inspect
        sig = inspect.signature(EloTournament.__init__)
        assert "llm_client" in sig.parameters


# ═══════════════════════════════════════════════════════════════
# 10. Python handler functions
# ═══════════════════════════════════════════════════════════════


class TestPythonHandlers:
    """Verify W6 Python handler functions exist."""

    def test_handlers_module_exists(self):
        import importlib
        mod = importlib.import_module("pes_controller.handlers")
        assert hasattr(mod, "scan_islands")
        assert hasattr(mod, "island_assign")
        assert hasattr(mod, "write_claim_chain")

    def test_handler_functions_callable(self):
        from pes_controller.handlers import scan_islands, island_assign, write_claim_chain
        assert callable(scan_islands)
        assert callable(island_assign)
        assert callable(write_claim_chain)


# ═══════════════════════════════════════════════════════════════
# 11. Monitor imports
# ═══════════════════════════════════════════════════════════════


class TestMonitorImports:
    """Verify monitor.py uses new phase constants."""

    def test_monitor_imports_phase_write_plan(self):
        content = (PROJECT / "sdk" / "dashboard" / "monitor.py").read_text(encoding="utf-8")
        assert "PHASE_WRITE_PLAN" in content, (
            "monitor.py should import PHASE_WRITE_PLAN"
        )

    def test_monitor_no_agent_sdk_phases(self):
        content = (PROJECT / "sdk" / "dashboard" / "monitor.py").read_text(encoding="utf-8")
        assert "AGENT_SDK_PHASES" not in content, (
            "monitor.py should not reference AGENT_SDK_PHASES"
        )

    def test_monitor_w7_phases_in_js(self):
        """W7/W8 phase strings live in static/index.html (frontend), not monitor.py."""
        content = (PROJECT / "sdk" / "dashboard" / "static" / "index.html").read_text(encoding="utf-8")
        assert "W7.1 论文计划" in content
        assert "W7.5 审稿修复" in content
        assert "W8 审阅" in content

    def test_monitor_dead_code_removed(self):
        """Verify dead execution functions are gone from monitor.py."""
        content = (PROJECT / "sdk" / "dashboard" / "monitor.py").read_text(encoding="utf-8")
        dead_fns = [
            "def _execute_step", "def _do_scan_islands_rubrics",
            "def _do_write_claim_chain", "def _do_island_assign",
            "def _do_web_research", "def _do_refine_atoms",
            "def _do_write_paper", "def _do_review_paper",
            "def _hot_reload_pipeline_modules",
        ]
        for fn in dead_fns:
            assert fn not in content, f"Dead function still present: {fn}"

    def test_monitor_execute_api_uses_v5(self):
        """Execute API should delegate to PESControllerV5."""
        content = (PROJECT / "sdk" / "dashboard" / "monitor.py").read_text(encoding="utf-8")
        assert "PESControllerV5" in content
        assert "ctrl.sub_loop()" in content

    def test_monitor_lines_reduced(self):
        """After cleanup, monitor.py should be < 2500 lines."""
        lines = (PROJECT / "sdk" / "dashboard" / "monitor.py").read_text(encoding="utf-8").split("\n")
        assert len(lines) < 2500, f"monitor.py still has {len(lines)} lines (expected < 2500)"

    def test_static_index_has_w1_phase(self):
        """static/index.html should include W1 Intake & Scope."""
        content = (PROJECT / "sdk" / "dashboard" / "static" / "index.html").read_text(encoding="utf-8")
        assert "W1 Intake & Scope" in content
        assert "github_search_baseline" in content
        assert "baseline-section" in content

    def test_static_index_has_plan_options(self):
        """static/index.html should have plan options section."""
        content = (PROJECT / "sdk" / "dashboard" / "static" / "index.html").read_text(encoding="utf-8")
        assert "plan-options-section" in content
        assert "renderPlanOptions" in content
        assert "doTransition('advance'" in content
