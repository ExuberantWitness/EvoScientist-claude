"""PESController v5 — 轻量调度器。

保留与旧 controller.py 相同的公共 API（MCP tools、常量、状态管理）。
内部用 Phase Handler 注册制替代 4000 行 _build_step() 逻辑。

MCP Tools (7):
  mcp__pes_controller__init        — 初始化工作空间
  mcp__pes_controller__resume      — 崩溃恢复
  mcp__pes_controller__state       — 状态快照
  mcp__pes_controller__pre_loop    — 状态切换准备
  mcp__pes_controller__sub_loop    — 分步返回执行步骤
  mcp__pes_controller__post_loop   — 提交阶段数据写入
  mcp__pes_controller__transition  — Dashboard 控制阶段流转
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from pes_controller.protocol import atomic_read, atomic_write
from pes_controller.types import StepResult, TransitionResult

logger = logging.getLogger(__name__)

# ── Phase constants ──

PHASE_INTAKE   = "W1 Intake & Scope"
PHASE_PLAN_1   = "W2 问题分析"
PHASE_PLAN_2   = "W3 方案方向"
PHASE_IDEATE   = "W4 具体方案生成"
PHASE_CODE     = "W5 代码实现"
PHASE_ANALYZE  = "W6 结果分析"
PHASE_WRITE_PLAN   = "W7.1 论文计划"
PHASE_WRITE_FIGURE = "W7.2 图表生成"
PHASE_WRITE_LATEX  = "W7.3 LaTeX写作"
PHASE_WRITE_COMPILE= "W7.4 编译"
PHASE_WRITE_IMPROVE= "W7.5 审稿修复"
PHASE_REVIEW   = "W8 审阅"
PHASE_TERMINATED = "已终止"

AUTO_ADVANCE_PHASES = frozenset({PHASE_INTAKE, PHASE_PLAN_1, PHASE_PLAN_2, PHASE_IDEATE})

PHASES = [
    PHASE_INTAKE,
    PHASE_PLAN_1, PHASE_PLAN_2, PHASE_IDEATE,
    PHASE_CODE, PHASE_ANALYZE,
    PHASE_WRITE_PLAN, PHASE_WRITE_FIGURE, PHASE_WRITE_LATEX,
    PHASE_WRITE_COMPILE, PHASE_WRITE_IMPROVE,
    PHASE_REVIEW,
]

TRANSITIONS = {
    PHASE_INTAKE:  [PHASE_PLAN_1],
    PHASE_PLAN_1:   [PHASE_PLAN_2],
    PHASE_PLAN_2:   [PHASE_IDEATE],
    PHASE_IDEATE:   [PHASE_CODE],
    PHASE_CODE:     [PHASE_ANALYZE],
    PHASE_ANALYZE:  [PHASE_PLAN_1, PHASE_WRITE_PLAN],
    PHASE_WRITE_PLAN:   [PHASE_WRITE_FIGURE],
    PHASE_WRITE_FIGURE: [PHASE_WRITE_LATEX, PHASE_WRITE_PLAN],
    PHASE_WRITE_LATEX:  [PHASE_WRITE_COMPILE, PHASE_WRITE_PLAN],
    PHASE_WRITE_COMPILE:[PHASE_WRITE_IMPROVE, PHASE_WRITE_PLAN],
    PHASE_WRITE_IMPROVE:[PHASE_REVIEW, PHASE_WRITE_PLAN],
    PHASE_REVIEW:   [PHASE_WRITE_PLAN, PHASE_CODE, PHASE_PLAN_1, PHASE_TERMINATED],
}

# Phase migration map (old → new)
_PHASE_MIGRATION = {
    "方案提出": "W2 问题分析",
    "文献调研": "W2 问题分析",
    "ELO筛选": "W4 具体方案生成",
    "实验执行": "W5 代码实现",
    "结果分析": "W6 结果分析",
    "论文写作": "W7.1 论文计划",
    "论文审阅": "W8 审阅",
}

_PHASE_ALIASES = {
    "W7 论文写作": PHASE_WRITE_PLAN,
    "W6 Write": PHASE_WRITE_PLAN,
    "W7 Write": PHASE_WRITE_PLAN,
    "W7 Review": PHASE_REVIEW,
}

# CHAIN_STEPS is now defined in each Phase Handler's chain_steps class variable.
# This dict is kept for backward compat and is populated from handlers at runtime.
CHAIN_STEPS: dict[str, list[str]] = {}

# PRODUCT_SPECS (from old controller.py — unchanged)
PRODUCT_SPECS = {
    PHASE_INTAKE: {"required": ["confirmed_baselines"], "deliverables": ["confirmed_baselines.json"]},
    PHASE_PLAN_1: {"required": ["具体难点", "因果分析", "baseline局限性"], "deliverables": []},
    PHASE_PLAN_2: {"required": ["方向描述", "针对难点", "技术路径概要", "与baseline区分"], "deliverables": []},
    PHASE_IDEATE: {"required": ["伪代码", "架构改动", "损失函数签名", "计算开销"], "deliverables": []},
    PHASE_WRITE_PLAN: {"required": ["NARRATIVE_REPORT.md", "PAPER_PLAN.md"], "deliverables": ["NARRATIVE_REPORT.md", "PAPER_PLAN.md"]},
    PHASE_WRITE_FIGURE: {"required": ["figures/", "latex_includes.tex"], "deliverables": ["figures/", "figures/latex_includes.tex"]},
    PHASE_WRITE_LATEX: {"required": ["paper/main.tex", "paper/sections/"], "deliverables": ["paper/main.tex", "paper/references.bib"]},
    PHASE_WRITE_COMPILE: {"required": ["paper/main.pdf > 100KB"], "deliverables": ["paper/main.pdf"]},
    PHASE_WRITE_IMPROVE: {"required": ["PAPER_IMPROVEMENT_LOG.md"], "deliverables": ["paper/main.pdf", "PAPER_IMPROVEMENT_LOG.md"]},
    PHASE_REVIEW: {"required": ["AUTO_REVIEW.md", "REVIEW_STATE.json"], "deliverables": ["AUTO_REVIEW.md", "REVIEW_STATE.json"]},
}

FOUR_PERSONA_AGENTS = [
    "novel-academic-agent", "conservative-academic-agent",
    "novel-engineering-agent", "conservative-engineering-agent",
]

AGENT_ROLES = {
    PHASE_PLAN_1: FOUR_PERSONA_AGENTS,
    PHASE_PLAN_2: FOUR_PERSONA_AGENTS,
    PHASE_IDEATE: FOUR_PERSONA_AGENTS,
}


# ── PESController v5 ──

class PESController:
    """轻量调度器 — 所有 step 执行委托给 Phase Handler。"""

    def __init__(self, workspace_dir: str | Path, session_id: str = ""):
        self.workspace = Path(workspace_dir)
        if session_id and not (self.workspace / "PIPELINE_STATE.json").exists():
            self.session_dir = self.workspace / "sessions" / session_id
        else:
            self.session_dir = self.workspace
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.index_dir = self.session_dir / "_index"
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.session_dir / "PIPELINE_STATE.json"

        # Shared service instances (created lazily)
        self._llm_client = None
        self._tavily_client = None
        self._executor = None

        # Backward compat: claim chain / grid / rubric / fitness
        from claim_chain.chain import ClaimChain, migrate_schema
        migrate_schema(self.index_dir / 'cc.db')
        self.cc = ClaimChain(self.index_dir / 'cc.db')
        from claim_chain.cell_grid import CellGrid
        from pes_controller.rubric.scheduler import RubricScheduler
        from claim_chain.island_manager import IslandManager
        from sdk.status.fitness import FitnessTracker
        self.grid = CellGrid(self.session_dir / "evolve_archive")
        self.rubric = RubricScheduler(self.cc)
        self.islands = IslandManager(self.session_dir / "evolve_archive")
        self.fitness = FitnessTracker(self.session_dir / "_index")

        # Populate CHAIN_STEPS from handlers
        self._populate_chain_steps()

    # ── Shared service instances (lazy init) ──

    def _get_llm_client(self):
        if self._llm_client is None:
            from pes_controller.llm_client import LLMClient
            self._llm_client = LLMClient(
                api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
                base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
                model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
            )
        return self._llm_client

    def _get_tavily_client(self):
        if self._tavily_client is None:
            from pes_controller.tavily_client import TavilyClient
            self._tavily_client = TavilyClient(
                api_key=os.environ.get("TAVILY_API_KEY", ""),
            )
        return self._tavily_client

    def _get_executor(self):
        if self._executor is None:
            from pes_controller.skill_executor import SkillExecutor
            skills_dir = Path(__file__).parent.parent / "skills"
            self._executor = SkillExecutor(
                skills_dir=skills_dir,
                llm_client=self._get_llm_client(),
                tavily_client=self._get_tavily_client(),
            )
        return self._executor

    def _populate_chain_steps(self):
        """从 Handler 注册表填充 CHAIN_STEPS（向后兼容）。"""
        from pes_controller.phases import get_all_handlers
        for phase, handler_cls in get_all_handlers().items():
            if handler_cls.chain_steps:
                CHAIN_STEPS[phase] = handler_cls.chain_steps

    # ═══════════════════════════════════════════════════════════════
    # 状态读写
    # ═══════════════════════════════════════════════════════════════

    def _read_state(self) -> dict:
        _default = {
            "protocol_version": 1,
            "phase": PHASE_INTAKE,
            "iteration": 0,
            "sub_loop_step": 0,
            "status": "not_initialized",
            "timestamp": None,
            "session_id": None,
            "config": {},
        }
        if not self.state_path.exists():
            return _default
        try:
            state = atomic_read(self.state_path)
        except (json.JSONDecodeError, ValueError, OSError):
            backup = self.state_path.with_suffix(".json.corrupted")
            self.state_path.rename(backup)
            atomic_write(self.state_path, _default)
            return _default
        if "phase" not in state:
            state["phase"] = PHASE_INTAKE
        phase = state.get("phase", PHASE_INTAKE)
        if phase in _PHASE_MIGRATION:
            state["phase"] = _PHASE_MIGRATION[phase]
            atomic_write(self.state_path, state)
        phase = state.get("phase", PHASE_PLAN_1)
        if phase in _PHASE_ALIASES:
            state["phase"] = _PHASE_ALIASES[phase]
            atomic_write(self.state_path, state)
        return state

    def _write_state(self, state: dict):
        state["timestamp"] = time.time()
        atomic_write(self.state_path, state)

    def _legal_next(self, phase: str) -> list[str]:
        return TRANSITIONS.get(phase, [])

    # ═══════════════════════════════════════════════════════════════
    # MCP Tool: init
    # ═══════════════════════════════════════════════════════════════

    def init(self, research_topic: str, part2_dimensions: list[dict] | None = None) -> dict:
        for d in ["evolve_archive", "artifacts", "Algorithms", "Bottlenecks",
                  "Islands", "iterations", "_index", "_pipeline", "_memory"]:
            (self.session_dir / d).mkdir(parents=True, exist_ok=True)

        self.cc.get_graph_summary()
        dims = part2_dimensions or []
        self.grid.init(dims)

        state = {
            "phase": PHASE_INTAKE,
            "iteration": 0,
            "sub_loop_step": 0,
            "status": "in_progress",
            "timestamp": time.time(),
            "session_id": None,
            "research_topic": research_topic,
            "config": {},
        }
        self._write_state(state)
        return {
            "workspace_ready": True,
            "phase": PHASE_INTAKE,
            "iteration": 0,
            "needs_session": True,
            "workspace_dir": str(self.session_dir),
        }

    # ═══════════════════════════════════════════════════════════════
    # MCP Tool: sub_loop — 轻量调度
    # ═══════════════════════════════════════════════════════════════

    def sub_loop(self) -> dict:
        """分步返回：每次调用返回当前阶段的下一个执行步骤。"""
        state = self._read_state()

        if state.get("status") == "awaiting_decision":
            return {
                "done": False, "phase": state["phase"],
                "action": "wait_for_decision",
                "message": "等待用户在 Dashboard 做决策...",
            }

        if state.get("status") == "awaiting_user_code":
            return {
                "done": False, "phase": state["phase"],
                "action": "wait_for_user_code",
                "message": "等待用户在 Claude Code 中完成代码实现...",
            }

        phase = state["phase"]
        step_idx = state.get("sub_loop_step", 0)
        chain = CHAIN_STEPS.get(phase, [])

        if step_idx >= len(chain):
            return {"done": True, "phase": phase}

        step_name = chain[step_idx]
        state["sub_loop_step"] = step_idx + 1
        self._write_state(state)

        # 委托给 Phase Handler
        from pes_controller.phases import get_handler
        handler_cls = get_handler(phase)
        if handler_cls is None:
            return {"done": True, "phase": phase, "step": step_name,
                    "action": "error", "message": f"No handler for {phase}"}

        handler = handler_cls(
            executor=self._get_executor(),
            llm_client=self._get_llm_client(),
            tavily_client=self._get_tavily_client(),
            state={**state, "workspace_dir": str(self.workspace)},
        )
        result = handler.build_step(step_name)

        # 转换 StepResult → dict（向后兼容）
        return {
            "done": result.done,
            "phase": result.phase,
            "step": result.step,
            "step_index": result.step_index,
            "action": result.action,
            **result.data,
        }

    # ═══════════════════════════════════════════════════════════════
    # MCP Tool: transition
    # ═══════════════════════════════════════════════════════════════

    def transition_phase(self, action: str, target_phase: str | None = None,
                         feedback: str = "", selected_plan: str | None = None) -> dict:
        """Dashboard 调用的阶段流转。"""
        state = self._read_state()
        phase = state["phase"]

        if action == "satisfied":
            next_phase = self._auto_next_phase(phase, state)
            if next_phase is None:
                return {"error": f"阶段 '{phase}' 需要显式选择目标（advance action）",
                        "valid_targets": TRANSITIONS.get(phase, [])}
            state["phase"] = next_phase
            state["sub_loop_step"] = 0
            state["status"] = "in_progress"
            if phase == PHASE_ANALYZE:
                state["iteration"] = state.get("iteration", 0) + 1
            self._write_state(state)
            self._post_to_dashboard(state.get("session_id", ""), "phase_changed",
                                    {"from": phase, "to": next_phase})
            return {"transitioned": True, "from": phase, "to": next_phase}

        elif action == "advance":
            if target_phase is None:
                return {"error": "advance 需要 target_phase",
                        "valid_targets": TRANSITIONS.get(phase, [])}
            valid = TRANSITIONS.get(phase, [])
            if target_phase not in valid:
                return {"error": f"不允许从 '{phase}' 转到 '{target_phase}'",
                        "valid_targets": valid}
            if selected_plan and phase == PHASE_WRITE_PLAN:
                self._activate_selected_plan(state, selected_plan)
            if target_phase == PHASE_WRITE_PLAN and phase != PHASE_WRITE_PLAN:
                self._archive_current_products(state)
            state["phase"] = target_phase
            state["sub_loop_step"] = 0
            state["status"] = "in_progress"
            if feedback:
                state["iteration_feedback"] = feedback
            self._write_state(state)
            self._post_to_dashboard(state.get("session_id", ""), "phase_changed",
                                    {"from": phase, "to": target_phase})
            return {"transitioned": True, "from": phase, "to": target_phase}

        elif action == "redo":
            state["sub_loop_step"] = 0
            state["status"] = "in_progress"
            if feedback:
                state["iteration_feedback"] = feedback
            self._write_state(state)
            return {"transitioned": False, "phase": phase,
                    "message": f"重做阶段 '{phase}'"}

        elif action == "redo_with_review":
            state["sub_loop_step"] = 0
            state["status"] = "in_progress"
            state["needs_regeneration"] = True
            if feedback:
                state["iteration_feedback"] = feedback
            self._write_state(state)
            return {"transitioned": False, "phase": phase,
                    "message": f"带审稿意见重做 '{phase}'"}

        elif action == "jump_to_plan":
            state["phase"] = PHASE_PLAN_1
            state["sub_loop_step"] = 0
            state["status"] = "in_progress"
            if feedback:
                state["iteration_feedback"] = feedback
            self._write_state(state)
            return {"transitioned": True, "from": phase, "to": PHASE_PLAN_1}

        elif action == "terminate":
            state["phase"] = PHASE_TERMINATED
            state["status"] = "terminated"
            self._write_state(state)
            return {"transitioned": True, "to": PHASE_TERMINATED}

        return {"error": f"Unknown action: {action}"}

    def _auto_next_phase(self, phase: str, state: dict) -> str | None:
        if phase == PHASE_INTAKE:   return PHASE_PLAN_1
        if phase == PHASE_PLAN_1:   return PHASE_PLAN_2
        elif phase == PHASE_PLAN_2: return PHASE_IDEATE
        elif phase == PHASE_IDEATE: return PHASE_CODE
        elif phase == PHASE_CODE:   return PHASE_ANALYZE
        elif phase == PHASE_ANALYZE:
            target = self._read_success_target()
            if target is not None:
                fs = self.fitness.get_stats()
                best = fs.get("global", {}).get("max_score", 0)
                if best >= target:
                    return PHASE_WRITE_PLAN
            return PHASE_PLAN_1
        # W7.1-W7.5, W8: 返回 None 要求人工选择
        return None

    def _read_success_target(self):
        """读取 success_criteria.md 中的目标分数。"""
        sc_path = self.session_dir / "success_criteria.md"
        if not sc_path.exists():
            return None
        try:
            text = sc_path.read_text(encoding="utf-8")
            for line in text.split("\n"):
                if "target_score" in line.lower():
                    parts = line.split(":")
                    if len(parts) >= 2:
                        return float(parts[-1].strip())
        except Exception:
            pass
        return None

    # ── W7.1 helpers ──

    def _activate_selected_plan(self, state, selected_plan: str):
        PLAN_DISPLAY_MAP = {
            "A": "novel-academic", "B": "conservative-academic",
            "C": "novel-engineering", "D": "conservative-engineering",
        }
        persona_name = PLAN_DISPLAY_MAP.get(selected_plan.upper(), selected_plan)
        ws = self.session_dir
        plan_file = ws / "paper_plans" / f"plan_{persona_name}.json"
        if plan_file.exists():
            data = json.loads(plan_file.read_text(encoding="utf-8"))
            llm_raw = data.get("llm_response", "")
            try:
                plan_data = json.loads(llm_raw)
            except (json.JSONDecodeError, TypeError):
                plan_data = {"method_sketch": llm_raw, "hypothesis": ""}
            (ws / "PAPER_PLAN.md").write_text(
                plan_data.get("method_sketch", llm_raw), encoding="utf-8")
            (ws / "NARRATIVE_REPORT.md").write_text(
                f"# 研究叙事报告\n\n## 核心发现\n{plan_data.get('hypothesis', '')}",
                encoding="utf-8")

    def _archive_current_products(self, state):
        import shutil
        ws = self.session_dir
        iteration = state.get("paper_iteration", 0)
        archive_dir = ws / "paper_plans" / f"archive_iter_{iteration}"
        archive_dir.mkdir(parents=True, exist_ok=True)
        for f in ["PAPER_PLAN.md", "NARRATIVE_REPORT.md"]:
            src = ws / f
            if src.exists():
                shutil.copy2(str(src), str(archive_dir / f))

    # ═══════════════════════════════════════════════════════════════
    # MCP Tool: state / resume / pre_loop / post_loop
    # ═══════════════════════════════════════════════════════════════

    def state(self) -> dict:
        return self._read_state()

    def resume(self) -> dict:
        state = self._read_state()
        state["status"] = "in_progress"
        self._write_state(state)
        return {"resumed": True, "phase": state["phase"],
                "sub_loop_step": state.get("sub_loop_step", 0)}

    def pre_loop(self, phase: str | None = None) -> dict:
        state = self._read_state()
        if phase:
            state["phase"] = phase
            state["sub_loop_step"] = 0
            state["status"] = "in_progress"
            self._write_state(state)
        return {"phase": state["phase"], "sub_loop_step": state.get("sub_loop_step", 0)}

    def post_loop(self, phase_data: dict) -> dict:
        state = self._read_state()
        state.update(phase_data)
        self._write_state(state)
        return {"posted": True}

    # ═══════════════════════════════════════════════════════════════
    # SSE 事件推送
    # ═══════════════════════════════════════════════════════════════

    def _post_to_dashboard(self, session_id: str, event_type: str, data: dict):
        try:
            import urllib.request
            payload = json.dumps({
                "session_id": session_id,
                "type": event_type,
                "data": data,
            }).encode()
            req = urllib.request.Request(
                "http://localhost:8420/api/internal/events",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass


# ── Module-level helpers ──

_controller: PESController | None = None


def get_controller(workspace_dir: str = "", session_id: str = "") -> PESController:
    global _controller
    if _controller is None and workspace_dir:
        _controller = PESController(workspace_dir, session_id=session_id)
    elif _controller is None:
        _controller = PESController(os.getcwd(), session_id=session_id)
    return _controller
