"""Negative archive for failed atom refinements (ADAS mechanism).

Records verify_atom failures so future refinement rounds can use them
as anti-pattern few-shot examples. Prevents MAP-Elites from re-generating
variants of previously-failed atoms.

Separate from cell_grid.py anomaly detection — those are runtime
experiment anomalies, these are schema-level failures.

Usage:
  from tools.negative_archive import NegativeArchive
  na = NegativeArchive(session_dir)
  na.record_failure(atom_id, attempt, error_class, stderr_snippet, model)
  na.get_recent_failures(n=5)  # for anti-pattern few-shot
  na.should_ban_direction(atom_id)  # for MAP-Elites budget control
"""

import json
import time
from pathlib import Path


class NegativeArchive:
    """Tracks failed atom refinements for anti-pattern learning.

    Stored in _index/refine_failures.jsonl (NOT cell_grid anomaly archive).
    """

    def __init__(self, session_dir: Path):
        self.session_dir = Path(session_dir)
        self.index_dir = self.session_dir / "_index"
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.index_dir / "refine_failures.jsonl"

        # Ban direction after this many failures of the same atom_id class
        self.MAX_FAILURES_PER_CLASS = 5

    def record_failure(
        self,
        atom_id: str,
        attempt: int,
        error_class: str,
        stderr_snippet: str,
        refine_model: str = "unknown",
    ) -> dict:
        """Record a failed refinement attempt."""
        record = {
            "atom_id": atom_id,
            "attempt": attempt,
            "verify_error_class": error_class,
            "verify_stderr_snippet": stderr_snippet[:500],
            "timestamp": time.time(),
            "refine_model": refine_model,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def get_recent_failures(self, n: int = 5) -> list[dict]:
        """Get N most recent failures for anti-pattern few-shot in evo-refine prompt."""
        if not self.path.exists():
            return []
        records = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return sorted(records, key=lambda r: r.get("timestamp", 0), reverse=True)[:n]

    def count_failures(self, atom_id_prefix: str) -> int:
        """Count failures for atoms sharing a prefix (e.g., 'map' matches 'map1', 'map2')."""
        if not self.path.exists():
            return 0
        count = 0
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rec = json.loads(line)
                        if rec.get("atom_id", "").startswith(atom_id_prefix):
                            count += 1
                    except json.JSONDecodeError:
                        pass
        return count

    def should_ban_direction(self, atom_id: str) -> bool:
        """Check if this atom direction should be banned from further attempts.

        Returns True if the same atom_id prefix has failed too many times,
        indicating MAP-Elites should stop exploring this direction.
        """
        # Strip trailing numbers to get the "class" prefix
        prefix = atom_id.rstrip("0123456789_")
        if not prefix:
            prefix = atom_id
        failures = self.count_failures(prefix)
        return failures >= self.MAX_FAILURES_PER_CLASS

    def get_ban_list(self) -> list[str]:
        """Get list of atom_id prefixes that are currently banned."""
        if not self.path.exists():
            return []
        prefix_counts: dict[str, int] = {}
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rec = json.loads(line)
                        aid = rec.get("atom_id", "")
                        prefix = aid.rstrip("0123456789_")
                        if not prefix:
                            prefix = aid
                        prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1
                    except json.JSONDecodeError:
                        pass
        return [
            p for p, c in prefix_counts.items()
            if c >= self.MAX_FAILURES_PER_CLASS
        ]


def atom_verify_gate(atom_json_path: Path, session_dir: Path | None = None) -> tuple[bool, str]:
    """Gate for MAP-Elites fitness: reject atoms that fail verify_atom.

    Called before fitness evaluation. Returns (pass, reason).

    Usage in fitness function:
      from tools.negative_archive import atom_verify_gate
      ok, reason = atom_verify_gate(atom_path)
      if not ok:
          return -float('inf')
    """
    import subprocess
    import sys

    args = [
        sys.executable,
        str(Path(__file__).parent / "verify_atom.py"),
        "--quick" if session_dir is None else "--session",
    ]
    if session_dir:
        args.append(str(session_dir))
    args.extend(["--atom", str(atom_json_path)])

    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        return False, r.stdout.strip()[:200]
    return True, "PASS"
