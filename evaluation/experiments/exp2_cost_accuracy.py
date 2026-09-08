"""Experiment 2: Cost-Accuracy Trade-offs (Tests H2, H3).

Compares four configurations:
  (a) Local-only — Tier 1 only
  (b) Cloud-only — Tier 2 on every submission
  (c) Hybrid-static — always both tiers
  (d) Dual-tier — proposed gated pipeline

Metrics: Precision, Recall, F1, per-category F1, cost, latency.
Statistical test: Paired t-test with Bonferroni correction.

Note (2026-07-03): the dual-tier configuration is loaded from an existing
`run_evaluation.py` output CSV rather than re-simulated here. An earlier
version of this script re-simulated gating inline with hardcoded
tau_low=0.25/tau_high=0.75 -- stale values that don't reflect
settings.TAU_HIGH after retuning (see evaluation/reports/01_tier2_bugfix_and_retuning.md).
Re-simulating gating is also just a second, less trustworthy implementation
of logic that already exists and is tested in app.services.detection_pipeline.
Run `python -m evaluation.run_evaluation --split test --output <path>` first,
then pass that path via --dual-tier-csv.
"""

import csv
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

import numpy as np

from baselines.local_only import run_local_only
from baselines.cloud_only import run_cloud_only
from baselines.hybrid_static import run_hybrid_static
from metrics import (
    compute_metrics,
    per_category_f1,
    paired_comparison,
    compute_cost,
    compute_latency,
    format_report,
)


def _json_default(o):
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    return str(o)


def load_labels(data_dir: str) -> dict:
    """Load labels keyed by filename, matching the real dataset schema
    (filename/category/is_plagiarised/source_ref/dataset/task -- see
    evaluation/reports/00_dataset_reconciliation.md)."""
    labels = {}
    with open(os.path.join(data_dir, "labels.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            labels[row["filename"]] = {
                "category": row["category"],
                "plagiarism": int(row["is_plagiarised"]),
            }
    return labels


def _leaked_submission_basenames(data_dir: str) -> set[str]:
    """Filenames in sources/ that are actually duplicates of real submissions
    (bare filename with the cs_/pb_ split-prefix stripped), not genuine
    independent reference documents -- see run_evaluation.py's identical
    helper and evaluation/reports/00_dataset_reconciliation.md's addendum."""
    leaked = set()
    for fname in os.listdir(os.path.join(data_dir, "submissions")):
        for prefix in ("cs_", "pb_"):
            if fname.startswith(prefix):
                leaked.add(fname[len(prefix):])
                break
    return leaked


def load_sources(data_dir: str) -> list[dict]:
    """Load the source corpus (same corpus run_evaluation.py indexes) so
    baseline comparisons are tested against the same reference set as the
    dual-tier numbers being compared against. Excludes files that are
    actually duplicates of real submissions (see _leaked_submission_basenames)."""
    leaked = _leaked_submission_basenames(data_dir)
    sources_dir = os.path.join(data_dir, "sources")
    corpus = []
    for fname in os.listdir(sources_dir):
        if not fname.endswith(".txt") or fname in leaked:
            continue
        path = os.path.join(sources_dir, fname)
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read().strip()
        if text:
            corpus.append({"id": fname, "text": text})
    return corpus


def load_submissions(data_dir: str, split: str, labels: dict) -> list[dict]:
    split_path = os.path.join(data_dir, "splits", f"{split}.csv")
    sub_dir = os.path.join(data_dir, "submissions")
    submissions = []
    with open(split_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            fname = row["filename"]
            path = os.path.join(sub_dir, fname)
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8", errors="replace") as sf:
                text = sf.read().strip()
            if not text:
                continue
            submissions.append({
                "id": fname,
                "text": text,
                **labels.get(fname, {"category": "unknown", "plagiarism": 0}),
            })
    return submissions


def load_dual_tier_from_csv(csv_path: str) -> list[dict]:
    """Load an already-run dual-tier evaluation (run_evaluation.py output)."""
    results = []
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            results.append({
                "id": row["filename"],
                "category": row["category"],
                "plagiarism": int(row["true"]),
                "score": float(row["score"]),
                "predicted": int(row["pred"]),
                "latency_ms": float(row["latency_ms"]),
                "escalated": row["escalated"] == "True",
            })
    return results


def run_experiment(
    data_dir: str = "data",
    threshold: float = 0.5,
    alpha: float = 0.6,
    split: str = "test",
    dual_tier_csv: str | None = None,
):
    """Run Experiment 2: Cost-Accuracy Trade-offs."""
    print("=" * 60)
    print("EXPERIMENT 2: Cost-Accuracy Trade-offs")
    print("=" * 60)

    labels = load_labels(data_dir)
    corpus = load_sources(data_dir)
    submissions = load_submissions(data_dir, split, labels)
    print(f"Corpus (sources): {len(corpus)}, {split} submissions: {len(submissions)}")

    id_to_true = {s["id"]: s["plagiarism"] for s in submissions}
    id_to_cat = {s["id"]: s["category"] for s in submissions}

    configs = {}

    print("\n--- (a) Local-only ---")
    configs["local_only"] = run_local_only(corpus, submissions, threshold=threshold)

    print("\n--- (b) Cloud-only ---")
    configs["cloud_only"] = run_cloud_only(corpus, submissions, threshold=threshold, alpha=alpha)

    print("\n--- (c) Hybrid-static ---")
    configs["hybrid_static"] = run_hybrid_static(corpus, submissions, threshold=threshold, alpha=alpha)

    print("\n--- (d) Dual-tier (real pipeline) ---")
    if dual_tier_csv and os.path.exists(dual_tier_csv):
        dt_full = load_dual_tier_from_csv(dual_tier_csv)
        dt_by_id = {r["id"]: r for r in dt_full}
        configs["dual_tier"] = [dt_by_id[s["id"]] for s in submissions if s["id"] in dt_by_id]
        missing = [s["id"] for s in submissions if s["id"] not in dt_by_id]
        if missing:
            print(f"WARNING: {len(missing)} submissions missing from dual-tier CSV: {missing}")
    else:
        raise SystemExit(
            "No --dual-tier-csv provided (or file not found). Run "
            "`python -m evaluation.run_evaluation --split "
            f"{split} --output <path>` first, then pass that path here. "
            "Dual-tier is intentionally NOT re-simulated inline -- see module "
            "docstring."
        )

    # Compute metrics for each, aligning y_true/category to each config's own id order.
    all_metrics = {}
    for name, results in configs.items():
        yt = np.array([id_to_true[r["id"]] for r in results])
        cat = np.array([id_to_cat[r["id"]] for r in results])
        yp = np.array([r["predicted"] for r in results])

        m = compute_metrics(yt, yp)
        pc = per_category_f1(yt, yp, cat)
        lat = compute_latency(np.array([r["latency_ms"] for r in results]))
        escalation = np.array([r.get("escalated", name in ("cloud_only", "hybrid_static")) for r in results])
        cost = compute_cost(escalation)

        all_metrics[name] = {"metrics": m, "per_cat": pc, "latency": lat, "cost": cost, "y_true": yt, "y_pred": yp}
        print(f"\n{name}:")
        print(format_report(m, cost, lat, pc))

    # Statistical comparison: paired t-test on per-submission correctness.
    print("\n--- Paired t-tests (Dual-tier vs baselines, Bonferroni-corrected) ---")
    dt_yt = all_metrics["dual_tier"]["y_true"]
    dt_yp = all_metrics["dual_tier"]["y_pred"]
    dualtier_scores = (dt_yp == dt_yt).astype(float)

    baseline_scores = {}
    for name in ["local_only", "cloud_only", "hybrid_static"]:
        yt = all_metrics[name]["y_true"]
        yp = all_metrics[name]["y_pred"]
        baseline_scores[name] = (yp == yt).astype(float)

    comparisons = paired_comparison(dualtier_scores, baseline_scores)
    for name, comp in comparisons.items():
        sig = "SIGNIFICANT" if comp["significant"] else "not significant"
        print(f"  vs {name}: diff={comp['diff_mean']:.3f} CI={comp['diff_ci']}, "
              f"t={comp['t_stat']:.3f}, p={comp['p_value']:.4f}, "
              f"corrected_alpha={comp['corrected_alpha']:.4f} ({sig})")

    # Save results.
    output_path = os.path.join(os.path.dirname(__file__), "exp2_results.json")
    summary = {}
    for name, data in all_metrics.items():
        n = len(data["y_true"])
        summary[name] = {
            "f1": data["metrics"].f1,
            "precision": data["metrics"].precision,
            "recall": data["metrics"].recall,
            "f1_ci": list(data["metrics"].f1_ci),
            "per_category_f1": data["per_cat"],
            "escalation_rate": data["cost"].escalation_rate,
            "cost_per_1000": data["cost"].total_cost * (1000 / max(n, 1)),
            "latency_p50": data["latency"].p50,
            "latency_p95": data["latency"].p95,
            "latency_p99": data["latency"].p99,
        }
    summary["paired_tests_vs_dual_tier"] = comparisons
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=_json_default)
    print(f"\nResults saved to {output_path}")

    try:
        from plots import plot_configuration_comparison
        config_names = ["local_only", "cloud_only", "hybrid_static", "dual_tier"]
        f1s = [all_metrics[c]["metrics"].f1 for c in config_names]
        f1_cis = [all_metrics[c]["metrics"].f1_ci for c in config_names]
        costs = [summary[c]["cost_per_1000"] for c in config_names]
        plot_configuration_comparison(config_names, f1s, f1_cis, costs)
        print("Plots saved to evaluation/figures/")
    except Exception as exc:
        print(f"Plot generation skipped ({exc}) -- numeric results above are unaffected.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--split", default="test")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--alpha", type=float, default=0.6)
    parser.add_argument(
        "--dual-tier-csv",
        default=None,
        help="Path to a run_evaluation.py output CSV for the same split.",
    )
    args = parser.parse_args()

    run_experiment(args.data_dir, args.threshold, args.alpha, args.split, args.dual_tier_csv)
