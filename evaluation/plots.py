"""Visualization scripts for evaluation results.

Generates publication-ready figures for the thesis:
  - Threshold sensitivity heatmap
  - Configuration comparison bar chart
  - Per-category F1 breakdown
  - Latency distribution
  - Cost comparison
"""

import os

import matplotlib.pyplot as plt
import numpy as np

# Consistent style for thesis figures.
plt.rcParams.update({
    "figure.figsize": (8, 5),
    "figure.dpi": 150,
    "font.size": 11,
    "axes.titlesize": 13,
    "axes.labelsize": 12,
    "legend.fontsize": 10,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.1,
})

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "figures")


def _ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def plot_threshold_heatmap(
    tau_lows: list[float],
    tau_highs: list[float],
    f1_matrix: np.ndarray,
    escalation_matrix: np.ndarray,
    save: bool = True,
) -> plt.Figure:
    """Plot threshold sensitivity as a heatmap (Experiment 3).

    Args:
        tau_lows: List of tau_low values tested.
        tau_highs: List of tau_high values tested.
        f1_matrix: (len(tau_lows), len(tau_highs)) F1 scores.
        escalation_matrix: Same shape, escalation rates.
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # F1 heatmap.
    im1 = ax1.imshow(f1_matrix, cmap="YlGn", aspect="auto", vmin=0, vmax=1)
    ax1.set_xticks(range(len(tau_highs)))
    ax1.set_xticklabels([f"{v:.2f}" for v in tau_highs])
    ax1.set_yticks(range(len(tau_lows)))
    ax1.set_yticklabels([f"{v:.2f}" for v in tau_lows])
    ax1.set_xlabel(r"$\tau_{high}$")
    ax1.set_ylabel(r"$\tau_{low}$")
    ax1.set_title("F1-Score")
    plt.colorbar(im1, ax=ax1)

    for i in range(len(tau_lows)):
        for j in range(len(tau_highs)):
            ax1.text(j, i, f"{f1_matrix[i, j]:.2f}", ha="center", va="center", fontsize=9)

    # Escalation rate heatmap.
    im2 = ax2.imshow(escalation_matrix, cmap="YlOrRd", aspect="auto", vmin=0, vmax=0.5)
    ax2.set_xticks(range(len(tau_highs)))
    ax2.set_xticklabels([f"{v:.2f}" for v in tau_highs])
    ax2.set_yticks(range(len(tau_lows)))
    ax2.set_yticklabels([f"{v:.2f}" for v in tau_lows])
    ax2.set_xlabel(r"$\tau_{high}$")
    ax2.set_ylabel(r"$\tau_{low}$")
    ax2.set_title(r"Escalation Rate ($\rho$)")
    plt.colorbar(im2, ax=ax2)

    for i in range(len(tau_lows)):
        for j in range(len(tau_highs)):
            ax2.text(j, i, f"{escalation_matrix[i, j]:.2f}", ha="center", va="center", fontsize=9)

    fig.suptitle("Threshold Sensitivity Analysis", fontsize=14)
    plt.tight_layout()

    if save:
        _ensure_output_dir()
        fig.savefig(os.path.join(OUTPUT_DIR, "threshold_heatmap.png"))

    return fig


def plot_configuration_comparison(
    configs: list[str],
    f1_scores: list[float],
    f1_cis: list[tuple[float, float]],
    costs: list[float],
    save: bool = True,
) -> plt.Figure:
    """Bar chart comparing F1 and cost across configurations (Experiment 2).

    Args:
        configs: Configuration names.
        f1_scores: F1 for each config.
        f1_cis: (lower, upper) CI for each.
        costs: Cost per 1000 submissions for each.
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    x = np.arange(len(configs))
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]

    # F1 bar chart.
    errors = np.array([(f1 - lo, hi - f1) for f1, (lo, hi) in zip(f1_scores, f1_cis)]).T
    ax1.bar(x, f1_scores, yerr=errors, color=colors[:len(configs)],
            capsize=5, alpha=0.85, edgecolor="black", linewidth=0.5)
    ax1.set_xticks(x)
    ax1.set_xticklabels(configs, rotation=15, ha="right")
    ax1.set_ylabel("F1-Score")
    ax1.set_ylim(0, 1.1)
    ax1.set_title("Detection Accuracy")
    ax1.axhline(y=0.8, color="gray", linestyle="--", alpha=0.5, label="Target F1=0.80")
    ax1.legend()

    # Cost bar chart.
    ax2.bar(x, costs, color=colors[:len(configs)],
            alpha=0.85, edgecolor="black", linewidth=0.5)
    ax2.set_xticks(x)
    ax2.set_xticklabels(configs, rotation=15, ha="right")
    ax2.set_ylabel("Cost per 1000 submissions ($)")
    ax2.set_title("Processing Cost")

    fig.suptitle("Configuration Comparison", fontsize=14)
    plt.tight_layout()

    if save:
        _ensure_output_dir()
        fig.savefig(os.path.join(OUTPUT_DIR, "config_comparison.png"))

    return fig


def plot_per_category_f1(
    categories: list[str],
    f1_by_config: dict[str, list[float]],
    save: bool = True,
) -> plt.Figure:
    """Grouped bar chart of per-category F1 across configurations."""
    fig, ax = plt.subplots(figsize=(10, 5))

    x = np.arange(len(categories))
    width = 0.8 / len(f1_by_config)

    for i, (config_name, f1_values) in enumerate(f1_by_config.items()):
        offset = (i - len(f1_by_config) / 2 + 0.5) * width
        ax.bar(x + offset, f1_values, width, label=config_name, alpha=0.85, edgecolor="black", linewidth=0.5)

    ax.set_xticks(x)
    ax.set_xticklabels(categories)
    ax.set_ylabel("F1-Score")
    ax.set_title("Per-Category Detection Performance")
    ax.legend()
    ax.set_ylim(0, 1.1)
    plt.tight_layout()

    if save:
        _ensure_output_dir()
        fig.savefig(os.path.join(OUTPUT_DIR, "per_category_f1.png"))

    return fig


def plot_latency_distribution(
    latencies_ms: np.ndarray,
    p95_budget: float = 5000,
    save: bool = True,
) -> plt.Figure:
    """Histogram of processing latency with p95 budget line."""
    fig, ax = plt.subplots()

    ax.hist(latencies_ms, bins=30, color="#1f77b4", alpha=0.7, edgecolor="black", linewidth=0.5)
    ax.axvline(np.percentile(latencies_ms, 95), color="red", linestyle="--",
               label=f"p95 = {np.percentile(latencies_ms, 95):.0f} ms")
    ax.axvline(p95_budget, color="orange", linestyle=":",
               label=f"Budget = {p95_budget:.0f} ms")

    ax.set_xlabel("Latency (ms)")
    ax.set_ylabel("Count")
    ax.set_title("End-to-End Processing Latency")
    ax.legend()
    plt.tight_layout()

    if save:
        _ensure_output_dir()
        fig.savefig(os.path.join(OUTPUT_DIR, "latency_distribution.png"))

    return fig


def plot_escalation_breakdown(
    categories: list[str],
    tier1_resolved: list[int],
    escalated: list[int],
    save: bool = True,
) -> plt.Figure:
    """Stacked bar chart showing Tier 1 resolution vs escalation by category."""
    fig, ax = plt.subplots()

    x = np.arange(len(categories))
    ax.bar(x, tier1_resolved, label="Resolved at Tier 1", color="#2ca02c", alpha=0.85)
    ax.bar(x, escalated, bottom=tier1_resolved, label="Escalated to Tier 2", color="#d62728", alpha=0.85)

    ax.set_xticks(x)
    ax.set_xticklabels(categories)
    ax.set_ylabel("Count")
    ax.set_title("Tier Resolution by Category")
    ax.legend()
    plt.tight_layout()

    if save:
        _ensure_output_dir()
        fig.savefig(os.path.join(OUTPUT_DIR, "escalation_breakdown.png"))

    return fig
