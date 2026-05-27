"""BaseAlgorithm — abstract contract for all research method implementations.

All agents/experiment methods MUST inherit from BaseAlgorithm.
verify_atom.py checks issubclass() as a hard gate.

Phase 0a: Soft check via __init_subclass__ (warning, not error).
Phase 0b: Enable @abstractmethod enforcement after audit confirms alignment.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict

logger = logging.getLogger(__name__)

# Set to True in Phase 0b after audit confirms all agents match
ENFORCE_ABSTRACT = True


class BaseAlgorithm(ABC):
    """Contract for any computational research method.

    All methods in the EvoScientist pipeline that produce executable code
    must inherit from BaseAlgorithm. The four required methods cover the
    full lifecycle: inference, learning, persistence.
    """

    @abstractmethod
    def select_action(self, obs, deterministic: bool = False):
        """Produce an action/prediction/output from observations/inputs."""
        ...

    @abstractmethod
    def train(self, training_data, batch_size: int = 64) -> Dict:
        """Execute one training step using the provided data. Returns metrics dict."""
        ...

    @abstractmethod
    def save(self, path: str) -> None:
        """Persist model state to disk."""
        ...

    @abstractmethod
    def load(self, path: str) -> None:
        """Restore model state from disk."""
        ...

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if ENFORCE_ABSTRACT:
            return  # Already enforcing — ABC will catch missing methods

        # Soft check: verify required methods exist
        required = {
            "select_action": ["self", "obs"],
            "train": ["self", "training_data"],
            "save": ["self", "path"],
            "load": ["self", "path"],
        }

        for method_name, min_params in required.items():
            method = getattr(cls, method_name, None)
            if method is None:
                logger.warning(
                    "%s.%s is missing method '%s'. "
                    "Add it before Phase 0b enables @abstractmethod enforcement.",
                    cls.__module__, cls.__qualname__, method_name,
                )
            elif hasattr(method, "__isabstractmethod__") and method.__isabstractmethod__:
                logger.warning(
                    "%s.%s inherits abstract '%s'. Implement before Phase 0b.",
                    cls.__module__, cls.__qualname__, method_name,
                )
