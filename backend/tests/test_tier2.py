"""Unit tests for the Tier 2 detector.

Note: These tests require sentence-transformers to be installed.
They are marked with pytest.mark.slow since embedding generation
takes time on CPU.
"""

import pytest
from app.services.bm25_service import BM25Index
from app.services.faiss_service import FAISSIndex
from app.services.tier2_detector import Tier2Detector, Tier2Result
from app.services.embedding_service import chunk_text, encode_texts


@pytest.fixture
def corpus_texts():
    return {
        "source1": (
            "Machine learning is a subset of artificial intelligence that provides "
            "systems the ability to automatically learn and improve from experience "
            "without being explicitly programmed. Machine learning focuses on the "
            "development of computer programs that can access data and use it to "
            "learn for themselves. The process begins with observations or data."
        ),
        "source2": (
            "Cloud computing is the delivery of computing services including servers, "
            "storage, databases, networking, software, analytics, and intelligence "
            "over the Internet to offer faster innovation, flexible resources, and "
            "economies of scale. You typically pay only for cloud services you use."
        ),
    }


@pytest.fixture
def tier2(corpus_texts):
    bm25_index = BM25Index()
    faiss_index = FAISSIndex()
    detector = Tier2Detector(faiss_index=faiss_index, bm25_index=bm25_index, alpha=0.6)

    for doc_id, text in corpus_texts.items():
        bm25_index.add_document(doc_id, text)
        detector.index_chunks(doc_id, text)

    return detector


@pytest.mark.slow
class TestTier2Detector:
    def test_returns_tier2_result(self, tier2):
        result = tier2.detect("test", "some short text about cooking")
        assert isinstance(result, Tier2Result)

    def test_verbatim_high_score(self, tier2, corpus_texts):
        result = tier2.detect("copy", corpus_texts["source1"])
        assert result.score > 0.3

    def test_paraphrased_detected(self, tier2):
        paraphrase = (
            "AI systems can learn from data without explicit programming. "
            "This branch of computer science creates programs that improve "
            "automatically through experience and data access."
        )
        result = tier2.detect("para", paraphrase)
        # Semantic similarity should detect this
        assert result.dense_score > 0.0

    def test_unrelated_low_score(self, tier2):
        unrelated = (
            "The history of ancient Egypt spans thousands of years, beginning "
            "with the early dynastic period around 3100 BCE and continuing "
            "through numerous kingdoms and intermediate periods."
        )
        result = tier2.detect("unrelated", unrelated)
        assert result.score < 0.5

    def test_chunks_processed_tracked(self, tier2, corpus_texts):
        result = tier2.detect("test", corpus_texts["source1"])
        assert result.chunks_processed > 0

    def test_index_chunks(self, tier2):
        new_text = (
            "Blockchain technology is a decentralized distributed ledger "
            "that records transactions across many computers. This ensures "
            "that the record cannot be altered retroactively."
        )
        count = tier2.index_chunks("blockchain_doc", new_text)
        assert count > 0

    def test_winning_pair_exposes_submission_and_source_chunk(self, tier2, corpus_texts):
        """A near-verbatim match should expose which submission chunk and
        which source chunk index produced the winning dense score, not just
        the winning document id."""
        result = tier2.detect("copy", corpus_texts["source1"])
        assert result.best_match_id == "source1"
        assert result.best_submission_chunk is not None
        assert result.best_source_chunk_index is not None
        assert result.best_source_chunk_index >= 0

    def test_bm25_only_winner_has_no_chunk_pair(self, corpus_texts, tmp_path):
        """A candidate that was only ever indexed into BM25 (never FAISS)
        can win on fused score via sparse alone, but must never expose a
        chunk pair -- it was never a dense candidate, so there's nothing
        real to point to. This is the ALPHA=0.6 "close to unreachable"
        case documented on Tier2Result -- constructed directly here rather
        than relying on it never happening in practice.

        Uses an explicit, unique index_path: FAISSIndex() with no path
        loads the shared /tmp/test_faiss_index.faiss file (conftest.py's
        override), which persists vectors added by OTHER tests in this
        same file/run -- a bare FAISSIndex() here would silently inherit
        leftover documents and defeat the "never indexed into FAISS"
        premise this test depends on.
        """
        bm25_index = BM25Index()
        faiss_index = FAISSIndex(index_path=str(tmp_path / "isolated_faiss.faiss"))
        detector = Tier2Detector(faiss_index=faiss_index, bm25_index=bm25_index, alpha=0.6)

        # Indexed into BM25 only -- deliberately never calls index_chunks(),
        # so this doc_id can never appear as a FAISS/dense candidate. A
        # second, unrelated document is also added (both to BM25 and FAISS,
        # like a real corpus) so BM25's IDF isn't degenerate on a
        # single-document corpus, and so there's a real competing dense
        # candidate the fused score must still lose to.
        distinctive_text = (
            "Xylophonic quibbleworth zantrification protocols govern the "
            "flibbergast oscillation matrices used in zanderplex assembly. "
            "Every zanderplex assembly depends on stable quibbleworth "
            "zantrification for correct flibbergast oscillation output."
        )
        bm25_index.add_document("bm25_only_doc", distinctive_text)
        bm25_index.add_document("source1", corpus_texts["source1"])
        detector.index_chunks("source1", corpus_texts["source1"])

        result = detector.detect("query", distinctive_text)
        assert result.best_match_id == "bm25_only_doc"
        assert result.best_submission_chunk is None
        assert result.best_source_chunk_index is None

    def test_winning_pair_not_first_chunk(self, tier2, corpus_texts, monkeypatch):
        """Guard against an off-by-index bug: when the winning match comes
        from a LATER chunk on either side (not chunk 0), the exposed pair
        must point at the actual winning chunks, not silently default to
        the first one."""
        from app.config import settings
        monkeypatch.setattr(settings, "CHUNK_SIZE", 8)
        monkeypatch.setattr(settings, "CHUNK_OVERLAP", 0)

        unrelated_filler = (
            "Completely unrelated filler content about gardening tools and "
            "seasonal vegetable planting schedules for temperate climates. "
        )
        submission = unrelated_filler + corpus_texts["source1"]

        result = tier2.detect("query", submission)
        assert result.best_match_id == "source1"
        assert result.best_submission_chunk is not None
        # The matching content was appended after the filler, so the
        # winning submission chunk must not be chunk index 0.
        assert result.best_submission_chunk.index > 0


class TestBm25OnlyWinnerCannotReachStructuralBand:
    def test_alpha_invariant(self):
        """Documents the load-bearing invariant behind the 'skip, don't
        fall back' decision for the no-chunk-pair case (see
        detection_pipeline.py's structural-confirm call site and
        evaluation/reports/04_exp3_threshold_sensitivity.md Addendum 6/7):
        a BM25-only candidate has dense_score=0, so its fused score can
        never reach STRUCTURAL_TAU_VERIFY at the deployed ALPHA. If this
        test ever fails, that "close to unreachable" claim no longer
        holds and the skip-vs-fallback decision needs revisiting."""
        from app.config import settings

        max_possible_fused_score_for_bm25_only = (1 - settings.ALPHA) * 1.0
        assert max_possible_fused_score_for_bm25_only < settings.STRUCTURAL_TAU_VERIFY


@pytest.mark.slow
class TestChunking:
    def test_chunk_text_basic(self):
        text = "First sentence here. Second sentence here. Third sentence here."
        chunks = chunk_text(text, max_tokens=10, overlap_tokens=2)
        assert len(chunks) >= 1
        assert chunks[0].char_start == 0

    def test_chunk_text_empty(self):
        assert chunk_text("") == []

    def test_chunk_text_positions(self):
        text = "Hello world. This is a test. Another sentence for chunking purposes."
        chunks = chunk_text(text, max_tokens=5, overlap_tokens=1)
        for chunk in chunks:
            assert chunk.char_start >= 0
            assert chunk.char_end > chunk.char_start

    def test_encode_texts(self):
        texts = ["hello world", "test sentence"]
        embeddings = encode_texts(texts)
        assert embeddings.shape == (2, 384)
        # Normalized embeddings should have unit norm
        norms = (embeddings**2).sum(axis=1) ** 0.5
        for n in norms:
            assert abs(n - 1.0) < 0.01
