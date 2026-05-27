"""Phase A: 清理 workspace 根目录散落文件，移入 sessions/sess_15b7792b/legacy/。

用法:
    python cleanup_polluted_files.py [--dry-run] [--workspace /path/to/workspace]
"""

import argparse
import shutil
import sys
from pathlib import Path

# 白名单: workspace 根目录保留的文件和目录 (不被移动)
KEEP_ROOT = {
    "EvoScientist-claude",   # 项目本身
    "sessions",              # 新 session 目录
    ".git", ".gitignore",
    ".evo_sessions", ".evo_session_registry.json",
    "PIPELINE_STATE.json",   # Dashboard API 兼容需要
    "claim_chain", "evolve_archive", "memory", "artifacts",  # bootstrap 创建的
}

# 模式: 匹配需要移动的散落文件
SCATTERED_MD = [
    "analysis_report.md", "architecture.md", "architecture_v2.md",
    "command_log.md", "data-analysis.md",
    "discussion_hopper_actor_critic.md", "discussion_hopper_w2.md",
    "discussion_hopper_w2_plan.md", "discussion_hopper_w3_5.md",
    "discussion_hopper_w35.md",
    "EvoScientist_Architecture_Decision_Record.md",
    "experiment_plan.md", "experiment-plan-pendulum-rl.md",
    "EXPERIMENT_REPORT.md", "final_discussion.md", "FINAL_PAPER.md",
    "idea_candidates.md", "IDEA_CANDIDATES.md", "IDEA_CANDIDATES_MORPH.md",
    "IDEA.md", "idea_report.md", "implementation_plan.md",
    "LIT_SURVEY_CREATIVITY.md", "LIT_SURVEY.md", "LIT_SURVEY_MORPH.md",
    "MinerU_markdown_ATEC2026*.md", "NOVELTY_REPORT.md",
    "report.md", "RESEARCH_BRIEF.md",
    "research_memo_actor_critic_improvements.md",
    "research_notes.md", "RESEARCH_PIPELINE_REPORT.md",
    "research_proposal.md", "research_report_barrier_bsrs_hopper.md",
    "research_report_ceiling_analysis.md", "research_request.md",
    "W6_FINAL_PAPER.md",
]


def main():
    parser = argparse.ArgumentParser(description="清理 workspace 根目录散落文件")
    parser.add_argument("--dry-run", action="store_true", help="只列出将移动的文件，不实际移动")
    parser.add_argument("--workspace", default="/home/exuber/CODE/CORE/pythonProject1/AUTORESEARCH")
    args = parser.parse_args()

    ws = Path(args.workspace)
    legacy_dir = ws / "sessions" / "sess_15b7792b" / "legacy"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    moved = 0
    skipped = 0

    for item in sorted(ws.iterdir()):
        name = item.name
        if name in KEEP_ROOT:
            continue
        if name.startswith("."):
            continue  # 保留所有隐藏文件

        # 移动 .md, .py, .json (散落文件), 和旧实验目录
        if (item.is_file() and (name.endswith(".md") or name.endswith(".py") or
                                 name.endswith(".json") or name.endswith(".sh")) or
            item.is_dir() and name not in KEEP_ROOT and not name.startswith(".") and
            name not in {"sessions", "EvoScientist-claude"}):

            dest = legacy_dir / name
            if args.dry_run:
                print(f"[DRY RUN] 将移动: {item} → {dest}")
            else:
                try:
                    shutil.move(str(item), str(dest))
                    print(f"已移动: {item} → {dest}")
                    moved += 1
                except Exception as e:
                    print(f"移动失败 {item}: {e}")
                    skipped += 1

    print(f"\n总结: 移动 {moved} 个文件, 跳过 {skipped} 个")
    if args.dry_run:
        print("(dry-run 模式，未实际移动)")


if __name__ == "__main__":
    main()
