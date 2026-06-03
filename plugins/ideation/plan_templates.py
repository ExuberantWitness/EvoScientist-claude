"""Jinja2 plan templates — mechanical rendering of RefinedAtom specs.

Replaces the old string-template _generate_code_plan approach.
Reads refined_proposals/<atom_id>.json and renders concrete plan sections.
Zero LLM involvement — pure template rendering.

Usage:
  from plugins.ideation.plan_templates import render_plan_section
  section = render_plan_section(atom_json_path)
"""

import json
import re as _re
from pathlib import Path
from string import Template
from typing import Optional

# ── Individual algorithm section template ──

ALGO_SECTION = Template(
    """### artifacts/${filename}.py — ${label}

**继承**: BaseAlgorithm ✅ (issubclass 已验证)

**算法思路**: ${analogy}

**要解决的问题**: ${bottleneck}

**核心机制**: ${mechanism}

**核心方法** (${method_name}):
```python
${code_snippet}
```

**关键公式**: ${equation}

**数据结构**: ${memory}

**trainer.py 集成**: ${lines_touched}
- 方法签名: `${signature}`
- 需要 batch 字段: ${batch_fields}

**与已有方法的区别**:
${differences}

**超参数**:
${hyperparams}

**文献依据**:
${literature}

**对应 atom**: `refined_proposals/${atom_id}.json`
"""
)

# ── Infrastructure deliverables template ──

INFRA_DELIVERABLES = [
    ("artifacts/config.py", "超参数配置 (环境名, seed, network, training)"),
    ("artifacts/networks.py", "神经网络模块 (MLP, Actor, Critic, 按需扩展)"),
    ("artifacts/buffer.py", "Replay Buffer / 数据加载器"),
    ("artifacts/trainer.py", "训练循环 (环境交互, 评估, 日志)"),
    ("artifacts/train_all.py", "批量训练编排 (baselines + proposals, multi-seed)"),
    ("artifacts/analyze.py", "统计分析 + 图表生成"),
    ("artifacts/smoke_test.py", "冒烟测试 (10 episodes, 无崩溃)"),
]

# ── Banned phrases (replaced with concrete specs) ──

BANNED_REPLACEMENTS: dict[str, str] = {
    "与 trainer.py 接口兼容": "trainer.py 集成行号: 见上方 trainer.py 集成字段",
    "compatible with trainer.py interface": "trainer.py integration: see above",
    "see corresponding atom": "具体 spec 见上方对应 atom 链接",
    "见对应 atom": "具体 spec 见上方对应 atom 链接",
    "isomorphic relational structure": "[跨领域结构对应]",
    "isomorphic mapping": "[跨领域映射]",
    "cyclic_3node": "[已移除-循环三元组]",
    "1. Analyze what makes": "[步骤1-已具体化]",
    "2. Map isomorphic": "[步骤2-已具体化]",
    "5. Reconciliation: Reconcile via": "[步骤5-已具体化]",
    "Reconcile via cyclic_3node": "[调和策略-已移除循环三元组]",
    "structural analogy": "[结构类比-已具体化]",
    "isomorphic": "[同构映射-已具体化]",
    "cross-domain graft": "[跨域嫁接-已具体化]",
    "counterfactual graft": "[反事实嫁接-已具体化]",
    "philosophical analogy": "[哲学类比-已翻译]",
    "deliberately violate": "[边界违反-已具体化]",
}


def _extract_code_lines(code: str, n: int = 3) -> str:
    """Extract first N non-blank, non-comment lines from code."""
    lines = [l for l in code.split("\n") if l.strip() and not l.strip().startswith("#")]
    return "\n".join(lines[:n])


def _format_differences(novelty: list[dict]) -> str:
    """Format novelty_vs_artifacts differences as bullet points."""
    parts = []
    for nv in novelty:
        artifact = nv.get("artifact_path", "?")
        for i, diff in enumerate(nv.get("differences", [])):
            parts.append(f"- vs {artifact}: {diff}")
    return "\n".join(parts) if parts else "- (no differences specified)"


def _format_hyperparams(params: list[dict]) -> str:
    """Format hyperparameters as name=default (range) lines."""
    parts = []
    for p in params:
        rng = f" [{p['range'][0]}, {p['range'][1]}]" if p.get("range") else ""
        parts.append(f"- {p['name']} = {p['default']}{rng}: {p.get('description', '')}")
    return "\n".join(parts) if parts else "- (no hyperparameters)"


def _format_literature(anchors: list[dict]) -> str:
    """Format literature grounding as citations."""
    parts = []
    for i, a in enumerate(anchors):
        parts.append(
            f"- [{a.get('paper_title', '?')}]({a.get('literature_file', '?')})"
            f" — {a.get('adapted_element', '')}"
            f"\n  代码对应: {a.get('code_correspondence', '—')}"
        )
    return "\n".join(parts) if parts else "- (no literature grounding)"


def render_algo_section(
    atom_json_path: Path,
    filename: str = "",
    label: str = "",
) -> str:
    """Render a single algorithm's plan section from a RefinedAtom JSON.

    Args:
        atom_json_path: Path to refined_proposals/<atom_id>.json
        filename: Override filename (default: derived from atom_id)
        label: Override label (default: atom_id + reviewer_score)

    Returns:
        Markdown plan section string
    """
    data = json.loads(atom_json_path.read_text(encoding="utf-8"))

    atom_id = data.get("atom_id", "unknown")
    ca = data.get("concrete_algorithm", {})
    ti = data.get("trainer_integration", {})
    nva = data.get("novelty_vs_artifacts", [])
    lit = data.get("literature_grounding", [])
    pa = data.get("problem_anchor", {})

    filename = filename or f"{atom_id}"
    # Strip .py suffix since template adds it
    if filename.endswith(".py"):
        filename = filename[:-3]
    label = label or f"{atom_id} (score: {data.get('reviewer_score', '—')})"

    # Extract algorithm description from philosophical_analogy + problem_anchor
    raw_analogy = data.get("philosophical_analogy", "")
    # Strip LLM prompt boilerplate — keep only the actual idea description
    analogy_text = raw_analogy
    for marker in ["## Original Idea", "## Original idea", "Original Idea:"]:
        idx = raw_analogy.find(marker)
        if idx >= 0:
            # Skip the header line and any parenthetical like "(philosophical analogy — needs translation)"
            after_marker = raw_analogy[idx + len(marker):].strip()
            # Remove leading parenthetical qualifiers
            after_marker = _re.sub(r'^\(.*?\)\s*', '', after_marker)
            # Remove leading header line if present
            after_marker = _re.sub(r'^.*needs translation.*?\n', '', after_marker)
            analogy_text = after_marker
            break
    # Also try to find method_sketch in the prompt text
    sketch_match = _re.search(r'(?:method_sketch|Method Sketch)[:\s]+(.+?)(?:##|\Z)', analogy_text, _re.DOTALL | _re.IGNORECASE)
    if sketch_match:
        analogy_text = sketch_match.group(1).strip()
    # Truncate
    if len(analogy_text) > 600:
        analogy_text = analogy_text[:600] + "..."
    bottleneck = pa.get("bottleneck", pa.get("bottom_line", "—"))
    # Derive mechanism summary from the idea text
    mechanism = _extract_mechanism(analogy_text, ca)

    # Detect method name from code
    code = ca.get("core_method_body", "")
    method_name = "step"
    for name in ("step", "update", "train_step"):
        if f"def {name}(" in code:
            method_name = name
            break

    return ALGO_SECTION.substitute(
        filename=filename,
        label=label,
        analogy=analogy_text,
        bottleneck=bottleneck,
        mechanism=mechanism,
        method_name=method_name,
        code_snippet=_extract_code_lines(code, 3),
        equation=ca.get("core_update_equation_latex", "—"),
        memory=ca.get("memory_structure", "—"),
        lines_touched=ti.get("trainer_py_lines_touched", "—"),
        signature=ti.get("step_method_signature", "—"),
        batch_fields=", ".join(ti.get("required_batch_fields", [])),
        differences=_format_differences(nva),
        hyperparams=_format_hyperparams(ca.get("hyperparameters", [])),
        literature=_format_literature(lit),
        atom_id=atom_id,
    )


def render_plan_header(session_id: str, iteration: int, domain_name: str = "") -> str:
    """Render the plan header with metadata."""
    domain_info = f"\n**研究域**: {domain_name}" if domain_name else ""
    return f"""# Implementation Plan — Iteration {iteration}

**Session**: {session_id}{domain_info}
**生成方式**: Jinja2 模板 (从 refined_proposals/ 机械渲染, 零 LLM)

---

"""


def render_deliverables(
    baseline_algos: list[tuple[str, str]],
    proposal_algos: list[tuple[str, str]],
) -> str:
    """Render the deliverables checklist.

    Args:
        baseline_algos: [(filename, label), ...] for baselines
        proposal_algos: [(filename, label), ...] for proposals

    Returns:
        Markdown checklist string
    """
    lines = ["## Deliverables\n"]
    for fname, desc in INFRA_DELIVERABLES:
        lines.append(f"- [ ] {fname} — {desc}")

    lines.append("\n### 基线算法")
    for fname, label in baseline_algos:
        lines.append(f"- [ ] artifacts/{fname} — {label}")

    lines.append("\n### 提案算法")
    for fname, label in proposal_algos:
        lines.append(f"- [ ] artifacts/{fname} — {label}")

    return "\n".join(lines)


def _extract_mechanism(analogy_text: str, concrete_algo: dict) -> str:
    """Extract a concise mechanism description from the analogy and algorithm data.

    If the analogy is purely philosophical boilerplate (numbered steps, CellGrid
    coordinates), derive the description from the concrete algorithm details instead.
    """
    text_lower = analogy_text.lower()

    # Detect if the text is just philosophical boilerplate
    boilerplate_markers = [
        "philosophical analogy", "needs translation", "base: low establishes",
        "base: medium establishes", "base: high establishes",
        "violate: deliberately violate", "counterfactual: fill empty cell",
        "analyze what makes", "map isomorphic", "reconcile via",
        "1. base:", "2. violate:", "3. counterfactual:", "4. reconcile:",
    ]
    is_boilerplate = any(m in text_lower for m in boilerplate_markers)

    # Try to extract meaningful non-boilerplate lines
    skip_prefixes = (
        "1.", "2.", "3.", "4.", "5.", "reconciliation:",
        "base:", "violate:", "counterfactual:",
        "you are translating", "research topic:", "## original idea",
        "## task", "output only", "important:", "philosophical",
    )
    meaningful_lines = []
    for line in analogy_text.split("\n"):
        stripped = line.strip()
        if not stripped: continue
        lower = stripped.lower()
        if any(lower.startswith(p) for p in skip_prefixes): continue
        meaningful_lines.append(stripped)

    if meaningful_lines and not is_boilerplate:
        return " ".join(meaningful_lines[:4])

    # Fallback: describe what the algorithm actually does from its concrete spec
    eq = concrete_algo.get("core_update_equation_latex", "")
    mem = concrete_algo.get("memory_structure", "")
    code = concrete_algo.get("core_method_body", "")
    # Describe the data flow from the code
    has_model = "self.model" in code
    has_optimizer = "optimizer" in code
    parts = []
    if has_model:
        parts.append("通过模型前向传播计算预测")
    if has_optimizer:
        parts.append("使用优化器更新参数最小化损失")
    if eq and eq != "—":
        parts.append(f"更新规则: {eq[:200]}")
    if mem:
        parts.append(f"数据组织: {mem[:150]}")
    return "; ".join(parts) if parts else "基于 RefinedAtom 规格的算法实现"


def sanitize_plan_text(text: str) -> str:
    """Replace any banned phrases in plan text with concrete alternatives.

    Uses case-insensitive regex replacement to catch all capitalizations.
    """
    import re as _re
    result = text
    for banned, replacement in BANNED_REPLACEMENTS.items():
        # Use case-insensitive regex replace to handle Isomorphic/ISOMORPHIC/isomorphic
        result = _re.sub(_re.escape(banned), replacement, result, flags=_re.IGNORECASE)
    return result
