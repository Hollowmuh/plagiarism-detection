"""Baseline (c): Hybrid-static — always run both Tier 1 and Tier 2.

No gating function. Runs Winnowing + BM25 + embeddings + FAISS for
every submission. Uses the maximum of Tier 1 and Tier 2 scores.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

import numpy as np

from app.services.winnowing import FingerprintIndex
from app.services.bm25_service import BM25Index
from app.services.faiss_service import FAISSIndex
from app.services.tier1_detector import Tier1Detector
from app.services.tier2_detector import Tier2Detector


def run_hybrid_static(
    corpus: list[dict],
    submissions: list[dict],
    threshold: float = 0.5,
    alpha: float = 0.6,
    winnow_k: int = 5,
    winnow_w: int = 4,
) -> list[dict]:
    """Run both Tier 1 and Tier 2 on every submission (no gating).

    Args:
        corpus: List of {"id": str, "text": str} already-indexed documents.
        submissions: List of {"id": str, "text": str} to evaluate.
        threshold: Score above which classified as plagiarised.
        alpha: Dense fusion weight for Tier 2.

    Returns:
        List of result dicts with scores from both tiers.
    """
    import time

    fp_index = FingerprintIndex(k=winnow_k, w=winnow_w)
    bm25_index = BM25Index()
    faiss_index = FAISSIndex()

    tier1 = Tier1Detector(fingerprint_index=fp_index, bm25_index=bm25_index)
    tier2 = Tier2Detector(faiss_index=faiss_index, bm25_index=bm25_index, alpha=alpha)

    # Build corpus index.
    for doc in corpus:
        fp_index.submit(doc["id"], doc["text"])
        bm25_index.add_document(doc["id"], doc["text"])
        tier2.index_chunks(doc["id"], doc["text"])

    results = []
    for sub in submissions:
        start = time.perf_counter()

        t1 = tier1.detect(sub["id"], sub["text"])
        t2 = tier2.detect(sub["id"], sub["text"], bm25_results=t1.bm25_matches)

        final_score = max(t1.score, t2.score)
        elapsed_ms = (time.perf_counter() - start) * 1000

        results.append({
            "id": sub["id"],
            "tier1_score": t1.score,
            "tier2_score": t2.score,
            "score": final_score,
            "predicted": int(final_score > threshold),
            "latency_ms": elapsed_ms,
        })

    return results


if __name__ == "__main__":
    print("Hybrid-static baseline — run via experiment scripts")
