"""Baseline (a): Local-only detection — Tier 1 only, no escalation.

Runs Winnowing + BM25 on every submission and applies a fixed threshold
to classify. No Tier 2 semantic analysis is used.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

import numpy as np

from app.services.winnowing import FingerprintIndex
from app.services.bm25_service import BM25Index
from app.services.tier1_detector import Tier1Detector


def run_local_only(
    corpus: list[dict],
    submissions: list[dict],
    threshold: float = 0.5,
    winnow_k: int = 5,
    winnow_w: int = 4,
) -> list[dict]:
    """Run Tier 1-only detection on all submissions.

    Args:
        corpus: List of {"id": str, "text": str} already-indexed documents.
        submissions: List of {"id": str, "text": str} to evaluate.
        threshold: Score above which a submission is classified as plagiarised.

    Returns:
        List of {"id": str, "score": float, "predicted": int, "latency_ms": float}.
    """
    import time

    fp_index = FingerprintIndex(k=winnow_k, w=winnow_w)
    bm25_index = BM25Index()
    tier1 = Tier1Detector(fingerprint_index=fp_index, bm25_index=bm25_index)

    # Build corpus index.
    for doc in corpus:
        fp_index.submit(doc["id"], doc["text"])
        bm25_index.add_document(doc["id"], doc["text"])

    results = []
    for sub in submissions:
        start = time.perf_counter()
        t1 = tier1.detect(sub["id"], sub["text"])
        elapsed_ms = (time.perf_counter() - start) * 1000

        results.append({
            "id": sub["id"],
            "score": t1.score,
            "predicted": int(t1.score > threshold),
            "latency_ms": elapsed_ms,
            "best_match": t1.best_match_id,
        })

    return results


if __name__ == "__main__":
    print("Local-only baseline — run via experiment scripts")
