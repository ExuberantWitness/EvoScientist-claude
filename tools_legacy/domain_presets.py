"""Domain configuration presets for EvoScientist pipeline.

Provides ready-to-use DomainConfig dicts for common research domains.
Used by evo-intake SKILL to auto-detect domain parameters.

Usage:
  from tools.domain_presets import get_domain_preset
  cfg = get_domain_preset("reinforcement_learning")
"""

DOMAIN_PRESETS: dict[str, dict] = {
    "reinforcement_learning": {
        "domain_name": "reinforcement_learning",
        "seed_keywords": [
            "reinforcement learning", "policy optimization", "actor-critic",
            "Q-learning", "model-free RL", "exploration strategies",
        ],
        "active_bottleneck_categories": [
            "overestimation_bias", "training_instability", "sample_inefficiency",
            "exploration_insufficient", "convergence_slow", "hyperparameter_sensitivity",
            "generalization_gap", "computational_cost", "reward_sparsity",
            "multi_objective_conflict", "distributional_shift", "gradient_interference",
            "representation_collapse", "credit_assignment_long",
        ],
        "search_query_templates": [
            "Standard benchmarks and baseline methods for {topic}",
            "State-of-the-art approaches for {topic} with open-source implementations",
            "Recent advances and公认 baselines in {topic} research",
        ],
        "sme_domains": [
            "reinforcement_learning", "evolutionary_algorithms",
            "neural_architecture_search", "information_theory",
            "causal_inference", "meta_learning",
        ],
        "acceptance_criteria": (
            "1. smoke_test.py passes (10 episodes, no crash)\n"
            "2. train_all.py --quick survives 5000 steps\n"
            "3. Baselines reach known range on benchmark environments\n"
            "4. At least 1 proposal beats best baseline by >5%\n"
            "5. analyze.py produces statistical comparison report"
        ),
    },

    "supervised_learning": {
        "domain_name": "supervised_learning",
        "seed_keywords": [
            "supervised learning", "classification", "regression",
            "deep neural networks", "training dynamics",
        ],
        "active_bottleneck_categories": [
            "generalization_gap", "hyperparameter_sensitivity", "computational_cost",
            "gradient_interference", "representation_collapse", "distributional_shift",
            "training_instability",
        ],
        "search_query_templates": [
            "Latest advances in {topic} 2024-2025",
            "Novel training methods for deep neural networks",
        ],
        "sme_domains": [
            "neural_architecture_search", "information_theory",
            "meta_learning", "causal_inference",
        ],
        "acceptance_criteria": "",
    },

    "biology_simulation": {
        "domain_name": "biology_simulation",
        "seed_keywords": [
            "molecular dynamics", "protein folding", "computational biology",
            "free energy", "force fields",
        ],
        "active_bottleneck_categories": [
            "computational_cost", "convergence_slow", "hyperparameter_sensitivity",
            "multi_objective_conflict", "distributional_shift",
        ],
        "search_query_templates": [
            "Latest advances in molecular simulation methods 2024-2025",
        ],
        "sme_domains": [
            "reinforcement_learning", "information_theory",
        ],
        "acceptance_criteria": "",
    },

    "general": {
        "domain_name": "general",
        "seed_keywords": ["research", "method", "experiment"],
        "active_bottleneck_categories": [],
        "search_query_templates": ["Latest advances in {topic} 2024-2025"],
        "sme_domains": [],
        "acceptance_criteria": "",
    },
}


def get_domain_preset(name: str) -> dict:
    """Get a domain configuration preset by name.

    Returns a copy (safe to mutate) or the 'general' preset if not found.
    """
    preset = DOMAIN_PRESETS.get(name, DOMAIN_PRESETS["general"])
    return {k: v.copy() if isinstance(v, (list, dict)) else v
            for k, v in preset.items()}


def list_presets() -> list[str]:
    """List available domain preset names."""
    return sorted(DOMAIN_PRESETS.keys())
