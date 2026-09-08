"""Evaluation metrics for the plagiarism detection system.

Provides:
  - Precision, Recall, F1-score (binary and per-category)
  - Bootstrap confidence intervals
  - Paired t-test with Bonferroni correction
  - Cost model computation
  - Latency statistics
"""

from dataclasses import dataclass

import numpy as np
from scipy.stats import ttest_rel
from sklearn.metrics import (
    precision_score,
    recall_score,
    f1_score,
    classification_report,
    confusion_matrix,
)


@dataclass
class MetricsResult:
    precision: float
    recall: float
    f1: float
    precision_ci: tuple[float, float]
    recall_ci: tuple[float, float]
    f1_ci: tuple[float, float]
    n_samples: int
    confusion: np.ndarray


@dataclass
class CostResult:
    total_submissions: int
    escalation_rate: float
    escalated_count: int
    cost_per_submission: float
    total_cost: float
    baseline_cost: float
    savings_pct: float


@dataclass
class LatencyResult:
    p50: float
    p95: float
    p99: float
    mean: float
    std: float
    n_samples: int


# ── Core metrics ─────────────────────────────────────────────────

def compute_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    n_bootstrap: int = 1000,
    ci: float = 0.95,
    seed: int = 42,
) -> MetricsResult:
    """Compute precision, recall, F1 with bootstrap confidence intervals.

    Args:
        y_true: Ground truth binary labels (0=original, 1=plagiarised).
        y_pred: Predicted binary labels.
        n_bootstrap: Number of bootstrap resamples.
        ci: Confidence level.
        seed: Random seed.

    Returns:
        MetricsResult with point estimates and CIs.
    """
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)

    prec = precision_score(y_true, y_pred, zero_division=0)
    rec = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)

    prec_ci = _bootstrap_ci(y_true, y_pred, precision_score, n_bootstrap, ci, seed)
    rec_ci = _bootstrap_ci(y_true, y_pred, recall_score, n_bootstrap, ci, seed)
    f1_ci = _bootstrap_ci(y_true, y_pred, f1_score, n_bootstrap, ci, seed)

    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])

    return MetricsResult(
        precision=prec, recall=rec, f1=f1,
        precision_ci=prec_ci, recall_ci=rec_ci, f1_ci=f1_ci,
        n_samples=len(y_true), confusion=cm,
    )


def _bootstrap_ci(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    metric_fn,
    n_bootstrap: int,
    ci: float,
    seed: int,
) -> tuple[float, float]:
    """Compute bootstrap confidence interval for a metric."""
    rng = np.random.default_rng(seed)
    n = len(y_true)
    samples = []

    for _ in range(n_bootstrap):
        idx = rng.choice(n, size=n, replace=True)
        try:
            val = metric_fn(y_true[idx], y_pred[idx], zero_division=0)
        except Exception:
            continue
        samples.append(val)

    if not samples:
        return (0.0, 0.0)

    alpha = (1 - ci) / 2
    lower = float(np.percentile(samples, alpha * 100))
    upper = float(np.percentile(samples, (1 - alpha) * 100))
    return (lower, upper)


def per_category_f1(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    categories: np.ndarray,
) -> dict[str, float]:
    """Compute F1-score for each category.

    Args:
        y_true: Ground truth binary labels.
        y_pred: Predicted binary labels.
        categories: Category label for each sample.

    Returns:
        Dict of category -> F1 score.
    """
    results = {}
    for cat in np.unique(categories):
        mask = categories == cat
        if mask.sum() == 0:
            continue
        results[cat] = float(f1_score(y_true[mask], y_pred[mask], zero_division=0))
    return results


# ── Statistical testing ──────────────────────────────────────────

def paired_comparison(
    dualtier_scores: np.ndarray,
    baseline_scores: dict[str, np.ndarray],
    alpha: float = 0.05,
) -> dict[str, dict]:
    """Paired t-test with Bonferroni correction.

    Compares the dual-tier system against each baseline.

    Args:
        dualtier_scores: Per-sample metric values for dual-tier.
        baseline_scores: Dict of baseline_name -> per-sample metric values.
        alpha: Family-wise significance level.

    Returns:
        Dict of baseline_name -> {t_stat, p_value, corrected_p, significant, diff_mean, diff_ci}.
    """
    n_comparisons = len(baseline_scores)
    corrected_alpha = alpha / n_comparisons  # Bonferroni

    results = {}
    for name, baseline in baseline_scores.items():
        stat, p_value = ttest_rel(dualtier_scores, baseline)
        diff = dualtier_scores - baseline
        diff_mean = float(np.mean(diff))

        # Bootstrap CI on the difference.
        rng = np.random.default_rng(42)
        boot_diffs = []
        for _ in range(1000):
            idx = rng.choice(len(diff), size=len(diff), replace=True)
            boot_diffs.append(np.mean(diff[idx]))
        diff_ci = (float(np.percentile(boot_diffs, 2.5)),
                   float(np.percentile(boot_diffs, 97.5)))

        results[name] = {
            "t_stat": float(stat),
            "p_value": float(p_value),
            "corrected_alpha": corrected_alpha,
            "significant": p_value < corrected_alpha,
            "diff_mean": diff_mean,
            "diff_ci": diff_ci,
        }

    return results


# ── Cost model ───────────────────────────────────────────────────

def compute_cost(
    escalation_flags: np.ndarray,
    cost_per_cloud: float = 0.0001,  # $0.10 / 1000 submissions
) -> CostResult:
    """Compute the cost metrics for the dual-tier system.

    Args:
        escalation_flags: Boolean array (True = escalated to Tier 2).
        cost_per_cloud: Cost per cloud-processed submission.

    Returns:
        CostResult with escalation rate, costs, and savings.
    """
    n = len(escalation_flags)
    n_escalated = int(np.sum(escalation_flags))
    rho = n_escalated / n if n > 0 else 0.0

    total_cost = n_escalated * cost_per_cloud
    baseline_cost = n * cost_per_cloud  # Cloud-only baseline
    savings = 1 - (total_cost / baseline_cost) if baseline_cost > 0 else 0.0

    return CostResult(
        total_submissions=n,
        escalation_rate=rho,
        escalated_count=n_escalated,
        cost_per_submission=total_cost / n if n > 0 else 0.0,
        total_cost=total_cost,
        baseline_cost=baseline_cost,
        savings_pct=savings * 100,
    )


# ── Latency ──────────────────────────────────────────────────────

def compute_latency(latencies_ms: np.ndarray) -> LatencyResult:
    """Compute latency percentile statistics.

    Args:
        latencies_ms: Array of latency measurements in milliseconds.

    Returns:
        LatencyResult with p50, p95, p99, mean, std.
    """
    latencies_ms = np.asarray(latencies_ms, dtype=float)
    return LatencyResult(
        p50=float(np.percentile(latencies_ms, 50)),
        p95=float(np.percentile(latencies_ms, 95)),
        p99=float(np.percentile(latencies_ms, 99)),
        mean=float(np.mean(latencies_ms)),
        std=float(np.std(latencies_ms)),
        n_samples=len(latencies_ms),
    )


# ── Reporting ────────────────────────────────────────────────────

def format_report(
    metrics: MetricsResult,
    cost: CostResult | None = None,
    latency: LatencyResult | None = None,
    per_cat: dict[str, float] | None = None,
) -> str:
    """Format evaluation results as a human-readable report."""
    lines = [
        "=" * 60,
        "EVALUATION REPORT",
        "=" * 60,
        "",
        f"Samples: {metrics.n_samples}",
        f"Precision: {metrics.precision:.3f}  (95% CI: [{metrics.precision_ci[0]:.3f}, {metrics.precision_ci[1]:.3f}])",
        f"Recall:    {metrics.recall:.3f}  (95% CI: [{metrics.recall_ci[0]:.3f}, {metrics.recall_ci[1]:.3f}])",
        f"F1-score:  {metrics.f1:.3f}  (95% CI: [{metrics.f1_ci[0]:.3f}, {metrics.f1_ci[1]:.3f}])",
        "",
        "Confusion Matrix:",
        f"  TN={metrics.confusion[0][0]}  FP={metrics.confusion[0][1]}",
        f"  FN={metrics.confusion[1][0]}  TP={metrics.confusion[1][1]}",
    ]

    if per_cat:
        lines.extend(["", "Per-category F1:"])
        for cat, f1_val in sorted(per_cat.items()):
            lines.append(f"  {cat}: {f1_val:.3f}")

    if cost:
        lines.extend([
            "",
            f"Escalation rate: {cost.escalation_rate:.2%} ({cost.escalated_count}/{cost.total_submissions})",
            f"Total cost: ${cost.total_cost:.4f}",
            f"Baseline cost: ${cost.baseline_cost:.4f}",
            f"Savings: {cost.savings_pct:.1f}%",
        ])

    if latency:
        lines.extend([
            "",
            f"Latency (ms): p50={latency.p50:.0f}  p95={latency.p95:.0f}  p99={latency.p99:.0f}",
            f"  mean={latency.mean:.0f}  std={latency.std:.0f}  n={latency.n_samples}",
        ])

    lines.append("=" * 60)
    return "\n".join(lines)
