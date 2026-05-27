"""FitnessTracker: 分层适应度追踪 + 方差监测。

追踪维度:
  - 全局: 所有轮次最高分趋势
  - 每 Island: 各方法家族的适应度变化
  - 每轮: 单轮内的最佳/平均/方差

存储: JSONL 文件 (memory/fitness_history.jsonl)
"""

import json
import time
from pathlib import Path


class FitnessTracker:
    """分层适应度追踪器。"""

    def __init__(self, workspace_dir: str | Path):
        self.path = Path(workspace_dir) / "memory" / "fitness_history.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ── 写入 ──

    def record(
        self,
        score: float,
        island_id: str = "",
        task_id: str = "",
        dimensions: dict | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """追加一条适应度记录。"""
        entry = {
            "timestamp": time.time(),
            "score": float(score),
            "island_id": island_id,
            "task_id": task_id,
            "dimensions": dimensions or {},
            "metadata": metadata or {},
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    # ── 读取 ──

    def get_history(self, limit: int = 50) -> list[dict]:
        """读取最近 N 条记录，时间升序。"""
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
        """最近 N 条记录的分数列表。"""
        history = self.get_history(limit=n)
        return [e["score"] for e in history[-n:]]

    # ── 趋势分析 ──

    def get_trend(self, window: int = 10) -> dict:
        """线性回归斜率 + 方差。

        Returns:
            {direction: "improving"|"declining"|"stable"|"insufficient_data",
             slope: float, mean: float, variance: float, n: int}
        """
        scores = self.get_recent_scores(n=window)
        n = len(scores)
        if n < 2:
            return {
                "direction": "insufficient_data",
                "slope": 0.0,
                "mean": 0.0,
                "variance": 0.0,
                "n": n,
            }

        mean = sum(scores) / n
        x_mean = (n - 1) / 2.0
        numerator = sum((i - x_mean) * (s - mean) for i, s in enumerate(scores))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        slope = numerator / denominator if denominator > 0 else 0.0

        variance = sum((s - mean) ** 2 for s in scores) / n

        if slope > 0.01:
            direction = "improving"
        elif slope < -0.01:
            direction = "declining"
        else:
            direction = "stable"

        return {
            "direction": direction,
            "slope": round(slope, 4),
            "mean": round(mean, 4),
            "variance": round(variance, 4),
            "n": n,
        }

    # ── 分层统计 ──

    def get_stats(self) -> dict:
        """全局 + 每 Island + 每轮分层统计。"""
        history = self.get_history(limit=1000)
        if not history:
            return {
                "total_runs": 0,
                "global": {"mean_score": 0.0, "max_score": 0.0, "min_score": 0.0,
                           "last_score": 0.0, "variance": 0.0},
                "by_island": {},
                "trend": self.get_trend(),
            }

        scores = [e["score"] for e in history]
        global_mean = sum(scores) / len(scores)
        global_var = sum((s - global_mean) ** 2 for s in scores) / len(scores)

        # 按 Island 分组
        by_island: dict[str, list[float]] = {}
        for e in history:
            iid = e.get("island_id", "") or "_global"
            by_island.setdefault(iid, []).append(e["score"])

        island_stats = {}
        for iid, i_scores in by_island.items():
            im = sum(i_scores) / len(i_scores)
            iv = sum((s - im) ** 2 for s in i_scores) / len(i_scores)
            island_stats[iid] = {
                "count": len(i_scores),
                "mean": round(im, 4),
                "max": round(max(i_scores), 4),
                "variance": round(iv, 4),
            }

        return {
            "total_runs": len(scores),
            "global": {
                "mean_score": round(global_mean, 4),
                "max_score": round(max(scores), 4),
                "min_score": round(min(scores), 4),
                "last_score": round(scores[-1], 4),
                "variance": round(global_var, 4),
            },
            "by_island": island_stats,
            "trend": self.get_trend(),
        }
