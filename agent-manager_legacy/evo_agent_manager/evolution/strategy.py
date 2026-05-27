"""Evolvable strategy file management with archiving and rollback.

Strategy files are markdown containing key-value parameters and descriptions.
The system reads them at runtime to configure IDE/IVE/ESE behavior, and
meta-evolution can modify them with automatic archiving and rollback.
"""

import json
import logging
import re
import time
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_DISTILLATION_STRATEGY = """\
# Distillation Strategy

Controls how IDE/IVE/ESE extract insights from interactions.

## IDE (Idea Direction Evolution)
ide_promising_method: median
ide_fail_threshold_ratio: 0.5
ide_bottom_third_ratio: 0.33

## IVE (Idea Validation Evolution)
ive_priority_level: HIGH
ive_auto_trigger_on_score_below: 0.3

## ESE (Experiment Strategy Evolution)
ese_success_threshold: 0.6
ese_applicability_tagging: auto

## Merge & Dedup
dedup_overlap_threshold: 0.8
merge_keep_higher_score: true

## General
baseline_score: 0.3
"""

DEFAULT_MEMORY_RETRIEVAL_STRATEGY = """\
# Memory Retrieval Strategy

Controls how inject_priors() allocates budget and prioritizes memory types.

## Budget Allocation (percentages, must sum to ~100)
failed_pct: 40
success_pct: 40
promising_pct: 20

## Entry Limits
failed_read_limit: 30
success_read_limit: 20
promising_read_limit: 10

## Relevance Scoring
applicability_boost: 0.2
min_budget_threshold: 80

## Per-Role Priority (comma-separated order)
role_planner: PROMISING,FAILED,SUCCESS
role_researcher: SUCCESS,FAILED,PROMISING
role_code: SUCCESS,FAILED
role_debug: FAILED,SUCCESS
role_analyst: SUCCESS,PROMISING
role_writer: PROMISING,SUCCESS

## General
inject_priors_max_chars: 2000
"""

DEFAULT_SELF_MODIFICATION_STRATEGY = """\
# Self-Modification Strategy

Controls when and how the system modifies its own strategy files.

## Trigger Conditions
stagnation_k: 5
stagnation_threshold: 0.01
peer_improvement_threshold: 0.1

## Safety
observation_window: 3
regression_threshold: 0.05
auto_rollback: true
cooldown_seconds: 300

## Scope
modifiable_files: distillation_strategy.md, memory_retrieval.md
frozen_files: scoring.py, elo.py, pipeline.py
"""


class StrategyManager:
    """Manages evolvable markdown strategy files with archiving and rollback."""

    SKILL_FILES = {
        "distillation_strategy.md": DEFAULT_DISTILLATION_STRATEGY,
        "memory_retrieval.md": DEFAULT_MEMORY_RETRIEVAL_STRATEGY,
        "self_modification.md": DEFAULT_SELF_MODIFICATION_STRATEGY,
    }

    def __init__(self, workspace_dir: str | Path):
        self.base_dir = Path(workspace_dir) / "memory" / "skills"
        self.archive_dir = Path(workspace_dir) / "memory" / "evolution" / "archive"
        self.patches_dir = Path(workspace_dir) / "memory" / "evolution" / "patches"
        self._version_counter = 0

        # Count existing patches to initialize version counter
        if self.patches_dir.exists():
            existing = list(self.patches_dir.glob("strategy_v*.json"))
            if existing:
                versions = []
                for p in existing:
                    m = re.search(r"v(\d+)", p.name)
                    if m:
                        versions.append(int(m.group(1)))
                if versions:
                    self._version_counter = max(versions)

    def ensure_defaults(self) -> None:
        """Create default strategy files if they don't exist."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in self.SKILL_FILES.items():
            path = self.base_dir / filename
            if not path.exists():
                path.write_text(content, encoding="utf-8")
                logger.info(f"[Strategy] Created default: {filename}")

    def load_strategy(self, filename: str = "distillation_strategy.md") -> str:
        """Read a strategy file, creating defaults if needed."""
        self.ensure_defaults()
        path = self.base_dir / filename
        if not path.exists():
            # Fallback to default content
            return self.SKILL_FILES.get(filename, "")
        return path.read_text(encoding="utf-8")

    def apply_patch(
        self,
        patch: str,
        rationale: str = "",
        target_file: str = "distillation_strategy.md",
    ) -> Path:
        """Apply a strategy modification: archive current, write new, record metadata."""
        self.ensure_defaults()
        target_path = self.base_dir / target_file
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.patches_dir.mkdir(parents=True, exist_ok=True)

        # Archive current version
        self._version_counter += 1
        version = self._version_counter
        stem = target_file.replace(".md", "")
        archive_path = self.archive_dir / f"{stem}_v{version}.md"

        if target_path.exists():
            archive_path.write_text(
                target_path.read_text(encoding="utf-8"), encoding="utf-8"
            )
        else:
            archive_path.write_text(
                self.SKILL_FILES.get(target_file, ""), encoding="utf-8"
            )

        # Write new content
        target_path.write_text(patch, encoding="utf-8")

        # Record patch metadata
        patch_meta = {
            "version": version,
            "target_file": target_file,
            "rationale": rationale,
            "timestamp": time.time(),
            "archive_path": str(archive_path),
        }
        patch_meta_path = self.patches_dir / f"strategy_v{version}.json"
        patch_meta_path.write_text(
            json.dumps(patch_meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        logger.info(
            f"[Strategy] Applied v{version} to {target_file}: {rationale[:100]}"
        )
        return archive_path

    def rollback(self, version: int | None = None, target_file: str | None = None) -> bool:
        """Rollback to a previous version. If version is None, rollback to the latest archive."""
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.patches_dir.mkdir(parents=True, exist_ok=True)

        if version is None:
            # Use the latest patch
            version = self._version_counter

        # Find patch metadata to determine target_file if not specified
        patch_meta_path = self.patches_dir / f"strategy_v{version}.json"
        if patch_meta_path.exists():
            meta = json.loads(patch_meta_path.read_text(encoding="utf-8"))
            if target_file is None:
                target_file = meta.get("target_file", "distillation_strategy.md")
        else:
            if target_file is None:
                target_file = "distillation_strategy.md"

        stem = target_file.replace(".md", "")
        archive_path = self.archive_dir / f"{stem}_v{version}.md"

        if not archive_path.exists():
            logger.warning(f"[Strategy] Archive not found: {archive_path}")
            return False

        target_path = self.base_dir / target_file

        # Archive current state before rollback (so rollback is itself reversible)
        self._version_counter += 1
        new_version = self._version_counter
        rollback_archive = self.archive_dir / f"{stem}_v{new_version}.md"
        if target_path.exists():
            rollback_archive.write_text(
                target_path.read_text(encoding="utf-8"), encoding="utf-8"
            )

        # Restore from archive
        target_path.write_text(
            archive_path.read_text(encoding="utf-8"), encoding="utf-8"
        )

        # Record rollback metadata
        rb_meta = {
            "version": new_version,
            "target_file": target_file,
            "rationale": f"Rollback to v{version}",
            "timestamp": time.time(),
            "archive_path": str(rollback_archive),
            "is_rollback": True,
            "rollback_from_version": version,
        }
        rb_meta_path = self.patches_dir / f"strategy_v{new_version}.json"
        rb_meta_path.write_text(
            json.dumps(rb_meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        logger.info(f"[Strategy] Rolled back {target_file} to v{version}")
        return True

    def get_version_history(self) -> list[dict]:
        """List all patch metadata chronologically."""
        if not self.patches_dir.exists():
            return []
        entries = []
        for p in sorted(self.patches_dir.glob("strategy_v*.json")):
            try:
                entries.append(json.loads(p.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
        return entries

    @staticmethod
    def parse_kv(content: str) -> dict[str, str]:
        """Extract key-value pairs from markdown content.

        Matches patterns like: key: value, - key: value, key_name: value
        """
        result = {}
        for line in content.splitlines():
            line = line.strip()
            # Skip headings and empty lines
            if not line or line.startswith("#"):
                continue
            # Match "key: value" or "- key: value"
            m = re.match(r"^-?\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.+)$", line)
            if m:
                result[m.group(1)] = m.group(2).strip()
        return result
