"""Experiment 1b: Threshold re-sweep against the corrected (leak-free) sources corpus.

Motivation (2026-07-04): tau_low=0.25/tau_high=0.68 were tuned against a
sources/ corpus that, unknown at the time, contained 95 leaked duplicates
of Clough & Stevenson submissions (see evaluation/reports/00_dataset_
reconciliation.md's addendum). That leak inflated Tier 1 scores for every
submission with a duplicate present, which very plausibly means the
current threshold pair is no longer well-calibrated now that the corpus
is fixed (Report 02's correction: escalation rose from 15.79% to 52.63%).

This does NOT re-simulate gating -- it calls the real pipeline components
(Tier1Detector, Tier2Detector, route()) directly, against the same
corrected corpus run_evaluation.py now uses, varying tau_low/tau_high.
"""

import csv
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

import numpy as np

from app.services.bm25_service import BM25Index
from app.services.faiss_service import FAISSIndex
from app.services.winnowing import FingerprintIndex
from app.services.tier1_detector import Tier1Detector
from app.services.tier2_detector import Tier2Detector
from app.services.gating import route, GateDecision

from metrics import compute_metrics
from run_evaluation import load_source_texts, DATA_DIR, SUBMISSIONS_DIR, SPLITS_DIR


def load_test_submissions() -> list[dict]:
    """Load test-split submissions with ground truth, same set Reports 02/03 use."""
    labels = {}
    with open(os.path.join(DATA_DIR, "labels.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            labels[row["filename"]] = {
                "category": row["category"],
                "plagiarism": int(row["is_plagiarised"]),
            }

    test_ids = []
    with open(os.path.join(SPLITS_DIR, "test.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            test_ids.append(row["filename"])

    submissions = []
    for fname in test_ids:
        path = os.path.join(SUBMISSIONS_DIR, fname)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read().strip()
        if not text:
            continue
        submissions.append({
            "id": fname,
            "text": text,
            **labels.get(fname, {"category": "unknown", "plagiarism": 0}),
        })
    return submissions


def build_shared_indexes(sources: dict[str, str], alpha: float = 0.6):
    """Build the expensive, threshold-independent indexes ONCE.

    BM25Index and FAISSIndex are only ever mutated by explicit add_document()/
    index_chunks() calls (both happen only here, during corpus setup) -- never
    by a read-only detect() call -- so they're safe to build once and reuse
    across every threshold configuration in the sweep.
    """
    bm25_index = BM25Index()
    faiss_index = FAISSIndex(index_path="/tmp/resweep_faiss.faiss")
    tier2 = Tier2Detector(faiss_index=faiss_index, bm25_index=bm25_index, alpha=alpha)

    for doc_id, text in sources.items():
        if not text.strip():
            continue
        bm25_index.add_document(doc_id, text)
        tier2.index_chunks(doc_id, text)

    return bm25_index, tier2


def build_fresh_tier1(sources: dict[str, str], bm25_index: BM25Index) -> Tier1Detector:
    """Build a FRESH FingerprintIndex + Tier1Detector for one sweep iteration.

    Critical correctness fix (2026-07-04): Tier1Detector.detect() calls
    FingerprintIndex.submit(), which unconditionally inserts the queried
    document into the fingerprint index as a side effect ("query first,
    then insert, for future queries" -- see winnowing.py). Reusing the same
    FingerprintIndex object across multiple threshold configurations means
    the FIRST configuration's test-submission queries poison the index with
    every submission's own fingerprint; from the SECOND configuration
    onward, every submission trivially self-matches (c1=1.0) regardless of
    threshold, degenerating into "predict everyone positive." A fresh
    FingerprintIndex (re-seeded with only the genuine corpus, not any test
    submission) is required for every threshold configuration to be a valid,
    independent measurement. BM25Index/FAISSIndex don't have this problem
    (see build_shared_indexes) and are reused as-is.
    """
    fp_index = FingerprintIndex()
    for doc_id, text in sources.items():
        if text.strip():
            fp_index.submit(doc_id, text)
    return Tier1Detector(fingerprint_index=fp_index, bm25_index=bm25_index)


def run_with_thresholds(tier1, tier2, submissions, tau_low, tau_high):
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
            "score": final_score,
            "predicted": predicted,
            "escalated": escalated,
            "latency_ms": elapsed_ms,
        })
    return results


def main():
    print("=" * 60)
    print("EXPERIMENT 1b: Threshold re-sweep (corrected sources corpus)")
    print("=" * 60)

    sources = load_source_texts()
    submissions = load_test_submissions()
    print(f"\nCorpus (leak-filtered sources): {len(sources)} docs")
    print(f"Test submissions: {len(submissions)}")

    print("\nBuilding shared BM25/FAISS indexes (built once, safe to reuse)...")
    bm25_index, tier2 = build_shared_indexes(sources)

    y_true = np.array([s["plagiarism"] for s in submissions])

    # Wider grid than the original 3x3: current tau_high=0.68 sits inside
    # this range, plus lower tau_high candidates (would let more borderline
    # true-positive Tier 1 scores resolve without escalating) and a couple
    # of tau_low variants.
    tau_lows = [0.20, 0.25, 0.30, 0.35]
    tau_highs = [0.55, 0.60, 0.65, 0.68, 0.70, 0.75]

    all_results = {}
    best = None

    print("\n--- Threshold sweep ---")
    for tl in tau_lows:
        for th in tau_highs:
            if th <= tl:
                continue
            tier1 = build_fresh_tier1(sources, bm25_index)
            results = run_with_thresholds(tier1, tier2, submissions, tl, th)
            y_pred = np.array([r["predicted"] for r in results])
            escalated = np.array([r["escalated"] for r in results])

            m = compute_metrics(y_true, y_pred)
            rho = float(np.mean(escalated))

            # Tier 1 precision: among non-escalated predictions only.
            non_esc_idx = ~escalated
            if non_esc_idx.sum() > 0:
                t1_precision = compute_metrics(
                    y_true[non_esc_idx], y_pred[non_esc_idx]
                ).precision
            else:
                t1_precision = float("nan")

            key = f"tl={tl:.2f}_th={th:.2f}"
            all_results[key] = {
                "f1": m.f1, "precision": m.precision, "recall": m.recall,
                "escalation_rate": rho, "tier1_precision": t1_precision,
            }
            print(f"  tau_low={tl:.2f}, tau_high={th:.2f}: "
                  f"F1={m.f1:.3f} P={m.precision:.3f} R={m.recall:.3f} "
                  f"rho={rho:.2%} tier1_P={t1_precision:.3f}")

            # "Best": maximize F1 subject to Tier1 precision >= 0.95
            # (Section 3.5.3's constraint) and overall precision >= the
            # current deployed operating point's precision (1.000), so we
            # don't quietly trade away the precision win just fixed.
            if t1_precision >= 0.95 and m.precision >= 0.95:
                if best is None or m.f1 > best["f1"] or (
                    m.f1 == best["f1"] and rho < best["escalation_rate"]
                ):
                    best = {"tau_low": tl, "tau_high": th, "f1": m.f1,
                             "precision": m.precision, "recall": m.recall,
                             "escalation_rate": rho, "tier1_precision": t1_precision}

    print("\n--- Current deployed operating point (tau_low=0.25, tau_high=0.68) ---")
    current = all_results.get("tl=0.25_th=0.68")
    print(json.dumps(current, indent=2))

    print("\n--- Best (subject to Tier1 precision >= 0.95 and overall precision >= 0.95) ---")
    print(json.dumps(best, indent=2))

    output_path = os.path.join(os.path.dirname(__file__), "exp1b_resweep_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "current_operating_point": current,
            "best_constrained": best,
            "all_configurations": all_results,
        }, f, indent=2)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
