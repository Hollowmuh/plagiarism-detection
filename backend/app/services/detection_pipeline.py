"""Full detection pipeline orchestrator.

Manages singleton service instances shared across Celery worker processes.
Coordinates: extract → tier1 → gate → tier2 (if escalated) → store result → index.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.config import settings
from app.services.bm25_service import BM25Index
from app.services.faiss_service import FAISSIndex
from app.services.gating import GateDecision, route
from app.services.segment_extraction import extract_matched_segment, MatchedSegmentData
from app.services.structural_detector import maybe_structural_confirm
from app.services.tier1_detector import Tier1Detector
from app.services.tier2_detector import Tier2Detector
from app.services.winnowing import FingerprintIndex
from app.core.logging import get_logger

log = get_logger("pipeline")

# ── Singleton service instances (per worker process) ─────────────
_fingerprint_index: FingerprintIndex | None = None
_bm25_index: BM25Index | None = None
_faiss_index: FAISSIndex | None = None
_tier1: Tier1Detector | None = None
_tier2: Tier2Detector | None = None


def get_fingerprint_index() -> FingerprintIndex:
    global _fingerprint_index
    if _fingerprint_index is None:
        _fingerprint_index = FingerprintIndex(
            k=settings.WINNOW_K,
            w=settings.WINNOW_W,
        )
    return _fingerprint_index


def get_bm25_index() -> BM25Index:
    global _bm25_index
    if _bm25_index is None:
        _bm25_index = BM25Index()
    return _bm25_index


def get_faiss_index() -> FAISSIndex:
    global _faiss_index
    if _faiss_index is None:
        _faiss_index = FAISSIndex()
    return _faiss_index


def get_tier1_detector() -> Tier1Detector:
    global _tier1
    if _tier1 is None:
        _tier1 = Tier1Detector(
            fingerprint_index=get_fingerprint_index(),
            bm25_index=get_bm25_index(),
        )
    return _tier1


def get_tier2_detector() -> Tier2Detector:
    global _tier2
    if _tier2 is None:
        _tier2 = Tier2Detector(
            faiss_index=get_faiss_index(),
            bm25_index=get_bm25_index(),
            alpha=settings.ALPHA,
        )
    return _tier2


# ── Pipeline result ──────────────────────────────────────────────

class PipelineResult:
    def __init__(self):
        self.tier1_score: float = 0.0
        self.tier2_score: float | None = None
        self.final_score: float = 0.0
        self.is_plagiarised: bool = False
        self.escalated: bool = False
        self.escalation_reason: str | None = None
        self.best_match_id: str | None = None
        self.gate_decision: str = ""
        self.structural_score: float | None = None
        self.structural_confirmed: bool = False
        self.matched_segment: MatchedSegmentData | None = None


def run_detection(doc_id: str, text: str) -> PipelineResult:
    """Run the full dual-tier detection pipeline.

    Args:
        doc_id: Unique document identifier.
        text: Extracted text content.

    Returns:
        PipelineResult with all scores and the gate decision.
    """
    result = PipelineResult()
    tier1 = get_tier1_detector()

    # ── Tier 1 ────────────────────────────────────────────────
    t1 = tier1.detect(doc_id, text)
    result.tier1_score = t1.score

    # ── Gating ────────────────────────────────────────────────
    gate = route(t1.score, settings.TAU_LOW, settings.TAU_HIGH)
    result.gate_decision = gate.decision.value

    if gate.decision == GateDecision.TIER1_ORIGINAL:
        result.final_score = t1.score
        result.is_plagiarised = False
        result.best_match_id = t1.best_match_id
        log.info("pipeline_resolved_tier1", doc_id=doc_id, decision="original", score=t1.score)

    elif gate.decision == GateDecision.TIER1_PLAGIARISED:
        result.final_score = t1.score
        result.is_plagiarised = True
        result.best_match_id = t1.best_match_id
        log.info("pipeline_resolved_tier1", doc_id=doc_id, decision="plagiarised", score=t1.score)

    elif gate.decision == GateDecision.ESCALATE_TO_TIER2:
        result.escalated = True
        result.escalation_reason = gate.reason

        # ── Tier 2 ────────────────────────────────────────────
        tier2 = get_tier2_detector()
        t2 = tier2.detect(doc_id, text, bm25_results=t1.bm25_matches)
        result.tier2_score = t2.score
        result.final_score = t2.score
        result.is_plagiarised = t2.score > settings.TAU_HIGH
        result.best_match_id = t2.best_match_id

        # ── Match explanation (Tier-2-resolved detections only) ──────
        # Computed once here and reused below for structural confirmation,
        # rather than each consumer independently re-fetching/re-slicing
        # the same source text. Tier 1-only resolutions never get a
        # matched_segment -- Winnowing discards positional information
        # early (FingerprintIndex.submit() keeps only hash values) and
        # its positions wouldn't map to original char offsets anyway
        # (computed post-preprocess(), which isn't length-preserving).
        # best_submission_chunk/best_source_chunk_index are None when
        # best_match_id was never a dense (FAISS) candidate -- a BM25-only
        # winner, which the ALPHA=0.6 deployed value makes unreachable
        # within the structural verify band (see test_tier2.py's
        # TestBm25OnlyWinnerCannotReachStructuralBand).
        if t2.best_submission_chunk is not None and t2.best_source_chunk_index is not None and t2.best_match_id:
            source_text = get_bm25_index().get_text(t2.best_match_id)
            if source_text:
                result.matched_segment = extract_matched_segment(
                    t2.best_submission_chunk, source_text, t2.best_source_chunk_index,
                )

        # ── Structural confirmation (confirmation-only; never widens
        # what counts as "escalated", only whether a score that missed
        # TAU_HIGH still gets confirmed as plagiarised). Anchored to the
        # specific matched chunk pair above, not the whole document --
        # see evaluation/reports/04_exp3_threshold_sensitivity.md Addendum
        # 6/7 for why a whole-document comparison regressed source-
        # matching precision (a multiple-comparisons problem in longer
        # documents) and why chunk-anchoring fixes it. No chunk pair
        # available -> skip the check entirely (matches maybe_structural_
        # confirm's existing match_text=None no-op), never fall back to
        # whole-document text -- falling back would reintroduce the exact
        # regression this anchoring fix exists to close.
        if not result.is_plagiarised and settings.STRUCTURAL_ENABLED:
            # match_text=None (no chunk pair -> maybe_structural_confirm's
            # existing no-op path) whenever result.matched_segment wasn't
            # populated above -- never falls back to whole-document text.
            submitted_chunk_text = t2.best_submission_chunk.text if t2.best_submission_chunk else ""
            match_text = result.matched_segment.source_text if result.matched_segment else None
            confirmed, skel_score = maybe_structural_confirm(
                t2.score,
                submitted_chunk_text,
                match_text,
                settings.TAU_HIGH,
                settings.STRUCTURAL_TAU_VERIFY,
                settings.STRUCTURAL_SKELETON_THRESHOLD,
                settings.STRUCTURAL_NGRAM_N,
            )
            result.structural_score = skel_score
            result.structural_confirmed = confirmed
            if confirmed:
                result.is_plagiarised = True

        log.info(
            "pipeline_resolved_tier2",
            doc_id=doc_id,
            t1_score=t1.score,
            t2_score=t2.score,
            structural_score=result.structural_score,
            structural_confirmed=result.structural_confirmed,
            plagiarised=result.is_plagiarised,
        )

    return result


def restore_indices(documents: Iterable[tuple[str, str]]) -> dict:
    """Repopulate the detection indices from already-processed documents.

    Winnowing and BM25 exist only in process memory, and FAISS is persisted
    only every ~100 vectors, so without this a restarted worker cannot match
    new submissions against earlier ones. The database holds the text, so it
    is the source of truth. Pass only documents whose detection has completed,
    otherwise a document still awaiting detection would match itself.
    """
    fp_index = get_fingerprint_index()
    bm25_index = get_bm25_index()
    faiss_idx = get_faiss_index()
    tier2 = get_tier2_detector()

    restored = 0
    vectors_added = 0
    for doc_id, text in documents:
        if not text or not text.strip():
            continue
        fp_index.submit(doc_id, text)
        bm25_index.add_document(doc_id, text)
        if not faiss_idx.has_document(doc_id):
            vectors_added += tier2.index_chunks(doc_id, text)
        restored += 1

    if vectors_added:
        faiss_idx.save()

    log.info("indices_restored", documents=restored, faiss_vectors_added=vectors_added)
    return {"documents": restored, "faiss_vectors_added": vectors_added}


def index_document(doc_id: str, text: str) -> None:
    """Index a document in all stores for future cross-submission detection.

    Called AFTER detection.
    """
    tier1 = get_tier1_detector()
    tier2 = get_tier2_detector()
    faiss_idx = get_faiss_index()

    before = faiss_idx.total_vectors

    # BM25 (Winnowing is already indexed by tier1.detect's fp_index.submit())
    tier1.index_document(doc_id, text)

    # FAISS dense embeddings
    tier2.index_chunks(doc_id, text)

    # Persist FAISS to disk roughly every 100 vectors. Compare which
    # hundred-bucket total_vectors was in before vs. after this call,
    # rather than checking for exact equality to a multiple of 100 --
    # a single call can add several vectors at once (a multi-chunk
    # document), which can jump the count past an exact multiple of 100
    # without ever equaling it, silently skipping the save indefinitely.
    # See evaluation/reports/07_full_pipeline_audit.md, finding 5.
    after = faiss_idx.total_vectors
    if after > 0 and before // 100 != after // 100:
        faiss_idx.save()
