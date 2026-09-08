"""Experiment 1: Tier Resolution Analysis (Tests H1).

Hypothesis: Tier 1 resolution rate >= 80%.

Procedure:
  1. Run all test submissions through the dual-tier pipeline.
  2. Record which tier resolved each submission.
  3. Compute resolution rate = fraction classified at Tier 1.
  4. Report per-category breakdown.
"""

import csv
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

import numpy as np

from app.config import settings
from app.services.winnowing import FingerprintIndex
from app.services.bm25_service import BM25Index
from app.services.faiss_service import FAISSIndex
from app.services.tier1_detector import Tier1Detector
from app.services.tier2_detector import Tier2Detector
from app.services.gating import route, GateDecision


def load_test_split(data_dir: str) -> tuple[list[dict], dict[str, dict]]:
    """Load test split submissions and labels."""
    # Load labels.
    labels = {}
    with open(os.path.join(data_dir, "labels.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            labels[row["id"]] = {
                "category": row["category"],
                "plagiarism": int(row["plagiarism"]),
            }

    # Load test split IDs.
    test_ids = set()
    with open(os.path.join(data_dir, "splits", "test.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            test_ids.add(row["id"])

    # Load submissions.
    submissions = []
    sub_dir = os.path.join(data_dir, "submissions")
    for sid in test_ids:
        path = os.path.join(sub_dir, f"{sid}.txt")
        if os.path.exists(path):
            text = open(path, encoding="utf-8").read().strip()
            submissions.append({
                "id": sid,
                "text": text,
                **labels.get(sid, {}),
            })

    return submissions, labels


def run_experiment(
    data_dir: str = "data",
    tau_low: float = 0.25,
    tau_high: float = 0.75,
    alpha: float = 0.6,
):
    """Run Experiment 1: Tier Resolution Analysis."""
    print("=" * 60)
    print("EXPERIMENT 1: Tier Resolution Analysis")
    print("=" * 60)

    submissions, labels = load_test_split(data_dir)
    print(f"Loaded {len(submissions)} test submissions")

    # Build indexes from training split.
    train_ids = set()
    train_path = os.path.join(data_dir, "splits", "train.csv")
    if os.path.exists(train_path):
        with open(train_path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                train_ids.add(row["id"])

    fp_index = FingerprintIndex()
    bm25_index = BM25Index()
    faiss_index = FAISSIndex()

    tier1 = Tier1Detector(fingerprint_index=fp_index, bm25_index=bm25_index)
    tier2 = Tier2Detector(faiss_index=faiss_index, bm25_index=bm25_index, alpha=alpha)

    # Index training corpus.
    sub_dir = os.path.join(data_dir, "submissions")
    indexed = 0
    for tid in train_ids:
        path = os.path.join(sub_dir, f"{tid}.txt")
        if os.path.exists(path):
            text = open(path, encoding="utf-8").read().strip()
            fp_index.submit(tid, text)
            bm25_index.add_document(tid, text)
            tier2.index_chunks(tid, text)
            indexed += 1
    print(f"Indexed {indexed} training documents")

    # Run detection on test set.
    results = []
    for sub in submissions:
        start = time.perf_counter()

        t1 = tier1.detect(sub["id"], sub["text"])
        gate = route(t1.score, tau_low, tau_high)

        tier_resolved = "tier1"
        final_score = t1.score
        escalated = False

        if gate.decision == GateDecision.ESCALATE_TO_TIER2:
            escalated = True
            tier_resolved = "tier2"
            t2 = tier2.detect(sub["id"], sub["text"], bm25_results=t1.bm25_matches)
            final_score = t2.score

        elapsed_ms = (time.perf_counter() - start) * 1000

        results.append({
            "id": sub["id"],
            "category": sub.get("category", "unknown"),
            "true_label": sub.get("plagiarism", 0),
            "tier1_score": t1.score,
            "final_score": final_score,
            "tier_resolved": tier_resolved,
            "escalated": escalated,
            "gate_decision": gate.decision.value,
            "latency_ms": elapsed_ms,
        })

    # Analyze results.
    total = len(results)
    tier1_resolved = sum(1 for r in results if r["tier_resolved"] == "tier1")
    resolution_rate = tier1_resolved / total if total > 0 else 0

    print(f"\n--- Results ---")
    print(f"Total submissions: {total}")
    print(f"Tier 1 resolved: {tier1_resolved} ({resolution_rate:.1%})")
    print(f"Escalated to Tier 2: {total - tier1_resolved} ({1 - resolution_rate:.1%})")
    print(f"H1 (>= 80%): {'SUPPORTED' if resolution_rate >= 0.80 else 'NOT SUPPORTED'}")

    # Per-category breakdown.
    print(f"\nPer-category breakdown:")
    categories = sorted(set(r["category"] for r in results))
    for cat in categories:
        cat_results = [r for r in results if r["category"] == cat]
        cat_resolved = sum(1 for r in cat_results if r["tier_resolved"] == "tier1")
        cat_rate = cat_resolved / len(cat_results) if cat_results else 0
        print(f"  {cat}: {cat_resolved}/{len(cat_results)} = {cat_rate:.1%} resolved at Tier 1")

    # Save results.
    output_path = os.path.join(os.path.dirname(__file__), "exp1_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "resolution_rate": resolution_rate,
            "total": total,
            "tier1_resolved": tier1_resolved,
            "tau_low": tau_low,
            "tau_high": tau_high,
            "per_category": {
                cat: {
                    "total": len([r for r in results if r["category"] == cat]),
                    "tier1_resolved": sum(1 for r in results if r["category"] == cat and r["tier_resolved"] == "tier1"),
                }
                for cat in categories
            },
            "details": results,
        }, f, indent=2)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--tau-low", type=float, default=0.25)
    parser.add_argument("--tau-high", type=float, default=0.75)
    args = parser.parse_args()

    run_experiment(args.data_dir, args.tau_low, args.tau_high)
