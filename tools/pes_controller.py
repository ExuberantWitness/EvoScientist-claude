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
PHASE_TERMINATED = "已终止"

PHASES = [PHASE_PLAN, PHASE_RESEARCH, PHASE_ELO, PHASE_EXECUTE, PHASE_ANALYZE]

# Phase transitions (from → [legal next])
TRANSITIONS = {
    PHASE_PLAN:      [PHASE_RESEARCH],
    PHASE_RESEARCH:  [PHASE_ELO],
    PHASE_ELO:       [PHASE_EXECUTE],
    PHASE_EXECUTE:   [PHASE_ANALYZE],
    PHASE_ANALYZE:   [PHASE_PLAN, PHASE_RESEARCH, PHASE_ELO, PHASE_EXECUTE, PHASE_TERMINATED],
}

# Execution chain steps per phase
CHAIN_STEPS = {
    PHASE_PLAN: [
        "step_cli", "step_indexing", "step_decomposer", "step_recomposer", "step_evaluator",
        "multi_agent_discuss", "elo_tournament", "evolution_memory",
    ],
    PHASE_RESEARCH: [
        "step_cli", "step_indexing", "step_decomposer", "step_recomposer", "step_evaluator",
        "multi_agent_discuss", "elo_tournament", "evolution_memory",
        "invoke_skill_research", "write_claim_chain",
    ],
    PHASE_ELO: [
        "step_cli", "step_indexing", "step_decomposer", "step_recomposer", "step_evaluator",
        "multi_agent_discuss", "elo_tournament", "evolution_memory",
    ],
    PHASE_EXECUTE: [
        "invoke_skill_code", "wait_external",
    ],
    PHASE_ANALYZE: [
        "step_cli", "step_indexing", "step_decomposer", "step_recomposer", "step_evaluator",
        "scan_islands_rubrics", "multi_agent_discuss", "evolution_memory",
        "write_claim_chain", "island_assign",
    ],
}

# Agent roles per phase
AGENT_ROLES = {
    PHASE_PLAN:      ["planner", "researcher", "analyst"],
    PHASE_RESEARCH:  ["researcher", "planner", "analyst"],
    PHASE_ELO:       ["planner", "researcher", "analyst"],
    PHASE_ANALYZE:   ["analyst", "planner", "researcher"],
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
        }
        self._write_state(state)

        return {"workspace_ready": True, "phase": PHASE_PLAN, "iteration": 0}

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

        if step_name in ("step_cli", "step_indexing", "step_decomposer",
                         "step_recomposer", "step_evaluator"):
            return {
                "done": False,
                "phase": phase,
                "step": step_name,
                "step_index": state.get("sub_loop_step", 0) - 1,
                "action": "invoke_skill",
                "skill": "/evo-ideation",
                "argument": f"[{phase}] {step_name}: 单Agent独立执行。Agent角色: {agents}。"
                           f"通过 STEP_CLI 自行检索 Claim Chain + Cell Grid。",
                "context": f"Phase: {phase}, Step: {step_name}, Agents: {agents}",
            }

        elif step_name == "multi_agent_discuss":
            return {
                "done": False,
                "phase": phase,
                "step": step_name,
                "step_index": state.get("sub_loop_step", 0) - 1,
                "action": "multi_agent",
                "tool": "evo_discuss",
                "topic": f"[{phase}] 多Agent汇总讨论。各Agent分享独立管线产出，从不同视角讨论。",
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

        return {"done": True, "phase": phase}

    # ═══════════════════════════════════════════════════════════════
    # MCP Tool: post_loop
    # ═══════════════════════════════════════════════════════════════

    def post_loop(self, satisfied: bool, chosen_next_phase: str = "",
                  notes: str = "") -> dict:
        """提交阶段结果 + 用户确认。"""
        state = self._read_state()
        phase = state["phase"]

        if not satisfied:
            # 状态不变，回到同一阶段
            state["sub_loop_step"] = 0
            self._write_state(state)
            return {"advanced": False, "next_phase": phase,
                    "message": "用户不满意，回到同一阶段重新执行。"}

        # 用户满意 → 写入 (按规则)
        events = []

        if phase == PHASE_RESEARCH:
            # 写入 CC: 真实文献原子
            events.append("claim_chain_updated: literature atoms from real papers")

        elif phase == PHASE_ANALYZE:
            # 写入 CC: 真实实验结果
            events.append("claim_chain_updated: verification atoms from real experiments")
            # Island 分配
            events.append("island_assigned")

        # 达标判断 (仅 W5)
        if phase == PHASE_ANALYZE:
            fs = self.fitness.get_stats()
            best = fs.get("global", {}).get("max_score", 0)
            # 从 success_criteria.md 读目标
            target = self._read_success_target()
            if target and best >= target:
                chosen_next_phase = PHASE_TERMINATED

        # 确定下一阶段
        if chosen_next_phase:
            next_phase = chosen_next_phase
        elif phase == PHASE_ANALYZE:
            next_phase = PHASE_TERMINATED  # 默认终止
        else:
            legal = self._legal_next(phase)
            next_phase = legal[0] if legal else PHASE_TERMINATED

        # 更新状态
        state["phase"] = next_phase
        state["sub_loop_step"] = 0
        if phase == PHASE_ANALYZE:
            state["iteration"] = state.get("iteration", 0) + 1

        self._write_state(state)

        return {
            "advanced": True,
            "next_phase": next_phase,
            "phase_completed": phase,
            "events": events,
            "message": f"阶段 '{phase}' 完成。进入 '{next_phase}'。" if next_phase != PHASE_TERMINATED
                       else "研究阶段结束。进入写作阶段。",
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
        """STEP_Decomposer: Python 预处理 + LLM 嫁接。

        Python 预处理: 从 CC 提取基元子图、关系链模式、可违反边界条件。
        返回结构化数据供 LLM 做跨域类比和反事实嫁接。
        """
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
            # 从 method 原子自动构建基元列表
            method_atoms = [a for a in atoms if a["type"] == "method" and a["status"] == "active"]
            primitives = [
                {"atom_id": a["id"], "title": a["title"], "tags": a.get("tags", []),
                 "content": a.get("content", "")[:200]}
                for a in method_atoms[:20]
            ]

        return {
            "primitives": primitives,
            "relation_patterns": {
                "validates_chains": validates_chains[:20],
                "derives_chains": derives_chains[:20],
                "contradicts_chains": contradicts_chains[:20],
            },
            "violable_boundaries": boundaries[:10],
            "mappings": [],    # LLM 填充: 跨域关系同构
            "grafts": [],      # LLM 填充: 反事实嫁接
            "conflict_zones": [],
        }

    def step_recomposer(self, grafted_materials: dict, phase: str = "") -> list[dict]:
        """STEP_Recomposer: 将 Decomposer 原材料格式化为单Agent可用的方案模板。

        grafted_materials: Decomposer 输出 {mappings, grafts, conflict_zones, primitives}
        """
        proposals = []

        for graft in grafted_materials.get("grafts", []):
            proposals.append({
                "title": f"Graft: {graft.get('primitive_a', '?')} + {graft.get('primitive_b', '?')}",
                "hypothesis": graft.get("potential_breakthrough", ""),
                "method_sketch": "",
                "primitives_used": [
                    graft.get("primitive_a", ""),
                    graft.get("primitive_b", ""),
                ],
                "novelty_claim": f"Cross-domain graft via {graft.get('violated_boundary', 'unknown')}",
            })

        for mapping in grafted_materials.get("mappings", []):
            proposals.append({
                "title": f"Map: {mapping.get('source_primitive', '?')} → {mapping.get('target_domain', '?')}",
                "hypothesis": mapping.get("isomorphic_relation", ""),
                "method_sketch": "",
                "primitives_used": [mapping.get("source_primitive", "")],
                "novelty_claim": f"Isomorphic mapping (confidence: {mapping.get('confidence', 'N/A')})",
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
