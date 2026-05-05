"""PESController: 单一状态机 + 五步渐进式发现管线 + MCP Server。

MCP Tools (6):
  mcp__pes_controller__init       — 初始化工作空间
  mcp__pes_controller__resume     — 崩溃恢复
  mcp__pes_controller__state      — 状态快照
  mcp__pes_controller__pre_loop   — 状态切换准备 (基础状态管理)
  mcp__pes_controller__sub_loop   — 分步返回执行步骤
  mcp__pes_controller__post_loop  — 提交结果 + 用户确认

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

PHASE_PLAN = "方案提出"
PHASE_RESEARCH = "文献调研"
PHASE_ELO = "ELO筛选"
PHASE_EXECUTE = "实验执行"
PHASE_ANALYZE = "结果分析"
PHASE_WRITE = "论文写作"
PHASE_WRITE_REVIEW = "论文审阅"
PHASE_TERMINATED = "已终止"

PHASES = [PHASE_PLAN, PHASE_RESEARCH, PHASE_ELO, PHASE_EXECUTE,
          PHASE_ANALYZE, PHASE_WRITE, PHASE_WRITE_REVIEW]

# Phase transitions (from → [legal next])
TRANSITIONS = {
    PHASE_PLAN:          [PHASE_RESEARCH],
    PHASE_RESEARCH:      [PHASE_ELO],
    PHASE_ELO:           [PHASE_EXECUTE],
    PHASE_EXECUTE:       [PHASE_ANALYZE],
    PHASE_ANALYZE:       [PHASE_PLAN, PHASE_RESEARCH, PHASE_ELO, PHASE_EXECUTE, PHASE_WRITE],
    PHASE_WRITE:         [PHASE_WRITE_REVIEW, PHASE_PLAN],
    PHASE_WRITE_REVIEW:  [PHASE_WRITE, PHASE_PLAN, PHASE_TERMINATED],
}

# Execution chain steps per phase
# run_step_pipeline: Python internal CLI→Indexing→Decomposer→Recomposer→Evaluator
CHAIN_STEPS = {
    PHASE_PLAN: [
        "web_reconnaissance", "run_step_pipeline", "multi_agent_discuss",
        "elo_tournament", "evolution_memory",
    ],
    PHASE_RESEARCH: [
        "web_reconnaissance", "run_step_pipeline", "multi_agent_discuss",
        "elo_tournament", "evolution_memory",
        "invoke_skill_research", "write_claim_chain",
    ],
    PHASE_ELO: [
        "web_reconnaissance", "run_step_pipeline", "multi_agent_discuss",
        "elo_tournament", "evolution_memory",
    ],
    PHASE_EXECUTE: [
        "invoke_skill_code", "wait_external",
    ],
    PHASE_ANALYZE: [
        "run_step_pipeline", "ingest_results", "scan_islands_rubrics",
        "multi_agent_discuss", "evolution_memory",
        "write_claim_chain", "island_assign",
    ],
    PHASE_WRITE:         ["invoke_skill_write"],
    PHASE_WRITE_REVIEW:  ["invoke_skill_review"],
}

# Agent roles per phase
AGENT_ROLES = {
    PHASE_PLAN:          ["planner", "researcher", "analyst"],
    PHASE_RESEARCH:      ["researcher", "planner", "analyst"],
    PHASE_ELO:           ["planner", "researcher", "analyst"],
    PHASE_ANALYZE:       ["analyst", "planner", "researcher"],
    PHASE_WRITE:         ["writer"],
    PHASE_WRITE_REVIEW:  ["writer"],
}


class PESController:
    """单一状态机 + 五步渐进式发现管线。"""

    def __init__(self, workspace_dir: str | Path):
        self.workspace = Path(workspace_dir)
        self.state_path = self.workspace / "PIPELINE_STATE.json"
        self.cc = ClaimChain(self.workspace)
        self.grid = CellGrid(self.workspace / "evolve_archive")
        self.rubric = RubricScheduler(self.cc)
        self.islands = IslandManager(self.workspace / "evolve_archive")
        self.fitness = FitnessTracker(self.workspace)

    # ═══════════════════════════════════════════════════════════════
    # 状态读写
    # ═══════════════════════════════════════════════════════════════

    def _read_state(self) -> dict:
        if not self.state_path.exists():
            return {
                "phase": PHASE_PLAN,
                "iteration": 0,
                "sub_loop_step": 0,
                "status": "not_initialized",
                "timestamp": None,
                "session_id": None,
                "config": {},
            }
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _write_state(self, state: dict):
        state["timestamp"] = time.time()
        self.state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))

    def _legal_next(self, phase: str) -> list[str]:
        return TRANSITIONS.get(phase, [])

    # ═══════════════════════════════════════════════════════════════
    # MCP Tool: init
    # ═══════════════════════════════════════════════════════════════

    def init(self, research_topic: str, part2_dimensions: list[dict] | None = None) -> dict:
        """初始化工作空间。"""
        # 目录结构
        for d in ["claim_chain", "evolve_archive", "memory", "artifacts"]:
            (self.workspace / d).mkdir(parents=True, exist_ok=True)

        # Claim Chain (空)
        self.cc.get_graph_summary()

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
            "needs_session": True,
            "needs_intake": True,
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
            PHASE_PLAN: "基于 Claim Chain 先验，多Agent 讨论制定实验计划",
            PHASE_RESEARCH: "按计划方向调研文献，收集真实论文数据",
            PHASE_ELO: "多Agent 方案构思 + ELO 锦标赛筛选",
            PHASE_EXECUTE: "单Agent 代码实现 + 等待用户运行实验",
            PHASE_ANALYZE: "多Agent 结果分析 + Rubrics 评分 + Island 分配",
            PHASE_WRITE: "撰写论文报告，汇总所有实验发现",
            PHASE_WRITE_REVIEW: "外部 LLM 审阅论文，迭代修改直到通过",
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
        """加载 Evolution Memory 概要。"""
        em_path = self.workspace / "memory" / "evolution_memory.jsonl"
        if not em_path.exists():
            return {"last_ide_session": None, "prior_failures": []}

        entries = []
        with open(em_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        ide_entries = [e for e in entries if e.get("type") in ("ide", "IDE")]
        failure_entries = [e for e in entries
                          if e.get("type") in ("ive", "IVE") and
                          e.get("metadata", {}).get("outcome") == "contradicted"]

        return {
            "last_ide_session": ide_entries[-1].get("summary", "") if ide_entries else None,
            "prior_failures": [e.get("summary", "") for e in failure_entries[-3:]],
        }

    def _generate_user_prompt(self, state: dict) -> str:
        phase = state["phase"]
        iteration = state["iteration"]
        fs = self.fitness.get_stats()
        best = fs.get("global", {}).get("max_score", 0)
        ft = self.fitness.get_trend()

        prompts = {
            PHASE_PLAN: f"第{iteration+1}轮·方案提出。当前最佳{best:.1f}，趋势{ft['direction']}。是否继续？",
            PHASE_RESEARCH: f"第{iteration+1}轮·文献调研。请确认调研方向。",
            PHASE_ELO: f"第{iteration+1}轮·方案筛选。ELO 锦标赛将排序候选方案。",
            PHASE_EXECUTE: f"第{iteration+1}轮·实验执行。准备生成代码。",
            PHASE_ANALYZE: f"第{iteration+1}轮·结果分析。当前最佳{best:.1f}。",
            PHASE_WRITE: f"论文写作。基于实验结果撰写报告。",
            PHASE_WRITE_REVIEW: f"论文审阅。外部审阅将评估报告质量。",
        }
        return prompts.get(phase, f"当前阶段: {phase}")

    # ═══════════════════════════════════════════════════════════════
    # MCP Tool: sub_loop
    # ═══════════════════════════════════════════════════════════════

    def sub_loop(self) -> dict:
        """分步返回：每次调用返回当前阶段的下一个执行步骤。"""
        state = self._read_state()
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
            # Execute 5 STEP pipeline internally: CLI → Indexing → Decomposer → Recomposer → Evaluator
            primary_agent = agents[0] if agents else "planner"
            cli_result = self.step_cli("summary")
            indexing_result = self.step_indexing(phase, primary_agent)
            decomposer_result = self.step_decomposer()
            recomposer_result = self.step_recomposer(decomposer_result, phase)
            evaluator_results = []
            for proposal in recomposer_result:
                evaluator_results.append(self.step_evaluator(proposal))

            context_bundle = {
                "cli_summary": cli_result,
                "indexing": indexing_result,
                "primitives": decomposer_result.get("primitives", []),
                "relation_patterns": decomposer_result.get("relation_patterns", {}),
                "violable_boundaries": decomposer_result.get("violable_boundaries", []),
                "proposals": recomposer_result,
                "evaluation": evaluator_results,
                "exploration_guidance": decomposer_result.get("exploration_guidance", {}),
            }

            state["last_pipeline_context"] = context_bundle
            self._write_state(state)

            self._post_to_dashboard(
                state.get("session_id", ""), "pipeline_step_completed",
                {"phase": phase, "proposals_count": len(recomposer_result),
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
                    f"4. 三公理评估：自识别 + 复述不变性 + 累积性"
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
            distill_type = {"方案提出": "ide", "文献调研": "ive",
                           "ELO筛选": "ide", "结果分析": "ese"}.get(phase, "ide")
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

        elif step_name == "invoke_skill_code":
            return {
                "done": False,
                "phase": phase,
                "step": step_name,
                "step_index": state.get("sub_loop_step", 0) - 1,
                "action": "invoke_skill",
                "skill": "/evo-code",
                "argument": "基于plan.md实现实验代码。单Agent模式。",
            }

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
    # MCP Tool: post_loop
    # ═══════════════════════════════════════════════════════════════

    def post_loop(self, satisfied: bool, chosen_next_phase: str = "",
                  notes: str = "", cc_atoms: list[dict] | None = None,
                  experiment_results: list[dict] | None = None) -> dict:
        """提交阶段结果 + 用户确认。按规则写入CC/Cell Grid/Evolution Memory/Island。"""
        state = self._read_state()
        phase = state["phase"]

        if not satisfied:
            if phase == PHASE_WRITE_REVIEW:
                state["phase"] = PHASE_WRITE
                state["sub_loop_step"] = 0
                self._write_state(state)
                return {"advanced": False, "next_phase": PHASE_WRITE,
                        "message": "审阅未通过，回到论文写作阶段修改。"}
            state["sub_loop_step"] = 0
            self._write_state(state)
            return {"advanced": False, "next_phase": phase,
                    "message": "用户不满意，回到同一阶段重新执行。"}

        # 用户满意 → 实际写入
        events = []

        if phase == PHASE_RESEARCH and cc_atoms:
            # 写入 CC: 真实文献原子（仅来自真实论文，非 LLM 推测）
            for atom_data in cc_atoms:
                atom_type = atom_data.get("type", "fact")
                title = atom_data.get("title", "")
                content = atom_data.get("content", "")
                tags = atom_data.get("tags", [])
                self.cc.add_atom(type=atom_type, title=title, content=content, tags=tags)
            cc_summary = self.cc.get_graph_summary()
            events.append(f"claim_chain_updated: {len(cc_atoms)} literature atoms written, total: {cc_summary.get('atom_count', 0)}")

        elif phase == PHASE_ANALYZE:
            # 写入 CC: 真实实验结果
            if cc_atoms:
                for atom_data in cc_atoms:
                    self.cc.add_atom(
                        type=atom_data.get("type", "verification"),
                        title=atom_data.get("title", ""),
                        content=atom_data.get("content", ""),
                        tags=atom_data.get("tags", []),
                    )
                events.append(f"claim_chain_updated: {len(cc_atoms)} experiment result atoms written")

            # 记录 fitness + Island 分配
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

        # Gap 分析 (仅 W5 Analyze)
        gap_analysis = None
        if phase == PHASE_ANALYZE:
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
                gap = 0
                gap_pct = 0
                target_met = False

            gap_analysis = {
                "target_score": target,
                "best_score": best,
                "gap": gap,
                "gap_percent": round(gap_pct, 1),
                "target_met": target_met,
                "cc_atom_count": cc_summary.get("total_atoms", 0),
                "grid_filled": coverage.get("filled", 0),
                "grid_total": coverage.get("total", 0),
                "iteration": state.get("iteration", 0),
            }

        # 确定下一阶段
        if chosen_next_phase:
            next_phase = chosen_next_phase
        elif phase == PHASE_ANALYZE:
            # 达标 → 写作；未达标 → 回到 W2 开始新一轮迭代
            target = self._read_success_target()
            fs = self.fitness.get_stats()
            best = fs.get("global", {}).get("max_score", 0)
            if target is not None and best >= target:
                next_phase = PHASE_WRITE
            else:
                next_phase = PHASE_PLAN
        elif phase == PHASE_WRITE:
            next_phase = PHASE_WRITE_REVIEW
        elif phase == PHASE_WRITE_REVIEW:
            next_phase = PHASE_TERMINATED
        else:
            legal = self._legal_next(phase)
            next_phase = legal[0] if legal else PHASE_TERMINATED

        # 更新状态
        state["phase"] = next_phase
        state["sub_loop_step"] = 0
        if phase == PHASE_ANALYZE:
            state["iteration"] = state.get("iteration", 0) + 1
        if gap_analysis:
            state["last_gap_analysis"] = gap_analysis

        self._write_state(state)

        msg = f"阶段 '{phase}' 完成。进入 '{next_phase}'。"
        if next_phase == PHASE_PLAN and phase == PHASE_ANALYZE:
            msg = f"第{state.get('iteration', 0)}轮迭代完成。未达标，回到方案提出。"
        elif next_phase == PHASE_WRITE:
            msg = "达标！进入论文写作阶段。"
        elif next_phase == PHASE_TERMINATED:
            msg = "管线完成。"

        return {
            "advanced": True,
            "next_phase": next_phase,
            "phase_completed": phase,
            "events": events,
            "gap_analysis": gap_analysis,
            "message": msg,
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
        """STEP_indexing: 结构化概要 + 自主探索建议。

        phase: "Plan"|"Research"|"Ideate"|"RubricsJudge"
        agent_role: "planner"|"researcher"|"analyst"
        """
        atoms = self.cc.get_atoms(limit=200)
        relations = self.cc.get_relations(limit=200)
        elites = self.grid.get_elites()
        empty_cells = self.grid.get_empty_cells()
        anomalies = self.grid.get_anomaly_cells()

        # 概要：按阶段侧重点不同
        if phase in ("Plan", PHASE_PLAN):
            # 发现研究残缺
            validated = [a for a in atoms if a["type"] == "method" and
                        any(r["type"] == "validates" and r["source_id"] == a["id"]
                            for r in relations)]
            contradicts = [r for r in relations if r["type"] == "contradicts"]
            summary = {
                "focus": "研究残缺",
                "validated_methods_count": len(validated),
                "contradicts_count": len(contradicts),
                "gaps": f"{len(empty_cells)} 个未探索cell",
            }
            suggested_queries = [
                "查询所有 validates 关系 — 哪些方法已被验证有效？",
                "查询所有 contradicts 关系 — 哪些方法已被证伪？",
                "查询 boundary_of 关系 — 已知参数边界在哪？",
            ]

        elif phase in ("Research", PHASE_RESEARCH):
            # 发现不确定性
            boundary_relations = [r for r in relations if r["type"] == "boundary_of"]
            contradicts = [r for r in relations if r["type"] == "contradicts"]
            summary = {
                "focus": "不确定性",
                "boundary_count": len(boundary_relations),
                "contradicts_count": len(contradicts),
                "uncertainty_zones": f"{len(anomalies)} 个异常cell待解决",
            }
            suggested_queries = [
                "查询所有 boundary_of 关系 — 哪些边界条件模糊？",
                "查询异常 cell 详情 — 同CC条件下为何性能差异巨大？",
                "查询文献来源的 fact 原子 — 有哪些外部参考？",
            ]

        elif phase in ("Ideate", "ELO筛选", PHASE_ELO):
            # 发现空白
            summary = {
                "focus": "空白",
                "empty_cells_count": len(empty_cells),
                "empty_cells_sample": empty_cells[:5],
                "elites_count": len(elites),
            }
            suggested_queries = [
                f"查询空 cell: {', '.join(empty_cells[:3]) if empty_cells else '全部已填充'}",
                "查询精英变体的 method 原子 — 哪些方向已验证成功？",
                "跨领域搜索：找与当前最优方法结构相似的相邻领域方法",
            ]

        elif phase in ("RubricsJudge", PHASE_ANALYZE):
            # 发现缺失评价维度
            summary = {
                "focus": "缺失评价维度",
                "anomaly_count": len(anomalies),
                "elites_count": len(elites),
                "active_dimensions": self.rubric.get_active_dimensions(),
            }
            suggested_queries = [
                "查询拥挤 cell — 哪些 cell 内有多个相近得分变体需要 Rubric 对比？",
                "查询当前活跃评分维度 — 是否有未覆盖的评估方面？",
                "查询 Island 摘要 — 哪些方法家族需要对比？",
            ]

        else:
            summary = {"focus": "general"}
            suggested_queries = ["查询 CC 摘要", "查询 Grid 覆盖率"]

        return {
            "summary": summary,
            "suggested_queries": suggested_queries,
            "agent_role": agent_role,
            "phase": phase,
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
        """CC 空时从研究主题 + Grid 维度生成保底提案。"""
        import random
        topic = state.get("research_topic", "")
        proposals = []

        algorithms = []
        for alg in ["ppo", "sac", "td3", "ddpg", "a2c", "a3c"]:
            if alg in topic.lower():
                algorithms.append(alg.upper())
        if not algorithms:
            algorithms = ["DDPG", "SAC", "TD3"]

        axes = ["network_architecture", "exploration_strategy", "training_tricks", "reward_shaping"]

        for alg in algorithms:
            for axis in axes:
                proposals.append({
                    "violated_boundary": f"{axis}_convention",
                    "primitive_a": alg,
                    "primitive_b": axis,
                    "counterfactual": f"What if we radically redesign {axis} for {alg}?",
                    "potential_breakthrough": f"Novel {axis} for {alg}",
                })

        for i in range(len(algorithms)):
            for j in range(i + 1, len(algorithms)):
                proposals.append({
                    "source_primitive": algorithms[i],
                    "target_domain": algorithms[j],
                    "isomorphic_relation": f"Both actor-critic; what works for {algorithms[i]} may transfer to {algorithms[j]}",
                    "confidence": 0.5,
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

    def step_recomposer(self, grafted_materials: dict, phase: str = "") -> list[dict]:
        """STEP_Recomposer: 将 Decomposer 原材料格式化为带具体步骤的方案。"""
        proposals = []

        for graft in grafted_materials.get("grafts", []):
            proposals.append({
                "title": f"Graft: {graft.get('primitive_a', '?')} × {graft.get('primitive_b', '?')}",
                "hypothesis": graft.get("potential_breakthrough", ""),
                "method_sketch": (
                    f"1. Base: {graft.get('primitive_a', '?')}\n"
                    f"2. Violate: {graft.get('violated_boundary', 'unknown')}\n"
                    f"3. Counterfactual: {graft.get('counterfactual', 'TBD')}\n"
                    f"4. Compare vs baseline"
                ),
                "primitives_used": [graft.get("primitive_a", ""), graft.get("primitive_b", "")],
                "novelty_claim": f"Cross-domain graft via {graft.get('violated_boundary', 'unknown')}",
                "proposal_type": "counterfactual_graft",
            })

        for mapping in grafted_materials.get("mappings", []):
            proposals.append({
                "title": f"Map: {mapping.get('source_primitive', '?')} → {mapping.get('target_domain', '?')}",
                "hypothesis": mapping.get("isomorphic_relation", ""),
                "method_sketch": (
                    f"1. Identify what works in {mapping.get('source_primitive', '?')}\n"
                    f"2. Map isomorphic structure to {mapping.get('target_domain', '?')}\n"
                    f"3. Adapt and test"
                ),
                "primitives_used": [mapping.get("source_primitive", "")],
                "novelty_claim": f"Isomorphic mapping (confidence: {mapping.get('confidence', 'N/A')})",
                "proposal_type": "structural_mapping",
            })

        for zone in grafted_materials.get("conflict_zones", []):
            proposals.append({
                "title": f"Resolve: {zone.get('atom_a', '?')} vs {zone.get('atom_b', '?')}",
                "hypothesis": zone.get("resolution_opportunity", ""),
                "method_sketch": "Reproduce conflict conditions → control variables → determine driver",
                "primitives_used": [zone.get("atom_a", ""), zone.get("atom_b", "")],
                "novelty_claim": "Conflict resolution experiment",
                "proposal_type": "conflict_resolution",
            })

        return proposals

    def step_evaluator(self, proposal: dict) -> dict:
        """STEP_Evaluator: 三条公理判别 (均通过 LLM，这里提供 Python 预提取的对比材料)。

        Proposal: {title, hypothesis, method_sketch, primitives_used}
        """
        # 从 CC 提取对比材料
        atoms = self.cc.get_atoms(limit=200)
        relations = self.cc.get_relations(limit=200)

        # self_recognition 材料: 已有基元图
        existing_primitives = []
        for a in atoms:
            if a["type"] in ("method", "fact"):
                existing_primitives.append({
                    "atom_id": a["id"],
                    "title": a["title"],
                    "tags": a.get("tags", []),
                    "content_snippet": a.get("content", "")[:150],
                })

        # cumulative_property 材料: contradicts + boundaries
        contradictions = [
            {"source_id": r["source_id"], "target_id": r["target_id"],
             "evidence": r.get("evidence", "")}
            for r in relations if r["type"] == "contradicts"
        ]
        boundaries = [
            {"atom_id": r["source_id"], "evidence": r.get("evidence", ""),
             "metadata": r.get("metadata", {})}
            for r in relations if r["type"] == "boundary_of"
        ]

        return {
            "proposal": proposal,
            "evaluation_materials": {
                "existing_primitives": existing_primitives[:50],
                "contradictions": contradictions[:20],
                "boundaries": boundaries[:10],
            },
            "axioms": {
                "self_recognition": {
                    "description": "检查新基元组合是否与已有基元图高度重叠",
                    "requires_llm": True,
                },
                "paraphrase_invariance": {
                    "description": "换多种表述后重新拆解，检查是否依然独特",
                    "requires_llm": True,
                },
                "cumulative_property": {
                    "description": "是否解决了内在矛盾或提升了功能边界",
                    "requires_llm": True,
                },
            },
            "verdict": "pending_llm",  # "novel"|"borderline"|"pseudo"
            "scores": [0.0, 0.0, 0.0],
            "passed": [False, False, False],
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
            cc_summary = self.cc.get_graph_summary()
            queries.append("SOTA continuous control RL techniques beyond DDPG SAC TD3")
        elif phase == PHASE_ELO:
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
# MCP Server
# ═══════════════════════════════════════════════════════════════════

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

_controller: PESController | None = None


def get_controller(workspace_dir: str = "") -> PESController:
    global _controller
    if _controller is None and workspace_dir:
        _controller = PESController(workspace_dir)
    elif _controller is None:
        _controller = PESController(os.getcwd())
    return _controller


TOOLS = [
    Tool(
        name="pes_controller_init",
        description="初始化 PES 工作空间。创建目录结构、Claim Chain、Cell Grid。自动调用 W1 Intake。",
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_dir": {"type": "string", "description": "项目工作目录"},
                "research_topic": {"type": "string", "description": "研究问题"},
                "part2_dimensions": {
                    "type": "array", "items": {"type": "object"},
                    "description": "Part2 任务相关维度 [{\"name\":\"method_family\",\"values\":[\"baseline\",\"ppo\"]}]",
                },
            },
            "required": ["workspace_dir", "research_topic"],
        },
    ),
    Tool(
        name="pes_controller_resume",
        description="崩溃恢复：读 PIPELINE_STATE.json，验证文件完整性，返回恢复状态。",
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_dir": {"type": "string", "description": "项目工作目录"},
            },
            "required": ["workspace_dir"],
        },
    ),
    Tool(
        name="pes_controller_state",
        description="只读状态快照：当前阶段、CC摘要、Grid覆盖率、Fitness趋势、里程碑。",
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_dir": {"type": "string", "description": "项目工作目录"},
            },
            "required": ["workspace_dir"],
        },
    ),
    Tool(
        name="pes_controller_pre_loop",
        description="状态切换准备。只返回基础状态管理信息（不注入Claim Chain数据）。",
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_dir": {"type": "string", "description": "项目工作目录"},
            },
            "required": ["workspace_dir"],
        },
    ),
    Tool(
        name="pes_controller_sub_loop",
        description="分步返回当前阶段的执行步骤。每次调用返回下一步。全部完成返回done=true。",
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_dir": {"type": "string", "description": "项目工作目录"},
            },
            "required": ["workspace_dir"],
        },
    ),
    Tool(
        name="pes_controller_post_loop",
        description="提交阶段结果 + 用户确认。按规则写入CC/Cell Grid/Evolution Memory/Island。",
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_dir": {"type": "string", "description": "项目工作目录"},
                "satisfied": {"type": "boolean", "description": "用户是否满意当前阶段结果"},
                "chosen_next_phase": {"type": "string",
                                       "description": "用户选择的下一个阶段（不满意时可选）"},
                "notes": {"type": "string", "description": "用户备注"},
                "cc_atoms": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Claim Chain 原子列表（仅真实文献/实验结果）: [{type, title, content, tags}]",
                },
                "experiment_results": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "实验结果列表（W5专用）: [{variant_id, score, descriptor}]",
                },
            },
            "required": ["workspace_dir", "satisfied"],
        },
    ),
]


async def handle_tool(name: str, arguments: dict) -> str:
    ws = arguments.get("workspace_dir", os.getcwd())
    ctrl = get_controller(ws)

    if name == "pes_controller_init":
        result = ctrl.init(
            research_topic=arguments["research_topic"],
            part2_dimensions=arguments.get("part2_dimensions"),
        )
    elif name == "pes_controller_resume":
        result = ctrl.resume()
    elif name == "pes_controller_state":
        result = ctrl.get_state()
    elif name == "pes_controller_pre_loop":
        result = ctrl.pre_loop()
    elif name == "pes_controller_sub_loop":
        result = ctrl.sub_loop()
    elif name == "pes_controller_post_loop":
        result = ctrl.post_loop(
            satisfied=arguments["satisfied"],
            chosen_next_phase=arguments.get("chosen_next_phase", ""),
            notes=arguments.get("notes", ""),
            cc_atoms=arguments.get("cc_atoms"),
            experiment_results=arguments.get("experiment_results"),
        )
    else:
        result = {"error": f"Unknown tool: {name}"}

    return json.dumps(result, indent=2, ensure_ascii=False)


def create_server():
    server = Server("pes-controller")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        result_text = await handle_tool(name, arguments)
        return [TextContent(type="text", text=result_text)]

    return server


async def run_server():
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream,
                        server.create_initialization_options())


def main():
    import argparse
    parser = argparse.ArgumentParser(description="PES Controller MCP Server")
    parser.add_argument("--test", action="store_true", help="Print registered tools")
    args = parser.parse_args()

    if args.test:
        print("PES Controller — MCP Server")
        print(f"Tools: {len(TOOLS)}")
        for tool in TOOLS:
            print(f"  {tool.name}: {tool.description[:100]}")
        print("\nAdd to Claude Code with:")
        print("  claude mcp add pes-controller -- python tools/pes_controller.py")
    else:
        import asyncio
        asyncio.run(run_server())


if __name__ == "__main__":
    main()
