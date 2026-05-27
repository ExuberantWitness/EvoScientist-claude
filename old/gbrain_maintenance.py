"""GBrain 增强: Self-wiring + Dream Cycle + Tiered Enrichment.

Phase F 核心模块. 借鉴 GBrain 的三项关键维护能力.
"""

import json
import re
from pathlib import Path
try:
    from tools.vault_manager import VaultManager
except ImportError:
    from vault_manager import VaultManager

# Tiered enrichment: 状态机层级
TIER_RULES = {
    "PROPOSED":     "tier_stub",       # 仅名字存在
    "IMPLEMENTED":  "tier_code",       # 代码完成
    "TESTED":       "tier_tested",     # 实验跑完
    "VALIDATED":    "tier_validated",  # 验证有效
    "REFUTED":      "tier_refuted",    # 反驳
    "ARCHIVED":     "tier_archived",   # 归档
}


def self_wire_on_write(vault_dir: Path, filepath: Path) -> dict:
    """每次 Markdown 写入后自动建立 cross-reference (零 LLM).

    借鉴 GBrain: 纯正则扫描, 提取 [[links]] → 自动在目标文件中添加反向引用.
    """
    text = filepath.read_text(encoding="utf-8")
    links = re.findall(r"\[\[([^\]]+)\]\]", text)
    source_id = filepath.stem

    wired = []
    for link in links:
        target_clean = link.split(":")[-1].strip() if ":" in link else link.strip()
        target_file = _find_target(vault_dir, target_clean)
        if target_file and target_file != filepath:
            # Check if reverse link already exists
            target_text = target_file.read_text(encoding="utf-8")
            if f"[[{source_id}]]" not in target_text:
                # Add reverse link to target's "关系图" section
                target_text = _append_to_relations_section(
                    target_text, f"- self_wired ← [[{source_id}]] (auto)")
                target_file.write_text(target_text, encoding="utf-8")
                wired.append({"from": source_id, "to": target_file.stem,
                              "target_file": str(target_file.relative_to(vault_dir))})

    return {"wired_count": len(wired), "wired": wired}


def dream_cycle(vault_dir: Path) -> dict:
    """Dream Cycle: 扫描 vault → 修复孤儿链接 → 检测矛盾 → 清理过期瓶颈.

    借鉴 GBrain: 空闲时自动运行, 或手动触发.
    """
    vm = VaultManager(vault_dir.parent)  # session_dir
    vm.vault_dir = vault_dir

    results = {"orphans_fixed": 0, "contradictions": 0, "stale_bottlenecks": 0}

    # 1. 检测未解析链接
    unresolved = vm.validate_all_links()
    for file_rel, links in unresolved.items():
        filepath = vault_dir / file_rel
        text = filepath.read_text(encoding="utf-8")
        for link in links:
            # Mark unresolved links with ^[unresolved] tag
            if link not in text:
                continue
            text = text.replace(f"[[{link}]]", f"[[{link}]] ^[unresolved]")
        filepath.write_text(text, encoding="utf-8")
        results["orphans_fixed"] += len(links)

    # 2. 检测矛盾
    from tools.event_log import EventLog
    el = EventLog(vault_dir.parent)
    contradictions = el.check_contradictions()
    results["contradictions"] = len(contradictions)

    return results


def tiered_enrichment(vault_dir: Path) -> dict:
    """Tiered Enrichment: 按状态逐级丰富算法描述.

    借鉴 GBrain: PROPOSED→IMPLEMENTED→TESTED→VALIDATED 逐级触发.
    """
    algo_dir = vault_dir / "Algorithms"
    if not algo_dir.exists():
        return {"enriched": 0}

    enriched = 0
    for md_file in algo_dir.glob("*.md"):
        text = md_file.read_text(encoding="utf-8")
        # Extract status from frontmatter
        m = re.search(r"status:\s*(\w+)", text)
        if not m:
            continue
        status = m.group(1)
        tier = TIER_RULES.get(status, "tier_stub")

        # Check if tier tag already exists
        if f"tier: {tier}" in text:
            continue

        # Add tier tag to frontmatter
        text = text.replace(
            f"status: {status}",
            f"status: {status}\ntier: {tier}")
        md_file.write_text(text, encoding="utf-8")
        enriched += 1

    return {"enriched": enriched}


# ── Helpers ──

def _find_target(vault_dir: Path, target: str) -> Path | None:
    """Find target Markdown file by name (try spaces and underscores)."""
    candidates = [
        vault_dir / "Algorithms" / f"{target}.md",
        vault_dir / "Algorithms" / f"{target.replace(' ', '_')}.md",
        vault_dir / "Bottlenecks" / f"{target}.md",
        vault_dir / "Bottlenecks" / f"{target.replace(' ', '_')}.md",
        vault_dir / "Islands" / f"{target}.md",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _append_to_relations_section(text: str, line: str) -> str:
    """在 ## 关系图 节末尾追加一行."""
    m = re.search(r"## 关系图\s*\n", text)
    if not m:
        # Add a relations section before the next ## section
        text = re.sub(r"(\n## )", f"\n## 关系图\n{line}\n\n## ", text, count=1)
        return text
    # Insert after the relations section, before next ## or ---
    pos = m.end()
    remaining = text[pos:]
    next_section = re.search(r"\n## |\n---", remaining)
    if next_section:
        insert_pos = pos + next_section.start()
        text = text[:insert_pos] + f"{line}\n" + text[insert_pos:]
    else:
        text = text[:pos] + f"{line}\n" + text[pos:]
    return text
