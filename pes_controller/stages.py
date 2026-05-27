"""Pipeline phase definitions - canonical source for stages."""
import json, time, re as _re_stages
from pathlib import Path

PHASE_PLAN_1   = "W2.1 Problem Analysis"
PHASE_PLAN_2   = "W2.2 Solution Directions"
PHASE_PLAN_3   = "W2.3 Search Keywords"
PHASE_RESEARCH = "W3 Research"
PHASE_IDEATE   = "W3.5 Ideate"
PHASE_CODE     = "W4 Code"
PHASE_ANALYZE  = "W5 Analyze"
PHASE_WRITE    = "W6 Write"
PHASE_REVIEW   = "W7 Review"
PHASE_TERMINATED = "已终止"

# Auto-advance phases: transition to next without user confirmation
AUTO_ADVANCE_PHASES = frozenset({PHASE_PLAN_1, PHASE_PLAN_2, PHASE_PLAN_3})

PHASES = [PHASE_PLAN_1, PHASE_PLAN_2, PHASE_PLAN_3, PHASE_RESEARCH,
          PHASE_IDEATE, PHASE_CODE, PHASE_ANALYZE, PHASE_WRITE, PHASE_REVIEW]

# Phases that require Agent SDK subprocess (W6 Write, W7 Review)
AGENT_SDK_PHASES = frozenset({PHASE_WRITE, PHASE_REVIEW})

# Phase transitions (from → [legal next])
TRANSITIONS = {
    PHASE_PLAN_1:   [PHASE_PLAN_2],
    PHASE_PLAN_2:   [PHASE_PLAN_3],
    PHASE_PLAN_3:   [PHASE_RESEARCH],
    PHASE_RESEARCH: [PHASE_IDEATE],
    PHASE_IDEATE:   [PHASE_CODE],
    PHASE_CODE:     [PHASE_ANALYZE],
    PHASE_ANALYZE:  [PHASE_PLAN_1, PHASE_WRITE],
    PHASE_WRITE:    [PHASE_REVIEW, PHASE_TERMINATED],
    PHASE_REVIEW:   [PHASE_WRITE],
}

# Execution chain steps per phase
# W2.1/2.2/2.3: invoke 4 personas (each does SME → search → proposal) → ELO → EM → write SME
# W3 Research: same as above, personas search with "specific idea" focus
# W3.5 Ideate: same structure, personas focus on pseudocode
# Shared chain for all persona-driven phases (W2.1/2.2/2.3, W3, W3.5)
_PERSONA_CHAIN = [
    "invoke_four_personas", "evaluate_novelty", "elo_tournament",
    "verify_products", "evolution_memory", "write_sme",
    "write_claim_chain",
]

CHAIN_STEPS = {
    PHASE_PLAN_1:   list(_PERSONA_CHAIN),
    PHASE_PLAN_2:   list(_PERSONA_CHAIN),
    PHASE_PLAN_3:   list(_PERSONA_CHAIN),
    PHASE_RESEARCH: list(_PERSONA_CHAIN),
    PHASE_IDEATE:   list(_PERSONA_CHAIN),
    PHASE_CODE: [
        "run_step_pipeline",
        "write_claim_chain",
        "refine_atoms",
        "generate_code_plan",
        "wait_user_code",
    ],
    PHASE_ANALYZE: [
        "run_step_pipeline", "scan_islands_rubrics",
        "multi_agent_discuss", "evolution_memory",
        "write_claim_chain", "island_assign",
    ],
    PHASE_WRITE:   ["invoke_skill_write"],
    PHASE_REVIEW:  ["invoke_skill_review"],
}

# 4-Persona agents used for ideation phases
FOUR_PERSONA_AGENTS = [
    "novel-academic-agent",
    "conservative-academic-agent",
    "novel-engineering-agent",
    "conservative-engineering-agent",
]

# Agent roles per phase
AGENT_ROLES = {
    PHASE_PLAN_1:   FOUR_PERSONA_AGENTS,
    PHASE_PLAN_2:   FOUR_PERSONA_AGENTS,
    PHASE_PLAN_3:   FOUR_PERSONA_AGENTS,
    PHASE_RESEARCH: FOUR_PERSONA_AGENTS,
    PHASE_IDEATE:   FOUR_PERSONA_AGENTS,
    PHASE_ANALYZE:  ["analyst", "planner", "researcher"],
    PHASE_WRITE:    ["writer"],
    PHASE_REVIEW:   ["writer"],
}

# Product specification rules per phase (embedded in persona prompts)
PRODUCT_SPECS = {
    PHASE_PLAN_1: {
        "required": [
            "具体难点(到网络组件/loss项级别)",
            "因果分析(为什么这个难点会导致性能瓶颈)",
            "baseline为何无法解决(现有方法的局限性)",
        ],
    },
    PHASE_PLAN_2: {
        "required": [
            "方向描述(解决什么难点)",
            "针对哪些难点(关联W2.1的分析)",
            "技术路径概要(用什么方法解决)",
            "与baseline的区分点",
        ],
    },
    PHASE_PLAN_3: {
        "required": [
            "检索词列表",
            "每个检索词的搜索目标(搜什么类型的文献)",
            "预期命中什么文献类型",
            "覆盖的子主题列表",
        ],
    },
    PHASE_RESEARCH: {
        "required": [
            "具体方案(含修改哪些组件/模块)",
            "文献依据(引用搜索到的论文)",
            "可行性估计(计算开销、实现复杂度)",
            "与baseline的量化对比预期",
        ],
    },
    PHASE_IDEATE: {
        "required": [
            "伪代码(1-2段，清晰变量名，标注修改位置)",
            "架构改动列表(ADD/MODIFY/REMOVE)",
            "损失函数签名(fn_name(args) -> Tensor + 说明)",
            "计算开销估计",
        ],
    },
}

# Phase migration map (old Chinese → new W-based)
_PHASE_MIGRATION = {
    "方案提出": "W2.1 Problem Analysis",
    "文献调研": "W3 Research",
    "ELO筛选": "W3.5 Ideate",
    "实验执行": "W4 Code",
    "结果分析": "W5 Analyze",
    "论文写作": "W6 Write",
    "论文审阅": "W7 Review",
}


# ── Helper: smart refined_proposals lookup (handles prefix_id.json naming) ──
