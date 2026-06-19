import logging
logger = logging.getLogger(__name__)
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

from claim_chain.chain import ClaimChain
from claim_chain.cell_grid import CellGrid
from pes_controller.rubric.scheduler import RubricScheduler
from claim_chain.island_manager import IslandManager
from sdk.status.fitness import FitnessTracker


# ── Phase constants ──

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
# Deleted: PHASE_PLAN_3 (W2.3), PHASE_RESEARCH (W3) — persona self-searches now
# Backward compat: PHASE_WRITE replaced by W7.1-W7.5 sub-phases

AUTO_ADVANCE_PHASES = frozenset({PHASE_PLAN_1, PHASE_PLAN_2, PHASE_IDEATE})

PHASES = [PHASE_PLAN_1, PHASE_PLAN_2, PHASE_IDEATE,
          PHASE_CODE, PHASE_ANALYZE,
	          PHASE_WRITE_PLAN, PHASE_WRITE_FIGURE, PHASE_WRITE_LATEX,
	          PHASE_WRITE_COMPILE, PHASE_WRITE_IMPROVE,
	          PHASE_REVIEW]

AGENT_SDK_PHASES = frozenset({PHASE_WRITE_PLAN, PHASE_WRITE_FIGURE, PHASE_WRITE_LATEX,
                               PHASE_WRITE_COMPILE, PHASE_WRITE_IMPROVE, PHASE_REVIEW})

TRANSITIONS = {
    PHASE_PLAN_1:   [PHASE_PLAN_2],
    PHASE_PLAN_2:   [PHASE_IDEATE],
    PHASE_IDEATE:   [PHASE_CODE],
    PHASE_CODE:     [PHASE_ANALYZE],
    PHASE_ANALYZE:  [PHASE_PLAN_1, PHASE_WRITE_PLAN],
    PHASE_WRITE_PLAN:   [PHASE_WRITE_FIGURE],
    PHASE_WRITE_FIGURE: [PHASE_WRITE_LATEX],
    PHASE_WRITE_LATEX:  [PHASE_WRITE_COMPILE],
    PHASE_WRITE_COMPILE:[PHASE_WRITE_IMPROVE],
    PHASE_WRITE_IMPROVE:[PHASE_REVIEW],
    PHASE_REVIEW:   [PHASE_WRITE_PLAN, PHASE_CODE, PHASE_TERMINATED],
}

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
    PHASE_WRITE_PLAN:   ["invoke_skill_paper_plan", "verify_deliverables"],
    PHASE_WRITE_FIGURE: ["invoke_skill_paper_figure", "verify_deliverables"],
    PHASE_WRITE_LATEX:  ["invoke_skill_paper_write", "verify_deliverables"],
    PHASE_WRITE_COMPILE:["invoke_skill_paper_compile", "verify_deliverables"],
    PHASE_WRITE_IMPROVE:["invoke_skill_paper_improve", "verify_deliverables"],
    PHASE_REVIEW:       ["invoke_skill_flux_review", "verify_deliverables"],
}

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
    PHASE_WRITE_PLAN:   ["writer"],
    PHASE_WRITE_FIGURE: ["writer"],
    PHASE_WRITE_LATEX:  ["writer"],
    PHASE_WRITE_COMPILE:["writer"],
    PHASE_WRITE_IMPROVE:["writer"],
    PHASE_REVIEW:       ["writer"],
}

PRODUCT_SPECS = {
    PHASE_PLAN_1: {
        "required": [
            "具体难点(到网络组件/loss项级别)",
            "因果分析(为什么这个难点会导致性能瓶颈)",
            "baseline为何无法解决(现有方法的局限性)",
        ],
        "deliverables": [],
    },
    PHASE_PLAN_2: {
        "required": [
            "方向描述(解决什么难点)",
            "针对哪些难点(关联W2的分析)",
            "技术路径概要(用什么方法解决)",
            "与baseline的区分点",
        ],
        "deliverables": [],
    },
    PHASE_IDEATE: {
        "required": [
            "伪代码(1-2段，清晰变量名，标注修改位置)",
            "架构改动列表(ADD/MODIFY/REMOVE)",
            "损失函数签名(fn_name(args) -> Tensor + 说明)",
            "计算开销估计",
        ],
        "deliverables": [],
    },
    PHASE_WRITE_PLAN: {
        "required": [
            "NARRATIVE_REPORT.md exists",
            "PAPER_PLAN.md exists with: working title, venue, Claims-Evidence Matrix, section structure with page budgets, Figure Plan table, Citation Plan",
        ],
        "deliverables": ["NARRATIVE_REPORT.md", "PAPER_PLAN.md"],
    },
    PHASE_WRITE_FIGURE: {
        "required": [
            "figures/ directory exists",
            "At least 1 .pdf file in figures/",
            "figures/latex_includes.tex exists and non-empty",
        ],
        "deliverables": ["figures/", "figures/latex_includes.tex"],
    },
    PHASE_WRITE_LATEX: {
        "required": [
            "paper/main.tex exists",
            "paper/sections/ has .tex files",
            "paper/references.bib exists",
            "paper/math_commands.tex exists",
        ],
        "deliverables": ["paper/main.tex", "paper/sections/", "paper/references.bib", "paper/math_commands.tex"],
    },
    PHASE_WRITE_COMPILE: {
        "required": [
            "paper/main.pdf exists and > 100KB",
        ],
        "deliverables": ["paper/main.pdf"],
    },
    PHASE_WRITE_IMPROVE: {
        "required": [
            "PAPER_IMPROVEMENT_LOG.md exists",
            "PAPER_IMPROVEMENT_STATE.json exists with status='completed'",
        ],
        "deliverables": ["paper/main.pdf", "PAPER_IMPROVEMENT_LOG.md", "PAPER_IMPROVEMENT_STATE.json"],
    },
    PHASE_REVIEW: {
        "required": [
            "AUTO_REVIEW.md exists with: round history, full raw reviewer text, fixes, remaining issues",
            "REVIEW_STATE.json exists with status='completed'",
            "CLAIMS_FROM_RESULTS.md exists",
        ],
        "deliverables": ["AUTO_REVIEW.md", "REVIEW_STATE.json", "CLAIMS_FROM_RESULTS.md"],
    },
}

# Phase migration map (old Chinese → new W-based)
_PHASE_MIGRATION = {
    "方案提出": "W2 问题分析",
    "文献调研": "W2 问题分析",
    "ELO筛选": "W4 具体方案生成",
    "实验执行": "W5 代码实现",
    "结果分析": "W6 结果分析",
    "论文写作": "W7.1 论文计划",
    "论文审阅": "W8 审阅",
}

# Backward compatibility aliases: old phase names → new phases
_PHASE_ALIASES = {
    "W7 论文写作": PHASE_WRITE_PLAN,
    "W6 Write": PHASE_WRITE_PLAN,
    "W7 Write": PHASE_WRITE_PLAN,
    "W7 Review": PHASE_REVIEW,
}


# ── Helper: smart refined_proposals lookup (handles prefix_id.json naming) ──

def _search_github_for_baselines(topic: str) -> list[str]:
    """Search GitHub for open-source baselines using the github-search skill.

    Calls the Node.js github-search.mjs script via subprocess.
    Extracts repository names as candidate baselines from structured output.
    Returns empty list if skill unavailable or search fails.
    """
    skill_script = Path.home() / ".claude" / "skills" / "github-search" / "scripts" / "github-search.mjs"
    if not skill_script.exists():
        return []

    # Find a recent Node.js (v14+ required for optional chaining)
    node_bin = "/usr/bin/node"
    for candidate in [
        Path.home() / ".nvm/versions/node/v22.22.2/bin/node",
        Path.home() / ".nvm/versions/node/v20.19.5/bin/node",
    ]:
        if candidate.exists():
            node_bin = str(candidate)
            break

    try:
        import subprocess as _sp
        # Build query: extract English words from topic for meaningful GitHub search
        import re as _re_query
        eng_words = _re_query.findall(r'[A-Za-z][A-Za-z0-9\-]*', topic)
        # For search query, only skip very common English stop words (not technical terms)
        _query_stop = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                       "to", "of", "in", "for", "on", "with", "at", "by", "from",
                       "and", "or", "not", "but", "if", "then", "else", "when",
                       "this", "that", "these", "those", "it", "its", "can", "will"}
        query_parts = [w for w in eng_words if w.lower() not in _query_stop][:8]
        query = " ".join(query_parts) if query_parts else " ".join(topic.split()[:5])
        # Pass proxy env to subprocess (required for GitHub API access)
        env = os.environ.copy()
        # Ensure proxy is available — try common configurations
        for proxy_env in ['https_proxy', 'http_proxy', 'HTTPS_PROXY', 'HTTP_PROXY', 'all_proxy', 'ALL_PROXY']:
            if proxy_env not in env or not env.get(proxy_env):
                env[proxy_env] = env.get(proxy_env.lower(), env.get(proxy_env.upper(), ''))
        # Fallback: local proxy if none set
        if not any(env.get(k) for k in ['https_proxy', 'HTTPS_PROXY', 'http_proxy', 'HTTP_PROXY']):
            env['https_proxy'] = 'http://127.0.0.1:6789'
            env['http_proxy'] = 'http://127.0.0.1:6789'
        r = _sp.run(
            [node_bin, str(skill_script), query, "--limit", "15", "--sort", "stars", "--min-stars", "10", "--output", "json"],
            capture_output=True, text=True, timeout=30,
            cwd=str(skill_script.parent),
            env=env,
        )
        if r.returncode != 0:
            return []

        # Parse JSON output
        results = json.loads(r.stdout) if r.stdout.strip() else {}
        items = results if isinstance(results, list) else results.get("results", results.get("items", []))

        candidates = []
        for item in items[:10]:
            name = item.get("name", "") or item.get("full_name", "")
            description = item.get("description", "") or ""
            # Also check topics/tags
            topics = item.get("topics", []) if isinstance(item.get("topics"), list) else []
            full_text = f"{name} {description} {' '.join(topics)}"
            candidates.extend(_extract_candidates_from_topic(full_text))
            # Extract method-like names from repo name
            name_clean = name.replace("-", " ").replace("_", " ").replace(".", " ").split("/")[-1]
            for word in name_clean.split():
                w = word.strip().upper()
                if 2 <= len(w) <= 8 and w.isalpha() and w not in _skip_words:
                    candidates.append(w)

        return list(dict.fromkeys(candidates))
    except Exception:
        return []


def _search_web_for_baselines(topic: str) -> list[str]:
    """Search for standard baselines — primary source is GitHub via the github-search skill."""
    return _search_github_for_baselines(topic)


# Common words to skip when extracting candidate names
_skip_words = {"THE", "AND", "FOR", "ARE", "NOT", "BUT", "CAN", "ALL", "NEW", "FROM",
               "WHEN", "THAT", "WITH", "THIS", "WILL", "HAVE", "BEEN", "WERE", "THEY",
               "WHAT", "WHICH", "THERE", "THEIR", "ABOUT", "WOULD", "COULD", "SHOULD"}
# Common non-method terms to skip
_skip_terms = {"critic", "actor", "model", "method", "network", "algorithm", "system",
               "data", "learning", "training", "policy", "value", "state", "action",
               "reward", "agent", "environment", "layer", "neural", "deep", "batch",
               "gradient", "loss", "function", "parameter", "weight"}


def _extract_candidates_from_topic(topic: str) -> list[str]:
    """Extract candidate method names from research topic text using generic heuristics.

    No hardcoded domain lists. Detects:
    - Uppercase acronyms (2-8 chars) in any language context
    - MixedCase compound names
    - Terms prefixed to Chinese method indicators (算法/方法/模型/网络)

    Returns deduplicated list. Empty if nothing detected.
    """
    import re as _re3
    candidates = []
    # 1) ALL-CAPS acronyms (2-8 chars). Use custom boundary: preceded/followed by
    #    Chinese char, space, punctuation, or string boundary
    caps = _re3.findall(r'(?:^|[\s，,、。；;：:（(）)！!？?一-鿿])'
                        r'([A-Z]{2,8})'
                        r'(?=[\s，,、。；;：:（(）)！!？?一-鿿]|$)', topic)
    candidates.extend(c for c in caps if c not in _skip_words and c.lower() not in _skip_terms)
    # 2) MixedCase compound names
    mixed = _re3.findall(r'(?:^|[\s，,、。；;：:（(）)！!？?一-鿿])'
                         r'([A-Z][a-z]+(?:[A-Z][a-z0-9]+)+)'
                         r'(?=[\s，,、。；;：:（(）)！!？?一-鿿]|$)', topic)
    candidates.extend(c for c in mixed if c.lower() not in _skip_terms)
    # 3) Chinese-prefixed names: "X算法", "X方法", "X模型", "X网络"
    cn = _re3.findall(r'([A-Za-z0-9]+)(?:算法|方法|模型|网络)', topic)
    candidates.extend(c for c in cn if c.lower() not in _skip_terms)
    # 4) Bare acronyms without Chinese context (English text): word-bounded
    caps_en = _re3.findall(r'\b([A-Z]{2,8})\b', topic)
    candidates.extend(c for c in caps_en if c not in _skip_words and c not in candidates)
    return list(dict.fromkeys(candidates))  # dedup, preserve order


def _discover_baselines_from_cc(cc_atoms: list[dict]) -> list[str]:
    """Discover baseline methods from Claim Chain atoms.

    A baseline is:
    - type='fact' + tag='baseline' (explicitly marked)
    - type='method' + tag='proposal' + metadata.verified=True (experimentally validated)

    Returns list of baseline names. Empty if CC has no data yet.
    """
    baselines = []
    for a in cc_atoms:
        tags = a.get("tags", [])
        if a.get("type") == "fact" and "baseline" in tags:
            baselines.append(a.get("title", ""))
        elif a.get("type") == "method" and "proposal" in tags:
            meta = a.get("metadata", {}) if isinstance(a.get("metadata"), dict) else {}
            if meta.get("verified", False):
                baselines.append(a.get("title", ""))
    return baselines


def _get_domain_config(state: dict) -> dict:
    """Load DomainConfig from PIPELINE_STATE or fall back to empty dict."""
    dc = state.get("domain_config", {})
    if isinstance(dc, dict) and dc:
        return dc
    # Fallback: try to load from domain_presets
    try:
        from domain_presets import get_domain_preset
        domain_name = state.get("domain_name", "general")
        return get_domain_preset(domain_name)
    except ImportError:
        return {}


def _sanitize_sketch(sketch: str) -> str:
    """Strip philosophical boilerplate from a method sketch, keeping mechanism descriptions."""
    result = sketch
    # Remove numbered philosophical steps
    import re as _re2
    result = _re2.sub(r'\d+\.\s*(Analyze what makes|Map isomorphic|Adapt the mapped|Test whether the|Reconcile via|Reconciliation:).*?(\n|$)', '', result)
    # Remove empty lines and boilerplate prefixes
    lines = []
    for line in result.split('\n'):
        stripped = line.strip()
        if not stripped: continue
        if stripped.startswith(('Reconcile via', 'Reconciliation:', 'cyclic_3node', 'isomorphic')):
            continue
        lines.append(stripped)
    return '\n'.join(lines[:8])


def _domain_infra_spec(filename: str, domain_cfg: dict, default: str = "") -> str:
    """Return domain-specific infra spec if available, otherwise the default template."""
    infra = domain_cfg.get("infrastructure_specs", {})
    return infra.get(filename, default)


def _find_refined_json(refined_dir: Path, fname: str, atom_id: int = 0):
    """Find a refined proposal JSON by fname with multiple matching strategies.

    Handles the {prefix}_{atom_id}.json naming pattern from _do_refine_atoms.
    When atom_id is provided, prefers exact {prefix}_{atom_id}.json match.
    Examples: "graft"+id=1 → graft_1.json, "map"+id=3 → map_3.json
    """
    if not refined_dir.exists():
        return None
    # Strategy 0: precise match with atom_id (prefix_atom_id.json)
    if atom_id:
        first_part = fname.split(":")[0].strip().split()[0].lower().replace(" ", "_")[:20]
        precise = refined_dir / f"{first_part}_{atom_id}.json"
        if precise.exists():
            return precise
    # Strategy 1: exact match
    exact = refined_dir / f"{fname}.json"
    if exact.exists():
        return exact
    # Strategy 2: first-part match (for "graft: ..." style names)
    first_part = fname.split(":")[0].strip()
    fp = refined_dir / f"{first_part}.json"
    if fp.exists():
        return fp
    # Strategy 3: first-word match
    first_word = fname.split()[0] if fname.split() else fname
    fw = refined_dir / f"{first_word}.json"
    if fw.exists():
        return fw
    # Strategy 4: prefix glob (handles graft_1.json when looking for "graft")
    prefix = first_part.lower().replace(" ", "_")
    candidates = sorted(refined_dir.glob(f"{prefix}_*.json"))
    if candidates:
        return candidates[0]
    # Strategy 5: strip numeric suffix (handles "graft1" → "graft" → graft_*.json)
    import re as _re
    stripped = _re.sub(r'\d+$', '', fname)
    if stripped and stripped != fname:
        prefix2 = stripped.lower().replace(" ", "_")
        candidates2 = sorted(refined_dir.glob(f"{prefix2}_*.json"))
        if candidates2:
            return candidates2[0]
    return None

def _baseline_inline_spec(algo: str) -> str:
    """Generate a domain-agnostic inline spec for a baseline algorithm.

    Provides a minimal spec referencing BaseAlgorithm compliance.
    No domain-specific content — domain details come from DomainConfig.
    """
    return (
        f"- **基线算法**: {algo}\n"
        f"- **核心方法**: `def step(self, batch)` — 具体实现见对应的 refined_proposal JSON\n"
        f"- **trainer.py 集成**: BaseAlgorithm ✅ (issubclass 已验证)\n"
        f"- **超参数**: 见 refined_proposals/{algo.lower()}.json 或 DomainConfig"
    )


class PESController:
    """单一状态机 + 五步渐进式发现管线。"""

    def __init__(self, workspace_dir: str | Path, session_id: str = ""):
        self.workspace = Path(workspace_dir)
        # session_dir: 所有产物隔离到 sessions/{sid}/ 下
        if session_id and not (self.workspace / "PIPELINE_STATE.json").exists():
            self.session_dir = self.workspace / "sessions" / session_id
        else:
            self.session_dir = self.workspace
        self.session_dir.mkdir(parents=True, exist_ok=True)
        # 数据直接存在 session_dir 下 (无中间 vault/ 层)
        self.index_dir = self.session_dir / "_index"
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.session_dir / "PIPELINE_STATE.json"
        # Auto-migrate old schema BEFORE creating ClaimChainV2 (avoids WAL lock)
        from claim_chain.chain import migrate_schema
        migrate_schema(self.index_dir / 'cc.db')
        self.cc = ClaimChain(self.index_dir / 'cc.db')
        self.grid = CellGrid(self.session_dir / "evolve_archive")
        self.rubric = RubricScheduler(self.cc)
        self.islands = IslandManager(self.session_dir / "evolve_archive")
        self.fitness = FitnessTracker(self.session_dir / "_index")

    # ═══════════════════════════════════════════════════════════════
    # 状态读写
    # ═══════════════════════════════════════════════════════════════

    def _read_state(self) -> dict:
        """原子读 + 旧中文阶段名自动迁移。损坏文件自动回退到默认状态。"""
        _default = {
            "protocol_version": 1,
            "phase": PHASE_PLAN_1,
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
            state["phase"] = PHASE_PLAN_1
        phase = state.get("phase", PHASE_PLAN_1)
        if phase in _PHASE_MIGRATION:
            state["phase"] = _PHASE_MIGRATION[phase]
            atomic_write(self.state_path, state)
        # Apply backward compat aliases (e.g. "W7 论文写作" → W7.1)
        phase = state.get("phase", PHASE_PLAN_1)
        if phase in _PHASE_ALIASES:
            state["phase"] = _PHASE_ALIASES[phase]
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
        """初始化工作空间。创建 session 目录树。"""
        for d in ["evolve_archive", "artifacts",
                  "Algorithms", "Bottlenecks", "Islands", "iterations",
                  "_index", "_pipeline", "_memory"]:
            (self.session_dir / d).mkdir(parents=True, exist_ok=True)

        # Claim Chain — create empty JSONL files
        self.cc.get_graph_summary()
        # touch empty files if they don't exist
        # DB auto-created by SQLite, no need to touch files

        # Cell Grid: Part1(内置) + Part2(用户定义)
        dims = part2_dimensions or []
        self.grid.init(dims)

        # PIPELINE_STATE.json
        state = {
            "phase": PHASE_PLAN_1,
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
            "phase": PHASE_PLAN_1,
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
        cc_ok = (self.index_dir / "cc.db").exists()
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
            PHASE_PLAN_1: "4-Persona独立分析核心难点 → ELO排序 → EM",
            PHASE_PLAN_2: "4-Persona独立提出解决方向 → ELO排序 → EM",
            PHASE_IDEATE: "4-Persona独立生成伪代码级方案 → ELO排序 → EM",
            PHASE_CODE: "Spec-first：生成BuildSpec → 代码实现",
            PHASE_ANALYZE: "Island/Rubric扫描 → 多Agent分析 → 结果写入CC",
            PHASE_WRITE_PLAN: "论文计划: Claims-Evidence Matrix + section structure + 图表计划",
            PHASE_WRITE_FIGURE: "图表生成: 从实验数据生成矢量格式图表",
            PHASE_WRITE_LATEX: "LaTeX写作: 基于PAPER_PLAN逐section生成内容",
            PHASE_WRITE_COMPILE: "编译: 编译paper/main.tex为PDF，修复错误",
            PHASE_WRITE_IMPROVE: "审稿修复: 外部LLM多轮审稿修复",
            PHASE_REVIEW: "多轮研究审阅（含故事逻辑维度）",
        }
        return descriptions.get(phase, "")

    @staticmethod
    def _get_phase_dims(phase: str) -> list[str]:
        """Get ELO dimension names for a phase."""
        try:
            from pes_controller.elo.tournament import ELO_DIMENSIONS
        except ImportError:
            return ["novelty", "feasibility", "relevance", "clarity"]
        dims = ELO_DIMENSIONS.get(phase, {})
        return dims.get("dimensions", ["novelty", "feasibility", "relevance", "clarity"])

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

    def _sync_jsonl_to_cc(self) -> dict:
        """Sync atoms.jsonl → cc.db, then delete JSONL. Called after every JSONL write."""
        atoms_path = self.index_dir / "atoms.jsonl"
        rels_path = self.index_dir / "relations.jsonl"
        result = {"atoms_synced": 0, "relations_synced": 0}

        # Read current iteration/phase from PIPELINE_STATE for temporal metadata
        ps_path = self.index_dir.parent / "PIPELINE_STATE.json"
        iter_num = 0
        current_phase = "unknown"
        if ps_path.exists():
            try:
                ps = json.loads(ps_path.read_text(encoding="utf-8"))
                iter_num = ps.get("iteration", 0)
                current_phase = ps.get("phase", "unknown")
            except Exception:
                pass

        if atoms_path.exists():
            try:
                for line in atoms_path.read_text(encoding="utf-8").strip().split("\n"):
                    if not line.strip():
                        continue
                    try:
                        atom = json.loads(line)
                        self.cc.add_atom(
                            type=atom.get("type", "method"),
                            title=atom.get("title", ""),
                            content=atom.get("content", ""),
                            tags=atom.get("tags", []),
                            evidence_level=atom.get("evidence_level", "experiment"),
                            metadata=atom.get("metadata", {}),
                            iteration=iter_num,
                            phase=current_phase,
                        )
                        result["atoms_synced"] += 1
                    except Exception as e:
                        logger.warning(f"Failed to sync atom: {e}")
                atoms_path.unlink()
                logger.info(f"Synced {result['atoms_synced']} atoms → cc.db, deleted atoms.jsonl")
            except Exception as e:
                logger.error(f"Failed to sync atoms.jsonl: {e}")

        if rels_path.exists():
            try:
                for line in rels_path.read_text(encoding="utf-8").strip().split("\n"):
                    if not line.strip():
                        continue
                    try:
                        rel = json.loads(line)
                        self.cc.add_relation(
                            source_id=str(rel.get("source_id", "")),
                            target_id=str(rel.get("target_id", "")),
                            type=rel.get("type", "background"),
                            evidence=rel.get("evidence", ""),
                            metadata=rel.get("metadata", {}),
                        )
                        result["relations_synced"] += 1
                    except Exception as e:
                        logger.warning(f"Failed to sync relation: {e}")
                rels_path.unlink()
                logger.info(f"Synced {result['relations_synced']} relations → cc.db, deleted relations.jsonl")
            except Exception as e:
                logger.error(f"Failed to sync relations.jsonl: {e}")

        return result

    def _build_algo_cc_context(self, unique_methods: list[dict]) -> str:
        """Build CC context for algorithm proposals (2-hop subgraph around each method)."""
        if not unique_methods:
            return ""
        from claim_chain.query import CCQueryInterface
        qi = CCQueryInterface(self.cc)
        lines = []
        for m in unique_methods[:5]:
            atom_id = m.get("atom_id", m.get("id", ""))
            if atom_id:
                neighbors = qi.query_neighbors(atom_id, depth=1)
                if neighbors.get("neighbors"):
                    neighbor_titles = [n["title"] for n in neighbors["neighbors"]]
                    lines.append(f"- {m.get('title', '?')} → {', '.join(neighbor_titles)}")
        return "\n".join(lines) if lines else ""

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
            PHASE_PLAN_1: f"第{iteration+1}轮·W2 问题分析。分析核心难点。{em_suffix}",
            PHASE_PLAN_2: f"第{iteration+1}轮·W3 方案方向。针对识别的难点提出解决方向。{em_suffix}",
            PHASE_IDEATE: f"第{iteration+1}轮·W4 具体方案生成。伪代码级实现方案。{em_suffix}",
            PHASE_CODE: f"第{iteration+1}轮·W4 Code。单Agent代码实现。{em_suffix}",
            PHASE_ANALYZE: f"第{iteration+1}轮·W5 Analyze。当前最佳{best:.1f}。Judge+Rubrics评分。{em_suffix}",
            PHASE_WRITE_PLAN: f"W7.1 论文计划。构建Claims-Evidence Matrix和大纲。{em_suffix}",
            PHASE_WRITE_FIGURE: f"W7.2 图表生成。基于PAPER_PLAN生成矢量图表。{em_suffix}",
            PHASE_WRITE_LATEX: f"W7.3 LaTeX写作。逐section生成内容。{em_suffix}",
            PHASE_WRITE_COMPILE: f"W7.4 编译。编译paper/main.tex为PDF。{em_suffix}",
            PHASE_WRITE_IMPROVE: f"W7.5 审稿修复。外部LLM多轮审稿修复。{em_suffix}",
            PHASE_REVIEW: f"W8 Review。多轮研究审阅（含故事逻辑维度）。{em_suffix}",
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

        if step_name == "invoke_four_personas":
            # Each persona independently runs: Progressive Discovery+SME →
            # academic_search → proposal. 4 independent calls, then ELO ranks.
            search_focus = {
                PHASE_PLAN_1: "方向搜索 — 搜索研究领域内的理论难点和已有方法的已知局限",
                PHASE_PLAN_2: "方向搜索 — 搜索针对已识别难点的可能解决方向、跨领域灵感",
                PHASE_IDEATE: "实现细节搜索 — 搜索伪代码实现、架构设计、损失函数设计、计算优化",
            }.get(phase, "方向搜索")

            sme_contexts = state.get("sme_contexts", [])
            sme_context_text = ""
            if sme_contexts:
                for sc in sme_contexts[-3:]:  # Last 3 upstream phases
                    sme_context_text += f"\n### 上游阶段: {sc.get('phase', '?')}\n"
                    for rp in sc.get("ranked_proposals", [])[:2]:
                        sme_context_text += f"- [{rp.get('rank', '?')}] {rp.get('title', '?')}: {rp.get('content', '')[:300]}\n"

            product_spec = PRODUCT_SPECS.get(phase, {})
            spec_text = json.dumps(product_spec, ensure_ascii=False, indent=2)

            persona_topic = (
                f"[{phase}] 4-Persona 独立方案生成。\n"
                f"研究问题: {state.get('research_topic', '')}\n\n"
                f"## 你的任务\n"
                f"你是一个具有独特视角的 AI 研究者。请独立完成以下三步：\n\n"
                f"### 第1步: Progressive Discovery + SME 创造性思维\n"
                f"1. 拆解问题为基元概念和关系\n"
                f"2. 搜索跨领域结构同构(结构映射引擎)\n"
                f"3. 尝试反事实嫁接——违反边界条件，制造认知冲突，再看能否调和\n"
                f"4. 用三公理自检: 自识别/复述不变性/累积性\n\n"
                f"### 第2步: academic_search\n"
                f"搜索侧重: {search_focus}\n"
                f"使用所有可用搜索工具(paper-navigator, WebSearch, WebFetch)\n\n"
                f"### 第3步: 产出方案\n"
                f"根据产物规格要求，产出结构化方案。\n\n"
                f"## 产物规格(必须全部包含)\n{spec_text}\n\n"
                f"## 上游 SME Context(从前序阶段传递)\n{sme_context_text or '(无——这是第一个阶段)'}\n\n"
            )

            # Inject experiment feedback from previous iterations
            if state.get("iteration", 0) > 0:
                exp_fb = _build_experiment_feedback(state, self.session_dir)
                if exp_fb:
                    persona_topic += f"## 上一轮实验结果与反馈\n{exp_fb}\n\n"

            # Inject Claim Chain ideation context (structure-guided)
            cc_ctx = _build_cc_ideation_context(state, self.session_dir, phase)
            if cc_ctx:
                persona_topic += f"## Claim Chain 引导 (Structure-Guided Ideation)\n{cc_ctx}\n\n"

            # W2: Read ALL existing CC atoms as structured knowledge baseline
            if phase == PHASE_PLAN_1:
                cc_full = _build_cc_full_context(self.session_dir)
                if cc_full:
                    persona_topic += f"{cc_full}\n\n"

            # Inject regeneration feedback: tell personas to REVISE, not regenerate
            if state.get("needs_regeneration"):
                last_verif = state.get("last_verification", {})
                if last_verif:
                    persona_topic += "## REVISION: 请基于你上次的方案进行针对性修改\n"
                    persona_topic += f"审核反馈: {last_verif.get('details', '不符合产物规格')}\n"
                    failures = last_verif.get('failures_per_proposal', {})
                    if failures:
                        persona_topic += "各方案缺失/不足项:\n"
                        for title, reason in list(failures.items())[:4]:
                            persona_topic += f"  - {title[:60]}: {reason}\n"
                    persona_topic += "\n重要: 你会收到你上次生成的方案。请直接在原方案基础上修改改进——补充缺失内容，加深分析深度，修正不足。不要从头重新生成，保留原方案中正确的部分。\n\n"

            # Build phase-specific JSON output format that maps PRODUCT_SPECS to fields
            required_items = product_spec.get("required", [])
            if phase == PHASE_PLAN_1:
                json_format_desc = (
                    '{"title": "方案标题(简洁，80字内)", '
                    '"hypothesis": "核心假设: 明确指出具体的难点(到网络组件/loss项级别)，因果分析(为什么导致性能瓶颈)，以及baseline为何无法解决(2-3句话)", '
                    '"method_sketch": "详细方法描述: (1)具体难点识别——到网络组件/loss项级别; (2)因果分析——为什么这个难点导致性能瓶颈; (3)baseline局限性——现有方法为什么解决不了; (4)你的方案思路(至少300字)", '
                    '"search_results_summary": "搜索到的关键文献/资源摘要"}'
                )
            elif phase == PHASE_PLAN_2:
                json_format_desc = (
                    '{"title": "方向标题(简洁，80字内)", '
                    '"hypothesis": "核心假设: 这个方向如何解决W2识别的难点(2-3句话)", '
                    '"method_sketch": "详细方向描述: (1)方向描述——解决什么难点; (2)针对哪些难点——关联W2分析; (3)技术路径概要——用什么方法; (4)与baseline的区分点(至少300字)", '
                    '"search_results_summary": "搜索到的关键文献/资源摘要"}'
                )
            elif phase == PHASE_IDEATE:
                json_format_desc = (
                    '{"title": "方案标题(简洁，80字内)", '
                    '"hypothesis": "核心假设: 算法改动的核心idea(2-3句话)", '
                    '"method_sketch": "实现详情: (1)伪代码(清晰变量名，标注修改位置); (2)架构改动列表(ADD/MODIFY/REMOVE); (3)损失函数签名(fn_name(args)->Tensor+说明); (4)计算开销估计(至少400字)", '
                    '"search_results_summary": "搜索到的实现参考"}'
                )
            else:
                json_format_desc = (
                    '{"title": "方案标题", "hypothesis": "核心假设", '
                    '"method_sketch": "具体方法描述", '
                    '"search_results_summary": "搜索到的关键文献/资源摘要"}'
                )

            persona_topic += (
                f"## CRITICAL: 输出格式\n"
                f"你的完整回复必须是一个JSON对象，不要写任何其他文字。\n"
                f"JSON结构:\n"
                f"{json_format_desc}\n"
                f"注意: method_sketch 必须包含产物规格中的所有必要项。\n"
            )

            regen_context = {}
            if state.get("needs_regeneration"):
                regen_context["prev_proposals"] = state.get("last_persona_proposals", [])
                regen_context["needs_regeneration"] = True

            return {
                "done": False,
                "phase": phase,
                "step": step_name,
                "step_index": state.get("sub_loop_step", 0) - 1,
                "action": "invoke_personas",
                "persona_agents": FOUR_PERSONA_AGENTS,
                "topic": persona_topic,
                "search_focus": search_focus,
                "product_spec": product_spec,
                "regen_context": regen_context,
                "instruction": (
                    f"[{phase}] 4 Persona 独立调用。每个 persona 独立完成: "
                    f"SME创造性思维 → {search_focus} → 产出方案。"
                ),
            }

        elif step_name == "sync_to_cc":
            # Sync search results + persona proposals to CC via grounding pipeline
            proposals = state.get("last_persona_proposals", [])
            return {
                "done": False,
                "phase": phase,
                "step": step_name,
                "step_index": state.get("sub_loop_step", 0) - 1,
                "action": "sync_to_cc",
                "proposals": proposals,
                "session_dir": str(self.session_dir),
                "instruction": (
                    f"[{phase}] sync_to_cc: 将文献搜索结果同步到 Claim Chain "
                    f"(via CCGrounding gatekeeper + BGE-M3 dedup)."
                ),
            }

        elif step_name == "evaluate_novelty":
            # RND coarse + LLM rubric fine evaluation
            proposals = state.get("last_persona_proposals", [])
            return {
                "done": False,
                "phase": phase,
                "step": step_name,
                "step_index": state.get("sub_loop_step", 0) - 1,
                "action": "evaluate_novelty",
                "proposals": proposals,
                "rnd_kb_path": str(self.session_dir / "_index" / "rnd_kb.jsonl"),
                "instruction": (
                    f"[{phase}] RND 创新评价: BGE-M3 粗筛 → LLM 5维 rubric 精筛."
                ),
            }

        elif step_name == "write_sme":
            tourney = state.get("last_tournament_result", {})
            ranked = tourney.get("ranked", [])
            sme_context = {
                "phase": phase,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "ranked_proposals": [
                    {
                        "rank": i + 1,
                        "persona": rp.get("source_agent", rp.get("persona", "?")),
                        "title": rp.get("title", ""),
                        "content": rp.get("method_sketch", rp.get("hypothesis", "")),
                        "elo_score": rp.get("elo_rating", 0),
                        "dimension_scores": {
                            d: rp.get(d, 0)
                            for d in self._get_phase_dims(phase)
                        },
                    }
                    for i, rp in enumerate(ranked)
                ],
                "verification": state.get("last_verification_result", {}),
            }
            if "sme_contexts" not in state:
                state["sme_contexts"] = []
            state["sme_contexts"].append(sme_context)
            self._write_state(state)

            return {
                "done": False,
                "phase": phase,
                "step": step_name,
                "step_index": state.get("sub_loop_step", 0) - 1,
                "action": "write_sme",
                "sme_context": sme_context,
                "instruction": (
                    f"[{phase}] SME Context 已写入。{len(ranked)} 个排名方案传递至下一阶段。"
                ),
            }

        elif step_name == "run_step_pipeline":
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
                json.dumps(ctx.get("indexing", {}), ensure_ascii=False, indent=2)[:1000000],
                "",
                "### 概念基元",
                json.dumps(ctx.get("primitives", [])[:10], ensure_ascii=False, indent=2)[:1000000],
                "",
                "### 可违反边界条件",
                json.dumps(ctx.get("violable_boundaries", [])[:5], ensure_ascii=False, indent=2)[:1000000],
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

        elif step_name == "verify_products":
            return {
                "done": False,
                "phase": phase,
                "step": step_name,
                "step_index": state.get("sub_loop_step", 0) - 1,
                "action": "verify_products",
                "product_spec": PRODUCT_SPECS.get(phase, {}),
                "topic": f"[{phase}] 产物验证: 检查排名方案是否满足产物规格。",
            }

        elif step_name == "evolution_memory":
            distill_type = {
                PHASE_PLAN_1: "ide", PHASE_PLAN_2: "ide",
                PHASE_IDEATE: "ide",
                PHASE_ANALYZE: "ese",
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

        elif step_name == "generate_code_spec":
            return self._generate_code_spec(state, phase)

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

        elif step_name == "refine_atoms":
            return {
                "done": False,
                "phase": phase,
                "step": step_name,
                "step_index": state.get("sub_loop_step", 0) - 1,
                "action": "refine_atoms",
                "argument": f"[{phase}] 将 CC atoms 翻译为具体算法规格 (RefinedAtom schema)。"
                           f"对每个 method+proposal atom 生成 refined_proposals/<atom_id>.json",
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

        elif step_name == "invoke_skill_paper_plan":
            return {
                "done": False,
                "phase": phase,
                "step": step_name,
                "step_index": state.get("sub_loop_step", 0) - 1,
                "action": "invoke_skill",
                "skill": "/flux-paper-plan",
                "instruction": (
                    "生成论文大纲。若缺少NARRATIVE_REPORT.md，先从W6讨论记录+cc.db提取核心发现。"
                    "构建Claims-Evidence Matrix。完成故事框架自检（One-Sentence Contribution + What/Why/So What）。"
                    f"研究问题: {state.get('research_topic', '')}"
                ),
            }

        elif step_name == "invoke_skill_paper_figure":
            return {
                "done": False,
                "phase": phase,
                "step": step_name,
                "step_index": state.get("sub_loop_step", 0) - 1,
                "action": "invoke_skill",
                "skill": "/flux-paper-figure",
                "instruction": "基于PAPER_PLAN.md中的图表计划，从实验数据生成矢量格式图表。12-point质量检查。",
            }

        elif step_name == "invoke_skill_paper_write":
            return {
                "done": False,
                "phase": phase,
                "step": step_name,
                "step_index": state.get("sub_loop_step", 0) - 1,
                "action": "invoke_skill",
                "skill": "/flux-paper-write",
                "instruction": (
                    "基于PAPER_PLAN.md和figures/目录，逐section生成LaTeX内容。"
                    "使用paper/math_commands.tex中的数学宏。"
                    "遵循flux-shared-references/writing-principles.md。"
                    f"研究问题: {state.get('research_topic', '')}"
                ),
            }

        elif step_name == "invoke_skill_paper_compile":
            return {
                "done": False,
                "phase": phase,
                "step": step_name,
                "step_index": state.get("sub_loop_step", 0) - 1,
                "action": "invoke_skill",
                "skill": "/flux-paper-compile",
                "instruction": "编译paper/main.tex为PDF。检查引用、字体、页面数。修复编译错误直到成功。",
            }

        elif step_name == "invoke_skill_paper_improve":
            return {
                "done": False,
                "phase": phase,
                "step": step_name,
                "step_index": state.get("sub_loop_step", 0) - 1,
                "action": "invoke_skill",
                "skill": "/flux-paper-improve",
                "instruction": (
                    "使用外部LLM（MiMo）对论文进行多轮审稿修复。"
                    "每轮：提交论文→获取评分→修复问题→重新编译。"
                    "最多3轮。保存每轮PDF快照。"
                    f"研究问题: {state.get('research_topic', '')}"
                ),
            }

        elif step_name == "invoke_skill_flux_review":
            return {
                "done": False,
                "phase": phase,
                "step": step_name,
                "step_index": state.get("sub_loop_step", 0) - 1,
                "action": "invoke_skill",
                "skill": "/flux-review-loop",
                "instruction": (
                    "多轮研究审稿（含故事逻辑维度）。"
                    "三选一：回W5(修改算法) / 补实验(就地) / 放展望(limits)。"
                    f"研究问题: {state.get('research_topic', '')}"
                ),
            }

        elif step_name == "verify_deliverables":
            specs = PRODUCT_SPECS.get(phase, {})
            deliverables = specs.get("deliverables", [])
            workspace_dir = Path(state.get("workspace_dir", "."))
            missing = []
            for d in deliverables:
                p = workspace_dir / d
                if d.endswith("/"):
                    if not p.is_dir():
                        missing.append(d)
                else:
                    if not p.exists():
                        missing.append(d)
            return {
                "done": True,
                "phase": phase,
                "step": step_name,
                "step_index": state.get("sub_loop_step", 0) - 1,
                "verified": len(missing) == 0,
                "missing": missing,
                "deliverables": deliverables,
            }

        return {"done": True, "phase": phase}

    # ═══════════════════════════════════════════════════════════════
    # W4 Code — Plan-driven 模式: generate_code_plan + wait_user_code
    # ═══════════════════════════════════════════════════════════════

    def _generate_code_spec(self, state: dict, phase: str) -> dict:
        """生成 build_spec.json —— 实现之前精确指定要做什么。"""
        import uuid
        from pes_controller.build_spec import BuildSpec, ComponentChange, LossSpec, Hyperparams

        workspace = self.workspace
        spec_id = str(uuid.uuid4())[:8]
        iteration = state.get("iteration", 0)
        research_topic = state.get("research_topic", "")

        tournament = state.get("last_tournament_result", {})
        ranked = tournament.get("ranked", [])
        winner = ranked[0] if ranked else {}
        winner_title = winner.get("title", research_topic)
        hypothesis = winner.get("hypothesis", "")
        method_sketch = winner.get("method_sketch", "")

        cc_atoms = self.cc.get_atoms(limit=200) if self.cc else []
        confirmed_raw = state.get("confirmed_baselines")
        if isinstance(confirmed_raw, list) and len(confirmed_raw) > 0:
            baselines = [b if isinstance(b, str) else b.get("title", str(b)) for b in confirmed_raw]
        else:
            dc = state.get("domain_config", {})
            dc_baselines = dc.get("known_baselines", []) if isinstance(dc, dict) else []
            baselines = dc_baselines if dc_baselines else []
        target_baseline = baselines[0] if baselines else ""

        component_changes = []
        if method_sketch:
            for comp in cc_atoms:
                comp_title = comp.get("title", "")
                if comp_title and any(
                    kw.lower() in method_sketch.lower()
                    for kw in comp_title.split(".")[-1].split("_")
                ):
                    component_changes.append(ComponentChange(
                        action="MODIFY", component=comp_title,
                        reason=f"Required by: {winner_title[:80]}",
                        before=comp.get("content", "")[:200],
                        after=f"[To be specified per {winner_title[:60]}]",
                    ))
        seen = set()
        component_changes = [c for c in component_changes if not (c.component in seen or seen.add(c.component))][:12]

        loss_specs = []
        for comp in cc_atoms:
            comp_title = comp.get("title", "").lower()
            if any(kw in comp_title for kw in ["loss", "actor_loss", "critic_loss", "qf_loss", "td_error", "entropy"]):
                loss_specs.append(LossSpec(
                    name=comp.get("title", "unknown"),
                    signature=f"def loss_fn(...) -> Tensor",
                    formula="See CC atom content",
                    description=comp.get("content", "")[:300],
                ))

        hp = Hyperparams()
        success_criteria = [
            f"Mean return > best baseline ({target_baseline}) on confirmed benchmark environment",
            "p < 0.05 over 5 seeds",
            "Training wall time < 2x baseline",
        ]

        spec = BuildSpec(
            spec_id=spec_id, target_method=winner_title,
            target_baseline=target_baseline, research_topic=research_topic,
            hypothesis=hypothesis, method_sketch=method_sketch,
            component_changes=component_changes, loss_specs=loss_specs,
            hyperparams=hp, baselines=baselines,
            benchmark=state.get("confirmed_benchmark") or state.get("domain_config", {}).get("default_benchmark", ""),
            success_criteria=success_criteria,
            cc_atom_ids=[a.get("id", "") for a in cc_atoms[:10]],
        )

        spec.save(self.session_dir / "build_spec.json")
        errors = spec.validate()

        return {
            "done": False, "phase": phase,
            "step": "generate_code_spec",
            "action": "generate_code_spec",
            "spec_path": str(self.session_dir / "build_spec.json"),
            "spec": spec.to_dict(),
            "validation_errors": errors,
            "instruction": (
                f"[{phase}] BuildSpec: {target_baseline} + "
                f"{len(component_changes)} changes, {len(loss_specs)} loss fns, "
                f"vs {', '.join(baselines[:3])}"
                + (f"\n校验错误: {errors}" if errors else "")
            ),
        }

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
            plan_text = plan_md.read_text(encoding='utf-8')[:1000000]
            context_parts.append(f"## 实验计划\n{plan_text}")

        # Claim Chain atoms (from cc.db — canonical SQL store)
        cc_atoms = self.cc.get_atoms()
        if cc_atoms:
            # Format atoms as display text for plan context
            cc_lines = []
            for a in cc_atoms:
                cc_lines.append(json.dumps(a, ensure_ascii=False))
            raw_display = "\n".join(cc_lines)
            try:
                from plan_templates import sanitize_plan_text
                raw_display = sanitize_plan_text(raw_display[:1000000])
            except ImportError:
                raw_display = raw_display[:1000000]
            context_parts.append(f"## Claim Chain 原子\n{raw_display}")

        rn_text = ""
        rn_path = workspace / "research_notes.md"
        if rn_path.exists():
            rn_text = rn_path.read_text(encoding='utf-8')[:1000000]
            context_parts.append(f"## 文献调研笔记\n{rn_text}")

        em_summary = self._load_evolution_memory_summary()
        if em_summary:
            context_parts.append(f"## Evolution Memory\n{json.dumps(em_summary, indent=2)[:1000000]}")

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
                methods.append({"title": title, "tags": tags, "content": content,
                               "atom_id": a.get("id", 0)})
            elif atom_type == "fact" and any(
                t in tags for t in ["next-iteration", "method", "literature", "SOTA_2026"]
            ):
                methods.append({"title": title, "tags": tags, "content": content,
                               "atom_id": a.get("id", 0)})
            elif atom_type == "fact" and any(
                t in tags for t in ["benchmark", "baseline"]
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

        # ── Domain-aware infrastructure deliverables ──
        # Read from DomainConfig if available, otherwise use generic templates
        domain_cfg = _get_domain_config(state)

        deliverables.append("- [ ] artifacts/config.py — 实验配置 (超参数, 随机种子, 数据路径)")
        deliverables.append("- [ ] artifacts/model.py — 模型定义 (网络结构, 层数, 激活函数)")
        deliverables.append("- [ ] artifacts/data.py — 数据加载器 (批处理, 预处理, 增强)")
        deliverables.append("- [ ] artifacts/trainer.py — 训练器 (训练循环, 评估, 日志, checkpoint)")

        specs.append(_domain_infra_spec("config.py", domain_cfg, default=(
            "### artifacts/config.py\n- 实验环境配置\n- 共享超参数 (seed, batch_size, 优化器设置)\n- 各算法专属参数")))
        specs.append(_domain_infra_spec("model.py", domain_cfg, default=(
            "### artifacts/model.py\n- 模型网络定义\n- 可配置的层数和激活函数\n- 支持常见正则化方法")))

        # ── 迭代感知基线选择 ──
        # Meta tags that describe atom type/category, NOT algorithm names
        _META_TAGS = {"experiment", "w5-analyze", "benchmark", "literature", "method", "survey",
                      "next-iteration",
                      "evaluation", "diagnosis", "baseline",
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

        # 读 CC relations from cc.db
        cc_relations = self.cc.get_relations()

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

        # ── Baseline discovery (web search + CC + topic text, NOT static presets) ──
        cc_baselines = _discover_baselines_from_cc(cc_atoms)
        topic_candidates = _extract_candidates_from_topic(state.get("research_topic", ""))
        web_candidates = _search_web_for_baselines(state.get("research_topic", ""))
        known_baselines = list(dict.fromkeys(cc_baselines + web_candidates + topic_candidates))
        # Persist discovered baselines to CC via CCGrounding (gatekeeper-validated)
        new_baselines = []
        for bl in topic_candidates:
            if not any(a.get("title") == bl and a.get("type") == "fact" and "baseline" in a.get("tags", []) for a in cc_atoms):
                new_baselines.append({"title": bl, "content": f"Baseline: {bl}", "source": "topic_extraction"})
                cc_atoms.append({"title": bl, "type": "fact", "tags": ["baseline", "auto-discovered", "w2-plan"]})
        if new_baselines:
            try:
                from claim_chain.grounding import CCGrounding
                grounding = CCGrounding(self.cc)
                grounding.enrich_from_web_search(new_baselines)
            except Exception:
                pass
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
            # 首次迭代: 使用 DomainConfig 中定义的已知基线
            if known_baselines:
                base_algos.update(known_baselines[:3])
                baseline_notes.append(f"首次: {', '.join(known_baselines[:3])} 基线")
        elif not experiment_atoms and proposal_atoms:
            # 有提案但无实验 — 上次计划未执行
            if known_baselines:
                base_algos.update(known_baselines[:3])
                baseline_notes.append(f"有提案未执行: {', '.join(known_baselines[:3])} 基线 + 上次提案")
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
            for algo, info in tested_algos.items():
                if info.get("score", 0) > 0:
                    base_algos.add(algo)
            # 核心基线: 使用 DomainConfig 已知基线中尚未覆盖的
            for bl in known_baselines[:3]:
                if bl.upper() not in base_algos and bl.upper() not in base_algos:
                    base_algos.add(bl.upper())
                    baseline_notes.append(f"保留 {bl} 作为 baseline 对照")

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

            # Phase 5: Try Jinja2 rendering from refined_proposals
            # Try multiple filename variants + glob for prefix_{id}.json naming pattern
            refined_dir = self.session_dir / "iterations" / str(iteration) / "refined_proposals"
            refined_json = _find_refined_json(refined_dir, fname)
            if refined_json and refined_json.exists():
                try:
                    from plan_templates import render_algo_section
                    spec_lines = [render_algo_section(refined_json, filename=f"{fname}")]
                    specs.append("\n".join(spec_lines))
                    continue  # skip manual spec building
                except Exception:
                    pass  # fall through to manual spec

            # Fallback: generate inline spec for baselines from DomainConfig
            if algo.lower() in (b.lower() for b in known_baselines):
                spec_lines.append(_baseline_inline_spec(algo))
            elif info.get("title"):
                spec_lines.append(f"- **上次实验**: {info['title'][:120]}")
            # Add proposal mechanism description from ranked items
            if algo in proposed_algos:
                for r_item in ranked[:5]:
                    if r_item.get("title", "").split(":")[0].strip().upper()[:10] == algo[:10]:
                        sketch = r_item.get("method_sketch", "")[:1000000]
                        if sketch:
                            cleaned = _sanitize_sketch(sketch)
                            if cleaned.strip():
                                spec_lines.append(f"- **算法思路**: {cleaned[:1000000]}")
                        break
            # Add atom content if available
            atom = info.get("atom")
            if atom and atom.get("content", "").strip():
                content_preview = atom["content"][:300].replace("\n", " ")
                spec_lines.append(f"- CC 记录: {content_preview}")
            elif algo in tested_algos:
                spec_lines.append(f"- 分数: {score_val:.1f}")
                spec_lines.append("trainer.py 集成: 见 refined_proposals/<atom_id>.json — BaseAlgorithm ✅")
            else:
                spec_lines.append("trainer.py 集成: 见 refined_proposals/<atom_id>.json — BaseAlgorithm ✅")
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
                            "method_sketch": p.get("method_sketch", "")[:1000000],
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
                proposal_count += 1
                proposed_algos.add(algo_abbr.upper())

                # Phase 5: Try Jinja2 rendering from refined_proposals
                # Pass atom_id for precise {prefix}_{id}.json matching
                refined_dir = self.session_dir / "iterations" / str(iteration) / "refined_proposals"
                atom_id_for_lookup = m.get("atom_id", 0)
                refined_json = _find_refined_json(refined_dir, algo_abbr, atom_id=atom_id_for_lookup)
                if refined_json and refined_json.exists():
                    try:
                        from plan_templates import render_algo_section
                        spec = render_algo_section(refined_json, filename=f"{algo_abbr}")
                        specs.append(spec)
                        continue  # skip to next proposal
                    except Exception:
                        pass

                # Manual fallback spec — extract and display the proposal's unique idea
                spec_parts = [f"### artifacts/{algo_abbr}.py", f"- 来源: {title}"]
                pp = prop_by_title.get(title) or {}
                sketch = pp.get("method_sketch", "")[:1000000]
                if sketch:
                    # Strip philosophical boilerplate, keep mechanism description
                    cleaned = _sanitize_sketch(sketch)
                    if cleaned.strip():
                        spec_parts.append(f"- **算法思路**: {cleaned[:1000000]}")
                # Also extract from CC atom content
                if m.get("content", "").strip():
                    try:
                        content_json = json.loads(m["content"]) if isinstance(m["content"], str) else m["content"]
                        hypothesis = content_json.get("hypothesis", "")
                        novelty = content_json.get("novelty_claim", "")
                        primitives = content_json.get("primitives_used", [])
                        if hypothesis:
                            spec_parts.append(f"- **假设**: {hypothesis[:300]}")
                        if novelty:
                            spec_parts.append(f"- **创新点**: {novelty[:300]}")
                        if primitives:
                            spec_parts.append(f"- **概念基元**: {', '.join(primitives[:8])}")
                    except (json.JSONDecodeError, TypeError):
                        spec_parts.append(f"- **摘要**: {str(m['content'])[:300]}")
                spec_parts.append("trainer.py 集成: BaseAlgorithm ✅ (issubclass 已验证)")
                specs.append("\n".join(spec_parts))

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
                        winner_sketch = r_item.get("method_sketch", "")[:1000000]
                        break
                spec_parts = [f"### artifacts/{winner_short}.py", f"- ELO 冠军提案: {winner}"]
                if winner_sketch:
                    spec_parts.append(f"- 方法思路: {winner_sketch}")
                spec_parts.append("trainer.py 集成: 见 refined_proposals/<atom_id>.json — BaseAlgorithm ✅")
                specs.append("\n".join(spec_parts))
                used_fnames.add(winner_short)

        # 运行脚本
        deliverables.append("- [ ] artifacts/train_all.py — 一键训练所有算法的 master 脚本")
        deliverables.append("- [ ] artifacts/analyze.py — 结果分析脚本 (学习曲线, 性能对比表, 统计检验)")
        deliverables.append("- [ ] artifacts/smoke_test.py — Smoke test (1 episode, 检查无 NaN/维度错误)")

        specs.append("### artifacts/train_all.py\n- 依次或并行运行所有算法配置\n- 每个算法保存独立 checkpoint 和日志\n- 支持 --algo 参数只跑指定算法\n- 支持 --quick 模式 (减少 timesteps 用于快速验证)")
        specs.append("### artifacts/analyze.py\n- 读取所有算法日志, 绘制学习曲线\n- 输出性能对比表 (mean ± std over seeds)\n- Welch's t-test 显著性检验\n- 输出 analysis_report.md")

        # ── 生成验收标准 (domain-aware) ──
        acceptance_tpl = domain_cfg.get("acceptance_criteria", "")
        if acceptance_tpl:
            acceptance = acceptance_tpl
        else:
            acceptance = """1. `python artifacts/smoke_test.py` 所有算法通过 (无 import 错误, 无崩溃, 无维度 mismatch)
2. `python artifacts/train_all.py --quick` 所有算法在快速模式下不崩溃
3. 基线算法达到 DomainConfig 中定义的已知性能范围
4. 至少一个提案方法在完整训练后超越最强基线 >5%
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

        # Final sanitize: remove residual buzzwords from the full plan text
        try:
            from plan_templates import sanitize_plan_text
            plan_content = sanitize_plan_text(plan_content)
        except ImportError:
            pass

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
                "  1. /flux-code-agent-pre " + str(plan_path) + "\n"
                "  2. [实现代码...]\n"
                "  3. /flux-code-agent-check " + str(plan_path) + "\n"
                "  4. [修正...]\n"
                "  5. /flux-code-agent-post " + str(plan_path) + "\n"
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
        """等待用户通过 /flux-code-agent-post 完成代码实现。
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
                "完成后运行 /flux-code-agent-post 回传结果。"
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

        # 1. CC 写入 — 统一走 CCGrounding
        if phase == PHASE_ANALYZE:
            if cc_atoms:
                from claim_chain.grounding import CCGrounding
                grounding = CCGrounding(self.cc)
                # Collect results for enrich_from_experiments
                results_dict = {}
                for atom_data in cc_atoms:
                    title = atom_data.get("title", "unknown")
                    results_dict[title] = {
                        "score_mean": atom_data.get("score", atom_data.get("mean", 0)),
                        "score_std": 0,
                        "status": "tested",
                    }
                report = grounding.enrich_from_experiments(results_dict)
                events.append(f"claim_chain_updated: {report['atoms_created']} experiment result atoms written (via CCGrounding)")

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
            return {"transitioned": True, "to": PHASE_WRITE_PLAN}

        elif action == "terminate":
            state["phase"] = PHASE_TERMINATED
            state["status"] = "terminated"
            self._write_state(state)
            return {"transitioned": True, "to": PHASE_TERMINATED}

        return {"error": f"Unknown action: {action}"}

    def _auto_next_phase(self, phase: str, state: dict) -> str:
        """根据当前阶段自动计算下一阶段。"""
        if phase == PHASE_PLAN_1:
            return PHASE_PLAN_2
        elif phase == PHASE_PLAN_2:
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
            return PHASE_PLAN_1  # 未达标→回到Plan-1，Island上已有积累
        elif phase == PHASE_WRITE_PLAN:
            return PHASE_TERMINATED  # 满意→终止（不满意由用户选Review）
        elif phase == PHASE_REVIEW:
            return PHASE_WRITE_PLAN  # Review后回到Write
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

        if phase in ("Plan", PHASE_PLAN_1, PHASE_PLAN_2, PHASE_IDEATE):
            return self._step_indexing_plan(agent_role, cc_idx, grid_idx)
        elif phase in ("Ideate", PHASE_IDEATE):
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
            primitives = []
            for a in relevant_atoms[:20]:
                is_proposal = "proposal" in a.get("tags", [])
                # For proposals, extract sub-concepts from primitives_used to avoid self-referencing
                if is_proposal:
                    try:
                        content = json.loads(a.get("content", "{}")) if isinstance(a.get("content"), str) else a.get("content", {})
                        sub_primitives = content.get("primitives_used", [])
                        for sp in sub_primitives:
                            if sp and not any(sp.lower() in p["title"].lower() for p in primitives):
                                primitives.append({
                                    "atom_id": a["id"], "title": sp, "tags": a.get("tags", []),
                                    "content": f"Sub-concept of: {a['title'][:100]}",
                                    "is_sub_primitive": True,
                                })
                    except (json.JSONDecodeError, TypeError):
                        pass
                if not is_proposal or len(primitives) < 2:
                    primitives.append({
                        "atom_id": a["id"], "title": a["title"], "tags": a.get("tags", []),
                        "content": a.get("content", "")[:200],
                    })

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
            from plugins.ideation.structure_mapping import StructureMappingEngine
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
        """Generate meaningful proposals when CC is empty.

        Produces proposals with concrete, testable hypotheses derived from:
        1. Cross-domain isomorphism search (SME engine)
        2. Topic-aware mechanism generation (no hardcoded domain axes)
        3. DomainConfig improvement strategies

        NO CellGrid coordinates, NO philosophical templates.
        Each proposal must describe a specific, falsifiable mechanism.
        """
        import random
        topic = state.get("research_topic", "")
        proposals = []

        # ── Source 1: SME cross-domain isomorphism search ──
        try:
            from plugins.ideation.structure_mapping import StructureMappingEngine
            sme = StructureMappingEngine()
            isos = sme.find_isomorphisms_across_library([topic[:60]], min_similarity=0.4)
            for iso in isos[:8]:
                src_pat = " × ".join(iso.get("source_pattern", ["?"])[:2])
                tgt_pat = " × ".join(iso.get("target_pattern", ["?"])[:2])
                src_domain = iso.get('source_domain', '')
                tgt_domain = iso.get('target_domain', '')
                relation = iso.get("isomorphic_relation_chain", "")
                proposals.append({
                    "source_primitive": f"{src_domain}:{src_pat}",
                    "target_domain": f"{tgt_domain}:{tgt_pat}",
                    "isomorphic_relation": relation,
                    "confidence": iso.get("confidence", 0.5),
                    "method_sketch": (
                        f"Transfer the {src_pat} mechanism from {src_domain} to {tgt_domain}. "
                        f"The key insight is that {relation}. "
                        f"Adapt the structural pattern to {tgt_domain} constraints, then validate "
                        f"whether the transferred mechanism preserves its core properties."
                    ),
                    "novelty_claim": f"Cross-domain transfer: {src_domain} → {tgt_domain} via {src_pat}",
                })
        except Exception:
            pass

        # ── Source 2: Topic-driven mechanism proposals ──
        # Discover candidate methods from topic text + CC atoms
        # Discover baselines: GitHub → CC → topic text (in priority order)
        cc_atoms = self.cc.get_atoms(limit=200)
        cc_baselines = _discover_baselines_from_cc(cc_atoms)
        github_baselines = _search_github_for_baselines(topic)
        text_baselines = _extract_candidates_from_topic(topic)
        known = list(dict.fromkeys(github_baselines + cc_baselines + text_baselines))
        # If GitHub found baselines, persist them to CC via CCGrounding
        new_baselines = []
        for bl in github_baselines:
            if not any(a.get("title") == bl and a.get("type") == "fact" for a in cc_atoms):
                new_baselines.append({"title": bl, "content": f"Baseline: {bl}", "source": "github_search"})
        if new_baselines:
            try:
                from claim_chain.grounding import CCGrounding
                grounding = CCGrounding(self.cc)
                grounding.enrich_from_web_search(new_baselines)
            except Exception:
                pass
        algorithms = []
        for name in known:
            if name.lower() in topic.lower():
                algorithms.append(name.upper())
        if not algorithms:
            algorithms = known[:3] if len(known) >= 3 else (known or [])

        # Improvement strategies — phrased as testable mechanisms, NOT domain-specific
        # Each strategy describes WHAT to change and WHY it might work
        improvement_strategies = [
            {
                "axis": "representation_learning",
                "mechanism": "Learn a compressed latent representation that discards task-irrelevant variation, "
                           "reducing overfitting and improving generalization",
                "hypothesis": "Compressing the input representation removes noise dimensions, "
                            "allowing the learning algorithm to focus on causally relevant features",
            },
            {
                "axis": "exploration_vs_exploitation",
                "mechanism": "Introduce structured variation into the decision process that systematically "
                           "probes under-explored regions of the solution space, decaying over time",
                "hypothesis": "Structured exploration discovers higher-reward regions that random "
                            "perturbations miss, without sacrificing final performance",
            },
            {
                "axis": "ensemble_diversity",
                "mechanism": "Maintain multiple independent models with enforced diversity, using their "
                           "disagreement to reduce estimation bias and variance",
                "hypothesis": "Diverse ensemble predictions provide a tighter lower bound on the "
                            "target quantity than any single model, reducing systematic errors",
            },
            {
                "axis": "curriculum_learning",
                "mechanism": "Order training examples by difficulty, starting with easy cases and "
                           "progressively introducing harder ones as performance improves",
                "hypothesis": "Curriculum ordering prevents the model from converging to poor local "
                            "minima early in training, enabling better final solutions",
            },
            {
                "axis": "self_supervised_pretraining",
                "mechanism": "Pre-train the model on an auxiliary task derived from unlabeled data "
                            "before fine-tuning on the target objective",
                "hypothesis": "Self-supervised pretraining builds useful internal representations "
                            "that accelerate convergence and improve final performance",
            },
        ]

        if algorithms:
            for alg in algorithms[:2]:
                for strat in random.sample(improvement_strategies, min(3, len(improvement_strategies))):
                    proposals.append({
                        "violated_boundary": f"{alg.lower()}_standard_approach",
                        "primitive_a": alg,
                        "primitive_b": strat["axis"],
                        "counterfactual": (
                            f"What if we apply {strat['axis']} to {alg}? "
                            f"Instead of the standard approach, {strat['mechanism'][:200]}"
                        ),
                        "potential_breakthrough": f"{strat['axis']} for {alg}: {strat['hypothesis'][:200]}",
                        "method_sketch": (
                            f"Modify {alg} by incorporating {strat['axis']}: {strat['mechanism'][:1000000]}. "
                            f"Hypothesis: {strat['hypothesis'][:300]}. "
                            f"Compare against standard {alg} baseline to quantify improvement."
                        ),
                        "novelty_claim": f"Novel combination of {alg} with {strat['axis']} mechanism",
                    })
                    # Also generate a mapping-style version
                    proposals.append({
                        "source_primitive": alg,
                        "target_domain": strat["axis"],
                        "isomorphic_relation": strat["mechanism"][:200],
                        "confidence": 0.3,
                        "method_sketch": (
                            f"Analyze how {strat['axis']} works in its native context. "
                            f"Map the core mechanism to {alg}'s architecture: {strat['mechanism'][:300]}. "
                            f"Hypothesis: {strat['hypothesis'][:200]}."
                        ),
                        "novelty_claim": f"Cross-paradigm integration: {strat['axis']} principles into {alg}",
                    })
        else:
            # No specific algorithms detected — generate generic but concrete proposals
            for i, strat in enumerate(improvement_strategies[:5]):
                proposals.append({
                    "source_primitive": f"baseline_method_{i}",
                    "target_domain": strat["axis"],
                    "isomorphic_relation": strat["mechanism"][:200],
                    "confidence": 0.25,
                    "method_sketch": (
                        f"Apply {strat['axis']} to the current approach: {strat['mechanism'][:300]}. "
                        f"Hypothesis: {strat['hypothesis'][:200]}."
                    ),
                    "novelty_claim": f"Incorporating {strat['axis']} into the existing method",
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
        # Use the proposal's own method_sketch if provided (from improved fallback generator)
        if graft.get("method_sketch"):
            return {
                "title": f"Graft: {graft.get('primitive_a', '?')} + {graft.get('primitive_b', '?')}",
                "hypothesis": graft.get("potential_breakthrough", graft.get("counterfactual", "")),
                "method_sketch": graft["method_sketch"][:1000000],
                "primitives_used": [graft.get("primitive_a", ""), graft.get("primitive_b", "")],
                "novelty_claim": graft.get("novelty_claim", f"Graft combining {graft.get('primitive_a','')} with {graft.get('primitive_b','')}"),
                "proposal_type": "counterfactual_graft",
                "violated_boundary": boundary,
            }
        return {
            "title": f"Graft: {graft.get('primitive_a', '?')} + {graft.get('primitive_b', '?')}",
            "hypothesis": graft.get("potential_breakthrough", graft.get("counterfactual", "")),
            "method_sketch": (
                f"Combine {graft.get('primitive_a', '?')} with {graft.get('primitive_b', '?')}: "
                f"{graft.get('counterfactual', 'explore the combination')}. "
                f"Expected breakthrough: {graft.get('potential_breakthrough', 'novel synthesis')}."
            ),
            "primitives_used": [graft.get("primitive_a", ""), graft.get("primitive_b", "")],
            "novelty_claim": graft.get("novelty_claim", f"Novel combination of {graft.get('primitive_a','')} and {graft.get('primitive_b','')}"),
            "proposal_type": "counterfactual_graft",
            "violated_boundary": boundary,
        }

    def _make_mapping_candidate(self, mapping: dict, mp_key: str) -> dict:
        if mapping.get("method_sketch"):
            return {
                "title": f"Map: {mapping.get('source_primitive', '?')} → {mapping.get('target_domain', '?')}",
                "hypothesis": mapping.get("isomorphic_relation", ""),
                "method_sketch": mapping["method_sketch"][:1000000],
                "primitives_used": [mapping.get("source_primitive", "")],
                "novelty_claim": mapping.get("novelty_claim", f"Cross-domain mapping via {mapping.get('isomorphic_relation','')}"),
                "proposal_type": "structural_mapping",
                "violated_boundary": mp_key,
            }
        return {
            "title": f"Map: {mapping.get('source_primitive', '?')} → {mapping.get('target_domain', '?')}",
            "hypothesis": mapping.get("isomorphic_relation", ""),
            "method_sketch": (
                f"Transfer the mechanism from {mapping.get('source_primitive', '?')} "
                f"to {mapping.get('target_domain', '?')}. "
                f"Core insight: {mapping.get('isomorphic_relation', 'structural similarity')}. "
                f"Adapt the approach to target domain constraints and validate empirically."
            ),
            "primitives_used": [mapping.get("source_primitive", "")],
            "novelty_claim": mapping.get("novelty_claim", f"Cross-domain transfer to {mapping.get('target_domain','?')}"),
            "proposal_type": "structural_mapping",
            "violated_boundary": mp_key,
        }

    def _make_sme_candidate(self, sme: dict, sme_key: str) -> dict:
        src_pat = " × ".join(sme.get("source_pattern", ["?"])[:2])
        tgt_pat = " × ".join(sme.get("target_pattern", ["?"])[:2])
        src_d = sme.get('source_domain', '?')
        tgt_d = sme.get('target_domain', '?')
        if sme.get("method_sketch"):
            return {
                "title": f"SME: {src_d}/{src_pat} → {tgt_d}/{tgt_pat}",
                "hypothesis": sme.get("interpretation", ""),
                "method_sketch": sme["method_sketch"][:1000000],
                "primitives_used": sme.get("source_pattern", []) + sme.get("target_pattern", []),
                "novelty_claim": sme.get("novelty_claim", f"Cross-domain isomorphism: {src_d} → {tgt_d}"),
                "proposal_type": "structural_mapping",
                "violated_boundary": sme_key,
            }
        return {
            "title": f"SME: {src_d}/{src_pat} → {tgt_d}/{tgt_pat}",
            "hypothesis": sme.get("interpretation", ""),
            "method_sketch": (
                f"Transfer the {src_pat} pattern from {src_d} to {tgt_d} using "
                f"{sme.get('isomorphic_relation_chain', 'structural homology')} as the mapping principle. "
                f"Adapt {tgt_pat} to the target context and validate the transfer empirically."
            ),
            "primitives_used": sme.get("source_pattern", []) + sme.get("target_pattern", []),
            "novelty_claim": f"Cross-domain isomorphism: {src_d} → {tgt_d} (confidence={sme.get('confidence',0):.2f})",
            "proposal_type": "structural_mapping",
            "violated_boundary": sme_key,
        }

    def _convergent_reconcile(self, candidates: list[dict], materials: dict) -> list[dict]:
        """CONVERGENT: 为每个候选构建具体调和机制。

        调和机制描述如何将跨域概念适配到目标领域的具体技术路径。
        不再使用 philosophical boilerplate (cyclic_3node, isomorphism 等)。
        """
        sme_mappings = materials.get("sme_mappings", [])
        primitives = materials.get("primitives", [])

        for candidate in candidates:
            # Skip if method_sketch already has sufficient detail (from improved fallback)
            if candidate.get("method_sketch", "") and len(candidate["method_sketch"]) > 300:
                continue

            reconciliation = ""

            # 策略1: 从 SME mappings 借用具体机制描述
            for sme_map in sme_mappings[:5]:
                source = sme_map.get("source_pattern", [])
                target = sme_map.get("target_pattern", [])
                if source and target:
                    reconciliation = (
                        f"The {target[-1] if target else 'mapped mechanism'} from "
                        f"{sme_map.get('target_domain', 'the target domain')} can be adapted to "
                        f"handle the integration. Specifically: apply "
                        f"{' + '.join(target[:2]) if len(target) >= 2 else target[0] if target else 'the adapted pattern'} "
                        f"to resolve the boundary between "
                        f"{' and '.join(source[:2]) if len(source) >= 2 else source[0] if source else 'components'}."
                    )
                    break

            # 策略2: 从 primitives 找互补机制
            if not reconciliation and len(primitives) >= 2:
                a = primitives[0].get("title", primitives[0].get("name", "A"))
                b = primitives[-1].get("title", primitives[-1].get("name", "B"))
                reconciliation = (
                    f"'{a}' provides the foundational framework; "
                    f"'{b}' contributes the specific mechanism to address the integration challenge."
                )

            # 策略3: 通用调和 — 描述实证验证路径
            if not reconciliation:
                reconciliation = (
                    "Validate the approach empirically: start with the simplest integration, "
                    "measure the performance delta, and iteratively refine the adaptation "
                    "based on diagnostic metrics."
                )

            candidate["reconciliation_mechanism"] = reconciliation
            # Only append if method_sketch doesn't already describe the full approach
            if len(candidate.get("method_sketch", "")) < 300:
                candidate["method_sketch"] = candidate.get("method_sketch", "") + f" Integration approach: {reconciliation}"

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
        """Legacy recomposer: formats graft/mapping materials into proposals."""
        proposals = []
        for graft in grafted_materials.get("grafts", []):
            # Use provided method_sketch if available, otherwise build from parts
            if graft.get("method_sketch"):
                sketch = graft["method_sketch"][:1000000]
            else:
                sketch = (
                    f"Combine {graft.get('primitive_a', '?')} with {graft.get('primitive_b', '?')}: "
                    f"{graft.get('counterfactual', 'explore the novel combination')}. "
                    f"Expected: {graft.get('potential_breakthrough', 'performance improvement')}."
                )
            proposals.append({
                "title": f"Graft: {graft.get('primitive_a', '?')} + {graft.get('primitive_b', '?')}",
                "hypothesis": graft.get("potential_breakthrough", ""),
                "method_sketch": sketch,
                "primitives_used": [graft.get("primitive_a", ""), graft.get("primitive_b", "")],
                "novelty_claim": graft.get("novelty_claim", f"Novel combination of {graft.get('primitive_a','')} and {graft.get('primitive_b','')}"),
                "proposal_type": "counterfactual_graft",
            })
        for mapping in grafted_materials.get("mappings", []):
            if mapping.get("method_sketch"):
                sketch = mapping["method_sketch"][:1000000]
            else:
                sketch = (
                    f"Transfer the mechanism from {mapping.get('source_primitive', '?')} "
                    f"to {mapping.get('target_domain', '?')}. "
                    f"Core insight: {mapping.get('isomorphic_relation', 'structural similarity')}."
                )
            proposals.append({
                "title": f"Map: {mapping.get('source_primitive', '?')} → {mapping.get('target_domain', '?')}",
                "hypothesis": mapping.get("isomorphic_relation", ""),
                "method_sketch": sketch,
                "primitives_used": [mapping.get("source_primitive", "")],
                "novelty_claim": mapping.get("novelty_claim", f"Cross-domain transfer to {mapping.get('target_domain','?')}"),
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
        """根据阶段和 CC 当前状态生成搜索查询。从 DomainConfig 读取模板。"""
        topic = state.get("research_topic", "")
        domain_cfg = self._get_domain_config() if hasattr(self, "_get_domain_config") else {}
        templates = domain_cfg.get("search_query_templates", [])

        if templates:
            queries = [t.format(topic=topic) for t in templates[:3]]
        else:
            queries = [f"Latest advances in {topic} 2024-2025"]

        if phase == PHASE_IDEATE:
            gap = state.get("last_gap_analysis")
            if gap:
                queries.append(f"How to improve from {gap.get('best_score')} to {gap.get('target_score')}")

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
        """Classify a variant name into a method family (domain-agnostic)."""
        name_lower = name.lower()
        # Extract family from common naming patterns: "Prefix: or AlgoName ..."
        parts = name_lower.replace(":", " ").replace("-", " ").split()
        return parts[0][:12] if parts else "unknown"

    @staticmethod
    def _classify_axis(name: str) -> str:
        """Classify improvement axis from variant name (domain-agnostic)."""
        return "method_variant"

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

from pes_controller.protocol import atomic_read, atomic_write, dashboard_write, dashboard_write_approval

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


# ---------------------------------------------------------------------------
# Experiment feedback builder (for persona prompts in subsequent iterations)
# ---------------------------------------------------------------------------

def _build_cc_full_context(session_dir: Path) -> str:
    """Read ALL CC atoms grouped by iteration/phase/status for W2 persona context.

    Gives each persona a complete survey of: what baselines exist, what proposals
    were made, what experiments ran, what was validated/refuted — grouped by iteration.
    """
    try:
        from claim_chain.chain import ClaimChainV2
    except ImportError:
        return ""

    cc_db = session_dir / "_index" / "cc.db"
    if not cc_db.exists():
        return ""

    try:
        cc = ClaimChainV2(cc_db)
        atoms = cc.get_atoms()
        cc.close()
    except Exception:
        return ""

    if not atoms:
        return ""

    # Group by iteration
    by_iter: dict[int, list[dict]] = {}
    for a in atoms:
        meta = a.get("metadata", {})
        it = meta.get("iter", 0)
        by_iter.setdefault(it, []).append(a)

    total = len(atoms)
    validated_count = sum(1 for a in atoms if a.get("status") == "validated")
    refuted_count = sum(1 for a in atoms if a.get("status") == "refuted")

    lines = [
        f"## Claim Chain 全量知识 ({total} atoms, {validated_count} ✓ validated, {refuted_count} ✗ refuted)",
        "",
        "> 以下是你已积累的所有知识。请基于这些已知结论规划新方案，",
        "> 避免重复已验证失败的方向，优先拓展已验证成功的方向。",
        "",
    ]

    for it in sorted(by_iter.keys()):
        iter_atoms = by_iter[it]
        lines.append(f"### 第 {it + 1} 轮迭代 ({len(iter_atoms)} atoms)")

        # Group by phase
        by_phase: dict[str, list[dict]] = {}
        for a in iter_atoms:
            meta = a.get("metadata", {})
            ph = meta.get("phase", "unknown")
            by_phase.setdefault(ph, []).append(a)

        for ph in sorted(by_phase.keys()):
            ph_atoms = by_phase[ph]

            baselines = [a for a in ph_atoms if "baseline" in a.get("tags", [])]
            experiments = [a for a in ph_atoms if "Experiment:" in a.get("title", "")]
            proposals = [a for a in ph_atoms
                        if "proposal" in a.get("tags", []) and a not in experiments]
            others = [a for a in ph_atoms
                     if a not in baselines + proposals + experiments]

            lines.append(f"#### {ph}")

            if baselines:
                names = ", ".join(a["title"][:35] for a in baselines)
                lines.append(f"- **Baselines**: {names}")

            if proposals:
                lines.append(f"- **提案** ({len(proposals)}):")
                for a in proposals:
                    status = a.get("status", "?")
                    icon = "✓" if status == "validated" else ("✗" if status == "refuted" else "○")
                    meta = a.get("metadata", {})
                    complete = " ✅completed" if meta.get("iter_complete") else ""
                    rolled = " ⚠rolled_back" if meta.get("iter_rollback") else ""
                    lines.append(f"  - {icon} [{status}]{complete}{rolled} {a['title'][:80]}")

            if experiments:
                lines.append(f"- **实验结果** ({len(experiments)}):")
                for a in experiments:
                    try:
                        content = json.loads(a.get("content", "{}"))
                        score = content.get("score_mean", "?")
                        success = content.get("success", True)
                        icon = "✓" if success else "✗"
                    except Exception:
                        score = "?"
                        icon = "?"
                    algo = a["title"].replace("Experiment: ", "")
                    lines.append(f"  - {icon} {algo}: score={score}")

            if others:
                for a in others:
                    meta = a.get("metadata", {})
                    complete = " ✅" if meta.get("iter_complete") else ""
                    rolled = " ⚠" if meta.get("iter_rollback") else ""
                    lines.append(f"- [{a.get('type', '?')}]{complete}{rolled} {a['title'][:80]}")

    return "\n".join(lines)


def _build_cc_ideation_context(state: dict, session_dir: Path, phase: str) -> str:
    """Build Claim Chain context for structure-guided ideation.

    Returns a CC subgraph summary for persona agents to anchor proposals.
    """
    cc = None
    try:
        # Import here to avoid circular deps
        from claim_chain.chain import ClaimChain
        from claim_chain.query import CCQueryInterface
        from pes_controller.elo.neighborhood import RNDEvaluator

        cc = ClaimChain(session_dir / "_index" / "cc.db")
        ps_path = session_dir / "PIPELINE_STATE.json"
        if ps_path.exists():
            import json
            ps = json.loads(ps_path.read_text(encoding="utf-8"))
            cc.set_session_context(ps.get("iteration", 0), ps.get("phase", "unknown"))

        kb_path = session_dir / "_index" / "rnd_kb.jsonl"
        rnd_eval = RNDEvaluator(kb_path=kb_path) if kb_path.exists() else None
        if rnd_eval:
            try:
                rnd_eval.load()
            except Exception:
                rnd_eval = None

        qif = CCQueryInterface(cc, rnd_evaluator=rnd_eval)

        # Get related atoms for the research topic
        topic = state.get("research_topic", "")
        related = qif.query_related(topic, top_k=10)

        # Get graph gaps
        gaps = qif.query_gaps()

        # Phase-specific CC guidance level
        guidance_levels = {
            "W2 问题分析": "low",
            "W3 方案方向": "medium",
            "W4 具体方案生成": "highest",
        }
        level = guidance_levels.get(phase, "medium")

        lines = []
        lines.append(f"CC 引导级别: {level}")
        lines.append(f"CC 图谱规模: {gaps.get('total_atoms', 0)} atoms, {gaps.get('total_relations', 0)} relations")
        lines.append(f"孤立 atoms (无关联): {gaps.get('orphan_count', 0)}")

        if related.get("related_atoms"):
            lines.append("\n### 与研究方向最相关的 CC Atoms (BGE-M3 检索)")
            for i, a in enumerate(related["related_atoms"][:8]):
                lines.append(
                    f"{i+1}. [{a['type']}] {a['title'][:80]} "
                    f"(tags: {', '.join(a.get('tags', [])[:3])})"
                )

        if level in ("high", "highest"):
            lines.append("\n### 提案锚定要求")
            lines.append("你的 method_sketch 必须明确标注:")
            lines.append("- CC 锚点: 提案基于哪些已有 CC atom(s)?")
            lines.append("- 新增 atoms: 提案引入了哪些新概念/方法/组件?")
            lines.append("- 关系变更: 新增了哪些 relations (implements/motivates/depends_on 等)?")
            lines.append("- 与已有知识的区分: 提案与最相似的已有 atom 的本质差异是什么?")

        return "\n".join(lines)

    except Exception as e:
        import logging; logging.warning(f"_build_cc_ideation_context failed: {e}")
        return ""
    finally:
        if cc is not None:
            cc.close()


def _build_experiment_feedback(state: dict, session_dir: Path) -> str:
    """Extract experiment results from state + events.jsonl for persona prompts."""
    lines = []

    # 1. From code_results
    cr = state.get("code_results", {})
    if isinstance(cr, dict) and cr:
        best = cr.get("best_proposal", "")
        ranking = cr.get("final_ranking", {})
        sig = cr.get("cdr_vs_td3_significance", cr.get("significance", {}))
        if best:
            lines.append(f"- **最佳提案**: {best}")
        if ranking and isinstance(ranking, dict):
            lines.append("- **最终排名**:")
            for algo, info in ranking.items():
                if isinstance(info, dict):
                    val = info.get('mean', info.get('score', info.get('rank', '?')))
                    # Clean key: "1_sac" -> "sac", "2_cdr_critic" -> "cdr_critic"
                    label = algo.split('_', 1)[-1] if '_' in algo else algo
                    lines.append(f"  - {label}: {val}")
        if sig and isinstance(sig, dict):
            p_val = sig.get('p_bonferroni', sig.get('p_raw', sig.get('p_value', sig.get('p', '?'))))
            lines.append(f"- **统计显著性**: p={p_val}")

    # 2. From events.jsonl
    events_path = session_dir / "_index" / "events.jsonl"
    if events_path.exists():
        algo_scores = {}
        try:
            with open(events_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    evt = json.loads(line)
                    if evt.get("event_type") == "expt_completed":
                        pl = evt.get("payload", {})
                        if isinstance(pl, dict):
                            algo_scores[pl.get("algo_id", "?")] = pl
                    elif evt.get("event_type") == "algo_status_change":
                        pl = evt.get("payload", {})
                        if isinstance(pl, dict):
                            oid = evt.get("object_id", "")
                            if oid not in algo_scores:
                                algo_scores[oid] = {}
                            algo_scores[oid]["status"] = pl.get("new_status", "")
            if algo_scores:
                lines.append("\n### 已测试算法及结果")
                lines.append("| 算法 | 分数 (mean±std) | 状态 |")
                lines.append("|------|----------------|------|")
                for name, info in sorted(algo_scores.items()):
                    if isinstance(info, dict):
                        mean = info.get("score_mean", "?")
                        std = info.get("score_std", "?")
                        status = info.get("status", "?")
                        lines.append(f"| {name} | {mean}±{std} | {status} |")
        except Exception:
            pass

    if not lines:
        return ""

    lines.insert(0, "### 关键发现")
    return "\n".join(lines)


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
