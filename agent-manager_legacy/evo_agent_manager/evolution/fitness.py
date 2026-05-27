"""Cross-run fitness tracking for self-evolution.

Records eval scores over time, detects trends (improving/declining/stable),
and provides statistics for meta-evolution triggers.
"""

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class FitnessTracker:
    """Records and analyzes eval scores across pipeline runs."""

    def __init__(self, workspace_dir: str | Path):
        self.path = Path(workspace_dir) / "memory" / "fitness_history.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        score: float,
        task_id: str = "",
        dimensions: dict | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Append a fitness entry. Returns the entry dict."""
        entry = {
            "timestamp": time.time(),
            "score": float(score),
            "task_id": task_id,
            "dimensions": dimensions or {},
            "metadata": metadata or {},
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def get_history(self, limit: int = 50) -> list[dict]:
        """Read last N entries sorted by timestamp ascending."""
        if not self.path.exists():
            return []
        entries = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return entries[-limit:]

    def get_recent_scores(self, n: int = 5) -> list[float]:
        """Return the last N eval scores as a flat float list."""
        history = self.get_history(limit=n)
        return [e["score"] for e in history[-n:]]

    def get_trend(self, window: int = 10) -> dict:
        """Compute trend over the last N scores via linear regression slope.

        Returns:
            {"direction": "improving"|"declining"|"stable"|"insufficient_data",
             "slope": float, "mean": float, "n": int}
        """
        scores = self.get_recent_scores(n=window)
        n = len(scores)
        if n < 2:
            return {"direction": "insufficient_data", "slope": 0.0, "mean": 0.0, "n": n}

        mean = sum(scores) / n
        # Simple linear regression: y = mx + b
        x_mean = (n - 1) / 2.0
        numerator = sum((i - x_mean) * (s - mean) for i, s in enumerate(scores))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        slope = numerator / denominator if denominator > 0 else 0.0

        if slope > 0.01:
            direction = "improving"
        elif slope < -0.01:
            direction = "declining"
        else:
            direction = "stable"

        return {"direction": direction, "slope": round(slope, 4), "mean": round(mean, 4), "n": n}

    def get_stats(self) -> dict:
        """Summary statistics over all recorded runs."""
        history = self.get_history(limit=1000)
        if not history:
            return {
                "total_runs": 0,
                "mean_score": 0.0,
                "max_score": 0.0,
                "min_score": 0.0,
                "last_score": 0.0,
                "trend": {"direction": "insufficient_data", "slope": 0.0, "mean": 0.0, "n": 0},
            }

        scores = [e["score"] for e in history]
        return {
            "total_runs": len(scores),
            "mean_score": round(sum(scores) / len(scores), 4),
            "max_score": round(max(scores), 4),
            "min_score": round(min(scores), 4),
            "last_score": round(scores[-1], 4),
            "trend": self.get_trend(),
        }
