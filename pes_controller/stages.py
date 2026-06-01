"""Pipeline phase definitions — canonical source aligned with spec framework."""

PHASE_PLAN_1   = "W2 问题分析"
PHASE_PLAN_2   = "W3 方案方向"
PHASE_IDEATE   = "W4 具体方案生成"
PHASE_CODE     = "W5 代码实现"
PHASE_ANALYZE  = "W6 结果分析"
PHASE_WRITE    = "W7 论文写作"
PHASE_REVIEW   = "W8 审阅"
PHASE_TERMINATED = "已终止"

# Deleted phases (per framework):
#   PHASE_PLAN_3 = W2.3 Search Keywords
#   PHASE_RESEARCH = W3 Research
# Persona agents now self-search in each phase, no separate search phases needed.

# Auto-advance: W2→W3→W4 (persona phases), then requires user confirmation
AUTO_ADVANCE_PHASES = frozenset({PHASE_PLAN_1, PHASE_PLAN_2, PHASE_IDEATE})

PHASES = [PHASE_PLAN_1, PHASE_PLAN_2, PHASE_IDEATE,
          PHASE_CODE, PHASE_ANALYZE, PHASE_WRITE, PHASE_REVIEW]

# Phases that require Agent SDK subprocess
AGENT_SDK_PHASES = frozenset({PHASE_WRITE, PHASE_REVIEW})

# Phase transitions (from → [legal next])
TRANSITIONS = {
    PHASE_PLAN_1:   [PHASE_PLAN_2],
    PHASE_PLAN_2:   [PHASE_IDEATE],
    PHASE_IDEATE:   [PHASE_CODE],
    PHASE_CODE:     [PHASE_ANALYZE],
    PHASE_ANALYZE:  [PHASE_PLAN_1, PHASE_WRITE],
    PHASE_WRITE:    [PHASE_REVIEW, PHASE_TERMINATED],
    PHASE_REVIEW:   [PHASE_WRITE],
}

# Shared chain for all persona-driven phases (W2, W3, W4)
# invoke_four_personas: each persona does set_style → search_literature → generate_proposal
_PERSONA_CHAIN = [
    "invoke_four_personas", "sync_to_cc", "evaluate_novelty", "elo_tournament",
    "verify_products", "evolution_memory", "write_claim_chain",
]

CHAIN_STEPS = {
    PHASE_PLAN_1:   list(_PERSONA_CHAIN),
    PHASE_PLAN_2:   list(_PERSONA_CHAIN),
    PHASE_IDEATE:   list(_PERSONA_CHAIN),
    PHASE_CODE: [
        "generate_code_spec", "run_step_pipeline",
        "generate_code_plan", "wait_user_code",
    ],
    PHASE_ANALYZE: [
        "run_step_pipeline", "scan_islands_rubrics",
        "multi_agent_discuss", "evolution_memory",
        "island_assign", "refine_atoms", "write_claim_chain",
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

AGENT_ROLES = {
    PHASE_PLAN_1:   FOUR_PERSONA_AGENTS,
    PHASE_PLAN_2:   FOUR_PERSONA_AGENTS,
    PHASE_IDEATE:   FOUR_PERSONA_AGENTS,
    PHASE_ANALYZE:  ["analyst", "planner", "researcher"],
    PHASE_WRITE:    ["writer"],
    PHASE_REVIEW:   ["writer"],
}

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
            "针对哪些难点(关联W2的分析)",
            "技术路径概要(用什么方法解决)",
            "与baseline的区分点",
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
