#!/usr/bin/env python3
"""
Analysis and plotting script for Hopper-v4 experiments.

Reads training logs (CSV/JSON) and produces:
  1. Learning curves (return vs steps, per algorithm)
  2. Comparison tables (mean, std, min, max)
  3. Statistical tests (bootstrap confidence intervals)
  4. Ablation analysis

Usage:
    python analyze.py --results-dir ./hopper_experiments
    python analyze.py --results-dir ./hopper_experiments --plot-only
"""

import os
import sys
import json
import csv
import argparse
import numpy as np
from collections import defaultdict
from typing import Dict, List, Tuple

try:
    from scipy import stats
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

# Optional imports
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import seaborn as sns
    HAS_PLOTTING = True
except ImportError:
    HAS_PLOTTING = False
    print("Warning: matplotlib/seaborn not available. Plotting disabled.")


def load_results(results_dir: str) -> Dict[str, List[Dict]]:
    """Load all training results from directory structure."""
    results = defaultdict(list)

    for root, dirs, files in os.walk(results_dir):
        for f in files:
            if f.endswith('_logs.json'):
                algo = os.path.basename(root)
                seed_str = f.split('_seed')[1].split('_logs')[0]
                try:
                    seed = int(seed_str)
                except ValueError:
                    continue
                with open(os.path.join(root, f)) as fp:
                    data = json.load(fp)
                results[algo].append({"seed": seed, "logs": data})

    return dict(results)


def compute_summary(results: Dict[str, List[Dict]], last_n: int = 10) -> Dict:
    """Compute summary statistics per algorithm."""
    summary = {}

    for algo, runs in results.items():
        final_returns = []
        for run in runs:
            logs = run["logs"]
            if "eval_return_mean" in logs and logs["eval_return_mean"]:
                returns = logs["eval_return_mean"]
                # Use last N evaluations
                final_returns.append(np.mean(returns[-last_n:]))

        if final_returns:
            summary[algo] = {
                "mean": float(np.mean(final_returns)),
                "std": float(np.std(final_returns)),
                "min": float(np.min(final_returns)),
                "max": float(np.max(final_returns)),
                "n_seeds": len(final_returns),
                "sem": float(np.std(final_returns) / np.sqrt(len(final_returns))),
            }

    return summary


def bootstrap_ci(data: List[float], n_bootstrap: int = 10000,
                 ci: float = 0.95) -> Tuple[float, float]:
    """Compute bootstrap confidence interval."""
    data = np.array(data)
    means = []
    n = len(data)
    for _ in range(n_bootstrap):
        sample = np.random.choice(data, size=n, replace=True)
        means.append(np.mean(sample))
    means = np.array(means)
    lower = np.percentile(means, (1 - ci) / 2 * 100)
    upper = np.percentile(means, (1 + ci) / 2 * 100)
    return float(lower), float(upper)


def welch_ttest(results: Dict, algo_a: str, algo_b: str):
    """Welch's t-test between two algorithms' final returns."""
    if not HAS_SCIPY:
        return float('nan'), float('nan')
    returns_a, returns_b = [], []
    for run in results.get(algo_a, []):
        logs = run["logs"]
        if "eval_return_mean" in logs and logs["eval_return_mean"]:
            returns_a.append(np.mean(logs["eval_return_mean"][-10:]))
    for run in results.get(algo_b, []):
        logs = run["logs"]
        if "eval_return_mean" in logs and logs["eval_return_mean"]:
            returns_b.append(np.mean(logs["eval_return_mean"][-10:]))
    if len(returns_a) < 2 or len(returns_b) < 2:
        return float('nan'), float('nan')
    t_stat, p_val = stats.ttest_ind(returns_a, returns_b, equal_var=False)
    return float(t_stat), float(p_val)


def compute_sample_efficiency(results: Dict[str, List[Dict]],
                              target_return: float) -> Dict:
    """Compute steps to reach target return per algorithm."""
    efficiency = {}
    for algo, runs in results.items():
        steps_to_target = []
        for run in runs:
            logs = run["logs"]
            if "step" not in logs or "eval_return_mean" not in logs:
                continue
            steps = logs["step"]
            returns = logs["eval_return_mean"]
            # Find first step where return >= target
            for s, r in zip(steps, returns):
                if r >= target_return:
                    steps_to_target.append(s)
                    break
            else:
                steps_to_target.append(float('inf'))

        if steps_to_target:
            finite = [s for s in steps_to_target if s != float('inf')]
            efficiency[algo] = {
                "target_return": target_return,
                "mean_steps": float(np.mean(steps_to_target)) if finite else float('inf'),
                "median_steps": float(np.median(steps_to_target)) if finite else float('inf'),
                "success_rate": len(finite) / len(steps_to_target),
            }

    return efficiency


def plot_learning_curves(results: Dict, output_dir: str,
                        title: str = "Hopper-v4 Learning Curves",
                        figsize: Tuple = (12, 7)):
    """Plot learning curves for all algorithms."""
    if not HAS_PLOTTING:
        return

    sns.set_style("whitegrid")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize)

    colors = plt.cm.tab10(np.linspace(0, 1, 10))
    algo_colors = {}

    for algo, runs in sorted(results.items()):
        all_returns = defaultdict(list)
        for run in runs:
            logs = run["logs"]
            if "step" not in logs or "eval_return_mean" not in logs:
                continue
            for s, r in zip(logs["step"], logs["eval_return_mean"]):
                all_returns[s].append(r)

        if not all_returns:
            continue

        steps = sorted(all_returns.keys())
        means = [np.mean(all_returns[s]) for s in steps]
        stds = [np.std(all_returns[s]) for s in steps]

        color = colors[len(algo_colors) % 10]
        algo_colors[algo] = color

        ax1.plot(steps, means, label=algo, color=color, linewidth=2)
        ax1.fill_between(steps,
                         np.array(means) - np.array(stds),
                         np.array(means) + np.array(stds),
                         alpha=0.2, color=color)

    ax1.set_xlabel("Steps", fontsize=12)
    ax1.set_ylabel("Mean Return", fontsize=12)
    ax1.set_title(title, fontsize=14)
    ax1.legend(fontsize=10)
    ax1.grid(True, alpha=0.3)

    # Sample efficiency plot
    if results:
        for algo in sorted(results.keys()):
            summary = compute_summary({algo: results[algo]})
            if algo in summary:
                ci = bootstrap_ci(
                    [np.mean(run["logs"]["eval_return_mean"][-10:])
                     for run in results[algo]
                     if len(run["logs"].get("eval_return_mean", [])) >= 10]
                )
                s = summary[algo]
                color = algo_colors.get(algo, 'gray')
                ax2.bar(algo, s["mean"], yerr=s["sem"], color=color,
                        alpha=0.7, capsize=5)
                ax2.errorbar(algo, s["mean"], yerr=[[s["mean"] - ci[0]],
                                                    [ci[1] - s["mean"]]],
                            fmt='none', color='black', capsize=3, linewidth=1)

    ax2.set_ylabel("Final Return", fontsize=12)
    ax2.set_title("Final Performance Comparison", fontsize=14)
    ax2.grid(True, alpha=0.3, axis='y')
    plt.setp(ax2.get_xticklabels(), rotation=45, ha='right')

    plt.tight_layout()
    save_path = os.path.join(output_dir, "learning_curves.png")
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Learning curves saved to {save_path}")


def plot_ablation_comparison(results: Dict, output_dir: str):
    """Plot ablation comparison bar chart."""
    if not HAS_PLOTTING:
        return

    summary = compute_summary(results)
    if not summary:
        return

    algos = sorted(summary.keys())
    means = [summary[a]["mean"] for a in algos]
    stds = [summary[a]["std"] for a in algos]

    plt.figure(figsize=(10, 6))
    bars = plt.bar(algos, means, yerr=stds, capsize=5, alpha=0.7,
                   color=plt.cm.viridis(np.linspace(0, 1, len(algos))))
    plt.ylabel("Mean Final Return")
    plt.title("Algorithm Comparison on Hopper-v4")
    plt.xticks(rotation=45, ha='right')
    plt.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()

    save_path = os.path.join(output_dir, "ablation_comparison.png")
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Ablation comparison saved to {save_path}")


def print_report(results: Dict, output_dir: str):
    """Print a comprehensive report."""
    summary = compute_summary(results)
    efficiency = compute_sample_efficiency(results, target_return=2500)

    report = []
    report.append("=" * 70)
    report.append("HOPPER-V4 EXPERIMENT REPORT")
    report.append("=" * 70)

    report.append("\n## Final Performance")
    report.append(f"{'Algorithm':<15} {'Mean':>10} {'Std':>8} {'Min':>8} {'Max':>8} {'Seeds':>6}")
    report.append("-" * 55)
    for algo, s in sorted(summary.items()):
        report.append(
            f"{algo:<15} {s['mean']:>10.1f} {s['std']:>8.1f} "
            f"{s['min']:>8.1f} {s['max']:>8.1f} {s['n_seeds']:>6}"
        )

    report.append("\n## Sample Efficiency (steps to reach return 2500)")
    if efficiency:
        report.append(f"{'Algorithm':<15} {'Mean Steps':>12} {'Success Rate':>13}")
        report.append("-" * 40)
        for algo, e in sorted(efficiency.items()):
            report.append(
                f"{algo:<15} {e['mean_steps']:>12.0f} {e['success_rate']:>12.1%}"
            )

    report.append("\n## Bootstrap 95% CI on Final Return")
    report.append(f"{'Algorithm':<15} {'Mean':>10} {'CI Lower':>10} {'CI Upper':>10}")
    report.append("-" * 45)
    for algo, runs in sorted(results.items()):
        returns = [np.mean(run["logs"].get("eval_return_mean", [0])[-10:])
                   for run in runs if len(run["logs"].get("eval_return_mean", [])) >= 10]
        if returns:
            lo, hi = bootstrap_ci(returns)
            report.append(f"{algo:<15} {np.mean(returns):>10.1f} {lo:>10.1f} {hi:>10.1f}")

    # Welch's t-test between best and others
    if HAS_SCIPY and len(summary) >= 2:
        best_algo = max(summary, key=lambda a: summary[a]["mean"])
        report.append("\n## Welch's t-test (vs best: {})".format(best_algo))
        report.append(f"{'Algorithm':<15} {'t-stat':>8} {'p-value':>8} {'Significant?':>12}")
        report.append("-" * 45)
        for algo in sorted(summary.keys()):
            if algo == best_algo:
                continue
            t_stat, p_val = welch_ttest(results, best_algo, algo)
            sig = "YES" if p_val < 0.05 else "no"
            report.append(f"{algo:<15} {t_stat:>8.2f} {p_val:>8.4f} {sig:>12}")

    report.append("\n" + "=" * 70)

    report_str = "\n".join(report)
    print(report_str)

    # Save to file
    report_path = os.path.join(output_dir, "analysis_report.txt")
    with open(report_path, 'w') as f:
        f.write(report_str)
    print(f"\nReport saved to {report_path}")


def main():
    parser = argparse.ArgumentParser(description="Analyze Hopper-v4 experiment results")
    parser.add_argument("--results-dir", type=str, default="./hopper_experiments",
                        help="Directory containing experiment results")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Output directory for plots")
    parser.add_argument("--plot-only", action="store_true",
                        help="Only generate plots, skip report")
    parser.add_argument("--target-return", type=float, default=2500,
                        help="Target return for sample efficiency")
    args = parser.parse_args()

    results_dir = args.results_dir
    output_dir = args.output_dir or os.path.join(results_dir, "analysis")
    os.makedirs(output_dir, exist_ok=True)

    if not os.path.exists(results_dir):
        print(f"Results directory not found: {results_dir}")
        print("Run training first: python train_baselines.py")
        return

    print(f"Loading results from: {results_dir}")
    results = load_results(results_dir)

    if not results:
        print("No results found. Check directory structure.")
        return

    print(f"Found {sum(len(v) for v in results.values())} runs "
          f"across {len(results)} algorithms")

    # Generate report
    if not args.plot_only:
        print_report(results, output_dir)

    # Generate plots
    if HAS_PLOTTING:
        plot_learning_curves(results, output_dir)
        plot_ablation_comparison(results, output_dir)

    # Save summary as JSON
    summary = compute_summary(results)
    summary_path = os.path.join(output_dir, "summary.json")
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"Summary saved to {summary_path}")


if __name__ == "__main__":
    main()
