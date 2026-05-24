"""SessionStore: Session 目录树管理 + Markdown 文件操作.

提供:
  - 创建 sessions/{sid}/ 完整目录树 (无中间 vault/ 层)
  - 从模板初始化 Markdown 文件
  - [[wiki-link]] 规范校验
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


class SessionStore:
    """管理 Session 目录树和 Markdown 文件的创建/读取/更新。

    所有子目录直接建在 session_dir 下，无中间 vault/ 层。
    """

    def __init__(self, session_dir: str | Path):
        self.session_dir = Path(session_dir)
        # _index/ lives directly under session_dir (no vault/ intermediate)
        self.index_dir = self.session_dir / "_index"
        self.pipeline_dir = self.session_dir / "_pipeline"

    # ── 初始化 ──

    def init_dirs(self, session_id: str, research_topic: str = "") -> dict:
        """创建完整 session 目录树。"""
        dirs = [
            "Algorithms",
            "Bottlenecks",
            "Islands",
            "Literature",
            "Iterations",
            "_index",
            "_pipeline",
            "_memory",
            "artifacts",
            "evolve_archive",
        ]
        for d in dirs:
            (self.session_dir / d).mkdir(parents=True, exist_ok=True)

        # Pipeline state
        state = {
            "session_id": session_id,
            "research_topic": research_topic,
            "session_dir": str(self.session_dir),
            "created_at": time.time(),
            "iteration": 0,
            "phase": "W2.1 Problem Analysis",
            "status": "ready",
            "config": {
                "domain": {
                    "domain_name": "general",
                    "research_topic": research_topic,
                },
                "gate": {
                    "enabled": True,
                    "min_score": 0.3,
                    "enforce_for_types": ["method"],
                    "block_on_failure": False,
                },
            },
        }

        state_path = self.session_dir / "PIPELINE_STATE.json"
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
        return state

    # ── Markdown 文件操作 ──

    def create_algorithm(self, algo_id: str, title: str, parent_id: str = "",
                         bottleneck: str = "", mechanism: str = "",
                         tags: list[str] | None = None) -> Path:
        """创建算法 Markdown 文件."""
        algo_dir = self.session_dir / "Algorithms"
        algo_dir.mkdir(parents=True, exist_ok=True)
        filepath = algo_dir / f"{algo_id}.md"

        lines = [
            "---",
            f"id: {algo_id}",
            f"parent: {parent_id}" if parent_id else "parent: null",
            "status: PROPOSED",
            f"bottleneck: {bottleneck}" if bottleneck else "",
            f"created: {datetime.now().strftime('%Y-%m-%d')}",
            f"tags: [{', '.join(tags or [])}]",
            "---",
            "",
            f"# {title}",
            "",
            "## 当前理解",
            "",
            f"### 机制: {mechanism}" if mechanism else "",
            "",
            "## 关系图",
        ]
        filepath.write_text("\n".join(line for line in lines if line), encoding="utf-8")
        return filepath

    def create_bottleneck(self, bn_id: str, category: str,
                          description: str = "") -> Path:
        """创建瓶颈 Markdown 文件."""
        bn_dir = self.session_dir / "Bottlenecks"
        bn_dir.mkdir(parents=True, exist_ok=True)
        filepath = bn_dir / f"{bn_id}.md"

        content = (
            f"---\nid: {bn_id}\ncategory: {category}\n---\n\n"
            f"# {bn_id}\n\n## 描述\n{description}\n\n## 解决方案\n"
        )
        filepath.write_text(content, encoding="utf-8")
        return filepath

    def create_island(self, island_name: str, member_algos: list[str]) -> Path:
        """创建方法家族文件."""
        island_dir = self.session_dir / "Islands"
        island_dir.mkdir(parents=True, exist_ok=True)
        filepath = island_dir / f"{island_name}.md"

        members = "\n".join(f"- [[{a}]]" for a in member_algos)
        content = f"---\nname: {island_name}\n---\n\n# {island_name}\n\n## 成员\n{members}\n"
        filepath.write_text(content, encoding="utf-8")
        return filepath

    def create_iteration(self, iteration_num: int, new_algos: list[str],
                         results: dict | None = None) -> Path:
        """创建迭代记录文件."""
        iter_dir = self.session_dir / "Iterations"
        iter_dir.mkdir(parents=True, exist_ok=True)
        filepath = iter_dir / f"Iteration_{iteration_num}.md"

        algos_str = "\n".join(f"- [[{a}]]" for a in new_algos)
        results_str = json.dumps(results, indent=2, ensure_ascii=False) if results else ""
        content = (
            f"---\niteration: {iteration_num}\n---\n\n"
            f"# Iteration {iteration_num}\n\n"
            f"## 新算法\n{algos_str}\n\n"
            f"## 结果\n{results_str}\n"
        )
        filepath.write_text(content, encoding="utf-8")
        return filepath

    # ── Wiki-link 校验 ──

    def validate_links(self, filepath: Path) -> list[str]:
        """校验文件中的 [[wiki-link]] 目标存在。返回断链列表。"""
        import re
        text = filepath.read_text(encoding="utf-8")
        links = re.findall(r"\[\[([^\]|#]+)(?:[|#][^\]]+)?\]\]", text)

        broken = []
        for target in links:
            target_clean = target.strip()
            found = False
            for subdir in ["Algorithms", "Bottlenecks", "Islands"]:
                candidate = self.session_dir / subdir / f"{target_clean}.md"
                if candidate.exists():
                    found = True
                    break
            if not found:
                broken.append(target_clean)
        return broken

    def validate_all_links(self) -> dict[str, list[str]]:
        """扫描所有 Markdown 的断链。返回 {filepath: [broken_links]}."""
        broken_map = {}
        for md_file in self.session_dir.rglob("*.md"):
            broken = self.validate_links(md_file)
            if broken:
                broken_map[str(md_file.relative_to(self.session_dir))] = broken
        return broken_map


# ── Factory ──

def create_session_store(base_dir: str | Path,
                         research_topic: str = "") -> "SessionStore":
    """创建新 session 的 SessionStore 并初始化目录。"""
    import uuid
    base = Path(base_dir)
    session_id = f"sess_{uuid.uuid4().hex[:8]}"
    session_dir = base / "sessions" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    store = SessionStore(session_dir)
    store.init_dirs(session_id, research_topic)
    return store


# Backward-compat alias
VaultManager = SessionStore
