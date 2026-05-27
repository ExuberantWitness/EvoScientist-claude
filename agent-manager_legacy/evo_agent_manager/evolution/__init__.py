"""EvoScientist Evolution Layer — RSPL/SEPL progressive architecture.

Resource Substrate Protocol Layer (RSPL):
    registry.py — resource registration with version tracking

Self Evolution Protocol Layer (SEPL):
    elo.py        — Elo tournament for idea ranking (paper §3.3)
    tree_search.py — Idea Tree Search for RA (paper §3.2)
    memory.py     — IDE/IVE/ESE evolution memory (paper §D.1-D.2)
    pipeline.py   — 3-phase research pipeline with auto-distillation
    scoring.py    — LLM-based article quality evaluation
    fitness.py    — Cross-run fitness tracking with trend detection
    strategy.py   — Evolvable strategy file management
    meta_agent.py — LLM-driven strategy proposal agent
    trigger.py    — Meta-cognition trigger conditions
    validator.py  — Auto-rollback on strategy regression
"""

from .elo import EloTournament
from .fitness import FitnessTracker
from .memory import EvolutionMemory
from .meta_agent import MetaAgent
from .pipeline import ResearchPipeline
from .scoring import evaluate_article, heuristic_score
from .strategy import StrategyManager
from .tree_search import IdeaTreeSearch
from .trigger import MetaCognitionTrigger
from .validator import EvolutionValidator

__all__ = [
    "EloTournament",
    "EvolutionMemory",
    "EvolutionValidator",
    "FitnessTracker",
    "IdeaTreeSearch",
    "MetaAgent",
    "MetaCognitionTrigger",
    "ResearchPipeline",
    "StrategyManager",
    "evaluate_article",
    "heuristic_score",
]
