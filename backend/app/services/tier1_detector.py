"""Tier 1 detection: local lexical analysis using Winnowing + BM25.

Computes c1(D) = max(norm(S_winnow), norm(max_bm25)).
No cloud API calls — runs entirely on local infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.bm25_service import BM25Index
from app.services.winnowing import FingerprintIndex, MatchResult as WinnowMatch
from app.core.logging import get_logger

log = get_logger("tier1")


@dataclass
class Tier1Result:
    """Result of Tier 1 detection."""
    score: float                          # c1(D) — the max of winnow and bm25 normalized
    winnow_score: float                   # Best Winnowing Jaccard
    bm25_score: float                     # Best BM25 normalized score
    best_match_id: str | None = None      # Document ID of best match
    winnow_matches: list[WinnowMatch] = field(default_factory=list)
    bm25_matches: list[tuple[str, float, float]] = field(default_factory=list)


class Tier1Detector:
    """Tier 1 detection engine combining Winnowing and BM25."""

    def __init__(
        self,
        fingerprint_index: FingerprintIndex,
        bm25_index: BM25Index,
    ):
        self.fp_index = fingerprint_index
        self.bm25_index = bm25_index

    def detect(self, doc_id: str, text: str) -> Tier1Result:
        """Run Tier 1 detection on a submission.

        Queries both indexes but does NOT insert into them.
        Insertion happens separately via index_submission.

        Args:
            doc_id: Unique document identifier.
            text: Extracted text content.

        Returns:
            Tier1Result with combined confidence score.
        """
        # ── Winnowing fingerprint matching ────────────────────
        winnow_matches = self.fp_index.submit(doc_id, text)
        # Use CONTAINMENT (not Jaccard) — measures "what fraction of
        # the query was actually copied" which is the true plagiarism
        # signal. Jaccard is symmetric and inflated by topical overlap.
        winnow_score = winnow_matches[0].containment if winnow_matches else 0.0

        # ── BM25 lexical retrieval ────────────────────────────
        bm25_results = self.bm25_index.search(text, top_k=10)
        bm25_best_norm = bm25_results[0][2] if bm25_results else 0.0

        # ── Combined Tier 1 score ─────────────────────────────
        # c1(D) = max(containment, bm25_norm)
        # BM25 contribution is capped at 0.6 so topical overlap alone
        # cannot trigger PLAGIARISED — only ESCALATE at most.
        bm25_capped = min(bm25_best_norm, 0.6)
        c1 = max(winnow_score, bm25_capped)

        # Determine best match
        best_match_id = None
        if winnow_score >= bm25_best_norm and winnow_matches:
            best_match_id = winnow_matches[0].target_id
        elif bm25_results:
            best_match_id = bm25_results[0][0]

        log.info(
            "tier1_result",
            doc_id=doc_id,
            c1=round(c1, 4),
            winnow=round(winnow_score, 4),
            bm25=round(bm25_best_norm, 4),
            best_match=best_match_id,
            corpus_size=self.bm25_index.document_count,
        )

        return Tier1Result(
            score=c1,
            winnow_score=winnow_score,
            bm25_score=bm25_best_norm,
            best_match_id=best_match_id,
            winnow_matches=winnow_matches,
            bm25_matches=bm25_results,
        )

    def index_document(self, doc_id: str, text: str) -> None:
        """Add a document to both indexes for future cross-submission detection.

        Called AFTER detection so the document is available for subsequent queries.
        Note: Winnowing submit() already inserts into the fingerprint index,
        so we only need to add to BM25 here.
        """
        self.bm25_index.add_document(doc_id, text)
        log.info(
            "document_indexed",
            doc_id=doc_id,
            bm25_corpus_size=self.bm25_index.document_count,
            fp_index_size=self.fp_index.document_count,
        )
