"""Tier 2 detection: hybrid semantic analysis (dense + sparse fusion).

Activates only for submissions escalated by the gating function.
Combines BM25 sparse scores with FAISS dense cosine similarity
via linear interpolation: c2 = α * dense + (1-α) * sparse.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.services.bm25_service import BM25Index
from app.services.embedding_service import chunk_text, encode_texts, TextChunk
from app.services.faiss_service import FAISSIndex
from app.core.logging import get_logger

log = get_logger("tier2")


@dataclass
class Tier2Result:
    """Result of Tier 2 hybrid detection."""
    score: float                    # c2(D) — hybrid fusion score
    dense_score: float              # Best dense similarity
    sparse_score: float             # Best BM25 normalized score
    best_match_id: str | None = None
    dense_matches: list[tuple[str, float]] = field(default_factory=list)
    sparse_matches: list[tuple[str, float, float]] = field(default_factory=list)
    chunks_processed: int = 0
    # Which specific (submission chunk, source chunk) pair produced
    # best_match_id's winning dense score -- None/None when best_match_id
    # was never a dense candidate (a BM25-only winner; see detect()'s
    # dense_best_pair comment for why this is close to unreachable at the
    # deployed alpha). Lets callers recover exact matched text/offsets
    # instead of only a document-level id. See segment_extraction.py.
    best_submission_chunk: TextChunk | None = None
    best_source_chunk_index: int | None = None


class Tier2Detector:
    """Tier 2 hybrid detection engine combining dense + sparse retrieval."""

    def __init__(
        self,
        faiss_index: FAISSIndex,
        bm25_index: BM25Index,
        alpha: float = 0.6,
    ):
        self.faiss_index = faiss_index
        self.bm25_index = bm25_index
        self.alpha = alpha

    def detect(
        self,
        doc_id: str,
        text: str,
        bm25_results: list[tuple[str, float, float]] | None = None,
    ) -> Tier2Result:
        """Run Tier 2 hybrid detection on an escalated submission.

        Args:
            doc_id: Unique document identifier.
            text: Extracted text content.
            bm25_results: Optional pre-computed BM25 results from Tier 1
                         (avoids redundant computation).

        Returns:
            Tier2Result with fused confidence score.
        """
        # ── Chunk and encode the submission ───────────────────
        chunks = chunk_text(text)
        if not chunks:
            return Tier2Result(score=0.0, dense_score=0.0, sparse_score=0.0)

        chunk_texts = [c.text for c in chunks]
        embeddings = encode_texts(chunk_texts)

        # ── Dense retrieval via FAISS ─────────────────────────
        # Search with each chunk's embedding, aggregate best scores per document.
        # FAISS is indexed at chunk granularity (index_chunks() below stores IDs
        # like "doc.txt__chunk_0"), but BM25 is indexed at document granularity
        # ("doc.txt"). Must collapse chunk IDs back to their base document ID
        # here, or the later fusion's dense/sparse lookups key-mismatch and
        # every candidate silently gets a 0.0 for whichever signal it didn't
        # originate from.
        # dense_best_pair tracks, per base_id, WHICH submission chunk (its
        # index into `chunks`/`embeddings`) and WHICH source chunk (parsed
        # from the winning match_id's "__chunk_N" suffix) produced that
        # base_id's current-best dense_scores entry -- updated in lockstep
        # with dense_scores itself, never as a separate pass, so the two
        # dicts can never drift out of sync.
        dense_scores: dict[str, float] = {}
        dense_best_pair: dict[str, tuple[int, int | None]] = {}
        for sub_idx, emb in enumerate(embeddings):
            results = self.faiss_index.search(emb, top_k=50)
            for match_id, score in results:
                parts = match_id.rsplit("__chunk_", 1)
                base_id = parts[0]
                if base_id not in dense_scores or score > dense_scores[base_id]:
                    dense_scores[base_id] = score
                    src_idx = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else None
                    dense_best_pair[base_id] = (sub_idx, src_idx)

        # Sort by score
        dense_ranked = sorted(dense_scores.items(), key=lambda x: -x[1])[:100]

        # ── Sparse retrieval via BM25 ─────────────────────────
        if bm25_results is None:
            bm25_results = self.bm25_index.search(text, top_k=100)

        # ── Candidate union ───────────────────────────────────
        candidates = set()
        for match_id, _ in dense_ranked:
            candidates.add(match_id)
        for match_id, _, _ in bm25_results:
            candidates.add(match_id)

        if not candidates:
            return Tier2Result(
                score=0.0,
                dense_score=0.0,
                sparse_score=0.0,
                chunks_processed=len(chunks),
            )

        # ── Gather scores for all candidates ──────────────────
        candidate_dense = []
        candidate_sparse = []
        candidate_ids = list(candidates)

        dense_lookup = dict(dense_ranked)
        sparse_lookup = {did: norm for did, _, norm in bm25_results}

        for cid in candidate_ids:
            candidate_dense.append(dense_lookup.get(cid, 0.0))
            candidate_sparse.append(sparse_lookup.get(cid, 0.0))

        dense_arr = np.array(candidate_dense, dtype=np.float64)
        sparse_arr = np.array(candidate_sparse, dtype=np.float64)

        # Dense scores are already cosine similarity [0, 1] for normalized
        # vectors, and sparse scores are already proportionally normalized
        # (raw / saturation, capped at 1.0) by BM25Index.search(). Use both
        # directly -- do NOT re-normalize per-query with min-max, which would
        # rescale relative to the local candidate pool and inflate whichever
        # candidate happens to be locally-best to 1.0 regardless of its true
        # absolute similarity (the exact bug pattern bm25_service.py's own
        # search() docstring documents avoiding).
        dense_norm = dense_arr
        sparse_norm = sparse_arr

        # ── Linear interpolation fusion ───────────────────────
        fused = self.alpha * dense_norm + (1 - self.alpha) * sparse_norm

        # ── Best match ────────────────────────────────────────
        best_idx = int(np.argmax(fused))
        best_match_id = candidate_ids[best_idx]
        c2 = float(fused[best_idx])

        best_submission_chunk: TextChunk | None = None
        best_source_chunk_index: int | None = None
        pair = dense_best_pair.get(best_match_id)
        if pair is not None and pair[1] is not None:
            best_submission_chunk = chunks[pair[0]]
            best_source_chunk_index = pair[1]

        log.info(
            "tier2_result",
            doc_id=doc_id,
            c2=round(c2, 4),
            dense_best=round(float(dense_norm[best_idx]), 4),
            sparse_best=round(float(sparse_norm[best_idx]), 4),
            alpha=self.alpha,
            candidates=len(candidates),
            chunks=len(chunks),
        )

        return Tier2Result(
            score=c2,
            dense_score=float(dense_arr[best_idx]),
            sparse_score=float(sparse_arr[best_idx]),
            best_match_id=best_match_id,
            dense_matches=dense_ranked[:10],
            sparse_matches=bm25_results[:10],
            chunks_processed=len(chunks),
            best_submission_chunk=best_submission_chunk,
            best_source_chunk_index=best_source_chunk_index,
        )

    def index_chunks(self, doc_id: str, text: str) -> int:
        """Chunk and index a document's embeddings in FAISS.

        Args:
            doc_id: Base document ID.
            text: Full document text.

        Returns:
            Number of chunks indexed.
        """
        chunks = chunk_text(text)
        if not chunks:
            return 0

        chunk_texts = [c.text for c in chunks]
        embeddings = encode_texts(chunk_texts)

        chunk_ids = [f"{doc_id}__chunk_{c.index}" for c in chunks]
        self.faiss_index.add_batch(chunk_ids, embeddings)

        log.info("chunks_indexed", doc_id=doc_id, count=len(chunks))
        return len(chunks)
