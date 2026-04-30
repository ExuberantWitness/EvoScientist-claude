"""EvoScientist Evolution Layer — RSPL/SEPL progressive architecture.

Resource Substrate Protocol Layer (RSPL):
    registry.py — resource registration with version tracking

Self Evolution Protocol Layer (SEPL):
    elo.py        — Elo tournament for idea ranking (paper §3.3)
    tree_search.py — Idea Tree Search for RA (paper §3.2)
    memory.py     — IDE/IVE/ESE evolution memory (paper §D.1-D.2)
    pipeline.py   — 3-phase research pipeline with auto-distillation
"""

from .elo import EloTournament
from .memory import EvolutionMemory
from .pipeline import ResearchPipeline
from .tree_search import IdeaTreeSearch

__all__ = [
    "EloTournament",
    "EvolutionMemory",
    "IdeaTreeSearch",
    "ResearchPipeline",
]
