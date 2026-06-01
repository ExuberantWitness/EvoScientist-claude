"""BuildSpec — code implementation specification generated before W4 Code phase.

Inspired by QUIT's BuildSpec.json: a structured, validatable contract that defines
exactly WHAT to implement before any code is written. User must approve the spec
before code generation begins.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ComponentChange:
    """A single component modification."""
    action: str           # ADD | MODIFY | REMOVE
    component: str        # CC atom title (e.g. "sac.actor_loss")
    reason: str           # Why this change is needed
    before: str = ""      # Current state (for MODIFY/REMOVE)
    after: str = ""       # Proposed state (for ADD/MODIFY)


@dataclass
class LossSpec:
    """Loss function specification."""
    name: str             # e.g. "actor_loss", "critic_loss"
    signature: str        # e.g. "def actor_loss(qf1, policy, obs) -> Tensor"
    formula: str          # Mathematical description
    description: str = ""


@dataclass
class Hyperparams:
    """Training hyperparameters."""
    learning_rate: float = 3e-4
    batch_size: int = 256
    buffer_size: int = 1_000_000
    gamma: float = 0.99
    tau: float = 0.005
    policy_frequency: int = 2
    target_noise: float = 0.2
    noise_clip: float = 0.5
    exploration_noise: float = 0.1
    total_timesteps: int = 1_000_000
    eval_frequency: int = 10_000
    seed_count: int = 5
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class BuildSpec:
    """Complete code implementation specification.

    Generated from CC atoms, winner proposal, and evolution memory.
    Must be approved by the user before code implementation.
    """
    spec_id: str
    target_method: str               # Winning proposal title
    target_baseline: str             # Which baseline to modify (e.g. "SAC")
    research_topic: str = ""
    hypothesis: str = ""             # Core hypothesis from winner proposal
    method_sketch: str = ""          # Method sketch from winner proposal

    # Architecture changes
    component_changes: list[ComponentChange] = field(default_factory=list)

    # Loss function changes
    loss_specs: list[LossSpec] = field(default_factory=list)

    # Training configuration
    hyperparams: Hyperparams = field(default_factory=Hyperparams)

    # Evaluation
    baselines: list[str] = field(default_factory=list)
    benchmark: str = ""
    success_criteria: list[str] = field(default_factory=list)

    # Metadata
    cc_atom_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "spec_id": self.spec_id,
            "target_method": self.target_method,
            "target_baseline": self.target_baseline,
            "research_topic": self.research_topic,
            "hypothesis": self.hypothesis,
            "method_sketch": self.method_sketch,
            "component_changes": [
                {"action": c.action, "component": c.component,
                 "reason": c.reason, "before": c.before, "after": c.after}
                for c in self.component_changes
            ],
            "loss_specs": [
                {"name": l.name, "signature": l.signature,
                 "formula": l.formula, "description": l.description}
                for l in self.loss_specs
            ],
            "hyperparams": {
                "learning_rate": self.hyperparams.learning_rate,
                "batch_size": self.hyperparams.batch_size,
                "buffer_size": self.hyperparams.buffer_size,
                "gamma": self.hyperparams.gamma,
                "tau": self.hyperparams.tau,
                "total_timesteps": self.hyperparams.total_timesteps,
                "eval_frequency": self.hyperparams.eval_frequency,
                "seed_count": self.hyperparams.seed_count,
                **self.hyperparams.extra,
            },
            "baselines": self.baselines,
            "benchmark": self.benchmark,
            "success_criteria": self.success_criteria,
            "cc_atom_ids": self.cc_atom_ids,
            "evidence_ids": self.evidence_ids,
        }

    def validate(self) -> list[str]:
        """Validate required fields. Returns list of errors (empty = valid)."""
        errors = []
        if not self.target_baseline:
            errors.append("target_baseline is required")
        if not self.target_method:
            errors.append("target_method is required")
        if not self.component_changes:
            errors.append("at least one component_change is required")
        if not self.loss_specs:
            errors.append("at least one loss_spec is required")
        if len(self.baselines) < 2:
            errors.append("at least 2 baselines are required for comparison")
        if not self.success_criteria:
            errors.append("at least one success_criterion is required")
        return errors

    def save(self, path: Path) -> None:
        """Write spec to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
                        encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "BuildSpec":
        """Load spec from JSON file."""
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "BuildSpec":
        """Create BuildSpec from dict (with defaults for missing fields)."""
        comps = [ComponentChange(**c) for c in data.get("component_changes", [])]
        losses = [LossSpec(**l) for l in data.get("loss_specs", [])]
        hp_data = data.get("hyperparams", {})
        hp = Hyperparams(
            learning_rate=hp_data.get("learning_rate", 3e-4),
            batch_size=hp_data.get("batch_size", 256),
            buffer_size=hp_data.get("buffer_size", 1_000_000),
            gamma=hp_data.get("gamma", 0.99),
            tau=hp_data.get("tau", 0.005),
            total_timesteps=hp_data.get("total_timesteps", 1_000_000),
            eval_frequency=hp_data.get("eval_frequency", 10_000),
            seed_count=hp_data.get("seed_count", 5),
            extra={k: v for k, v in hp_data.items()
                   if k not in ("learning_rate", "batch_size", "buffer_size",
                                "gamma", "tau", "total_timesteps",
                                "eval_frequency", "seed_count")},
        )
        return cls(
            spec_id=data.get("spec_id", ""),
            target_method=data.get("target_method", ""),
            target_baseline=data.get("target_baseline", ""),
            research_topic=data.get("research_topic", ""),
            hypothesis=data.get("hypothesis", ""),
            method_sketch=data.get("method_sketch", ""),
            component_changes=comps,
            loss_specs=losses,
            hyperparams=hp,
            baselines=data.get("baselines", []),
            benchmark=data.get("benchmark", ""),
            success_criteria=data.get("success_criteria", []),
            cc_atom_ids=data.get("cc_atom_ids", []),
            evidence_ids=data.get("evidence_ids", []),
        )