"""Unit tests for the Winnowing fingerprinting service."""

import pytest
from app.services.winnowing import (
    preprocess,
    rolling_hash,
    winnow,
    document_fingerprint,
    jaccard_similarity,
    containment_similarity,
    FingerprintIndex,
)


class TestPreprocess:
    def test_lowercase(self):
        assert preprocess("HELLO") == "hello"

    def test_strips_whitespace(self):
        assert preprocess("hello world") == "helloworld"

    def test_strips_punctuation(self):
        assert preprocess("hello, world!") == "helloworld"

    def test_unicode_normalization(self):
        # NFKD decomposes accented characters
        result = preprocess("café")
        assert "e" in result

    def test_empty_string(self):
        assert preprocess("") == ""


class TestRollingHash:
    def test_basic_output_length(self):
        # n-k+1 hashes for string of length n
        text = "abcde"
        hashes = rolling_hash(text, k=3)
        assert len(hashes) == 3  # 5 - 3 + 1

    def test_too_short(self):
        assert rolling_hash("ab", k=5) == []

    def test_deterministic(self):
        h1 = rolling_hash("abcdef", k=5)
        h2 = rolling_hash("abcdef", k=5)
        assert h1 == h2

    def test_different_strings_different_hashes(self):
        h1 = rolling_hash("abcde", k=5)
        h2 = rolling_hash("fghij", k=5)
        assert h1 != h2


class TestWinnow:
    def test_empty(self):
        assert winnow([], w=4) == set()

    def test_short_sequence(self):
        # Fewer hashes than window — returns single minimum
        hashes = [5, 3, 7]
        result = winnow(hashes, w=4)
        assert len(result) == 1
        assert (3, 1) in result  # min value 3 at index 1

    def test_produces_fingerprints(self):
        hashes = [10, 5, 8, 3, 9, 2, 7, 4, 6, 1]
        result = winnow(hashes, w=4)
        assert len(result) > 0
        # All fingerprints should be from the hash list
        for h, pos in result:
            assert h == hashes[pos]

    def test_rightmost_minimum_on_tie(self):
        # Duplicate minimum: should pick rightmost
        hashes = [5, 5, 5, 5]
        result = winnow(hashes, w=4)
        assert len(result) == 1
        _, pos = list(result)[0]
        assert pos == 3  # rightmost


class TestDocumentFingerprint:
    def test_basic(self):
        text = "The quick brown fox jumps over the lazy dog"
        fp = document_fingerprint(text)
        assert len(fp) > 0

    def test_identical_documents_same_fingerprints(self):
        text = "This is a test document with enough words to generate hashes"
        fp1 = document_fingerprint(text)
        fp2 = document_fingerprint(text)
        assert fp1 == fp2

    def test_short_text_returns_empty(self):
        fp = document_fingerprint("hi")
        assert fp == set()

    def test_different_documents_different_fingerprints(self):
        fp1 = document_fingerprint("alpha beta gamma delta epsilon zeta eta")
        fp2 = document_fingerprint("one two three four five six seven eight")
        # Hash values should differ
        h1 = {h for h, _ in fp1}
        h2 = {h for h, _ in fp2}
        assert h1 != h2


class TestSimilarity:
    def test_jaccard_identical(self):
        fp = {(1, 0), (2, 1), (3, 2)}
        assert jaccard_similarity(fp, fp) == 1.0

    def test_jaccard_disjoint(self):
        fp_a = {(1, 0), (2, 1)}
        fp_b = {(3, 0), (4, 1)}
        assert jaccard_similarity(fp_a, fp_b) == 0.0

    def test_jaccard_partial(self):
        fp_a = {(1, 0), (2, 1), (3, 2)}
        fp_b = {(1, 0), (2, 1), (4, 2)}
        sim = jaccard_similarity(fp_a, fp_b)
        assert 0.0 < sim < 1.0

    def test_containment_identical(self):
        fp = {(1, 0), (2, 1), (3, 2)}
        assert containment_similarity(fp, fp) == 1.0

    def test_containment_empty_query(self):
        fp_source = {(1, 0), (2, 1)}
        assert containment_similarity(set(), fp_source) == 0.0

    def test_containment_subset(self):
        fp_query = {(1, 0), (2, 1)}
        fp_source = {(1, 0), (2, 1), (3, 2)}
        assert containment_similarity(fp_query, fp_source) == 1.0


class TestFingerprintIndex:
    def test_submit_first_document_no_matches(self):
        idx = FingerprintIndex()
        matches = idx.submit("doc1", "This is a test document with plenty of words to hash")
        assert matches == []
        assert idx.document_count == 1

    def test_submit_identical_documents_match(self):
        idx = FingerprintIndex()
        text = "The quick brown fox jumps over the lazy dog repeatedly in the text"
        idx.submit("doc1", text)
        matches = idx.submit("doc2", text)
        assert len(matches) > 0
        assert matches[0].jaccard == 1.0

    def test_submit_different_documents_no_match(self):
        idx = FingerprintIndex()
        idx.submit("doc1", "alpha bravo charlie delta echo foxtrot golf hotel india juliet")
        matches = idx.submit("doc2", "one two three four five six seven eight nine ten eleven twelve")
        assert matches == []

    def test_remove_document(self):
        idx = FingerprintIndex()
        text = "The quick brown fox jumps over the lazy dog repeatedly in the park"
        idx.submit("doc1", text)
        assert idx.document_count == 1
        idx.remove("doc1")
        assert idx.document_count == 0

    def test_get_fingerprint(self):
        idx = FingerprintIndex()
        idx.submit("doc1", "enough words here to generate some fingerprint hashes for testing")
        fp = idx.get_fingerprint("doc1")
        assert fp is not None
        assert len(fp) > 0
