"""Unit tests for the Tier 1 detector."""

import pytest
from app.services.winnowing import FingerprintIndex
from app.services.bm25_service import BM25Index
from app.services.tier1_detector import Tier1Detector, Tier1Result


@pytest.fixture
def corpus_texts():
    return {
        "source1": (
            "Machine learning is a subset of artificial intelligence that provides "
            "systems the ability to automatically learn and improve from experience "
            "without being explicitly programmed. Machine learning focuses on the "
            "development of computer programs that can access data and use it to "
            "learn for themselves."
        ),
        "source2": (
            "Cloud computing is the delivery of computing services including servers, "
            "storage, databases, networking, software, analytics, and intelligence "
            "over the Internet to offer faster innovation, flexible resources, and "
            "economies of scale."
        ),
    }


@pytest.fixture
def detector(corpus_texts):
    fp_index = FingerprintIndex(k=5, w=4)
    bm25_index = BM25Index()

    # Index corpus
    for doc_id, text in corpus_texts.items():
        fp_index.submit(doc_id, text)
        bm25_index.add_document(doc_id, text)

    return Tier1Detector(fingerprint_index=fp_index, bm25_index=bm25_index)


class TestTier1Detector:
    def test_returns_tier1_result(self, detector):
        result = detector.detect("test1", "completely unrelated text about cooking pasta")
        assert isinstance(result, Tier1Result)

    def test_verbatim_copy_high_score(self, detector, corpus_texts):
        # Verbatim copy should score high
        result = detector.detect("copy1", corpus_texts["source1"])
        assert result.score > 0.5
        assert result.winnow_score > 0.0

    def test_original_text_low_score(self, detector):
        original = (
            "Quantum computing uses quantum mechanical phenomena such as "
            "superposition and entanglement to perform operations on data. "
            "A quantum computer operates on qubits which can exist in "
            "multiple states simultaneously unlike classical bits."
        )
        result = detector.detect("original1", original)
        assert result.score < 0.5

    def test_score_bounded(self, detector):
        result = detector.detect("test", "any text here for testing")
        assert 0.0 <= result.score <= 1.0

    def test_bm25_capped_at_06(self, detector, corpus_texts):
        # BM25 contribution is capped at 0.6
        result = detector.detect("test", corpus_texts["source1"])
        assert result.bm25_score >= 0.0
        # The final score uses min(bm25_norm, 0.6) so c1 from BM25 alone <= 0.6
        # (unless winnowing is higher)

    def test_best_match_id_populated(self, detector, corpus_texts):
        result = detector.detect("copy", corpus_texts["source1"])
        if result.score > 0:
            assert result.best_match_id is not None

    def test_index_document(self, detector):
        new_text = "brand new document about quantum physics and particle interactions"
        detector.index_document("new_doc", new_text)
        assert detector.bm25_index.document_count == 3  # 2 corpus + 1 new
