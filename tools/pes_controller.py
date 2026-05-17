"""PESController: 单一状态机 + 五步渐进式发现管线 + MCP Server。

MCP Tools (7):
  mcp__pes_controller__init        — 初始化工作空间
  mcp__pes_controller__resume      — 崩溃恢复
  mcp__pes_controller__state       — 状态快照
  mcp__pes_controller__pre_loop    — 状态切换准备 (基础状态管理)
  mcp__pes_controller__sub_loop    — 分步返回执行步骤
  mcp__pes_controller__post_loop   — 提交阶段数据写入（纯数据，不管流转）
  mcp__pes_controller__transition  — Dashboard 控制阶段流转

用法:
  python tools/pes_controller.py              # 启动 MCP server
  python tools/pes_controller.py --test        # 打印已注册 tools
"""

import json
import os
import sys
import time
from pathlib import Path

# Ensure tools/ is importable
TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from claim_chain import ClaimChain
from cell_grid import CellGrid
from rubric_scheduler import RubricScheduler
from island_manager import IslandManager
from fitness_tracker import FitnessTracker


# ── Phase constants ──

PHASE_PLAN     = "W2 Plan"
PHASE_RESEARCH = "W3 Research"
PHASE_IDEATE   = "W3.5 Ideate"
PHASE_CODE     = "W4 Code"
PHASE_ANALYZE  = "W5 Analyze"
PHASE_WRITE    = "W6 Write"
PHASE_REVIEW   = "W7 Review"
PHASE_TERMINATED = "已终止"

PHASES = [PHASE_PLAN, PHASE_RESEARCH, PHASE_IDEATE, PHASE_CODE,
          PHASE_ANALYZE, PHASE_WRITE, PHASE_REVIEW]

# Phases that require Agent SDK subprocess (W6 Write, W7 Review)
# W4 Code 改用 Plan-driven 模式 (generate_code_plan + wait_user_code)
AGENT_SDK_PHASES = frozenset({PHASE_WRITE, PHASE_REVIEW})

# Phase transitions (from → [legal next])
TRANSITIONS = {
    PHASE_PLAN:     [PHASE_RESEARCH],
    PHASE_RESEARCH: [PHASE_IDEATE],
    PHASE_IDEATE:   [PHASE_CODE],
    PHASE_CODE:     [PHASE_ANALYZE],
    PHASE_ANALYZE:  [PHASE_PLAN, PHASE_WRITE],
    PHASE_WRITE:    [PHASE_REVIEW, PHASE_TERMINATED],
    PHASE_REVIEW:   [PHASE_WRITE],
}

# Execution chain steps per phase (五条执行链路)
# 链路1: W2 Plan — 看CC/EM → 多Agent → ELO → EM
# 链路2: W3 Research — 看CC/EM → 多Agent → ELO → EM → 文献调研 → 写CC
# 链路3: W3.5 Ideate — 看CC/EM → 多Agent → ELO → EM
# 链路4: W4 Code — 看CC/EM → 单Agent代码实现
# 链路5: W5 Analyze — 看CC → Island/Rubric → Judge+EM → 写CC → Island分配
CHAIN_STEPS = {
    PHASE_PLAN: [
        "run_step_pipeline", "multi_agent_discuss",
        "elo_tournament", "evolution_memory",
        "write_claim_chain",      # 将 proposals 写入 CC, 供后续阶段读取
    ],
    PHASE_RESEARCH: [
        "run_step_pipeline", "multi_agent_discuss",
        "elo_tournament", "evolution_memory",
        "invoke_skill_research", "write_claim_chain",
    ],
    PHASE_IDEATE: [
        "run_step_pipeline", "multi_agent_discuss",
        "elo_tournament", "evolution_memory",
        "write_claim_chain",      # 将 ELO 排名结果写入 CC, 供 W4 Code 读取
    ],
    PHASE_CODE: [
        "run_step_pipeline",      # 加载 CC/EM 上下文, 生成 proposals
        "write_claim_chain",      # 将 proposals 写入 CC (确保 generate_code_plan 可读取)
        "generate_code_plan",     # 生成 implementation_plan.md
        "wait_user_code",         # 等待用户通过 /evo-code-agent-post 完成
    ],
    PHASE_ANALYZE: [
        "run_step_pipeline", "scan_islands_rubrics",
        "multi_agent_discuss", "evolution_memory",
        "write_claim_chain", "island_assign",
    ],
    PHASE_WRITE:   ["invoke_skill_write"],
    PHASE_REVIEW:  ["invoke_skill_review"],
}

# Agent roles per phase
AGENT_ROLES = {
    PHASE_PLAN:     ["planner", "researcher", "analyst"],
    PHASE_RESEARCH: ["researcher", "planner", "analyst"],
    PHASE_IDEATE:   ["planner", "researcher", "analyst"],
    PHASE_ANALYZE:  ["analyst", "planner", "researcher"],
    PHASE_WRITE:    ["writer"],
    PHASE_REVIEW:   ["writer"],
}


# Phase name migration map (old Chinese → new W-based)
_PHASE_MIGRATION = {
    "方案提出": "W2 Plan",
    "文献调研": "W3 Research",
    "ELO筛选": "W3.5 Ideate",
    "实验执行": "W4 Code",
    "结果分析": "W5 Analyze",
    "论文写作": "W6 Write",
    "论文审阅": "W7 Review",
}


class PESController:
    """单一状态机 + 五步渐进式发现管线。"""

    def __init__(self, workspace_dir: str | Path, session_id: str = ""):
        self.workspace = Path(workspace_dir)
        # session_dir: 所有产物隔离到 sessions/{sid}/ 下
        # 如果 workspace_dir 已经是 session 目录 (有 PIPELINE_STATE.json 或 vault/), 不嵌套
        _is_session_dir = (
            (self.workspace / "PIPELINE_STATE.json").exists() or
            (self.workspace / "vault").is_dir()
        )
        if session_id and not _is_session_dir:
            self.session_dir = self.workspace / "sessions" / session_id
        else:
            self.session_dir = self.workspace
        self.session_dir.mkdir(parents=True, exist_ok=True)
        # 所有数据统一在 vault/ 下
        self.vault_dir = self.session_dir / "vault"
        self.index_dir = self.vault_dir / "_index"
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.session_dir / "PIPELINE_STATE.json"
        self.cc = ClaimChain(self.session_dir, base_dir=self.index_dir)
        self.grid = CellGrid(self.vault_dir / "evolve_archive")
        self.rubric = RubricScheduler(self.cc)
        self.islands = IslandManager(self.vault_dir / "evolve_archive")
        self.fitness = FitnessTracker(self.vault_dir / "_index")

    # ═══════════════════════════════════════════════════════════════
    # 状态读写
    # ═══════════════════════════════════════════════════════════════

    def _read_state(self) -> dict:
        """原子读 + 旧中文阶段名自动迁移。损坏文件自动回退到默认状态。"""
        _default = {
            "protocol_version": 1,
            "phase": PHASE_PLAN,
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
            # 损坏的 state file — 重命名为备份并用默认值恢复
            backup = self.state_path.with_suffix(".json.corrupted")
            self.state_path.rename(backup)
            atomic_write(self.state_path, _default)
            return _default
        if "phase" not in state:
            state["phase"] = PHASE_PLAN
        phase = state.get("phase", PHASE_PLAN)
        if phase in _PHASE_MIGRATION:
            state["phase"] = _PHASE_MIGRATION[phase]
            atomic_write(self.state_path, state)
        return state

    def _write_state(self, state: dict):
        """Dashboard 侧写入（使用 pipeline_protocol 原子写）。"""
        state["timestamp"] = time.time()
        atomic_write(self.state_path, state)

    def _legal_next(self, phase: str) -> list[str]:
        return TRANSITIONS.get(phase, [])

    # ═══════════════════════════════════════════════════════════════
    # MCP Tool: init
    # ═══════════════════════════════════════════════════════════════

    def init(self, research_topic: str, part2_dimensions: list[dict] | None = None) -> dict:
        """初始化工作空间。创建 vault/ 下完整目录树。"""
        for d in ["evolve_archive", "artifacts",
                  "Algorithms", "Bottlenecks", "Islands", "Iterations",
                  "_index", "_pipeline", "_memory"]:
            (self.vault_dir / d).mkdir(parents=True, exist_ok=True)

        # Claim Chain — create empty JSONL files so vault structure is visible
        self.cc.get_graph_summary()
        # touch empty files if they don't exist
        if not self.cc.atoms_path.exists():
            self.cc.atoms_path.write_text("", encoding="utf-8")
        if not self.cc.relations_path.exists():
            self.cc.relations_path.write_text("", encoding="utf-8")

        # Cell Grid: Part1(内置) + Part2(用户定义)
        dims = part2_dimensions or []
        self.grid.init(dims)

        # PIPELINE_STATE.json
        state = {
            "phase": PHASE_PLAN,
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
            "phase": PHASE_PLAN,
            "iteration": 0,
            "needs_session": True,
            "needs_intake": True,
            "message": "工作空间已初始化。下一步：1) 调 /evo-intake 2) 调 evo_create_session 创建 agent session",
        }

    # ═══════════════════════════════════════════════════════════════
    # MCP Tool: resume
    # ═══════════════════════════════════════════════════════════════

    def resume(self) -> dict:
        """崩溃恢复。"""
        state = self._read_state()
        if state.get("status") == "not_initialized":
            return {"recovered": False, "error": "workspace_not_initialized",
                    "suggestion": "Call init first."}

        # 验证文件完整性
        cc_ok = (self.workspace / "claim_chain" / "atoms.jsonl").exists()
        grid_ok = (self.workspace / "evolve_archive" / "evolve_state.json").exists()

        if not cc_ok and not grid_ok:
            return {"recovered": False, "error": "state_files_missing",
                    "suggestion": "Workspace may be corrupted."}

        return {
            "recovered": True,
            "current_phase": state["phase"],
            "iteration": state["iteration"],
            "sub_loop_step": state.get("sub_loop_step", 0),
            "last_action_at": state.get("timestamp"),
        }

    # ═══════════════════════════════════════════════════════════════
    # MCP Tool: state
    # ═══════════════════════════════════════════════════════════════

    def get_state(self) -> dict:
        """只读状态快照。"""
        state = self._read_state()
        cc_summary = self.cc.get_graph_summary()
        grid_data = self.grid.get_heatmap_data()
        fitness_stats = self.fitness.get_stats()

        milestones = self.grid.detect_milestones()

        return {
            "phase": state["phase"],
            "iteration": state["iteration"],
            "sub_loop_step": state.get("sub_loop_step", 0),
            "status": state.get("status", "unknown"),
            "cc_summary": cc_summary,
            "grid_coverage": grid_data.get("coverage", {}),
            "fitness": fitness_stats,
            "recent_milestones": milestones[:5],
            "legal_next": self._legal_next(state["phase"]),
        }

    # ═══════════════════════════════════════════════════════════════
    # MCP Tool: pre_loop
    # ═══════════════════════════════════════════════════════════════

    def pre_loop(self) -> dict:
        """状态切换准备。只做基础状态管理，不注入 CC 数据。"""
        state = self._read_state()
        phase = state["phase"]

        # Fitness 趋势
        ft = self.fitness.get_trend()
        fs = self.fitness.get_stats()

        # Evolution Memory 概要
        em = self._load_evolution_memory_summary()

        return {
            "current_phase": phase,
            "iteration": state["iteration"],
            "phase_description": self._phase_description(phase),
            "fitness": {
                "trend": ft["direction"],
                "best_ever": fs.get("global", {}).get("max_score", 0),
                "current_streak": self._compute_streak(),
            },
            "evolution_memory_summary": em,
            "legal_next_phases": self._legal_next(phase),
            "user_prompt": self._generate_user_prompt(state),
        }

    def _phase_description(self, phase: str) -> str:
        descriptions = {
            PHASE_PLAN: "看CC/EM → 多Agent讨论制定实验计划 → ELO排序 → Evolution Memory",
            PHASE_RESEARCH: "看CC/EM → 多Agent文献调研 → ELO排序 → Evolution Memory → 真实文献写入CC",
            PHASE_IDEATE: "看CC/EM → 多Agent方案构思 → ELO锦标赛筛选 → Evolution Memory",
            PHASE_CODE: "看CC/EM → 单Agent代码实现",
            PHASE_ANALYZE: "看CC → Island/Rubric扫描 → 多Agent Judge+EM → 真实结果写入CC → Island分配",
            PHASE_WRITE: "撰写论文报告，汇总所有实验发现",
            PHASE_REVIEW: "外部LLM审阅论文，不满意则回到Write重写",
        }
        return descriptions.get(phase, "")

    def _compute_streak(self) -> int:
        """计算连续改进次数。"""
        history = self.fitness.get_history(limit=20)
        scores = [e["score"] for e in history]
        if len(scores) < 2:
            return 0
        streak = 0
        for i in range(len(scores) - 1, 0, -1):
            if scores[i] > scores[i-1]:
                streak += 1
            else:
                break
        return streak

    def _load_evolution_memory_summary(self) -> dict:
        """加载 Evolution Memory 概要（读取新格式 directions.jsonl + strategies.jsonl）。"""
        directions_path = self.workspace / "memory" / "ideation" / "directions.jsonl"
        strategies_path = self.workspace / "memory" / "experiment" / "strategies.jsonl"

        promising = []
        failures = []
        strategies = []

        for path, collector in [(directions_path, "directions"), (strategies_path, "strategies")]:
            if not path.exists():
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        status = entry.get("status", "")
                        if collector == "directions":
                            if status == "PROMISING":
                                promising.append(entry)
                            elif status == "FAILED":
                                failures.append(entry)
                        elif collector == "strategies":
                            strategies.append(entry)
            except Exception:
                pass

        # Sort by score descending, take top/bottom
        promising.sort(key=lambda e: e.get("score", 0), reverse=True)
        failures.sort(key=lambda e: e.get("score", 0), reverse=True)
        strategies.sort(key=lambda e: e.get("score", 0), reverse=True)

        return {
            "last_ide_session": promising[0].get("direction", "")[:300] if promising else None,
            "top_directions": [e.get("direction", "")[:120] for e in promising[:3]],
            "prior_failures": [e.get("direction", "")[:120] for e in failures[-5:]],
            "best_strategies": [e.get("strategy", e.get("direction", ""))[:120] for e in strategies[:3]],
            "promising_count": len(promising),
            "failure_count": len(failures),
            "strategy_count": len(strategies),
        }

    def _generate_user_prompt(self, state: dict) -> str:
        phase = state["phase"]
        iteration = state["iteration"]
        fs = self.fitness.get_stats()
        best = fs.get("global", {}).get("max_score", 0)
        ft = self.fitness.get_trend()

        # Include Evolution Memory context
        em = self._load_evolution_memory_summary()
        em_parts = []
        if em.get("top_directions"):
            em_parts.append(f"Top directions: {'; '.join(em['top_directions'][:3])}")
        if em.get("prior_failures"):
            em_parts.append(f"Prior failures: {'; '.join(em['prior_failures'][:3])}")
        if em.get("best_strategies"):
            em_parts.append(f"Best strategies: {'; '.join(em['best_strategies'][:3])}")
        em_suffix = "\n  EM: " + "\n  EM: ".join(em_parts) if em_parts else ""

        prompts = {
            PHASE_PLAN: f"第{iteration+1}轮·W2 Plan。当前最佳{best:.1f}，趋势{ft['direction']}。制定实验方案。{em_suffix}",
            PHASE_RESEARCH: f"第{iteration+1}轮·W3 Research。调研文献收集真实论文数据。{em_suffix}",
            PHASE_IDEATE: f"第{iteration+1}轮·W3.5 Ideate。ELO锦标赛排序候选方案。{em_suffix}",
            PHASE_CODE: f"第{iteration+1}轮·W4 Code。单Agent代码实现。{em_suffix}",
            PHASE_ANALYZE: f"第{iteration+1}轮·W5 Analyze。当前最佳{best:.1f}。Judge+Rubrics评分。{em_suffix}",
            PHASE_WRITE: f"W6 Write。基于实验结果撰写论文报告。{em_suffix}",
            PHASE_REVIEW: f"W7 Review。外部审阅评估论文质量。{em_suffix}",
        }
        return prompts.get(phase, f"当前阶段: {phase}")

    # ═══════════════════════════════════════════════════════════════
    # MCP Tool: sub_loop
    # ═══════════════════════════════════════════════════════════════

    def sub_loop(self) -> dict:
        """分步返回：每次调用返回当前阶段的下一个执行步骤。"""
        state = self._read_state()

        # 等待 Dashboard 决策时，LLM 不推进
        if state.get("status") == "awaiting_decision":
            return {
                "done": False,
                "phase": state["phase"],
                "action": "wait_for_decision",
                "message": "等待用户在 Dashboard (localhost:8420/pipeline) 做决策...",
            }

        # W4 Code: 等待用户在 Claude Code 中完成实现
        if state.get("status") == "awaiting_user_code":
            return self._wait_user_code(state, state["phase"])

        phase = state["phase"]
        step_idx = state.get("sub_loop_step", 0)
        chain = CHAIN_STEPS.get(phase, [])

        if step_idx >= len(chain):
            return {"done": True, "phase": phase}

        step_name = chain[step_idx]

        # 推进步骤计数器 (下一次 sub_loop 调用返回下一步)
        state["sub_loop_step"] = step_idx + 1
        self._write_state(state)

        return self._build_step(step_name, phase, state)

    def _build_step(self, step_name: str, phase: str, state: dict) -> dict:
        """根据步骤名构造返回的 action JSON。"""
        agents = AGENT_ROLES.get(phase, ["planner", "researcher", "analyst"])

        if step_name == "run_step_pipeline":
            # Execute 5 STEP pipeline: CLI → Indexing → Decomposer → Recomposer → Evaluator
            primary_agent = agents[0] if agents else "planner"
            cli_result = self.step_cli("summary")
            indexing_result = self.step_indexing(phase, primary_agent)
            decomposer_result = self.step_decomposer()
            recomposer_result = self.step_recomposer(decomposer_result, phase)
            evaluator_results = []
            filtered_proposals = []
            rejected_count = 0
            for proposal in recomposer_result:
                eval_result = self.step_evaluator(proposal)
                evaluator_results.append(eval_result)
                if eval_result.get("verdict") != "pseudo":
                    filtered_proposals.append(proposal)
                else:
                    rejected_count += 1

            context_bundle = {
                "cli_summary": cli_result,
                "indexing": indexing_result,
                "primitives": decomposer_result.get("primitives", []),
                "relation_patterns": decomposer_result.get("relation_patterns", {}),
                "sme_mappings": decomposer_result.get("sme_mappings", []),
                "violable_boundaries": decomposer_result.get("violable_boundaries", []),
                "proposals": filtered_proposals,
                "rejected_pseudo_proposals": rejected_count,
                "evaluation": evaluator_results,
                "exploration_guidance": decomposer_result.get("exploration_guidance", {}),
            }

            state["last_pipeline_context"] = context_bundle
            self._write_state(state)

            self._post_to_dashboard(
                state.get("session_id", ""), "pipeline_step_completed",
                {"phase": phase, "proposals_count": len(filtered_proposals),
                 "rejected_pseudo": rejected_count,
                 "mappings_count": len(decomposer_result.get("mappings", [])),
                 "grafts_count": len(decomposer_result.get("grafts", [])),
                 "web_primitives": decomposer_result.get("web_primitives_count", 0)},
            )

            return {
                "done": False,
                "phase": phase,
                "step": "run_step_pipeline",
                "step_index": state.get("sub_loop_step", 0) - 1,
                "action": "pipeline_context",
                "context_bundle": context_bundle,
                "agent_roles": agents,
                "instruction": (
                    f"[{phase}] STEP 管线分析完成。"
                    f"将 context_bundle 传给 evo_discuss，让每个 agent 独立推理：\n"
                    f"1. 结构映射：跨领域关系同构搜索\n"
                    f"2. 反事实嫁接：故意违反边界条件制造认知冲突\n"
                    f"3. 方案重组：基于嫁接材料构建新方案\n"
                    f"4. 三公理评估：自识别 + 复述不变性 + 累积性\n"
                    f"({rejected_count} pseudo-novel proposals rejected by axiom filters)"
                ),
            }

        elif step_name == "web_reconnaissance":
            search_queries = self._build_search_queries(phase, state)
            return {
                "done": False,
                "phase": phase,
                "step": step_name,
                "step_index": state.get("sub_loop_step", 0) - 1,
                "action": "multi_agent",
                "tool": "evo_discuss",
                "topic": (
                    f"[{phase}] Web 侦察：搜索最新研究进展。\n"
                    f"研究问题: {state.get('research_topic', '')}\n\n"
                    f"## 搜索任务\n"
                    f"每个 Agent 用 Tavily 独立搜索以下主题:\n"
                    + "\n".join(f"- {q}" for q in search_queries)
                    + "\n\n## 输出要求\n"
                    f"每个 Agent 输出结构化搜索结果，格式:\n"
                    f'[{{"title": "...", "summary": "...", "key_insight": "...", "tags": ["..."]}}]\n'
                    f"所有结果汇总保存到 workspace/web_research.json"
                ),
                "agents": agents,
                "exclude_agents": ["code-agent", "debug-agent"],
            }

        elif step_name == "multi_agent_discuss":
            ctx = state.get("last_pipeline_context", {})
            topic_parts = [
                f"[{phase}] 多Agent汇总讨论。研究问题: {state.get('research_topic', '')}",
                "",
                "## STEP 管线分析结果",
                "",
                "### 索引概要",
                json.dumps(ctx.get("indexing", {}), ensure_ascii=False, indent=2)[:2000],
                "",
                "### 概念基元",
                json.dumps(ctx.get("primitives", [])[:10], ensure_ascii=False, indent=2)[:1500],
                "",
                "### 可违反边界条件",
                json.dumps(ctx.get("violable_boundaries", [])[:5], ensure_ascii=False, indent=2)[:1000],
                "",
                "## 任务",
                "每个 Agent 从自己的视角独立推理：",
                "1. 搜索跨领域关系同构（结构映射）",
                "2. 违反边界条件制造认知冲突（反事实嫁接）",
                "3. 基于嫁接材料构建 2-3 个新方案",
                "4. 产出格式: {title, hypothesis, method_sketch}",
            ]
            guidance = ctx.get("exploration_guidance", {})
            if guidance:
                topic_parts.extend([
                    "", "## 探索指导（上轮 Gap 分析）",
                    f"- 上轮最佳: {guidance.get('previous_best', 'N/A')}",
                    f"- 目标: {guidance.get('target', 'N/A')}",
                    f"- Grid 覆盖率: {guidance.get('grid_coverage_pct', 0)}%",
                    f"- 未探索 Cell: {guidance.get('unexplored_count', 0)}",
                    f"- **指令**: {guidance.get('directive', '')}",
                ])

            # ── 迭代上下文: 从 CC 提取上次实验结论 ──
            iter_parts = self._build_iteration_context()
            if iter_parts:
                topic_parts.extend(iter_parts)

            return {
                "done": False,
                "phase": phase,
                "step": step_name,
                "step_index": state.get("sub_loop_step", 0) - 1,
                "action": "multi_agent",
                "tool": "evo_discuss",
                "topic": "\n".join(topic_parts),
                "agents": agents,
                "exclude_agents": ["code-agent", "debug-agent"],
            }

        elif step_name == "elo_tournament":
            return {
                "done": False,
                "phase": phase,
                "step": step_name,
                "step_index": state.get("sub_loop_step", 0) - 1,
                "action": "multi_agent",
                "tool": "evo_run_tournament",
                "topic": f"[{phase}] ELO 锦标赛排序候选方案。ELO 仅在本次锦标赛内使用，用完废弃。",
            }

        elif step_name == "evolution_memory":
            distill_type = {
                "W2 Plan": "ide", "W3 Research": "ive",
                "W3.5 Ideate": "ide", "W5 Analyze": "ese",
            }.get(phase, "ide")
            return {
                "done": False,
                "phase": phase,
                "step": step_name,
                "step_index": state.get("sub_loop_step", 0) - 1,
                "action": "multi_agent",
                "tool": "evo_distill",
                "distill_type": distill_type,
                "topic": f"[{phase}] 记录到 Evolution Memory (type={distill_type})。不写入 Claim Chain。",
            }

        elif step_name == "invoke_skill_research":
            return {
                "done": False,
                "phase": phase,
                "step": step_name,
                "step_index": state.get("sub_loop_step", 0) - 1,
                "action": "invoke_skill",
                "skill": "/evo-research",
                "argument": f"基于多Agent讨论结果，补充收集真实论文。"
                           f"研究方向: {state.get('research_topic', '')}",
            }

        elif step_name == "generate_code_plan":
            return self._generate_code_plan(state, phase)

        elif step_name == "wait_user_code":
            return self._wait_user_code(state, phase)

        elif step_name == "ingest_results":
            results = self._auto_ingest_results()
            state = self._read_state()
            state["ingested_results"] = results
            self._write_state(state)
            self._post_to_dashboard(
                state.get("session_id", ""), "results_ingested",
                {"count": len(results), "phase": phase},
            )
            return {
                "done": False,
                "phase": phase,
                "step": step_name,
                "step_index": state.get("sub_loop_step", 0) - 1,
                "action": "ingest_results",
                "experiment_results": results,
                "instruction": f"自动扫描发现 {len(results)} 个实验结果，将传入 post_loop。",
            }

        elif step_name == "wait_external":
            return {
                "done": False,
                "phase": phase,
                "step": step_name,
                "step_index": state.get("sub_loop_step", 0) - 1,
                "action": "wait_external",
                "prompt": "请运行训练脚本，完成后粘贴结果（得分 + 日志路径）。",
            }

        elif step_name == "scan_islands_rubrics":
            return {
                "done": False,
                "phase": phase,
                "step": step_name,
                "step_index": state.get("sub_loop_step", 0) - 1,
                "action": "invoke_skill",
                "skill": "/evo-analyze",
                "argument": f"[{phase}] 扫描 Island 触发 Rubrics 对比。"
                           f"检查同CC条件下的异常性能差异。",
            }

        elif step_name == "write_claim_chain":
            return {
                "done": False,
                "phase": phase,
                "step": step_name,
                "step_index": state.get("sub_loop_step", 0) - 1,
                "action": "invoke_skill",
                "skill": "/evo-claim",
                "argument": f"[{phase}] 写入 Claim Chain。"
                           f"仅真实文献输入或真实实验结果，LLM推测不写入。",
            }

        elif step_name == "island_assign":
            return {
                "done": False,
                "phase": phase,
                "step": step_name,
                "step_index": state.get("sub_loop_step", 0) - 1,
                "action": "invoke_skill",
                "skill": "/evo-iterate",
                "argument": f"[{phase}] 变体入岛分配。检测 Island 合并候选。",
            }

        elif step_name == "invoke_skill_write":
            return {
                "done": False,
                "phase": phase,
                "step": step_name,
                "step_index": state.get("sub_loop_step", 0) - 1,
                "action": "invoke_skill",
                "skill": "/evo-write",
                "argument": f"基于所有实验结果和分析报告撰写论文。研究问题: {state.get('research_topic', '')}",
            }

        elif step_name == "invoke_skill_review":
            return {
                "done": False,
                "phase": phase,
                "step": step_name,
                "step_index": state.get("sub_loop_step", 0) - 1,
                "action": "invoke_skill",
                "skill": "/evo-review",
                "argument": "审阅论文报告。target >= 7/10 才能通过。",
            }

        return {"done": True, "phase": phase}

    # ═══════════════════════════════════════════════════════════════
    # W4 Code — Plan-driven 模式: generate_code_plan + wait_user_code
    # ═══════════════════════════════════════════════════════════════

    def _generate_code_plan(self, state: dict, phase: str) -> dict:
        """生成 implementation_plan.md，从 CC/plan/research_notes 自动提取交付物清单。"""
        import uuid
        from datetime import datetime

        workspace = self.workspace
        plan_id = str(uuid.uuid4())
        session_id = state.get("session_id", "")
        research_topic = state.get("research_topic", "")
        iteration = state.get("iteration", 0)

        # ── 收集上下文 ──
        context_parts = []
        plan_text = ""

        plan_md = workspace / "plan.md"
        if plan_md.exists():
            plan_text = plan_md.read_text(encoding='utf-8')[:5000]
            context_parts.append(f"## 实验计划\n{plan_text}")

        # Claim Chain atoms (from vault/_index/ — canonical CC location)
        cc_atoms = []
        cc_dir = self.index_dir  # vault/_index/
        atoms_path = cc_dir / "atoms.jsonl"
        if atoms_path.exists():
            raw = atoms_path.read_text(encoding='utf-8')
            context_parts.append(f"## Claim Chain 原子\n{raw[:3000]}")
            for line in raw.strip().split("\n"):
                try:
                    cc_atoms.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

        rn_text = ""
        rn_path = workspace / "research_notes.md"
        if rn_path.exists():
            rn_text = rn_path.read_text(encoding='utf-8')[:3000]
            context_parts.append(f"## 文献调研笔记\n{rn_text}")

        em_summary = self._load_evolution_memory_summary()
        if em_summary:
            context_parts.append(f"## Evolution Memory\n{json.dumps(em_summary, indent=2)[:2000]}")

        context = "\n\n".join(context_parts) if context_parts else "(空工作空间，请从零开始)"

        # ── 从 CC 提取方法/实验/提案 ──
        methods = []
        baselines = []
        experiments = []
        for a in cc_atoms:
            title = a.get("title", "")
            tags = a.get("tags", [])
            content = a.get("content", "")[:200]
            atom_type = a.get("type", "")
            # Proposals from write_claim_chain (type="method" with "proposal" tag)
            if atom_type == "method" and "proposal" in tags:
                methods.append({"title": title, "tags": tags, "content": content})
            elif atom_type == "fact" and any(
                t in tags for t in ["next-iteration", "method", "literature", "SOTA_2026"]
            ):
                methods.append({"title": title, "tags": tags, "content": content})
            elif atom_type == "fact" and any(
                t in tags for t in ["benchmark", "baseline", "SAC", "TD3", "PPO", "DDPG"]
            ):
                baselines.append({"title": title, "tags": tags, "content": content})
            elif atom_type == "fact" and "experiment" in tags:
                experiments.append({"title": title, "tags": tags, "content": content})

        # 去重
        seen = set()
        unique_methods = []
        for m in methods:
            if m["title"] not in seen:
                seen.add(m["title"])
                unique_methods.append(m)

        # Collect proposal atoms (used in baseline selection below)
        proposal_atoms = [a for a in cc_atoms if a.get("type") == "method" and "proposal" in a.get("tags", [])]

        # ── 生成交付物清单 ──
        deliverables = []
        specs = []

        # 基础设施 (总是需要)
        deliverables.append("- [ ] artifacts/config.py — 超参数配置 (环境名/Hopper-v4, 种子, 网络结构, 训练参数)")
        deliverables.append("- [ ] artifacts/networks.py — Actor/Critic 网络定义 (MLP, 层数可配)")
        deliverables.append("- [ ] artifacts/buffer.py — Replay Buffer (支持 state/action/reward/done 存储)")
        deliverables.append("- [ ] artifacts/trainer.py — 通用训练器 (支持多算法, WandB 日志, checkpoint 保存)")
        specs.append("### artifacts/config.py\n- Hopper-v4 环境配置\n- 所有算法共享的超参数: seed=42, gamma=0.99, tau=0.005, batch_size=256, buffer_size=1e6\n- 每个算法的专属参数 (如 SAC alpha, TD3 policy_noise)")
        specs.append("### artifacts/networks.py\n- Actor: MLP(state_dim → 256 → 256 → action_dim), tanh 输出\n- Critic: MLP(state_dim+action_dim → 256 → 256 → 1)\n- 支持 BatchNorm (CrossQ 需要) 和 Dropout (DroQ 需要)")

        # ── 迭代感知基线选择 ──
        # Meta tags that describe atom type/category, NOT algorithm names
        _META_TAGS = {"experiment", "w5-analyze", "benchmark", "literature", "method", "survey",
                      "continuous-control", "actor_critic", "exploration", "next-iteration",
                      "overestimation", "evaluation", "diagnosis", "baseline",
                      "hub", "ideas", "index", "proposal", "ideation", "sota_2026"}
        # Non-algorithm tag patterns (skip when extracting algo names)
        _SKIP_TAG_PREFIXES = ("ICML", "AAAI", "NeurIPS", "ICLR", "IEEE", "ACM", "202")

        def _is_algo_tag(tag: str) -> bool:
            """Check if a tag looks like an algorithm name (not a meta/category tag)."""
            t = tag.lower()
            if t in _META_TAGS:
                return False
            if tag.upper().startswith(_SKIP_TAG_PREFIXES):
                return False
            # Skip rank_N, graft_N, dup_N tags from CC proposal storage
            if t.startswith("rank_") or t.startswith("graft_") or t.startswith("dup_"):
                return False
            return True

        # 读取实验结论：从 experiment atom 的 tags 自动提取算法名
        experiment_atoms = [a for a in cc_atoms
                          if "experiment" in a.get("tags", [])]
        tested_algos = {}  # algo_name → {"score": ..., "title": ..., "atom": ...}
        for a in experiment_atoms:
            title = a.get("title", "")
            content = a.get("content", "")
            # Extract score from title like "sac: score=985.7 (n=3)"
            import re as _re
            score_match = _re.search(r'score[=:\s]*(\d+\.?\d*)', title + " " + content)
            score_val = float(score_match.group(1)) if score_match else 0.0
            for tag in a.get("tags", []):
                if _is_algo_tag(tag):
                    upper = tag.upper()
                    if upper not in tested_algos or score_val > tested_algos[upper].get("score", 0):
                        tested_algos[upper] = {
                            "score": score_val,
                            "title": title[:120],
                            "atom": a,
                        }

        # 读 CC relations: 找 validates/contradicts (from vault/_index/)
        cc_relations = []
        rel_path = self.index_dir / "relations.jsonl"
        if rel_path.exists():
            for line in rel_path.read_text().split("\n"):
                if line.strip():
                    try:
                        cc_relations.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

        validated_algos = set()
        contradicted_algos = set()
        for r in cc_relations:
            if r.get("type") == "validates":
                src = next((a for a in cc_atoms if a.get("id") == r["source_id"]), None)
                # Only extract algorithm names from method/fact atoms (not observation/index)
                if src and src.get("type") in ("method", "fact"):
                    for tag in src.get("tags", []):
                        if _is_algo_tag(tag):
                            validated_algos.add(tag.upper())
            elif r.get("type") == "contradicts":
                tgt = next((a for a in cc_atoms if a.get("id") == r["target_id"]), None)
                if tgt and tgt.get("type") in ("method", "fact"):
                    for tag in tgt.get("tags", []):
                        if _is_algo_tag(tag):
                            contradicted_algos.add(tag.upper())

        # 决定基线: 首次迭代用 SAC+TD3，后续迭代加入上次提案 + ELO 冠军
        # 追踪上一轮已提出但未测试的算法 (从 ELO 结果和 pipeline proposals)
        proposed_algos = set()
        tournament = state.get("last_tournament_result", {})
        ranked = []
        if isinstance(tournament, dict):
            raw_ranked = tournament.get("ranked", [])
            if isinstance(raw_ranked, list):
                ranked = raw_ranked
                for r_item in ranked[:10]:
                    if isinstance(r_item, dict):
                        r_title = r_item.get("title", "")
                        if r_title:
                            abbr = r_title.split(":")[0].strip().split()[0].upper()[:10]
                            proposed_algos.add(abbr)
        # Also extract from pipeline context proposals
        pipeline_ctx = state.get("last_pipeline_context", {})
        if isinstance(pipeline_ctx, dict):
            for p in pipeline_ctx.get("proposals", [])[:10]:
                if not isinstance(p, dict):
                    continue
                p_title = p.get("title", "")
                if p_title:
                    abbr = p_title.split(":")[0].strip().split()[0].upper()[:10]
                    proposed_algos.add(abbr)

        base_algos = set()
        baseline_notes = []
        if not experiment_atoms and not proposal_atoms:
            # 真正首次迭代
            base_algos.update(["SAC", "TD3"])
            baseline_notes.append("首次: SAC + TD3 基线")
        elif not experiment_atoms and proposal_atoms:
            # 有提案但无实验 — 上次计划未执行
            base_algos.update(["SAC", "TD3"])
            baseline_notes.append("有提案未执行: SAC + TD3 基线 + 上次提案")
        else:
            baseline_notes.append(f"上次已测: {sorted(tested_algos.keys())}")
            if validated_algos:
                baseline_notes.append(f"已验证有效: {sorted(validated_algos)}")
            if contradicted_algos:
                baseline_notes.append(f"已验证矛盾 (需修正): {sorted(contradicted_algos)}")
            if proposed_algos - set(tested_algos.keys()):
                baseline_notes.append(f"上次提出未完成: {sorted(proposed_algos - set(tested_algos.keys()))}")
            # 保留已验证的作为 baseline (用于对照)
            base_algos.update(validated_algos)
            # Also include tested algos that performed well
            for algo, info in tested_algos.items():
                if info.get("score", 0) > 0:
                    base_algos.add(algo)
            # 核心基线不能少
            if "SAC" not in base_algos and "TD3" not in base_algos:
                base_algos.update(["SAC", "TD3"])
                baseline_notes.append("保留 SAC+TD3 作为 baseline 对照")

        # 追踪已用文件名避免重复
        used_fnames = {a.lower() for a in base_algos}
        used_fnames.update({"config", "networks", "buffer", "trainer", "train_all", "analyze", "smoke_test"})

        # 加入 ELO 排名 Top-3 提案方法
        elo_added = 0
        for r_item in ranked[:3]:
            r_title = r_item.get("title", "")
            if r_title and elo_added < 3:
                abbr = r_title.split(":")[0].strip().split()[0].lower()[:20]
                if abbr not in used_fnames:
                    base_algos.add(abbr.upper())
                    used_fnames.add(abbr.lower())
                    proposed_algos.add(abbr.upper())
                    baseline_notes.append(f"ELO Top-{elo_added+1}: {r_title[:60]}")
                    elo_added += 1

        # 生成 baseline 交付物 + 详细 spec
        for algo in sorted(base_algos):
            fname = algo.lower()
            info = tested_algos.get(algo, {})
            score_val = info.get("score", 0)

            # 标签逻辑: KEEP > RESOLVE > RETRY > NEW
            if algo in contradicted_algos:
                label = "[RESOLVE] 上次矛盾，需修正"
            elif algo in tested_algos and score_val > 0:
                label = f"[KEEP] 已验证 (score={score_val:.0f})"
            elif algo in tested_algos:
                label = "[WEAK] 效果不达预期"
            elif algo in proposed_algos:
                label = "[RETRY] 上次未完成"
            else:
                label = "[NEW] 新提案"

            deliverables.append(f"- [ ] artifacts/{fname}.py — {algo} {label}")

            # 生成有意义的 spec
            spec_lines = [f"### artifacts/{fname}.py"]
            if info.get("title"):
                spec_lines.append(f"- 上次实验: {info['title'][:120]}")
            # Try to get method sketch from pipeline proposals
            if algo in proposed_algos:
                for r_item in ranked[:5]:
                    if r_item.get("title", "").split(":")[0].strip().upper()[:10] == algo[:10]:
                        sketch = r_item.get("method_sketch", "")[:400]
                        if sketch:
                            spec_lines.append(f"- 方法思路: {sketch}")
                        break
            # Add atom content if available
            atom = info.get("atom")
            if atom and atom.get("content", "").strip():
                content_preview = atom["content"][:300].replace("\n", " ")
                spec_lines.append(f"- CC 记录: {content_preview}")
            elif algo in tested_algos:
                spec_lines.append(f"- 分数: {score_val:.1f}")
                spec_lines.append("- 与 trainer.py 接口兼容")
            else:
                spec_lines.append("- 与 trainer.py 接口兼容")
            specs.append("\n".join(spec_lines))

        used_fnames.update({a.lower() for a in base_algos})
        used_fnames.update({"config", "networks", "buffer", "trainer", "train_all", "analyze", "smoke_test"})

        # 提案方法 (从 CC unique_methods 和 pipeline_context.proposals 提取)
        proposal_count = 0
        # Build lookup from pipeline proposals for method sketches
        pipeline_proposals = []
        if isinstance(pipeline_ctx, dict):
            raw = pipeline_ctx.get("proposals", [])
            if isinstance(raw, list):
                pipeline_proposals = raw
        # Filter out non-dict entries
        pipeline_proposals = [p for p in pipeline_proposals if isinstance(p, dict)]
        prop_by_title = {p.get("title", ""): p for p in pipeline_proposals}

        # Primary source: CC atoms. Fallback: pipeline proposals from state.
        if unique_methods:
            proposal_source = unique_methods
        else:
            # Build synthetic method entries from pipeline proposals
            proposal_source = []
            for p in pipeline_proposals[:5]:
                title = p.get("title", "")
                if title:
                    proposal_source.append({
                        "title": title,
                        "tags": p.get("primitives_used", []),
                        "content": json.dumps({
                            "hypothesis": p.get("hypothesis", ""),
                            "method_sketch": p.get("method_sketch", "")[:500],
                        }, ensure_ascii=False),
                    })

        for m in proposal_source[:5]:  # 最多 5 个提案
            title = m["title"]
            # Step 1: 从 tags 找未占用的算法简称
            algo_abbr = None
            for tag in m.get("tags", []):
                if (tag.isupper() and 2 <= len(tag) <= 12
                        and _is_algo_tag(tag)):
                    abbr = tag.lower()
                    if abbr not in used_fnames:
                        algo_abbr = abbr
                        break
            # Step 2: fallback — 从 title 提取
            if not algo_abbr:
                first_word = title.split(":")[0].strip().split()[0]
                algo_abbr = first_word.lower().replace("-", "_").replace("(", "").replace(")", "")[:25]
            # Step 3: 如果还冲突，加数字后缀
            orig = algo_abbr
            counter = 1
            while algo_abbr in used_fnames:
                algo_abbr = f"{orig}{counter}"
                counter += 1
            if algo_abbr:
                used_fnames.add(algo_abbr)
                deliverables.append(f"- [ ] artifacts/{algo_abbr}.py — {title[:80]} [PROPOSED]")
                # Generate detailed spec: prefer pipeline proposal method_sketch > CC content
                spec_parts = [f"### artifacts/{algo_abbr}.py", f"- 来源: {title}"]
                pp = prop_by_title.get(title) or {}
                sketch = pp.get("method_sketch", "")[:400]
                if sketch:
                    spec_parts.append(f"- 方法思路: {sketch}")
                elif m.get("content", "").strip():
                    spec_parts.append(f"- 摘要: {m['content'][:300]}")
                spec_parts.append("- 与 trainer.py 接口兼容")
                specs.append("\n".join(spec_parts))
                proposal_count += 1
                proposed_algos.add(algo_abbr.upper())

        # ELO 最高提案 (仅在无其他提案时作为 fallback)
        winner = ""
        if isinstance(state.get("last_tournament_result"), dict):
            winner = state["last_tournament_result"].get("winner", "")
        if winner and proposal_count == 0:
            winner_short = winner.split(":")[0].strip().lower().replace(" ", "_")[:30]
            if winner_short not in used_fnames:
                deliverables.append(f"- [ ] artifacts/{winner_short}.py — ELO 冠军: {winner[:80]}")
                # Extract method sketch from ranked list
                winner_sketch = ""
                for r_item in ranked[:1]:
                    if r_item.get("title", "") == winner or r_item.get("title", "").startswith(winner[:30]):
                        winner_sketch = r_item.get("method_sketch", "")[:400]
                        break
                spec_parts = [f"### artifacts/{winner_short}.py", f"- ELO 冠军提案: {winner}"]
                if winner_sketch:
                    spec_parts.append(f"- 方法思路: {winner_sketch}")
                spec_parts.append("- 与 trainer.py 接口兼容")
                specs.append("\n".join(spec_parts))
                used_fnames.add(winner_short)

        # 运行脚本
        deliverables.append("- [ ] artifacts/train_all.py — 一键训练所有算法的 master 脚本")
        deliverables.append("- [ ] artifacts/analyze.py — 结果分析脚本 (学习曲线, 性能对比表, 统计检验)")
        deliverables.append("- [ ] artifacts/smoke_test.py — Smoke test (1 episode, 检查无 NaN/维度错误)")

        specs.append("### artifacts/train_all.py\n- 依次或并行运行所有算法配置\n- 每个算法保存独立 checkpoint 和日志\n- 支持 --algo 参数只跑指定算法\n- 支持 --quick 模式 (减少 timesteps 用于快速验证)")
        specs.append("### artifacts/analyze.py\n- 读取所有算法日志, 绘制学习曲线\n- 输出性能对比表 (mean ± std over seeds)\n- Welch's t-test 显著性检验\n- 输出 analysis_report.md")

        # ── 生成验收标准 ──
        acceptance = """1. `python artifacts/smoke_test.py` 所有算法通过 (无 import 错误, 无 NaN, 无维度 mismatch)
2. `python artifacts/train_all.py --quick` 所有算法在 5000 steps 内不崩溃
3. SAC 和 TD3 基线在 Hopper-v4 上 200k steps 达到已知性能范围 (SAC: ~2000-3000, TD3: ~2000-3500)
4. 至少一个提案方法在 200k steps 内超越最强基线 >5%
5. `python artifacts/analyze.py` 正常输出分析报告"""

        deliverables_str = "\n".join(deliverables)
        specs_str = "\n\n".join(specs)

        # 迭代上下文
        iter_context = ""
        proposal_atoms = [a for a in cc_atoms if a.get("type") == "method" and "proposal" in a.get("tags", [])]
        has_prior_data = experiment_atoms or proposal_atoms or cc_relations
        if has_prior_data:
            parts = [f"""## 迭代上下文 (来自上次迭代)
- 迭代: {iteration}
- CC atoms: {len(cc_atoms)} 个 (experiment: {len(experiment_atoms)}, proposal: {len(proposal_atoms)})
- CC relations: {len(cc_relations)} 条"""]
            if tested_algos:
                parts.append(f"- 上次已测算法: {len(tested_algos)} 个 ({', '.join(sorted(tested_algos.keys()))})")
            if validated_algos:
                parts.append(f"- 已验证有效: {sorted(validated_algos)}")
            if contradicted_algos:
                parts.append(f"- 已验证矛盾 (需修正): {sorted(contradicted_algos)}")
            if proposal_atoms:
                parts.append(f"- 上次提案: {len(proposal_atoms)} 个 ({', '.join(p.get('title','')[:40] for p in proposal_atoms[:5])})")
            if baseline_notes:
                parts.append(f"- 基线策略: {'; '.join(baseline_notes)}")
            if ranked:
                parts.append(f"- ELO 锦标赛 Top-1: {ranked[0].get('title', 'N/A')[:80] if ranked else 'N/A'}")
            parts.append("")
            iter_context = "\n".join(parts)
        else:
            iter_context = f"""## 迭代上下文
- 首次迭代 (iteration={iteration})
- CC atoms: 0 — 无上次实验数据
- 将从零建立基线

"""

        plan_content = f"""# Implementation Plan: {research_topic}
plan_id: {plan_id}
workspace: {self.session_dir}
session_id: {session_id}
created_at: {datetime.now().isoformat()}
iteration: {iteration}
session_folder: ""

{iter_context}
## 上下文
{context}

## 交付物清单
{deliverables_str}

## 规格说明
{specs_str}

## 验收标准
{acceptance}
"""

        plan_path = self.session_dir / "iterations" / str(iteration) / "implementation_plan.md"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(plan_content, encoding="utf-8")

        # 更新 state
        state["status"] = "awaiting_user_code"
        self._write_state(state)

        return {
            "done": False,
            "phase": phase,
            "step": "generate_code_plan",
            "step_index": state.get("sub_loop_step", 0) - 1,
            "action": "generate_code_plan",
            "plan_path": str(plan_path),
            "plan_id": plan_id,
            "deliverable_count": len(deliverables),
            "instruction": (
                "implementation_plan.md 已生成。请在 VS Code Claude Code 中依次执行:\n"
                "  1. /evo-code-agent-pre " + str(plan_path) + "\n"
                "  2. [实现代码...]\n"
                "  3. /evo-code-agent-check " + str(plan_path) + "\n"
                "  4. [修正...]\n"
                "  5. /evo-code-agent-post " + str(plan_path) + "\n"
                "完成后 Dashboard 将检测到完成信号并进入 W5 Analyze。"
            ),
        }

    def _build_iteration_context(self) -> list[str]:
        """从 CC 提取上次 W5 Analyze 的实验结论，插入 multi_agent_discuss topic。

        纯 CC 驱动，不加 PIPELINE_STATE 额外字段。
        返回 topic_parts 追加列表 (可能为空)。
        """
        parts = []
        try:
            atoms = self.cc.get_atoms(limit=200)
            relations = self.cc.get_relations(limit=200)

            experiment_atoms = [a for a in atoms
                              if "experiment" in a.get("tags", [])]
            if not experiment_atoms:
                return parts  # 无实验数据, 不追加

            parts.append("")
            parts.append("## 上次迭代结论 (来自 Claim Chain + W5 Analyze)")
            parts.append("")

            # 实验 atoms
            parts.append("### 已验证实验")
            for a in experiment_atoms[:10]:
                parts.append(f"- {a['title']}")

            # relations: validates/contradicts
            validates = [r for r in relations if r.get("type") == "validates"]
            contradicts = [r for r in relations if r.get("type") == "contradicts"]
            implements = [r for r in relations if r.get("type") == "implements"]

            if validates:
                parts.append("")
                parts.append("### 验证关系 (A validates B = A 优于 B)")
                for r in validates[:5]:
                    src = self.cc.get_atom(r["source_id"])
                    tgt = self.cc.get_atom(r["target_id"])
                    if src and tgt:
                        parts.append(f"- {src['title']} → validates → {tgt['title']}")

            if contradicts:
                parts.append("")
                parts.append("### 矛盾关系 (预期不符)")
                for r in contradicts[:5]:
                    src = self.cc.get_atom(r["source_id"])
                    tgt = self.cc.get_atom(r["target_id"])
                    if src and tgt:
                        parts.append(f"- {src['title']} ←→ contradicts ←→ {tgt['title']}")

            if implements:
                parts.append("")
                parts.append("### 代码归档 (code ↔ CC 关联)")
                for r in implements[:5]:
                    parts.append(f"- atom_{r['source_id']} → implements → {r.get('evidence', '?')[:80]}")

            # Grid 状态
            grid_idx = self.grid.get_discovery_index()
            filled = grid_idx.get("filled_cells", 0)
            total = grid_idx.get("total_cells", 0)
            if filled > 0:
                parts.append("")
                parts.append(f"### Grid 状态: {filled}/{total} cells 填充")

        except Exception:
            pass  # CC/Grid 不可用时静默跳过

        return parts

    def _wait_user_code(self, state: dict, phase: str) -> dict:
        """等待用户通过 /evo-code-agent-post 完成代码实现。
        通过检测 PIPELINE_STATE.json 中的 code_phase_status == 'completed'。
        """
        code_status = state.get("code_phase_status", "")
        if code_status == "completed":
            return {"done": True, "phase": phase}

        # 还在等待中 — 回退 sub_loop_step 以在下次 sub_loop 时重试此步骤
        chain = CHAIN_STEPS.get(phase, [])
        wait_idx = 0
        try:
            wait_idx = chain.index("wait_user_code")
        except ValueError:
            pass
        state["sub_loop_step"] = wait_idx
        self._write_state(state)

        return {
            "done": False,
            "phase": phase,
            "step": "wait_user_code",
            "step_index": wait_idx,
            "action": "wait_user_code",
            "status": "awaiting_user",
            "instruction": (
                "等待用户在 VS Code Claude Code 中完成代码实现。\n"
                "完成后运行 /evo-code-agent-post 回传结果。"
            ),
        }

    # ═══════════════════════════════════════════════════════════════
    # MCP Tool: post_loop
    # ═══════════════════════════════════════════════════════════════

    def post_loop(self, cc_atoms: list[dict] | None = None,
                  experiment_results: list[dict] | None = None) -> dict:
        """提交阶段数据写入。不做阶段流转决策（由 Dashboard 管控）。"""
        state = self._read_state()
        phase = state["phase"]
        events = []

        # 1. CC 写入（仅 W3 Research 和 W5 Analyze）
        if phase == PHASE_RESEARCH and cc_atoms:
            for atom_data in cc_atoms:
                atom_type = atom_data.get("type", "fact")
                title = atom_data.get("title", "")
                content = atom_data.get("content", "")
                tags = atom_data.get("tags", [])
                self.cc.add_atom(type=atom_type, title=title, content=content, tags=tags)
            cc_summary = self.cc.get_graph_summary()
            events.append(f"claim_chain_updated: {len(cc_atoms)} literature atoms written, total: {cc_summary.get('atom_count', 0)}")

        elif phase == PHASE_ANALYZE:
            if cc_atoms:
                for atom_data in cc_atoms:
                    self.cc.add_atom(
                        type=atom_data.get("type", "verification"),
                        title=atom_data.get("title", ""),
                        content=atom_data.get("content", ""),
                        tags=atom_data.get("tags", []),
                    )
                events.append(f"claim_chain_updated: {len(cc_atoms)} experiment result atoms written")

            # Fallback: 使用 ingest_results 自动扫描的结果
            if not experiment_results:
                experiment_results = state.get("ingested_results", [])
            if experiment_results:
                for result in experiment_results:
                    score = result.get("score", 0)
                    variant_id = result.get("variant_id", "")
                    descriptor = result.get("descriptor", {})
                    self.fitness.record(score=score, metadata=result)
                    cell_key = self.grid.assign(variant_id, descriptor)
                    self.grid.record_result(variant_id, score, descriptor)
                    island_id = self.islands.detect_and_assign(
                        variant_id, cell_key, score, descriptor,
                        method_family=descriptor.get("method_family", "default"),
                    )
                    events.append(f"fitness_recorded: score={score}, cell={cell_key}, island={island_id}")

        # 2. Gap analysis（仅 W5 Analyze）
        gap_analysis = None
        if phase == PHASE_ANALYZE:
            gap_analysis = self._compute_gap_analysis(state)

        # 3. 设置状态为"等待用户决策"
        state["status"] = "awaiting_decision"
        if gap_analysis:
            state["last_gap_analysis"] = gap_analysis
        self._write_state(state)

        cc_summary = self.cc.get_graph_summary()
        grid_data = self.grid.get_heatmap_data()
        coverage = grid_data.get("coverage", {})

        return {
            "phase": phase,
            "data_written": True,
            "events": events,
            "gap_analysis": gap_analysis,
            "cc_atom_count": cc_summary.get("total_atoms", 0),
            "grid_filled": coverage.get("filled", 0),
            "grid_total": coverage.get("total", 0),
            "message": f"阶段 '{phase}' 数据已写入。请在 Dashboard (localhost:8420/pipeline) 确认下一步。",
        }

    # ═══════════════════════════════════════════════════════════════
    # MCP Tool: transition_phase (Dashboard 控制)
    # ═══════════════════════════════════════════════════════════════

    def transition_phase(self, action: str) -> dict:
        """Dashboard 调用的阶段流转方法。LLM 不参与决策。"""
        state = self._read_state()
        phase = state["phase"]

        if action == "satisfied":
            next_phase = self._auto_next_phase(phase, state)
            state["phase"] = next_phase
            state["sub_loop_step"] = 0
            state["status"] = "in_progress"
            if phase == PHASE_ANALYZE:
                state["iteration"] = state.get("iteration", 0) + 1
            self._write_state(state)
            self._post_to_dashboard(
                state.get("session_id", ""), "phase_changed",
                {"from": phase, "to": next_phase},
            )
            return {"transitioned": True, "from": phase, "to": next_phase}

        elif action == "unsatisfied":
            if phase == PHASE_REVIEW:
                state["phase"] = PHASE_WRITE
            state["sub_loop_step"] = 0
            state["status"] = "in_progress"
            self._write_state(state)
            return {"transitioned": False, "phase": state["phase"],
                    "message": f"重做阶段 '{state['phase']}'"}

        elif action == "jump_to_write":
            gap = state.get("last_gap_analysis")
            if not gap or gap.get("target_score") is None:
                return {"error": "无法进入写作：未定义成功目标。请先创建 success_criteria.md"}
            state["phase"] = PHASE_WRITE
            state["sub_loop_step"] = 0
            state["status"] = "in_progress"
            self._write_state(state)
            return {"transitioned": True, "to": PHASE_WRITE}

        elif action == "terminate":
            state["phase"] = PHASE_TERMINATED
            state["status"] = "terminated"
            self._write_state(state)
            return {"transitioned": True, "to": PHASE_TERMINATED}

        return {"error": f"Unknown action: {action}"}

    def _auto_next_phase(self, phase: str, state: dict) -> str:
        """根据当前阶段自动计算下一阶段。"""
        if phase == PHASE_PLAN:
            return PHASE_RESEARCH
        elif phase == PHASE_RESEARCH:
            return PHASE_IDEATE
        elif phase == PHASE_IDEATE:
            return PHASE_CODE
        elif phase == PHASE_CODE:
            return PHASE_ANALYZE
        elif phase == PHASE_ANALYZE:
            target = self._read_success_target()
            if target is not None:
                fs = self.fitness.get_stats()
                best = fs.get("global", {}).get("max_score", 0)
                if best >= target:
                    return PHASE_WRITE
            return PHASE_PLAN  # 未达标→回到Plan，Island上已有积累
        elif phase == PHASE_WRITE:
            return PHASE_TERMINATED  # 满意→终止（不满意由用户选Review）
        elif phase == PHASE_REVIEW:
            return PHASE_WRITE  # Review后回到Write
        return PHASE_TERMINATED

    def _compute_gap_analysis(self, state: dict) -> dict:
        """计算 gap analysis。target=None 时 gap=None。"""
        target = self._read_success_target()
        fs = self.fitness.get_stats()
        best = fs.get("global", {}).get("max_score", 0)
        cc_summary = self.cc.get_graph_summary()
        grid_data = self.grid.get_heatmap_data()
        coverage = grid_data.get("coverage", {})

        if target is not None:
            gap = max(0, target - best)
            gap_pct = (gap / target * 100) if target > 0 else 0
            target_met = best >= target
        else:
            gap = None
            gap_pct = None
            target_met = False

        return {
            "target_score": target,
            "best_score": best,
            "gap": gap,
            "gap_percent": gap_pct,
            "target_met": target_met,
            "cc_atom_count": cc_summary.get("total_atoms", 0),
            "grid_filled": coverage.get("filled", 0),
            "grid_total": coverage.get("total", 0),
            "iteration": state.get("iteration", 0),
        }

    def _read_success_target(self) -> float | None:
        """从 success_criteria.md 读取目标得分。"""
        sc_path = self.workspace / "success_criteria.md"
        if not sc_path.exists():
            return None
        content = sc_path.read_text(encoding="utf-8")
        # 简单解析：找 "target" 或 "目标" 后的数字
        import re
        for pattern in [r"target[:\s]+(\d+\.?\d*)", r"目标[:\s]+(\d+\.?\d*)",
                        r"score[:\s]+(\d+\.?\d*)"]:
            m = re.search(pattern, content, re.IGNORECASE)
            if m:
                return float(m.group(1))
        return None

    # ═══════════════════════════════════════════════════════════════
    # 5 个 STEP 函数 (单Agent内部管线)
    # ═══════════════════════════════════════════════════════════════

    def step_cli(self, query_type: str, filters: dict | None = None) -> dict:
        """STEP_CLI: 包装 claim_chain.py + cell_grid.py 的查询。

        query_type: "atoms"|"relations"|"cells"|"milestones"|"summary"
        """
        filters = filters or {}
        limit = filters.get("limit", 30)

        if query_type == "atoms":
            return {"result": self.cc.get_atoms(
                type=filters.get("type"), tags=filters.get("tags"), limit=limit)}
        elif query_type == "relations":
            return {"result": self.cc.get_relations(
                type=filters.get("type"), limit=limit)}
        elif query_type == "cells":
            return {"result": self.grid.get_heatmap_data()}
        elif query_type == "milestones":
            return {"result": self.grid.detect_milestones()}
        elif query_type == "summary":
            return {"result": {
                "cc": self.cc.get_graph_summary(),
                "grid": self.grid.get_heatmap_data().get("coverage", {}),
                "anomalies": self.grid.get_anomaly_cells(),
            }}
        else:
            return {"error": f"Unknown query_type: {query_type}"}

    def step_indexing(self, phase: str, agent_role: str) -> dict:
        """STEP_indexing: 渐进式发现索引。

        返回 discovery_index (结构形状，不含数据) + discovery_prompts (引导问题 + action 指令)。
        Agent 必须通过 pes_cli 查询才能获取具体数据 — 不被 spoon-feed。

        phase: "Plan"|"Research"|"Ideate"|"RubricsJudge"
        """
        cc_idx = self.cc.get_atoms_index()
        grid_idx = self.grid.get_discovery_index()

        if phase in ("Plan", PHASE_PLAN):
            return self._step_indexing_plan(agent_role, cc_idx, grid_idx)
        elif phase in ("Research", PHASE_RESEARCH):
            return self._step_indexing_research(agent_role, cc_idx, grid_idx)
        elif phase in ("Ideate", "W3.5 Ideate", PHASE_IDEATE):
            return self._step_indexing_ideate(agent_role, cc_idx, grid_idx)
        elif phase in ("RubricsJudge", PHASE_ANALYZE):
            return self._step_indexing_rubrics_judge(agent_role, cc_idx, grid_idx)
        else:
            return {
                "discovery_index": {"cc": cc_idx, "grid": grid_idx},
                "discovery_prompts": [{"id": "gen-1", "question": "Explore the workspace", "action": "run pes_cli summary"}],
                "agent_role": agent_role,
                "phase_guidance": "Explore the workspace structure.",
            }

    def _step_indexing_plan(self, agent_role: str, cc_idx: dict, grid_idx: dict) -> dict:
        """Plan: 发现研究残缺 (缺少的CC类型、空cell区域、未定义岛心)。"""
        return {
            "discovery_index": {
                "claim_chain": cc_idx,
                "grid": {k: v for k, v in grid_idx.items()
                        if k in ("dimension_names", "dimension_values", "total_cells",
                                 "filled_cells", "empty_cells", "empty_regions")},
            },
            "discovery_prompts": [
                {
                    "id": "plan-gap-1",
                    "category": "missing_cc_types",
                    "question": f"The Claim Chain has types={cc_idx.get('type_counts',{})} but MISSING: {cc_idx.get('missing_atom_types',[])}. What method/theorem atoms should be created?",
                    "action": "Run pes_cli atoms --type fact to inspect existing content. Identify which facts imply unstated methods.",
                },
                {
                    "id": "plan-gap-2",
                    "category": "missing_relations",
                    "question": f"0 relations exist in CC. Which atoms logically relate to each other? Missing relation types: {cc_idx.get('missing_relation_types',[])}",
                    "action": "Run pes_cli atoms to compare titles and tags. Identify which fact atoms should validate/contradict/derive from others.",
                },
                {
                    "id": "plan-gap-3",
                    "category": "empty_grid_regions",
                    "question": f"{grid_idx.get('empty_cells',0)}/{grid_idx.get('total_cells',1)} cells empty. Are there adjacent empty regions representing unexplored behavioral regimes?",
                    "action": "Run pes_cli cells --status empty to find adjacent empty regions.",
                },
            ],
            "agent_role": agent_role,
            "phase_guidance": "Your mission as Plan agent: identify CONCRETE, TESTABLE research gaps. Focus on: (1) which empty behavioral regions are most promising, (2) which missing CC atom types block reasoning.",
        }

    def _step_indexing_research(self, agent_role: str, cc_idx: dict, grid_idx: dict) -> dict:
        """Research: 发现不确定性 (边界违规、矛盾、异常cell)。"""
        return {
            "discovery_index": {
                "claim_chain": cc_idx,
                "grid": {k: v for k, v in grid_idx.items()
                        if k in ("anomaly_count", "filled_cells", "total_cells")},
                "uncertainty_zones": [
                    {"type": "no_boundaries_defined", "severity": "high",
                     "implication": "We do not know where any method fails — boundaries are undefined"},
                    {"type": "no_contradictions_recorded", "severity": "medium",
                     "implication": "No competing claims have been tested against each other"},
                    {"type": f"all_{cc_idx.get('max_atom_id',0)}_atoms_are_orphans" if cc_idx.get('orphan_atom_count',0) > 0 else "connected",
                     "severity": "medium",
                     "implication": f"{cc_idx.get('orphan_atom_count',0)} atoms have zero relations — knowledge is fragmented"},
                ],
            },
            "discovery_prompts": [
                {
                    "id": "research-unc-1",
                    "question": "Without boundary_of relations, which fact atoms suggest implicit limits that should be formalized?",
                    "action": "Run pes_cli atoms and look for claims about 'limitations', 'fails when', or 'only works if' in content.",
                },
                {
                    "id": "research-unc-2",
                    "question": "Which fact atoms make potentially CONTRADICTORY claims? E.g., one says entropy helps, another says deterministic is better.",
                    "action": "Run pes_cli atoms --type fact and compare hypotheses across atoms with different tags.",
                },
                {
                    "id": "research-unc-3",
                    "question": f"Grid has {grid_idx.get('anomaly_count',0)} anomaly cells. Are there cells where similar methods produce very different scores?",
                    "action": "Run pes_cli anomalies to identify score gaps >30% between variants in same cell.",
                },
            ],
            "agent_role": agent_role,
            "phase_guidance": "Your mission as Research agent: discover UNCERTAINTIES. Where is our knowledge incomplete or contradictory? What boundaries are unknown?",
        }

    def _step_indexing_ideate(self, agent_role: str, cc_idx: dict, grid_idx: dict) -> dict:
        """Ideate: 发现空白 (未探索 cell 组合、未尝试 tag 组合)。"""
        tag_vocab = cc_idx.get("tag_vocabulary", [])
        return {
            "discovery_index": {
                "claim_chain": cc_idx,
                "grid": {k: v for k, v in grid_idx.items()
                        if k in ("dimension_names", "dimension_values", "total_cells",
                                 "filled_cells", "empty_cells", "empty_regions")},
                "unexplored_combinations": (
                    f"{len(tag_vocab)} tags available, "
                    f"{cc_idx.get('total_atoms',0)} atoms — "
                    f"countless cross-tag combinations never tried"
                ),
            },
            "discovery_prompts": [
                {
                    "id": "ideate-blank-1",
                    "question": f"{grid_idx.get('empty_cells',0)} empty cells. Which specific cell would represent the most SURPRISING behavioral regime compared to known methods?",
                    "action": "Run pes_cli cells --status empty. Map dimension values to algorithm properties. Find counter-intuitive combinations.",
                },
                {
                    "id": "ideate-blank-2",
                    "question": "Which pairs of CC fact tags have NEVER been combined? What would a method combining them look like?",
                    "action": "Run pes_cli atoms to get all atoms, compute tag co-occurrence matrix, find zero-count pairs.",
                },
                {
                    "id": "ideate-blank-3",
                    "question": "What cross-domain structural analogies could produce entirely new method types?",
                    "action": "Explore concept primitives library across evolution, NAS, causal inference, information theory, and control theory.",
                },
            ],
            "agent_role": agent_role,
            "phase_guidance": "Your mission as Ideate agent: discover BLANKS. Where are the unfilled spaces? What combinations have never been tried?",
        }

    def _step_indexing_rubrics_judge(self, agent_role: str, cc_idx: dict, grid_idx: dict) -> dict:
        """RubricsJudge: 发现缺失评价维度。"""
        return {
            "discovery_index": {
                "claim_chain": cc_idx,
                "grid": {k: v for k, v in grid_idx.items()
                        if k in ("dimension_names", "anomaly_count", "filled_cells")},
                "evaluation_gaps": (
                    f"Grid has {len(grid_idx.get('dimension_names',[]))} dimensions. "
                    f"Additional dimensions may be needed: sample_efficiency, wall_clock_time, "
                    f"hyperparameter_sensitivity, generalization_gap, compute_cost"
                ),
            },
            "discovery_prompts": [
                {
                    "id": "eval-gap-1",
                    "question": "Which evaluation dimensions are MISSING? Could 'sample_efficiency', 'wall_clock_time', or 'hyperparameter_sensitivity' distinguish methods that currently cluster together?",
                    "action": "Run pes_cli cells --status filled. If methods cluster in same cells, propose finer-grained dimensions.",
                },
                {
                    "id": "eval-gap-2",
                    "question": f"Grid dimensions ({grid_idx.get('dimension_names',[])}) — do they overlap or leave gaps?",
                    "action": "Check if 'generalization' or 'compute_efficiency' should be added to the grid.",
                },
            ],
            "agent_role": agent_role,
            "phase_guidance": "Your mission as RubricsJudge: discover MISSING evaluation dimensions. What aspects of performance are unmeasured?",
        }

    def step_decomposer(self, concept_primitives: list[dict] | None = None) -> dict:
        """STEP_Decomposer: 结构映射 + 反事实嫁接 + 冲突检测。

        处理 CC 内部数据 + Web 搜索结果，产生跨域映射和嫁接材料。
        """
        state = self._read_state()
        gap = state.get("last_gap_analysis")
        iteration = state.get("iteration", 0)

        # 从 CC 提取基元
        atoms = self.cc.get_atoms(limit=200)
        relations = self.cc.get_relations(limit=200)

        # 提取关系链模式
        validates_chains = []
        derives_chains = []
        contradicts_chains = []

        for r in relations:
            if r["type"] == "validates":
                method = self.cc.get_atom(r["source_id"])
                verification = self.cc.get_atom(r["target_id"])
                if method and verification:
                    validates_chains.append({
                        "method_id": r["source_id"],
                        "method_title": method["title"],
                        "verification_id": r["target_id"],
                        "verification_score": verification.get("metadata", {}).get("score"),
                        "evidence": r.get("evidence", ""),
                    })
            elif r["type"] == "derives":
                source = self.cc.get_atom(r["source_id"])
                target = self.cc.get_atom(r["target_id"])
                if source and target:
                    derives_chains.append({
                        "from_id": r["source_id"],
                        "from_title": source["title"],
                        "to_id": r["target_id"],
                        "to_title": target["title"],
                    })
            elif r["type"] == "contradicts":
                contradicts_chains.append({
                    "source_id": r["source_id"],
                    "target_id": r["target_id"],
                    "evidence": r.get("evidence", ""),
                })

        # 列出可违反的边界条件
        boundaries = []
        for r in relations:
            if r["type"] == "boundary_of":
                atom = self.cc.get_atom(r["source_id"])
                boundaries.append({
                    "atom_id": r["source_id"],
                    "atom_title": atom["title"] if atom else "",
                    "boundary_description": r.get("evidence", ""),
                    "metadata": r.get("metadata", {}),
                })

        # 当前领域基元
        primitives = concept_primitives or []
        if not primitives:
            # 从 method/fact 原子自动构建基元列表
            relevant_atoms = [a for a in atoms if a["type"] in ("method", "fact") and a["status"] == "active"]
            primitives = [
                {"atom_id": a["id"], "title": a["title"], "tags": a.get("tags", []),
                 "content": a.get("content", "")[:200]}
                for a in relevant_atoms[:20]
            ]

        # 融合 Web 搜索结果作为额外 primitives
        web_path = self.workspace / "web_research.json"
        web_count = 0
        if web_path.exists():
            try:
                web_findings = json.loads(web_path.read_text(encoding="utf-8"))
                if isinstance(web_findings, list):
                    for f in web_findings:
                        primitives.append({
                            "atom_id": f"web_{web_count}",
                            "title": f.get("title", ""),
                            "tags": f.get("tags", []),
                            "content": (f.get("summary", "") or f.get("key_insight", ""))[:200],
                            "source": "web_search",
                        })
                        web_count += 1
            except Exception:
                pass

        # 结构映射: 发现同构关系模式
        mappings = self._find_structural_mappings(atoms, relations)

        # 反事实嫁接: 从边界条件和 primitives 生成
        grafts = self._generate_counterfactual_grafts(boundaries, primitives)

        # 冲突区检测
        conflict_zones = []
        for cc_item in contradicts_chains:
            src = self.cc.get_atom(cc_item["source_id"])
            tgt = self.cc.get_atom(cc_item["target_id"])
            if src and tgt:
                conflict_zones.append({
                    "atom_a": src["title"], "atom_b": tgt["title"],
                    "tension": cc_item.get("evidence", ""),
                    "resolution_opportunity": f"Resolving {src['title']} vs {tgt['title']}",
                })

        # Fallback: CC 空时从研究主题生成
        if not mappings and not grafts:
            fallback = self._generate_fallback_proposals(state)
            for item in fallback:
                if "isomorphic_relation" in item:
                    mappings.append(item)
                else:
                    grafts.append(item)

        # 探索指导 (从上轮 gap analysis)
        exploration_guidance = {}
        if gap:
            empty = self.grid.get_empty_cells()
            exploration_guidance = {
                "previous_best": gap.get("best_score"),
                "target": gap.get("target_score"),
                "grid_coverage_pct": round(
                    gap.get("grid_filled", 0) / max(gap.get("grid_total", 1), 1) * 100, 1
                ),
                "unexplored_count": len(empty),
                "iteration": iteration,
                "directive": (
                    f"上轮最佳={gap.get('best_score')}，目标={gap.get('target_score')}。"
                    f"Grid 覆盖 {gap.get('grid_filled', 0)}/{gap.get('grid_total', 0)}。"
                    f"本轮必须提出结构上不同的方案，而非超参数调整。"
                ),
            }

        # SME: 跨域关系同构搜索 (Structure Mapping Engine)
        sme_mappings = []
        try:
            from structure_mapping_engine import StructureMappingEngine
            sme = StructureMappingEngine()
            seed_concepts = []
            for p in primitives[:10]:
                seed_concepts.extend(p.get("tags", []))
                seed_concepts.append(p.get("title", "")[:30])
            sme_isos = sme.find_isomorphisms_across_library(
                list(set(seed_concepts)), min_similarity=0.5
            )
            for iso in sme_isos[:10]:
                sme_mappings.append({
                    "source_domain": iso.get("source_domain", ""),
                    "target_domain": iso.get("target_domain", ""),
                    "source_pattern": iso.get("source_pattern", []),
                    "target_pattern": iso.get("target_pattern", []),
                    "relation_chain": iso.get("isomorphic_relation_chain", ""),
                    "confidence": iso.get("confidence", 0),
                    "type": iso.get("type", "cross_domain"),
                    "interpretation": iso.get("interpretation", ""),
                })
        except Exception:
            pass  # SME 不可用时静默跳过

        return {
            "primitives": primitives,
            "relation_patterns": {
                "validates_chains": validates_chains[:20],
                "derives_chains": derives_chains[:20],
                "contradicts_chains": contradicts_chains[:20],
            },
            "violable_boundaries": boundaries[:10],
            "mappings": mappings[:15],
            "grafts": grafts[:15],
            "sme_mappings": sme_mappings,
            "conflict_zones": conflict_zones[:5],
            "web_primitives_count": web_count,
            "exploration_guidance": exploration_guidance,
        }

    def _find_structural_mappings(self, atoms: list[dict], relations: list[dict]) -> list[dict]:
        """发现 CC atoms 之间同构的关系模式。"""
        atom_rels: dict[int, list[str]] = {}
        for r in relations:
            atom_rels.setdefault(r["source_id"], []).append(r["type"])
            atom_rels.setdefault(r["target_id"], []).append(r["type"])

        method_atoms = [a for a in atoms if a["type"] in ("method", "fact") and a["status"] == "active"]
        sig_groups: dict[tuple, list] = {}
        for a in method_atoms:
            sig = tuple(sorted(set(atom_rels.get(a["id"], []))))
            sig_groups.setdefault(sig, []).append(a)

        mappings = []
        for sig, group in sig_groups.items():
            if len(group) >= 2 and sig:
                for i in range(len(group)):
                    for j in range(i + 1, len(group)):
                        mappings.append({
                            "source_primitive": group[i]["title"],
                            "target_domain": group[j]["title"],
                            "isomorphic_relation": f"Both share pattern: {' + '.join(sig)}",
                            "confidence": 0.6,
                        })
        return mappings[:10]

    def _generate_counterfactual_grafts(self, boundaries: list[dict], primitives: list[dict]) -> list[dict]:
        """从边界条件和 primitives 生成反事实嫁接。"""
        grafts = []
        for b in boundaries:
            grafts.append({
                "violated_boundary": b.get("atom_title", ""),
                "primitive_a": b.get("atom_title", ""),
                "primitive_b": "NEGATED: " + b.get("boundary_description", "")[:100],
                "counterfactual": f"What if {b.get('atom_title', '')} does NOT hold?",
                "potential_breakthrough": "Violating boundary could reveal hidden assumptions.",
            })

        if not grafts and primitives:
            tags: dict[str, list] = {}
            for p in primitives:
                for t in p.get("tags", []):
                    tags.setdefault(t, []).append(p)
            tag_list = list(tags.keys())
            for i in range(len(tag_list)):
                for j in range(i + 1, min(i + 3, len(tag_list))):
                    pa = tags[tag_list[i]][0] if tags[tag_list[i]] else None
                    pb = tags[tag_list[j]][0] if tags[tag_list[j]] else None
                    if pa and pb:
                        grafts.append({
                            "violated_boundary": "tag_boundary",
                            "primitive_a": pa["title"],
                            "primitive_b": pb["title"],
                            "counterfactual": f"Combine {pa['title']} ({tag_list[i]}) with {pb['title']} ({tag_list[j]})?",
                            "potential_breakthrough": f"Cross-tag graft: {tag_list[i]} x {tag_list[j]}",
                        })
        return grafts[:10]

    def _generate_fallback_proposals(self, state: dict) -> list[dict]:
        """CC 空时从研究主题 + 概念基元库生成多样化保底提案。

        不再枚举 algorithm × axis 笛卡尔积。
        改用概念基元库的跨域同构 + 多类型提案。
        """
        import random
        topic = state.get("research_topic", "")
        proposals = []

        # 从 topic 提取算法名
        algorithms = []
        for alg in ["ppo", "sac", "td3", "ddpg", "a2c", "a3c", "crossq", "redq", "droq"]:
            if alg.lower() in topic.lower():
                algorithms.append(alg.upper())
        if not algorithms:
            algorithms = ["DDPG", "SAC", "TD3"]

        # 尝试加载概念基元库获取跨域同构
        try:
            from structure_mapping_engine import StructureMappingEngine
            sme = StructureMappingEngine()
            # 跨域搜索
            isos = sme.find_isomorphisms_across_library([topic[:60]], min_similarity=0.4)
            for iso in isos[:8]:
                src_pat = " × ".join(iso.get("source_pattern", ["?"])[:2])
                tgt_pat = " × ".join(iso.get("target_pattern", ["?"])[:2])
                proposals.append({
                    "source_primitive": f"{iso.get('source_domain','')}:{src_pat}",
                    "target_domain": f"{iso.get('target_domain','')}:{tgt_pat}",
                    "isomorphic_relation": iso.get("isomorphic_relation_chain", ""),
                    "confidence": iso.get("confidence", 0.5),
                })
        except Exception:
            pass

        # 如果 SME 无结果或不可用，用算法组合 + 多样化轴
        if len(proposals) < 3:
            diverse_axes = [
                ("entropy_regularization", "violates the deterministic policy requirement", "counterfactual_graft"),
                ("information_bottleneck_theory", "compresses task-irrelevant features", "structural_mapping"),
                ("causal_graph_discovery", "identifies interventions for exploration", "structural_mapping"),
                ("feedback_linearization", "replaces stochastic exploration with deterministic control", "counterfactual_graft"),
                ("batch_normalization_trick", "eliminates target networks via implicit normalization", "counterfactual_graft"),
            ]
            for alg in algorithms[:2]:
                for axis, mechanism, ptype in diverse_axes[:3]:
                    proposals.append({
                        "violated_boundary": f"{alg.lower()}_convention",
                        "primitive_a": alg,
                        "primitive_b": axis,
                        "counterfactual": f"What if we apply {axis} ({mechanism}) to {alg}?",
                        "potential_breakthrough": f"{axis} for {alg}: {mechanism}",
                    })
                    proposals.append({
                        "source_primitive": alg,
                        "target_domain": axis,
                        "isomorphic_relation": mechanism,
                        "confidence": 0.3,
                    })

        empty = self.grid.get_empty_cells()
        if empty:
            for cell_key in random.sample(empty, min(3, len(empty))):
                parts = cell_key.split("+")
                proposals.append({
                    "violated_boundary": "unexplored_region",
                    "primitive_a": parts[0] if parts else "unknown",
                    "primitive_b": parts[1] if len(parts) > 1 else "unknown",
                    "counterfactual": f"Fill empty cell: {cell_key}",
                    "potential_breakthrough": f"Unexplored: {cell_key}",
                })

        return proposals[:15]

    def step_recomposer(self, grafted_materials: dict, phase: str = "",
                        existing_proposals: list[dict] | None = None) -> list[dict]:
        """STEP_Recomposer: 三阶段创造性重组。

        DIVERGENT: 每个边界违规生成一个候选 (强制结构多样性)
        CONVERGENT: 为每个候选构建具体调和机制 (强制技术多样性)
        FILTER: 移除同质化提案 (Jaccard 去重)
        """
        # Stage 1: DIVERGENT — 每边界一候选
        candidates = self._divergent_generate(grafted_materials)
        if not candidates:
            candidates = self._legacy_recompose(grafted_materials)

        # Stage 2: CONVERGENT — 构建调和机制
        reconciled = self._convergent_reconcile(candidates, grafted_materials)

        # Stage 3: FILTER — 去重
        existing = existing_proposals or []
        filtered = self._filter_homogeneous(reconciled, existing)

        return filtered

    def _divergent_generate(self, materials: dict) -> list[dict]:
        """DIVERGENT: 每边界违规 + 跨域同构各生成候选。最少 3 个。"""
        grafts = materials.get("grafts", [])
        boundaries = materials.get("violable_boundaries", [])
        mappings = materials.get("mappings", [])
        sme_mappings = materials.get("sme_mappings", [])
        primitives = materials.get("primitives", [])
        candidates = []
        seen_boundaries = set()

        # Source 1: CC-internal grafts
        for graft in grafts:
            boundary = graft.get("violated_boundary", graft.get("boundary", ""))
            if not boundary:
                boundary = f"{graft.get('primitive_a','')}-{graft.get('primitive_b','')}"
            if boundary in seen_boundaries:
                continue
            seen_boundaries.add(boundary)
            candidates.append(self._make_graft_candidate(graft, boundary))

        # Source 2: CC-internal mappings
        for mapping in mappings:
            mp_key = f"map:{mapping.get('source_primitive','')}-{mapping.get('target_domain','')}"
            if mp_key in seen_boundaries:
                continue
            seen_boundaries.add(mp_key)
            candidates.append(self._make_mapping_candidate(mapping, mp_key))

        # Source 3: SME cross-domain isomorphisms
        for sme in sme_mappings:
            sme_key = f"sme:{sme.get('source_domain','')}-{sme.get('target_domain','')}"
            if sme_key in seen_boundaries:
                continue
            seen_boundaries.add(sme_key)
            candidates.append(self._make_sme_candidate(sme, sme_key))

        # Source 4: Primitive-pair grafts (when CC sparse)
        if len(candidates) < 3 and len(primitives) >= 2:
            tag_groups: dict[str, list] = {}
            for p in primitives:
                for t in p.get("tags", []):
                    tag_groups.setdefault(t, []).append(p)
            unique_tags = list(tag_groups.keys())
            for i in range(min(len(unique_tags), 4)):
                for j in range(i + 1, min(i + 3, len(unique_tags))):
                    pa = tag_groups[unique_tags[i]][0]
                    pb = tag_groups[unique_tags[j]][0]
                    boundary = f"{unique_tags[i]}×{unique_tags[j]}"
                    if boundary in seen_boundaries:
                        continue
                    seen_boundaries.add(boundary)
                    candidates.append({
                        "title": f"Cross-Tag: {pa.get('title','?')[:30]} × {pb.get('title','?')[:30]}",
                        "hypothesis": f"Combining {unique_tags[i]} with {unique_tags[j]} creates a novel synthesis",
                        "method_sketch": f"1. Extract {unique_tags[i]} mechanism from {pa.get('title','?')}\n2. Adapt to {unique_tags[j]} domain of {pb.get('title','?')}\n3. Test hybrid",
                        "primitives_used": [pa.get("title", ""), pb.get("title", "")],
                        "novelty_claim": f"Cross-domain combination of {unique_tags[i]} × {unique_tags[j]}",
                        "proposal_type": "counterfactual_graft",
                        "violated_boundary": boundary,
                    })

        # Ensure minimum: borrow SME if still too few
        if len(candidates) < 3 and sme_mappings:
            for sme in sme_mappings:
                for concept_domain in ["reinforcement_learning", "information_theory", "causal_inference"]:
                    alt_key = f"sme-alt:{concept_domain}-{sme.get('target_domain','')}"
                    if alt_key in seen_boundaries:
                        continue
                    seen_boundaries.add(alt_key)
                    candidates.append({
                        "title": f"SME-Discover: {concept_domain} insights for {sme.get('target_domain','')}",
                        "hypothesis": f"Structural analogy between {concept_domain} and {sme.get('target_domain','')}",
                        "method_sketch": f"1. Map {concept_domain} structural patterns\n2. Adapt to {sme.get('target_domain','')}\n3. Test transferred mechanism",
                        "primitives_used": [concept_domain, sme.get("target_domain", "")],
                        "novelty_claim": f"Cross-domain SME discovery: {concept_domain} → {sme.get('target_domain','')}",
                        "proposal_type": "structural_mapping",
                        "violated_boundary": alt_key,
                    })
                    break

        return candidates

    def _make_graft_candidate(self, graft: dict, boundary: str) -> dict:
        return {
            "title": f"Graft: {graft.get('primitive_a', '?')} × {graft.get('primitive_b', '?')}",
            "hypothesis": graft.get("potential_breakthrough", graft.get("counterfactual", "")),
            "method_sketch": (
                f"1. Base: {graft.get('primitive_a', '?')} establishes baseline\n"
                f"2. Violate: deliberately violate '{boundary}'\n"
                f"3. Counterfactual: {graft.get('counterfactual', 'explore what happens when the boundary does not hold')}\n"
                f"4. Reconcile: find a mechanism from another domain that naturally handles the violation\n"
                f"5. Compare vs baseline to quantify the effect"
            ),
            "primitives_used": [graft.get("primitive_a", ""), graft.get("primitive_b", "")],
            "novelty_claim": f"Cross-domain graft via deliberate violation of '{boundary}'",
            "proposal_type": "counterfactual_graft",
            "violated_boundary": boundary,
        }

    def _make_mapping_candidate(self, mapping: dict, mp_key: str) -> dict:
        return {
            "title": f"Map: {mapping.get('source_primitive', '?')} → {mapping.get('target_domain', '?')}",
            "hypothesis": mapping.get("isomorphic_relation", ""),
            "method_sketch": (
                f"1. Analyze what makes {mapping.get('source_primitive', '?')} work\n"
                f"2. Map isomorphic relational structure to {mapping.get('target_domain', '?')}\n"
                f"3. Adapt the mapped mechanism to the target domain's constraints\n"
                f"4. Test whether the structural analogy transfers"
            ),
            "primitives_used": [mapping.get("source_primitive", "")],
            "novelty_claim": f"Isomorphic cross-domain mapping (confidence: {mapping.get('confidence', 'N/A')})",
            "proposal_type": "structural_mapping",
            "violated_boundary": mp_key,
        }

    def _make_sme_candidate(self, sme: dict, sme_key: str) -> dict:
        src_pat = " × ".join(sme.get("source_pattern", ["?"])[:2])
        tgt_pat = " × ".join(sme.get("target_pattern", ["?"])[:2])
        return {
            "title": f"SME: {sme.get('source_domain','?')}/{src_pat} → {sme.get('target_domain','?')}/{tgt_pat}",
            "hypothesis": sme.get("interpretation", ""),
            "method_sketch": (
                f"1. Identify: {sme.get('source_pattern', ['?'])[0]} → {sme.get('target_pattern', ['?'])[0]}\n"
                f"2. Map via: {sme.get('isomorphic_relation_chain', 'structural homology')}\n"
                f"3. Adapt: {sme.get('target_pattern', ['?'])[-1] if sme.get('target_pattern') else 'mechanism'}\n"
                f"4. Test cross-domain transfer"
            ),
            "primitives_used": sme.get("source_pattern", []) + sme.get("target_pattern", []),
            "novelty_claim": f"SME-discovered cross-domain isomorphism ({sme.get('type','structural')}, confidence={sme.get('confidence',0):.2f})",
            "proposal_type": "structural_mapping",
            "violated_boundary": sme_key,
        }

    def _convergent_reconcile(self, candidates: list[dict], materials: dict) -> list[dict]:
        """CONVERGENT: 为每个候选构建具体调和机制。

        调和机制是使边界违规可行的具体技术方案。
        必须引用 SME 跨域同构中的具体技术。
        """
        sme_mappings = materials.get("sme_mappings", [])
        primitives = materials.get("primitives", [])

        for candidate in candidates:
            reconciliation = ""

            # 策略1: 从 SME mappings 借用机制
            for sme_map in sme_mappings[:5]:
                if sme_map.get("type", "") in ("cyclic_3node", "control", "functional_isomorphism"):
                    source = sme_map.get("source_pattern", [])
                    target = sme_map.get("target_pattern", [])
                    reconciliation = (
                        f"Reconcile via {sme_map.get('cross_domain_name', sme_map.get('type', 'SME'))}: "
                        f"the {'→'.join(source[:2])} → {'→'.join(target[:2])} isomorphism suggests "
                        f"using {target[-1] if target else 'the mapped mechanism'} "
                        f"to handle the boundary violation naturally"
                    )
                    break

            # 策略2: 从 primitives 找互补机制
            if not reconciliation and len(primitives) >= 2:
                a = primitives[0].get("title", primitives[0].get("name", "A"))
                b = primitives[-1].get("title", primitives[-1].get("name", "B"))
                reconciliation = (
                    f"Reconcile via complementary primitives: "
                    f"'{a}' provides the foundation; "
                    f"'{b}' supplies the mechanism to handle the boundary violation"
                )

            # 策略3: 通用调和
            if not reconciliation:
                reconciliation = (
                    "Reconcile via progressive constraint relaxation: "
                    "start with strict boundary, gradually relax, measure the trade-off curve, "
                    "identify the Pareto-optimal point where violation yields net positive gain"
                )

            candidate["reconciliation_mechanism"] = reconciliation
            # 扩展 method_sketch 加入调和步骤
            candidate["method_sketch"] += f"\n5. Reconciliation: {reconciliation}"

        return candidates

    def _filter_homogeneous(self, proposals: list[dict], existing: list[dict],
                           similarity_threshold: float = 0.6) -> list[dict]:
        """FILTER: 移除过于相似的提案 (Jaccard 去重)。"""
        if len(proposals) <= 1:
            return proposals

        kept = []
        for i, p in enumerate(proposals):
            p_tags = set(self._extract_tags_from_proposal(p))
            is_duplicate = False

            # 与已保留的比较
            for k in kept:
                k_tags = set(self._extract_tags_from_proposal(k))
                if p_tags and k_tags:
                    inter = len(p_tags & k_tags)
                    union = len(p_tags | k_tags)
                    sim = inter / max(union, 1)
                    if sim > similarity_threshold:
                        is_duplicate = True
                        break

            # 与已存在的比较
            if not is_duplicate:
                for e in existing:
                    e_tags = set(self._extract_tags_from_proposal(e))
                    if p_tags and e_tags:
                        inter = len(p_tags & e_tags)
                        union = len(p_tags | e_tags)
                        sim = inter / max(union, 1)
                        if sim > similarity_threshold:
                            is_duplicate = True
                            break

            if not is_duplicate:
                kept.append(p)

        return kept

    def _legacy_recompose(self, grafted_materials: dict) -> list[dict]:
        """Legacy recomposer: 当无边界/grafts 时的后备格式化。"""
        proposals = []
        for graft in grafted_materials.get("grafts", []):
            proposals.append({
                "title": f"Graft: {graft.get('primitive_a', '?')} × {graft.get('primitive_b', '?')}",
                "hypothesis": graft.get("potential_breakthrough", ""),
                "method_sketch": f"Base: {graft.get('primitive_a', '?')}\nViolate: {graft.get('violated_boundary', 'unknown')}\nCounterfactual: {graft.get('counterfactual', 'TBD')}",
                "primitives_used": [graft.get("primitive_a", ""), graft.get("primitive_b", "")],
                "novelty_claim": f"Cross-domain graft via {graft.get('violated_boundary', 'unknown')}",
                "proposal_type": "counterfactual_graft",
            })
        for mapping in grafted_materials.get("mappings", []):
            proposals.append({
                "title": f"Map: {mapping.get('source_primitive', '?')} → {mapping.get('target_domain', '?')}",
                "hypothesis": mapping.get("isomorphic_relation", ""),
                "method_sketch": f"Map structural analogy from {mapping.get('source_primitive', '?')} to {mapping.get('target_domain', '?')}",
                "primitives_used": [mapping.get("source_primitive", "")],
                "novelty_claim": f"Isomorphic mapping (confidence: {mapping.get('confidence', 'N/A')})",
                "proposal_type": "structural_mapping",
            })
        return proposals

    def step_evaluator(self, proposal: dict) -> dict:
        """STEP_Evaluator: 三条公理判别 (可计算，不依赖 LLM)。

        proposal: {title, hypothesis, method_sketch, primitives_used, violated_boundary, proposal_type}

        三公理:
        - Self-Recognition: Jaccard tag 重叠检查 (>0.4 → pseudo)
        - Paraphrase Invariance: 关键词组合唯一性 + 抽象结构稳定性
        - Cumulative Property: 是否填补 CC/Grid 的空白或解决矛盾
        """
        sr = self._compute_self_recognition(proposal)
        pi = self._compute_paraphrase_invariance(proposal)
        cp = self._compute_cumulative_property(proposal)

        scores = [sr["score"], pi["score"], cp["score"]]
        passed = [sr["verdict"] == "novel", pi["verdict"] == "novel", cp["verdict"] == "novel"]

        if all(passed):
            overall = "novel"
        elif sum(passed) >= 2:
            overall = "borderline"
        else:
            overall = "pseudo"

        return {
            "proposal": proposal.get("title", ""),
            "axioms": {
                "self_recognition": sr,
                "paraphrase_invariance": pi,
                "cumulative_property": cp,
            },
            "verdict": overall,
            "scores": scores,
            "passed": passed,
            "requires_llm_review": (overall == "borderline"),
        }

    def _compute_self_recognition(self, proposal: dict) -> dict:
        """Self-Recognition 公理: 结构重叠检查 (无 LLM)。

        Jaccard 相似度 = |proposal_tags ∩ existing_tags| / |proposal_tags ∪ existing_tags|
        阈值: >0.4 → pseudo (与已有知识太相似)
        """
        proposal_tags = set(self._extract_tags_from_proposal(proposal))

        atoms = self.cc.get_atoms(limit=200)
        max_similarity = 0.0
        most_similar_title = ""

        for atom in atoms:
            atom_tags = set(atom.get("tags", []))
            if not atom_tags and not proposal_tags:
                continue
            intersection = len(proposal_tags & atom_tags)
            union = len(proposal_tags | atom_tags)
            similarity = intersection / max(union, 1)
            if similarity > max_similarity:
                max_similarity = similarity
                most_similar_title = atom["title"]

        novelty_score = 1.0 - max_similarity

        return {
            "description": "检查新基元组合是否与已有基元图高度重叠 (Jaccard tag overlap)",
            "score": round(novelty_score, 4),
            "max_similarity_found": round(max_similarity, 4),
            "most_similar_existing": most_similar_title[:100],
            "overlap_threshold": 0.4,
            "verdict": "novel" if max_similarity <= 0.4 else "pseudo",
            "requires_llm": False,
        }

    def _extract_tags_from_proposal(self, proposal: dict) -> list[str]:
        """从 proposal 的多个字段提取代表性 tags。"""
        tags = set()
        for field in ["primitives_used", "tags"]:
            vals = proposal.get(field, [])
            if isinstance(vals, list):
                for v in vals:
                    tags.add(str(v).lower().replace(" ", "-")[:40])
        # 从 title 提取关键词
        title = proposal.get("title", "")
        for word in title.replace(":", " ").replace("×", " ").replace("→", " ").split():
            w = word.strip().lower()
            if len(w) > 2:
                tags.add(w)
        # 从 hypothesis 提取关键词
        hyp = proposal.get("hypothesis", "")
        for word in hyp.replace(":", " ").replace(";", " ").split():
            w = word.strip().lower()
            if len(w) > 3 and w not in ("that", "this", "will", "with", "from", "than"):
                tags.add(w[:30])
        return sorted(tags)[:50]

    def _compute_paraphrase_invariance(self, proposal: dict) -> dict:
        """Paraphrase Invariance 公理: 关键词组合唯一性检查。

        不依赖 LLM。检查:
        1. proposal 中的关键词组合是否在任一个 CC atom 中出现过
        2. primitives_used 的唯一性
        3. violated_boundary 的新颖性
        """
        proposal_tags = set(self._extract_tags_from_proposal(proposal))
        primitives = set(proposal.get("primitives_used", []))

        atoms = self.cc.get_atoms(limit=200)
        relations = self.cc.get_relations(limit=200)

        # 检查1: 关键词组合是否在 CC 中已出现?
        tag_overlap_count = 0
        for atom in atoms:
            atom_tags = set(atom.get("tags", []))
            common = proposal_tags & atom_tags
            if len(common) >= 3:  # 3个以上共同tag → 高度重叠
                tag_overlap_count += 1

        # 检查2: primitives 组合是否已存在?
        primitive_uniqueness = 1.0
        existing_primitive_sets = []
        for atom in atoms:
            existing_primitive_sets.append(set(atom.get("tags", [])))

        if primitives:
            max_prim_overlap = 0.0
            for eps in existing_primitive_sets:
                intersection = len(primitives & eps)
                union = len(primitives | eps)
                overlap = intersection / max(union, 1)
                max_prim_overlap = max(max_prim_overlap, overlap)
            primitive_uniqueness = 1.0 - max_prim_overlap

        # 检查3: violated_boundary 是否是新提出的?
        violated_boundary = proposal.get("violated_boundary", "")
        boundary_in_cc = False
        if violated_boundary:
            for r in relations:
                if r["type"] == "boundary_of":
                    evidence = r.get("evidence", "").lower()
                    if any(kw in evidence for kw in violated_boundary.lower().split()):
                        boundary_in_cc = True
                        break

        # 综合分数
        uniqueness_score = (
            (1.0 if tag_overlap_count == 0 else max(0, 1.0 - tag_overlap_count * 0.15)) * 0.4 +
            primitive_uniqueness * 0.4 +
            (1.0 if not boundary_in_cc else 0.5) * 0.2
        )

        return {
            "description": "换多种表述后重新拆解，检查关键词组合唯一性 + primitives 组合新颖性",
            "score": round(uniqueness_score, 4),
            "tag_overlap_count": tag_overlap_count,
            "primitive_uniqueness": round(primitive_uniqueness, 4),
            "boundary_already_in_cc": boundary_in_cc,
            "stability_threshold": 0.5,
            "verdict": "novel" if uniqueness_score >= 0.5 else "borderline",
            "requires_llm": False,
        }

    def _compute_cumulative_property(self, proposal: dict) -> dict:
        """Cumulative Property 公理: 是否填补 CC/Grid 空白或解决矛盾。

        检查:
        1. 目标空 cell? (Grid 中有对应的未探索区域)
        2. 创建缺失的 CC atom 类型? (method/theorem/verification)
        3. 解决已知矛盾? (CC 中的 contradicts 关系)
        4. 扩展已知边界? (CC 中的 boundary_of 关系)
        分数 = addressed_points / 4
        """
        addressed_gaps = []
        resolved_contradictions = []

        # 检查1: 目标空 cell?
        empty_cells = self.grid.get_empty_cells()
        proposal_tags = set(self._extract_tags_from_proposal(proposal))
        for cell_key in empty_cells[:30]:
            cell_parts = set(cell_key.split("+"))
            if any(tag.lower() in part.lower() for tag in proposal_tags for part in cell_parts):
                addressed_gaps.append(f"targets_empty_cell:{cell_key}")
                break

        # 检查2: 创建缺失的 CC atom 类型?
        cc_summary = self.cc.get_graph_summary()
        existing_types = set(cc_summary.get("atom_types", {}).keys())
        proposal_type = proposal.get("proposal_type", "")
        if proposal_type in ("counterfactual_graft", "structural_mapping") and "method" not in existing_types:
            addressed_gaps.append("creates_missing_cc_type:method")
        if proposal_type == "structural_mapping" and "theorem" not in existing_types:
            addressed_gaps.append("creates_missing_cc_type:theorem")

        # 检查3: 解决已知矛盾?
        relations = self.cc.get_relations(limit=200)
        contradictions = [r for r in relations if r["type"] == "contradicts"]
        proposal_primitives = set(proposal.get("primitives_used", []))
        for c in contradictions:
            src = self.cc.get_atom(c["source_id"])
            tgt = self.cc.get_atom(c["target_id"])
            if src and tgt:
                c_tags = set(src.get("tags", []) + tgt.get("tags", []))
                if proposal_primitives & c_tags:
                    resolved_contradictions.append(f"{src['title'][:50]} vs {tgt['title'][:50]}")
                    break

        # 检查4: 扩展已知边界?
        boundaries = [r for r in relations if r["type"] == "boundary_of"]
        proposal_boundary = proposal.get("violated_boundary", "")
        for b in boundaries:
            b_atom = self.cc.get_atom(b["source_id"])
            if b_atom and proposal_boundary:
                b_tags = set(b_atom.get("tags", []))
                if any(tag in proposal_boundary for tag in b_tags):
                    addressed_gaps.append(f"extends_boundary:{b_atom['title'][:50]}")
                    break

        addressed_count = len(set(addressed_gaps))
        score = addressed_count / 4.0

        return {
            "description": "检查新概念是否真正填补 CC/Grid 空白或解决已知矛盾",
            "score": round(score, 4),
            "addressed_gaps": addressed_gaps,
            "resolved_contradictions": resolved_contradictions,
            "cumulative_threshold": 0.25,
            "verdict": "novel" if score >= 0.25 else "pseudo",
            "requires_llm": False,
        }

    # ── Web reconnaissance helpers ──

    def _build_search_queries(self, phase: str, state: dict) -> list[str]:
        """根据阶段和 CC 当前状态生成搜索查询。"""
        topic = state.get("research_topic", "")
        queries = [f"Latest advances in {topic} 2024-2025"]

        if phase == PHASE_PLAN:
            queries.append("Novel actor-critic improvements beyond hyperparameter tuning")
            queries.append("Creative reinforcement learning techniques for continuous control")
        elif phase == PHASE_RESEARCH:
            queries.append("SOTA continuous control RL techniques beyond DDPG SAC TD3")
        elif phase == PHASE_IDEATE:
            gap = state.get("last_gap_analysis")
            if gap:
                queries.append(f"How to improve RL agent from {gap.get('best_score')} to {gap.get('target_score')}")
            queries.append("Novel exploration strategies for actor-critic methods")

        return queries[:5]

    # ── Auto-ingest helpers ──

    def _auto_ingest_results(self) -> list[dict]:
        """自动扫描 workspace 结果文件，构建 experiment_results 格式。"""
        results = []

        # Strategy 1: summary.json in results subdirectories
        for subdir in ["ablation", "ablation_v2"]:
            summary = self.workspace / "results" / subdir / "summary.json"
            if summary.exists():
                try:
                    entries = json.loads(summary.read_text(encoding="utf-8"))
                    if isinstance(entries, list):
                        for e in entries:
                            variant = e.get("variant", "unknown")
                            score = e.get("mean_final_reward", 0) or e.get("mean_reward", 0)
                            std = e.get("std_final_reward", 0) or e.get("std_reward", 0)
                            results.append({
                                "variant_id": variant,
                                "score": score,
                                "descriptor": {
                                    "method_family": self._classify_family(variant),
                                    "improvement_axis": self._classify_axis(variant),
                                },
                                "std": std,
                            })
                except Exception:
                    continue

        if results:
            return results

        # Strategy 2: Individual seed result JSON files
        results_dir = self.workspace / "results"
        if results_dir.exists():
            for json_file in sorted(results_dir.rglob("*.json")):
                if "summary" in json_file.name or "seed" not in json_file.name:
                    continue
                try:
                    data = json.loads(json_file.read_text(encoding="utf-8"))
                    evals = data.get("eval_results", [])
                    if evals:
                        score = evals[-1].get("mean_reward", 0)
                        variant = data.get("variant", json_file.stem)
                        results.append({
                            "variant_id": f"{variant}_seed{data.get('seed', 0)}",
                            "score": score,
                            "descriptor": {
                                "method_family": self._classify_family(variant),
                                "improvement_axis": self._classify_axis(variant),
                            },
                        })
                except Exception:
                    continue

        return results

    @staticmethod
    def _classify_family(name: str) -> str:
        name = name.lower()
        for f in ["ppo", "sac", "td3", "ddpg", "a2c", "a3c"]:
            if f in name:
                return f.upper()
        return "unknown"

    @staticmethod
    def _classify_axis(name: str) -> str:
        name = name.lower()
        if "twin" in name or "double" in name:
            return "training_tricks"
        if "per" in name or "prioritized" in name:
            return "training_tricks"
        if "param_noise" in name or "noise" in name:
            return "exploration_strategy"
        if "combined" in name:
            return "training_tricks"
        return "network_architecture"

    # ── Dashboard event posting ──

    def _post_to_dashboard(self, session_id: str, event_type: str, data: dict):
        """推送事件到 Dashboard SSE 流（非关键，失败静默）。"""
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


# ═══════════════════════════════════════════════════════════════════
# 工具函数 (不再作为 MCP Server 暴露)
# ═══════════════════════════════════════════════════════════════════

from pipeline_protocol import atomic_read, atomic_write, dashboard_write, dashboard_write_approval

_controller: PESController | None = None


def get_controller(workspace_dir: str = "", session_id: str = "") -> PESController:
    global _controller
    if _controller is None and workspace_dir:
        _controller = PESController(workspace_dir, session_id=session_id)
    elif _controller is None:
        _controller = PESController(os.getcwd(), session_id=session_id)
    return _controller


def _start_http_server(port: int = 8421):
    """启动 HTTP 服务器供 Dashboard 调用阶段流转 (保留兼容)。"""
    from http.server import HTTPServer, BaseHTTPRequestHandler

    class TransitionHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path == "/api/transition":
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length)) if length else {}
                workspace = body.get("workspace_dir", os.getcwd())
                action = body.get("action", "satisfied")
                try:
                    ctrl = get_controller(workspace)
                    result = ctrl.transition_phase(action)
                    code = 200
                except Exception as e:
                    result = {"error": str(e)}
                    code = 500
                payload = json.dumps(result, ensure_ascii=False).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("0.0.0.0", port), TransitionHandler)
    print(f"[PES HTTP] Listening on port {port} for Dashboard transitions")
    server.serve_forever()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="PES Controller (非 MCP, Dashboard 直调)")
    parser.add_argument("--test", action="store_true", help="Print phase/chains/transitions")
    args = parser.parse_args()

    if args.test:
        print("PES Controller — Dashboard 直驱模式")
        print(f"\nPhases: {PHASES}")
        print(f"\nCHAIN_STEPS:")
        for k, v in CHAIN_STEPS.items():
            print(f"  {k}: {v}")
        print(f"\nTRANSITIONS:")
        for k, v in TRANSITIONS.items():
            print(f"  {k} → {v}")
    else:
        import threading
        http_thread = threading.Thread(target=_start_http_server, daemon=True)
        http_thread.start()
        http_thread.join()


if __name__ == "__main__":
    main()
