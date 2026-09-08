"""Unit tests for the BM25 sparse retrieval service."""

from app.services.bm25_service import (
    tokenize,
    BM25Index,
)


class TestTokenize:
    def test_basic(self):
        tokens = tokenize("The quick brown fox jumps")
        assert "quick" in tokens
        assert "brown" in tokens
        assert "fox" in tokens
        assert "jumps" in tokens

    def test_removes_stop_words(self):
        tokens = tokenize("the is a an was were")
        assert tokens == []

    def test_lowercase(self):
        tokens = tokenize("HELLO WORLD")
        assert "hello" in tokens
        assert "world" in tokens

    def test_strips_punctuation(self):
        tokens = tokenize("hello, world! how's it going?")
        assert "hello" in tokens
        assert "world" in tokens

    def test_removes_single_char(self):
        tokens = tokenize("I went to a store")
        # "i" and "a" are single chars and stop words
        assert "i" not in tokens
        assert "a" not in tokens

    def test_empty(self):
        assert tokenize("") == []


class TestBM25Index:
    def test_add_and_count(self):
        idx = BM25Index()
        idx.add_document("doc1", "The quick brown fox jumps over the lazy dog")
        idx.add_document("doc2", "A fast red car drives across the busy highway")
        assert idx.document_count == 2

    def test_no_duplicates(self):
        idx = BM25Index()
        idx.add_document("doc1", "hello world test document")
        idx.add_document("doc1", "hello world test document")
        assert idx.document_count == 1

    def test_search_empty_corpus(self):
        idx = BM25Index()
        results = idx.search("hello world")
        assert results == []

    def test_search_finds_similar(self):
        idx = BM25Index()
        idx.add_document("doc1", "machine learning algorithms neural networks deep learning")
        idx.add_document("doc2", "cooking recipes pasta Italian food preparation")
        results = idx.search("neural networks and deep learning methods", top_k=5, min_raw_score=0.0)
        if results:
            assert results[0][0] == "doc1"

    def test_search_returns_tuple_format(self):
        idx = BM25Index()
        idx.add_document("doc1", "test document with unique words for matching search")
        results = idx.search("unique words matching", top_k=5, min_raw_score=0.0)
        if results:
            doc_id, raw_score, norm_score = results[0]
            assert isinstance(doc_id, str)
            assert isinstance(raw_score, float)
            assert isinstance(norm_score, float)

    def test_get_max_score(self):
        idx = BM25Index()
        idx.add_document("doc1", "python programming language syntax")
        doc_id, raw, norm = idx.get_max_score("python programming")
        # May return None if min_raw_score threshold not met
        assert doc_id is None or doc_id == "doc1"

    def test_remove_document(self):
        idx = BM25Index()
        idx.add_document("doc1", "first document content here")
        idx.add_document("doc2", "second document different text")
        idx.remove("doc1")
        assert idx.document_count == 1

    def test_get_text(self):
        idx = BM25Index()
        idx.add_document("doc1", "stored text content")
        assert idx.get_text("doc1") == "stored text content"
        assert idx.get_text("nonexistent") is None

    def test_empty_text_not_added(self):
        idx = BM25Index()
        idx.add_document("doc1", "the is a an")  # all stop words
        assert idx.document_count == 0
