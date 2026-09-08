"""Unit tests for the full detection pipeline.

Mocks the embedding service to avoid requiring sentence-transformers/torch
for fast unit testing. Use `pytest -m slow` separately for full integration tests.
"""

import pytest
from unittest.mock import patch, MagicMock
import numpy as np

from app.services.detection_pipeline import (
    run_detection,
    index_document,
    get_fingerprint_index,
    get_bm25_index,
    get_faiss_index,
    get_tier1_detector,
    get_tier2_detector,
    PipelineResult,
)
from app.services.gating import GateDecision, GateResult


def _mock_encode_texts(texts, batch_size=32):
    """Return random 384-dim normalized vectors."""
    rng = np.random.default_rng(42)
    emb = rng.random((len(texts), 384)).astype(np.float32)
    norms = np.linalg.norm(emb, axis=1, keepdims=True)
    return emb / norms


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset pipeline singletons between tests."""
    import app.services.detection_pipeline as dp
    dp._fingerprint_index = None
    dp._bm25_index = None
    dp._faiss_index = None
    dp._tier1 = None
    dp._tier2 = None
    yield


@pytest.fixture
def indexed_corpus():
    """Index a small corpus (mocking embeddings).

    Note: index_document() only adds to BM25 + FAISS because the pipeline
    assumes fingerprints were already inserted during detect(). For testing,
    we also call fp_index.submit() to populate the fingerprint index.
    """
    source1 = (
        "Machine learning is a subset of artificial intelligence that provides "
        "systems the ability to automatically learn and improve from experience "
        "without being explicitly programmed. Machine learning focuses on the "
        "development of computer programs that can access data and use it to "
        "learn for themselves."
    )
    source2 = (
        "Cloud computing is the delivery of computing services including servers, "
        "storage, databases, networking, software, analytics, and intelligence "
        "over the Internet to offer faster innovation, flexible resources, and "
        "economies of scale."
    )
    with patch("app.services.tier2_detector.encode_texts", side_effect=_mock_encode_texts):
        # Populate fingerprint index (normally done during detect())
        fp_idx = get_fingerprint_index()
        fp_idx.submit("source1", source1)
        fp_idx.submit("source2", source2)
        # Populate BM25 + FAISS
        index_document("source1", source1)
        index_document("source2", source2)
    return {"source1": source1, "source2": source2}


class TestSingletons:
    def test_fingerprint_index_singleton(self):
        idx1 = get_fingerprint_index()
        idx2 = get_fingerprint_index()
        assert idx1 is idx2

    def test_bm25_index_singleton(self):
        idx1 = get_bm25_index()
        idx2 = get_bm25_index()
        assert idx1 is idx2

    def test_faiss_index_singleton(self):
        idx1 = get_faiss_index()
        idx2 = get_faiss_index()
        assert idx1 is idx2

    def test_tier1_detector_singleton(self):
        d1 = get_tier1_detector()
        d2 = get_tier1_detector()
        assert d1 is d2

    def test_tier2_detector_singleton(self):
        d1 = get_tier2_detector()
        d2 = get_tier2_detector()
        assert d1 is d2


class TestRunDetection:
    def test_returns_pipeline_result(self, indexed_corpus):
        with patch("app.services.tier2_detector.encode_texts", side_effect=_mock_encode_texts):
            result = run_detection("test1", "completely original text about cooking")
        assert isinstance(result, PipelineResult)

    def test_original_text_not_plagiarised(self, indexed_corpus):
        original = (
            "Quantum computing uses quantum mechanical phenomena such as "
            "superposition and entanglement to perform operations on data. "
            "A quantum computer operates on qubits."
        )
        with patch("app.services.tier2_detector.encode_texts", side_effect=_mock_encode_texts):
            result = run_detection("original1", original)
        assert result.is_plagiarised is False
        assert result.gate_decision == GateDecision.TIER1_ORIGINAL.value

    def test_verbatim_copy_detected(self, indexed_corpus):
        with patch("app.services.tier2_detector.encode_texts", side_effect=_mock_encode_texts):
            result = run_detection("copy1", indexed_corpus["source1"])
        assert result.tier1_score > 0.5

    def test_score_bounded(self, indexed_corpus):
        with patch("app.services.tier2_detector.encode_texts", side_effect=_mock_encode_texts):
            result = run_detection("test", "any random text")
        assert 0.0 <= result.final_score <= 1.0
        assert 0.0 <= result.tier1_score <= 1.0

    def test_escalation_sets_tier2_score(self, indexed_corpus):
        partial = (
            "Machine learning provides systems the ability to learn. "
            "It focuses on computer programs. "
            "But this also talks about cooking and gardening and other things."
        )
        with patch("app.services.tier2_detector.encode_texts", side_effect=_mock_encode_texts):
            result = run_detection("partial1", partial)
        if result.escalated:
            assert result.tier2_score is not None
        else:
            assert result.tier2_score is None


class TestStructuralConfirmation:
    """Tests for the structural (stopword-skeleton) confirmation signal's
    wiring into run_detection(). Per test_pipeline.py's own established
    limitation, _mock_encode_texts returns seeded-random vectors with no
    controllable relationship to a target fused score, so these tests
    mock maybe_structural_confirm itself (and force the gate decision)
    rather than trying to organically drive a real score into the narrow
    verify band -- see structural_detector's own test_structural_detector.py
    for the real scoring logic's tests.
    """

    def test_structural_confirm_called_when_escalated_and_not_yet_plagiarised(self, indexed_corpus, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "STRUCTURAL_ENABLED", True)
        forced_gate = GateResult(decision=GateDecision.ESCALATE_TO_TIER2, confidence=0.5, reason="forced for test")
        with patch("app.services.detection_pipeline.route", return_value=forced_gate), \
             patch("app.services.detection_pipeline.maybe_structural_confirm", return_value=(True, 0.42)) as mock_confirm, \
             patch("app.services.tier2_detector.encode_texts", side_effect=_mock_encode_texts):
            result = run_detection("struct_test1", "some submission text about nothing in particular")

        assert mock_confirm.called
        assert result.structural_confirmed is True
        assert result.structural_score == 0.42
        assert result.is_plagiarised is True

    def test_structural_confirm_not_called_when_tier2_already_confirms(self, indexed_corpus, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "STRUCTURAL_ENABLED", True)
        # Force any tier2 score to exceed tau_high, so is_plagiarised is
        # already True before the structural branch is reached.
        monkeypatch.setattr(settings, "TAU_HIGH", -1.0)
        forced_gate = GateResult(decision=GateDecision.ESCALATE_TO_TIER2, confidence=0.5, reason="forced for test")
        with patch("app.services.detection_pipeline.route", return_value=forced_gate), \
             patch("app.services.detection_pipeline.maybe_structural_confirm") as mock_confirm, \
             patch("app.services.tier2_detector.encode_texts", side_effect=_mock_encode_texts):
            result = run_detection("struct_test2", "some submission text")

        mock_confirm.assert_not_called()
        assert result.is_plagiarised is True
        assert result.structural_confirmed is False
        assert result.structural_score is None

    def test_structural_disabled_never_calls_confirm(self, indexed_corpus, monkeypatch):
        """Kill-switch test: STRUCTURAL_ENABLED=False must make behavior
        byte-identical to pre-feature, not just 'usually skip'."""
        from app.config import settings
        monkeypatch.setattr(settings, "STRUCTURAL_ENABLED", False)
        forced_gate = GateResult(decision=GateDecision.ESCALATE_TO_TIER2, confidence=0.5, reason="forced for test")
        with patch("app.services.detection_pipeline.route", return_value=forced_gate), \
             patch("app.services.detection_pipeline.maybe_structural_confirm") as mock_confirm, \
             patch("app.services.tier2_detector.encode_texts", side_effect=_mock_encode_texts):
            result = run_detection("struct_test3", "some submission text")

        mock_confirm.assert_not_called()
        assert result.structural_confirmed is False
        assert result.structural_score is None

    def test_structural_confirm_receives_chunk_text_not_whole_document(self, monkeypatch, tmp_path):
        """Regression guard for the chunk-anchoring fix (Report 04 Addendum
        6/7): match_text must be the SPECIFIC matched chunk's text, not the
        whole source document -- a whole-document fallback is exactly what
        regressed source-matching precision before this fix. Uses a
        multi-chunk source document (small CHUNK_SIZE) so a single-chunk
        fixture couldn't hide a regression back to whole-document text by
        coincidence.

        Note: _mock_encode_texts is a fixed-seed RNG with no relationship
        to text content, so it can't be relied on to make a SPECIFIC chunk
        (e.g. "the second one") win by semantic similarity -- only that
        SOME single chunk wins, which is all this test needs to assert.

        Uses an isolated FAISSIndex (see test_tier2.py's identical fix):
        get_faiss_index()'s default singleton loads the shared
        /tmp/test_faiss_index.faiss file, which persists vectors across
        the WHOLE test session (not just this file) -- this test asserts
        exact chunk-index behavior, which the leaked prior vectors were
        found to break in practice, not just in theory.
        """
        import app.services.detection_pipeline as dp
        from app.config import settings
        from app.services.faiss_service import FAISSIndex
        monkeypatch.setattr(settings, "STRUCTURAL_ENABLED", True)
        monkeypatch.setattr(settings, "CHUNK_SIZE", 8)
        monkeypatch.setattr(settings, "CHUNK_OVERLAP", 0)
        dp._faiss_index = FAISSIndex(index_path=str(tmp_path / "isolated.faiss"))

        source_text = (
            "This is the first chunk about apples and oranges in the source. "
            "This is the second chunk about bananas and grapes in the source. "
            "This is the third chunk about mangoes and kiwis in the source."
        )
        submission_text = "This is the second chunk about bananas and grapes in the submission."

        with patch("app.services.tier2_detector.encode_texts", side_effect=_mock_encode_texts):
            fp_idx = get_fingerprint_index()
            fp_idx.submit("multi_chunk_source", source_text)
            index_document("multi_chunk_source", source_text)

        forced_gate = GateResult(decision=GateDecision.ESCALATE_TO_TIER2, confidence=0.5, reason="forced for test")
        with patch("app.services.detection_pipeline.route", return_value=forced_gate), \
             patch("app.services.detection_pipeline.maybe_structural_confirm", return_value=(False, 0.1)) as mock_confirm, \
             patch("app.services.tier2_detector.encode_texts", side_effect=_mock_encode_texts):
            result = run_detection("struct_test4", submission_text)

        assert mock_confirm.called
        call_args = mock_confirm.call_args[0]
        # (tier2_score, submission_text, match_text, tau_high, tau_verify, threshold, n)
        match_text_arg = call_args[2]
        assert match_text_arg is not None
        assert match_text_arg != source_text, "must not fall back to whole-document text"
        assert result.matched_segment is not None
        assert match_text_arg == result.matched_segment.source_text

    def test_structural_confirm_skipped_when_no_chunk_pair_available(self, monkeypatch):
        """No dense chunk pair -> skip the structural check entirely, never
        fall back to whole-document text (Q3's "skip, don't fall back"
        decision)."""
        from app.config import settings
        monkeypatch.setattr(settings, "STRUCTURAL_ENABLED", True)

        bm25_only_text = "Distinctive bm25-only content that is never indexed into FAISS at all."
        with patch("app.services.tier2_detector.encode_texts", side_effect=_mock_encode_texts):
            get_bm25_index().add_document("bm25_only_doc", bm25_only_text)

        forced_gate = GateResult(decision=GateDecision.ESCALATE_TO_TIER2, confidence=0.5, reason="forced for test")
        with patch("app.services.detection_pipeline.route", return_value=forced_gate), \
             patch("app.services.detection_pipeline.maybe_structural_confirm", return_value=(True, 0.9)) as mock_confirm, \
             patch("app.services.tier2_detector.encode_texts", side_effect=_mock_encode_texts):
            result = run_detection("struct_test5", bm25_only_text)

        if mock_confirm.called:
            # It's allowed to be called (e.g. best_match_id pointed at some
            # other, dense-indexed candidate instead) -- but if THIS
            # bm25-only doc is what won, match_text must be None, not a
            # whole-document fallback.
            if result.best_match_id == "bm25_only_doc":
                call_args = mock_confirm.call_args[0]
                assert call_args[2] is None
        assert result.matched_segment is None or result.best_match_id != "bm25_only_doc"

    def test_matched_segment_none_on_tier1_only_resolution(self, indexed_corpus):
        """Tier-1-only resolutions never get a matched_segment -- Winnowing
        has no recoverable positional information (see the escalate
        branch's comment in detection_pipeline.py for why)."""
        forced_gate = GateResult(decision=GateDecision.TIER1_PLAGIARISED, confidence=0.9, reason="forced for test")
        with patch("app.services.detection_pipeline.route", return_value=forced_gate):
            result = run_detection("struct_test6", "some submission text")

        assert result.escalated is False
        assert result.matched_segment is None

    def test_matched_segment_populated_on_real_escalated_match(self, indexed_corpus):
        """A real (non-mocked-confirm) escalated detection against an
        indexed multi-word source should populate matched_segment with
        sensible, non-empty text on both sides."""
        forced_gate = GateResult(decision=GateDecision.ESCALATE_TO_TIER2, confidence=0.5, reason="forced for test")
        with patch("app.services.detection_pipeline.route", return_value=forced_gate), \
             patch("app.services.tier2_detector.encode_texts", side_effect=_mock_encode_texts):
            result = run_detection("struct_test7", indexed_corpus["source1"])

        assert result.matched_segment is not None
        assert result.matched_segment.source_text
        assert result.matched_segment.submitted_text
        assert result.matched_segment.source_offset[1] > result.matched_segment.source_offset[0]
        assert result.matched_segment.submitted_offset[1] > result.matched_segment.submitted_offset[0]


class TestIndexDocument:
    def test_index_increments_corpus(self):
        with patch("app.services.tier2_detector.encode_texts", side_effect=_mock_encode_texts):
            index_document("doc1", "first document about testing")
        idx = get_bm25_index()
        assert idx.document_count >= 1

        with patch("app.services.tier2_detector.encode_texts", side_effect=_mock_encode_texts):
            index_document("doc2", "second document about something else")
        assert idx.document_count >= 2
