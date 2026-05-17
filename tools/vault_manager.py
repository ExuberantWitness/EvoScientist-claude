"""VaultManager: Obsidian vault 目录树管理 + Markdown 文件操作.

Phase A 核心模块. 提供:
  - 创建 sessions/{sid}/vault/ 完整目录树
  - 从模板初始化 Markdown 文件
  - [[wiki-link]] 规范校验
  - Obsidian .obsidian 配置生成
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

# 14类瓶颈分类 (Intern-Atlas 适配 RL)
BOTTLENECK_CATEGORIES = {
    "overestimation_bias", "training_instability", "sample_inefficiency",
    "exploration_insufficient", "convergence_slow", "hyperparameter_sensitivity",
    "generalization_gap", "computational_cost", "reward_sparsity",
    "multi_objective_conflict", "distributional_shift", "gradient_interference",
    "representation_collapse", "credit_assignment_long",
}

# 13 种合法边类型
VALID_EDGE_TYPES = {
    "extends", "improves", "replaces", "adapts",
    "uses_component", "compares", "compares_to", "background",
    "validates", "contradicts", "implements", "specializes", "derives",
    "causes", "boundary_of", "motivates",
    "creates", "affects", "addressed_by", "related_to",
    "replaced_by", "member_of",
}


class VaultManager:
    """管理 Obsidian vault 目录树和 Markdown 文件的创建/读取/更新."""

    def __init__(self, session_dir: str | Path):
        self.session_dir = Path(session_dir)
        self.vault_dir = self.session_dir / "vault"
        self.index_dir = self.vault_dir / "_index"
        self.pipeline_dir = self.vault_dir / "_pipeline"

    # ── 初始化 ──

    def init_vault(self, session_id: str, research_topic: str = "") -> dict:
        """创建完整 vault 目录树 + .obsidian 配置."""
        dirs = [
            "Algorithms", "Bottlenecks", "Islands",
            "Literature", "Iterations",
            "_index", "_pipeline", "_memory", "artifacts",
        ]
        for d in dirs:
            (self.vault_dir / d).mkdir(parents=True, exist_ok=True)

        # .obsidian 配置
        obsidian_config = self.vault_dir / ".obsidian"
        obsidian_config.mkdir(parents=True, exist_ok=True)
        (obsidian_config / "app.json").write_text(json.dumps({
            "showLineNumber": False, "defaultViewMode": "source",
            "livePreview": True, "showUnsupportedFiles": True,
        }, indent=2))

        # Graph view 配置 (显示所有节点, depth=3)
        (obsidian_config / "graph.json").write_text(json.dumps({
            "search": "", "showOrphans": True, "showTags": True,
            "collapse-filter": False, "depth": 3, "linkStrength": 1.0,
        }, indent=2))

        # Pipeline state
        state = {
            "session_id": session_id,
            "research_topic": research_topic,
            "vault_dir": str(self.vault_dir),
            "created_at": time.time(),
            "iteration": 0,
            "phase": "W2 Plan",
        }
        (self.pipeline_dir / "PIPELINE_STATE.json").write_text(
            json.dumps(state, indent=2, ensure_ascii=False))

        return {
            "vault_dir": str(self.vault_dir),
            "directories": [str(self.vault_dir / d) for d in dirs],
            "state": state,
        }

    # ── Algorithm SPEC.md ──

    def create_algorithm(self, algo_id: str, name: str, *,
                         parent_id: str = "", bottleneck: str = "",
                         tags: list[str] | None = None,
                         mechanism: str = "", tradeoff: str = "") -> Path:
        """创建 Algorithm SPEC.md 文件."""
        algo_dir = self.vault_dir / "Algorithms"
        algo_dir.mkdir(parents=True, exist_ok=True)
        filepath = algo_dir / f"{algo_id}.md"

        template = (TEMPLATES_DIR / "SPEC_TEMPLATE.md").read_text(encoding="utf-8")
        content = template.format(
            algo_id=algo_id,
            parent_id=parent_id or "none",
            display_name=name,
            created_date=datetime.now().strftime("%Y-%m-%d"),
            target_bottleneck=f"[[{bottleneck}]]" if bottleneck else "(待确定)",
            mechanism=mechanism or "(待确定)",
            tradeoff=tradeoff or "(待确定)",
            evidence="(尚无实验证据)",
            relations=f"- extends ← [[{parent_id}]]" if parent_id else "- (尚无关系)",
            experiment_history=f"### {datetime.now().strftime('%Y-%m-%d')}: 创建\n- 状态: PROPOSED\n",
        )
        filepath.write_text(content, encoding="utf-8")
        return filepath

    # ── Bottleneck ──

    def create_bottleneck(self, bottleneck_id: str, title: str, *,
                          category: str = "training_instability",
                          discovered_in: str = "", evidence: str = "",
                          affected_methods: list[str] | None = None) -> Path:
        """创建 Bottleneck Markdown 文件."""
        if category not in BOTTLENECK_CATEGORIES:
            raise ValueError(f"Invalid bottleneck category: {category}. "
                           f"Must be one of {sorted(BOTTLENECK_CATEGORIES)}")

        bottleneck_dir = self.vault_dir / "Bottlenecks"
        bottleneck_dir.mkdir(parents=True, exist_ok=True)
        filepath = bottleneck_dir / f"{bottleneck_id}.md"

        template = (TEMPLATES_DIR / "BOTTLENECK_TEMPLATE.md").read_text(encoding="utf-8")
        affected = ", ".join(affected_methods or [])
        content = template.format(
            bottleneck_id=bottleneck_id,
            category=category,
            display_name=title,
            discovered_in=discovered_in or "(unknown)",
            description="(待补充)",
            evidence=evidence or "(尚无证据)",
            relations=(f"- affects → [[{'; ]], [['.join(affected_methods)}]]"
                       if affected_methods else "- (尚无关系)"),
        )
        filepath.write_text(content, encoding="utf-8")
        return filepath

    # ── Island ──

    def create_island(self, island_id: str, name: str, *,
                      method_family: str = "default",
                      member_algos: list[str] | None = None,
                      claim_atom_id: str = "none") -> Path:
        """创建 Island STATE.md 文件."""
        island_dir = self.vault_dir / "Islands"
        island_dir.mkdir(parents=True, exist_ok=True)
        filepath = island_dir / f"{island_id}.md"

        template = (TEMPLATES_DIR / "ISLAND_STATE_TEMPLATE.md").read_text(encoding="utf-8")
        members = "\n".join(f"| {a} | - | - | - |" for a in (member_algos or []))
        relations = "\n".join(f"- member_of ← [[{a}]]" for a in (member_algos or []))
        content = template.format(
            island_id=island_id, method_family=method_family,
            display_name=name, claim_atom_id=claim_atom_id,
            created_date=datetime.now().strftime("%Y-%m-%d"),
            relations=relations or "- (尚无关系)",
        ).replace("| algo_id | status | best_score | bottleneck |\n|---|---|---|---|\n| - | - | - | - |",
                  f"| algo_id | status | best_score | bottleneck |\n|---|---|---|---|\n{members}")
        filepath.write_text(content, encoding="utf-8")
        return filepath

    # ── Iteration ──

    def create_iteration(self, n: int, session_id: str, *,
                         research_topic: str = "",
                         parent_iter_id: str = "",
                         new_algos: list[str] | None = None,
                         experiments: list[str] | None = None,
                         promoted: str = "", refuted: str = "",
                         new_claims: str = "", dead_ends: str = "",
                         open_problems: str = "",
                         discussion: str = "") -> Path:
        """创建 Iteration Markdown 文件."""
        iter_dir = self.vault_dir / "Iterations"
        iter_dir.mkdir(parents=True, exist_ok=True)
        iter_id = f"iter_{session_id}_{n}"
        filepath = iter_dir / f"Iteration_{n}.md"

        template = (TEMPLATES_DIR / "ITERATION_TEMPLATE.md").read_text(encoding="utf-8")
        content = template.format(
            iter_id=iter_id, n=n, session_id=session_id,
            parent_iter_id=parent_iter_id or "none",
            research_topic=research_topic,
            created_date=datetime.now().strftime("%Y-%m-%d"),
            new_algos="\n".join(f"- [[{a}]]" for a in (new_algos or [])) or "- (none)",
            experiments="\n".join(f"- {e}" for e in (experiments or [])) or "- (none)",
            promoted=promoted or "- (none)", refuted=refuted or "- (none)",
            new_claims=new_claims or "- (none)", dead_ends=dead_ends or "- (none)",
            open_problems=open_problems or "- (none)",
            discussion=discussion or "(待讨论)",
            relations="",
        )
        filepath.write_text(content, encoding="utf-8")
        return filepath

    # ── [[wiki-link]] 规范校验 ──

    def validate_links(self, filepath: Path) -> list[str]:
        """校验文件中所有 [[wiki-link]] 的目标是否存在. 返回 unresolved 列表."""
        import re
        text = filepath.read_text(encoding="utf-8")
        links = re.findall(r'\[\[([^\]]+)\]\]', text)
        unresolved = []
        for link in links:
            # Clean the link target (remove leading annotations like "CC Atom 5: ")
            clean = link.split(":")[-1].strip() if ":" in link else link.strip()
            # Try with underscores and spaces
            candidates = [
                self.vault_dir / "Algorithms" / f"{clean.replace(' ', '_')}.md",
                self.vault_dir / "Bottlenecks" / f"{clean.replace(' ', '_')}.md",
                self.vault_dir / "Islands" / f"{clean.replace(' ', '_')}.md",
                self.vault_dir / "Algorithms" / f"{clean}.md",
                self.vault_dir / "Bottlenecks" / f"{clean}.md",
            ]
            if not any(c.exists() for c in candidates):
                unresolved.append(link)
        return unresolved

    def validate_all_links(self) -> dict[str, list[str]]:
        """扫描整个 vault, 返回所有打破的链接."""
        all_unresolved = {}
        for md_file in self.vault_dir.rglob("*.md"):
            if md_file.parent.name.startswith("_") or md_file.parent.name.startswith("."):
                continue
            unresolved = self.validate_links(md_file)
            if unresolved:
                rel = str(md_file.relative_to(self.vault_dir))
                all_unresolved[rel] = unresolved
        return all_unresolved


# ── 便捷工厂函数 ──

def create_session_vault(workspace_root: str, session_id: str,
                         research_topic: str = "") -> VaultManager:
    """在 EvoScientist-claude/sessions/{sid}/ 下创建完整 vault."""
    base = Path(workspace_root) / "EvoScientist-claude" / "sessions" / session_id
    mgr = VaultManager(base)
    mgr.init_vault(session_id, research_topic)
    return mgr
