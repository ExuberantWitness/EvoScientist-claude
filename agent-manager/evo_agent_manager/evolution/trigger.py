"""Meta-cognition trigger for deciding when to self-modify strategies.

Three event-driven conditions:
1. Stagnation: K consecutive evals with no improvement
2. Cycle completion: finished a full pipeline cycle
3. Peer improvement: another session's strategy change led to gains
"""


class MetaCognitionTrigger:
    """Decide when to trigger self-modification of strategies."""

    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self.stagnation_k: int = cfg.get("stagnation_k", 5)
        self.stagnation_threshold: float = cfg.get("stagnation_threshold", 0.01)
        self.peer_improvement_threshold: float = cfg.get("peer_improvement_threshold", 0.1)

    def should_trigger(self, agent_state: dict) -> bool:
        """Check all trigger conditions. Returns True if any is met."""
        # Condition 1: Stagnation
        last_scores = agent_state.get("last_scores", [])
        if len(last_scores) >= self.stagnation_k:
            recent = last_scores[-self.stagnation_k:]
            score_range = max(recent) - min(recent)
            if score_range < self.stagnation_threshold:
                return True

        # Condition 2: Cycle completion
        if agent_state.get("phase_cycle_just_completed", False):
            return True

        # Condition 3: Peer improvement
        peer_log = agent_state.get("peer_evolution_log", [])
        for entry in peer_log[-5:]:
            delta = entry.get("score_delta", 0)
            if delta > self.peer_improvement_threshold:
                return True

        return False

    @staticmethod
    def build_agent_state(
        last_scores: list[float],
        cycle_just_completed: bool = False,
        peer_evolution_log: list[dict] | None = None,
    ) -> dict:
        """Build agent_state dict from raw data."""
        return {
            "last_scores": last_scores,
            "phase_cycle_just_completed": cycle_just_completed,
            "peer_evolution_log": peer_evolution_log or [],
        }
