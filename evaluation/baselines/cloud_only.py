"""Baseline (b): Cloud-only detection — Tier 2 on every submission.

Runs embedding-based dense retrieval + BM25 hybrid fusion for every
submission, regardless of Tier 1 scores. Maximum accuracy, maximum cost.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

import numpy as np

from app.services.bm25_service import BM25Index
from app.services.embedding_service import chunk_text, encode_texts
from app.services.faiss_service import FAISSIndex
from app.services.tier2_detector import Tier2Detector


def run_cloud_only(
    corpus: list[dict],
    submissions: list[dict],
    threshold: float = 0.5,
    alpha: float = 0.6,
) -> list[dict]:
    """Run Tier 2 (dense + sparse) detection on every submission.

    Args:
        corpus: List of {"id": str, "text": str} already-indexed documents.
        submissions: List of {"id": str, "text": str} to evaluate.
        threshold: Score above which classified as plagiarised.
        alpha: Dense fusion weight.

    Returns:
        List of {"id": str, "score": float, "predicted": int, "latency_ms": float}.
    """
    import time

    bm25_index = BM25Index()
    faiss_index = FAISSIndex()
    tier2 = Tier2Detector(faiss_index=faiss_index, bm25_index=bm25_index, alpha=alpha)

    # Build corpus index.
    for doc in corpus:
        bm25_index.add_document(doc["id"], doc["text"])
        tier2.index_chunks(doc["id"], doc["text"])

    results = []
    for sub in submissions:
        start = time.perf_counter()
        t2 = tier2.detect(sub["id"], sub["text"])
        elapsed_ms = (time.perf_counter() - start) * 1000

        results.append({
            "id": sub["id"],
            "score": t2.score,
            "predicted": int(t2.score > threshold),
            "latency_ms": elapsed_ms,
            "best_match": t2.best_match_id,
        })

    return results


if __name__ == "__main__":
    print("Cloud-only baseline — run via experiment scripts")
