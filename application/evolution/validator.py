"""Evolution validator with auto-rollback on regression.

Monitors the effect of strategy changes over an observation window.
If post-change performance drops below a threshold, automatically reverts.
"""

import logging
from pathlib import Path

from .fitness import FitnessTracker
from .strategy import StrategyManager

logger = logging.getLogger(__name__)


class EvolutionValidator:
    """Monitor strategy changes and auto-rollback if performance declines.

    Observation window of 3 evals, 5% regression threshold.
    Better to occasionally accept a neutral change than kill promising ones early.
    """

    OBSERVATION_WINDOW = 3
    REGRESSION_THRESHOLD = 0.05

    def __init__(self, workspace_dir: str):
        self.workspace_dir = workspace_dir
        self._pending: dict[str, dict] = {}
        self._fitness = FitnessTracker(workspace_dir)

    def on_strategy_change(self, agent_id: str, old_strategy_path: str | Path) -> None:
        """Archive old strategy and start observing after a change."""
        # Record pre-change scores
        pre_scores = self._fitness.get_recent_scores(n=5)
        self._pending[agent_id] = {
            "old_strategy_path": str(old_strategy_path),
            "pre_scores": pre_scores,
            "post_scores": [],
            "pre_mean": sum(pre_scores) / max(len(pre_scores), 1) if pre_scores else 0.0,
            "evals_since_change": 0,
        }
        logger.info(
            f"[Validator] Watching {agent_id} after strategy change "
            f"(pre_mean={self._pending[agent_id]['pre_mean']:.3f})"
        )

    def on_eval_complete(self, agent_id: str, score: float) -> str | None:
        """Called after each eval. Returns "rollback", "confirm", or None (still observing).

        Returns:
            "rollback" if regression detected
            "confirm" if performance sustained for OBSERVATION_WINDOW evals
            None if still in observation window
        """
        if agent_id not in self._pending:
            return None

        state = self._pending[agent_id]
        state["post_scores"].append(score)
        state["evals_since_change"] += 1
        n = state["evals_since_change"]

        if n < self.OBSERVATION_WINDOW:
            return None

        post_mean = sum(state["post_scores"]) / len(state["post_scores"])
        pre_mean = state["pre_mean"]

        # Check for regression
        if pre_mean > 0 and (pre_mean - post_mean) > self.REGRESSION_THRESHOLD:
            logger.warning(
                f"[Validator] Regression detected for {agent_id}: "
                f"pre={pre_mean:.3f}, post={post_mean:.3f}, "
                f"delta={pre_mean - post_mean:.3f} > {self.REGRESSION_THRESHOLD}"
            )
            self._rollback(agent_id)
            return "rollback"

        # Performance sustained
        logger.info(
            f"[Validator] Confirmed strategy change for {agent_id}: "
            f"pre={pre_mean:.3f}, post={post_mean:.3f}"
        )
        self._confirm(agent_id)
        return "confirm"

    def _rollback(self, agent_id: str) -> None:
        """Restore archived strategy."""
        state = self._pending.pop(agent_id)
        sm = StrategyManager(self.workspace_dir)
        old_path = state.get("old_strategy_path", "")
        # Determine target file from the archived path
        if old_path:
            filename = Path(old_path).name
            sm.rollback(target_file=filename)
        else:
            sm.rollback()  # rollback latest
        logger.info(f"[Validator] Auto-rolled back strategy for {agent_id}")

    def _confirm(self, agent_id: str) -> None:
        """Clear observation state."""
        self._pending.pop(agent_id, None)
