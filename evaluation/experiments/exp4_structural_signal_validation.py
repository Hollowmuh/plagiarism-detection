"""Experiment 4: Real-pipeline validation of the structural confirmation
signal (evaluation/reports/04_exp3_threshold_sensitivity.md Addendums 4-6).

Unlike exp3_threshold_sensitivity.py / exp3b_peer_threshold_resweep.py
(which call Tier1Detector/Tier2Detector directly, bypassing
detection_pipeline.run_detection(), deliberately, for sweep-isolation),
this script validates the ACTUAL shipped pipeline -- run_detection()
through the real singletons, at the single fixed shipped operating point
(settings.TAU_LOW/TAU_HIGH/STRUCTURAL_*), not a swept grid. This is "does
the shipped config work," not "what's optimal."

Compares against Addendum 5's real-pipeline baseline (P=1.000, R=0.417)
-- not the feasibility prototype's own baseline (P=1.000, R=0.375), which
used a different, non-gated methodology and is documented as not directly
comparable.

Usage:
    python -m evaluation.experiments.exp4_structural_signal_validation
"""

import csv
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent.parent))  # evaluation/ for metrics.py
sys.path.insert(0, str(Path(__file__).parent))  # evaluation/experiments/ for exp3_threshold_sensitivity.py

from app.config import settings
from app.services.detection_pipeline import (
    run_detection,
    index_document,
    get_fingerprint_index,
    get_bm25_index,
)

from exp3_threshold_sensitivity import load_data
from metrics import compute_metrics


def index_corpus(corpus: list[dict], verbose: bool = False):
    """Mirror run_evaluation.py's index_sources(): populate both the
    Winnowing fingerprint index (not touched by index_document()) and
    BM25/FAISS, since corpus documents here never go through detect()."""
    fp_idx = get_fingerprint_index()
    for doc in corpus:
        if not doc["text"].strip():
            continue
        fp_idx.submit(doc["id"], doc["text"])
        index_document(doc["id"], doc["text"])
    if verbose:
        print(f"Indexed {len(corpus)} corpus documents "
              f"(fingerprint={fp_idx.document_count}, bm25={get_bm25_index().document_count})")


def main():
    print("=" * 60)
    print("EXPERIMENT 4: Structural signal — real-pipeline peer-matching validation")
    print("=" * 60)
    # Force-enable regardless of the shipped STRUCTURAL_ENABLED default
    # (False, per Addendum 6 -- see config.py) -- this script exists
    # specifically to validate the enabled path.
    settings.STRUCTURAL_ENABLED = True
    print(f"STRUCTURAL_ENABLED={settings.STRUCTURAL_ENABLED} "
          f"TAU_VERIFY={settings.STRUCTURAL_TAU_VERIFY} "
          f"SKELETON_THRESHOLD={settings.STRUCTURAL_SKELETON_THRESHOLD} "
          f"NGRAM_N={settings.STRUCTURAL_NGRAM_N}")
    print(f"TAU_LOW={settings.TAU_LOW} TAU_HIGH={settings.TAU_HIGH}")

    data_dir = os.path.join(os.path.dirname(__file__), "..", "dataset", "data")
    corpus, submissions = load_data(data_dir)
    print(f"\nCorpus (train-split submissions): {len(corpus)}")
    print(f"Test submissions: {len(submissions)}")

    print("\nIndexing corpus through the REAL pipeline singletons...")
    index_corpus(corpus, verbose=True)

    print("\nRunning real_detection() on every test submission...")
    y_true, y_pred = [], []
    structural_confirms = []
    details = []
    for sub in submissions:
        result = run_detection(sub["id"], sub["text"])
        pred = 1 if result.is_plagiarised else 0
        y_true.append(sub.get("plagiarism", 0))
        y_pred.append(pred)
        if result.structural_confirmed:
            structural_confirms.append(sub["id"])
        details.append({
            "id": sub["id"], "true": sub.get("plagiarism", 0), "pred": pred,
            "category": sub.get("category", "unknown"),
            "tier1": result.tier1_score, "tier2": result.tier2_score,
            "structural_score": result.structural_score,
            "structural_confirmed": result.structural_confirmed,
            "escalated": result.escalated,
        })

    y_true = np.array(y_true)
    y_pred = np.array(y_pred)
    m = compute_metrics(y_true, y_pred)

    print(f"\n--- Result (real pipeline, shipped operating point) ---")
    print(f"F1={m.f1:.3f} Precision={m.precision:.3f} Recall={m.recall:.3f}")
    print(f"Structural signal confirmed {len(structural_confirms)} item(s): {structural_confirms}")

    print(f"\n--- Baseline comparison ---")
    print(f"Addendum 5 real-pipeline baseline (structural disabled): P=1.000 R=0.417 F1=0.588")
    print(f"This run ({'enabled' if settings.STRUCTURAL_ENABLED else 'disabled'}): "
          f"P={m.precision:.3f} R={m.recall:.3f} F1={m.f1:.3f}")

    output_path = os.path.join(os.path.dirname(__file__), "exp4_structural_validation_results.csv")
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=details[0].keys())
        writer.writeheader()
        writer.writerows(details)
    print(f"\nDetailed results saved to {output_path}")


if __name__ == "__main__":
    main()
