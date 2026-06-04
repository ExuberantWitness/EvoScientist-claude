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
