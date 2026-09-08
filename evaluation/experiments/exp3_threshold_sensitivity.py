"""Experiment 3: Threshold Sensitivity + Real-Time Demo (Tests H4, H5).

Threshold sweep:
  tau_low  in {0.20, 0.25, 0.30}
  tau_high in {0.70, 0.75, 0.80}
  9 configurations -> heatmap of (escalation rate, F1)

Real-time demonstration:
  Submit -> detect -> return within 5-second p95 latency budget.
"""

import csv
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

import numpy as np

from app.services.winnowing import FingerprintIndex
from app.services.bm25_service import BM25Index
from app.services.faiss_service import FAISSIndex
from app.services.tier1_detector import Tier1Detector
from app.services.tier2_detector import Tier2Detector
from app.services.gating import route, GateDecision

from metrics import compute_metrics, compute_latency
from plots import plot_threshold_heatmap, plot_latency_distribution


def load_data(data_dir: str):
    """Load test corpus and submissions.

    Schema note (2026-07-03): real labels.csv/splits use filename/is_plagiarised,
    not the id/plagiarism columns this previously assumed -- see
    evaluation/reports/00_dataset_reconciliation.md. Corpus is deliberately
    built from the TRAIN split's submissions (not evaluation/dataset/data/sources/,
    which run_evaluation.py and exp2 use) -- this matches Section 3.9.3's
    methodology of tuning thresholds against the frozen train/val/test split,
    a distinct design choice from the sources-based corpus used elsewhere.
    """
    labels = {}
    with open(os.path.join(data_dir, "labels.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            labels[row["filename"]] = {
                "category": row["category"],
                "plagiarism": int(row["is_plagiarised"]),
            }

    sub_dir = os.path.join(data_dir, "submissions")

    # Train corpus.
    train_ids = set()
    with open(os.path.join(data_dir, "splits", "train.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            train_ids.add(row["filename"])

    corpus = []
    for tid in train_ids:
        path = os.path.join(sub_dir, tid)
        if os.path.exists(path):
            corpus.append({"id": tid, "text": open(path, encoding="utf-8").read().strip()})

    # Test submissions.
    test_ids = set()
    with open(os.path.join(data_dir, "splits", "test.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            test_ids.add(row["filename"])

    submissions = []
    for sid in test_ids:
        path = os.path.join(sub_dir, sid)
        if os.path.exists(path):
            submissions.append({
                "id": sid,
                "text": open(path, encoding="utf-8").read().strip(),
                **labels.get(sid, {}),
            })

    return corpus, submissions


def build_shared_indexes(corpus: list[dict], alpha: float = 0.6):
    """Build the expensive, threshold-independent indexes ONCE.

    BM25Index and FAISSIndex are only ever mutated by explicit add_document()/
    index_chunks() calls (both happen only here, during corpus setup) -- never
    by a read-only detect() call -- so they're safe to build once and reuse
    across every threshold configuration in the sweep.
    """
    bm25_index = BM25Index()
    faiss_index = FAISSIndex()
    tier2 = Tier2Detector(faiss_index=faiss_index, bm25_index=bm25_index, alpha=alpha)

    for doc in corpus:
        bm25_index.add_document(doc["id"], doc["text"])
        tier2.index_chunks(doc["id"], doc["text"])

    return bm25_index, tier2


def build_fresh_tier1(corpus: list[dict], bm25_index: BM25Index) -> Tier1Detector:
    """Build a FRESH FingerprintIndex + Tier1Detector for one sweep iteration.

    Critical correctness fix (2026-07-04): Tier1Detector.detect() calls
    FingerprintIndex.submit(), which unconditionally inserts the queried
    document into the fingerprint index as a side effect ("query first,
    then insert, for future queries" -- see winnowing.py). Reusing the same
    FingerprintIndex across multiple threshold configurations (as this
    script previously did) means the FIRST configuration's test-submission
    queries poison the index with every submission's own fingerprint; from
    the SECOND configuration onward, every submission trivially
    self-matches (c1=1.0) regardless of threshold, degenerating into
    "predict everyone positive." This was caught 2026-07-04 while writing a
    similar new sweep script (exp1b_threshold_resweep.py) and traced back
    to this file too -- see evaluation/reports/04_exp3_threshold_sensitivity.md's
    2026-07-04 correction for the re-verified numbers.
    """
    fp_index = FingerprintIndex()
    for doc in corpus:
        fp_index.submit(doc["id"], doc["text"])
    return Tier1Detector(fingerprint_index=fp_index, bm25_index=bm25_index)


def run_with_thresholds(
    tier1: Tier1Detector,
    tier2: Tier2Detector,
    submissions: list[dict],
    tau_low: float,
    tau_high: float,
) -> list[dict]:
    """Run the dual-tier pipeline with specific threshold values."""
    results = []
    for sub in submissions:
        start = time.perf_counter()

        t1 = tier1.detect(sub["id"], sub["text"])
        gate = route(t1.score, tau_low, tau_high)

        escalated = gate.decision == GateDecision.ESCALATE_TO_TIER2
        final_score = t1.score

        if escalated:
            t2 = tier2.detect(sub["id"], sub["text"], bm25_results=t1.bm25_matches)
            final_score = t2.score

        predicted = int(final_score > tau_high)
        elapsed_ms = (time.perf_counter() - start) * 1000

        results.append({
            "id": sub["id"],
            "true_label": sub.get("plagiarism", 0),
            "category": sub.get("category", "unknown"),
            "score": final_score,
            "predicted": predicted,
            "escalated": escalated,
            "latency_ms": elapsed_ms,
        })

    return results


def run_experiment(data_dir: str = "data", alpha: float = 0.6):
    """Run Experiment 3: Threshold Sensitivity Analysis."""
    print("=" * 60)
    print("EXPERIMENT 3: Threshold Sensitivity + Real-Time Demo")
    print("=" * 60)

    corpus, submissions = load_data(data_dir)
    print(f"Corpus: {len(corpus)}, Test submissions: {len(submissions)}")

    print("\nBuilding shared BM25/FAISS indexes (built once, safe to reuse)...")
    bm25_index, tier2 = build_shared_indexes(corpus, alpha)

    tau_lows = [0.20, 0.25, 0.30]
    tau_highs = [0.70, 0.75, 0.80]

    y_true = np.array([s["plagiarism"] for s in submissions])

    f1_matrix = np.zeros((len(tau_lows), len(tau_highs)))
    esc_matrix = np.zeros((len(tau_lows), len(tau_highs)))

    all_results = {}

    print("\n--- Threshold sweep (9 configurations) ---")
    for i, tl in enumerate(tau_lows):
        for j, th in enumerate(tau_highs):
            tier1 = build_fresh_tier1(corpus, bm25_index)
            results = run_with_thresholds(tier1, tier2, submissions, tl, th)
            y_pred = np.array([r["predicted"] for r in results])
            escalated = np.array([r["escalated"] for r in results])

            m = compute_metrics(y_true, y_pred)
            rho = np.mean(escalated)

            f1_matrix[i, j] = m.f1
            esc_matrix[i, j] = rho

            key = f"tl={tl:.2f}_th={th:.2f}"
            all_results[key] = {"f1": m.f1, "escalation_rate": float(rho), "precision": m.precision, "recall": m.recall}

            print(f"  tau_low={tl:.2f}, tau_high={th:.2f}: F1={m.f1:.3f}, rho={rho:.2%}")

    # Find best configuration.
    best_idx = np.unravel_index(np.argmax(f1_matrix), f1_matrix.shape)
    best_tl = tau_lows[best_idx[0]]
    best_th = tau_highs[best_idx[1]]
    print(f"\nBest: tau_low={best_tl:.2f}, tau_high={best_th:.2f}, "
          f"F1={f1_matrix[best_idx]:.3f}, rho={esc_matrix[best_idx]:.2%}")

    # Constraint check: escalation rate <= 0.25.
    valid = esc_matrix <= 0.25
    if valid.any():
        masked = np.where(valid, f1_matrix, 0)
        best_constrained = np.unravel_index(np.argmax(masked), masked.shape)
        print(f"Best (rho<=0.25): tau_low={tau_lows[best_constrained[0]]:.2f}, "
              f"tau_high={tau_highs[best_constrained[1]]:.2f}, "
              f"F1={f1_matrix[best_constrained]:.3f}")

    # Real-time demo with best thresholds. Fresh tier1 per repetition for the
    # same reason as the sweep above -- otherwise repetitions 2-5 would run
    # against a self-contaminated fingerprint index from repetition 1.
    print(f"\n--- Real-time demo (5 iterations) ---")
    demo_latencies = []
    for run in range(5):
        tier1 = build_fresh_tier1(corpus, bm25_index)
        results = run_with_thresholds(tier1, tier2, submissions, best_tl, best_th)
        latencies = [r["latency_ms"] for r in results]
        demo_latencies.extend(latencies)
        lat = compute_latency(np.array(latencies))
        within_budget = lat.p95 <= 5000
        print(f"  Run {run + 1}: p95={lat.p95:.0f}ms "
              f"{'PASS' if within_budget else 'FAIL'} (budget: 5000ms)")

    overall_lat = compute_latency(np.array(demo_latencies))
    print(f"\nOverall: p50={overall_lat.p50:.0f}ms, p95={overall_lat.p95:.0f}ms, p99={overall_lat.p99:.0f}ms")

    # Generate plots.
    plot_threshold_heatmap(tau_lows, tau_highs, f1_matrix, esc_matrix)
    plot_latency_distribution(np.array(demo_latencies))

    # Save results.
    output_path = os.path.join(os.path.dirname(__file__), "exp3_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "tau_lows": tau_lows,
            "tau_highs": tau_highs,
            "f1_matrix": f1_matrix.tolist(),
            "escalation_matrix": esc_matrix.tolist(),
            "best_tau_low": best_tl,
            "best_tau_high": best_th,
            "configurations": all_results,
            "latency": {
                "p50": overall_lat.p50,
                "p95": overall_lat.p95,
                "p99": overall_lat.p99,
            },
        }, f, indent=2)
    print(f"\nResults saved to {output_path}")
    print("Plots saved to evaluation/figures/")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--alpha", type=float, default=0.6)
    args = parser.parse_args()

    run_experiment(args.data_dir, args.alpha)
