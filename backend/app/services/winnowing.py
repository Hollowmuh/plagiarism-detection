"""Winnowing document fingerprinting algorithm (Schleimer et al., 2003).

Guarantees detection of any shared substring >= K + W - 1 tokens.
Default: k=5, w=4 → detects matches >= 8 characters.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from threading import RLock
from typing import TYPE_CHECKING

from app.core.logging import get_logger

log = get_logger("winnowing")

# ── Algorithm constants ──────────────────────────────────────────
DEFAULT_K = 5
DEFAULT_W = 4
BASE = 256
MOD = 10**9 + 7


# ── Preprocessing ────────────────────────────────────────────────

def preprocess(text: str) -> str:
    """Normalize text for fingerprinting.

    - Unicode NFKD normalization
    - Lowercase
    - Strip ALL whitespace and punctuation → contiguous alphanumeric stream
    """
    text = unicodedata.normalize("NFKD", text)
    text = text.lower()
    text = re.sub(r"[^a-z0-9]", "", text)
    return text


# ── Karp-Rabin rolling hash ─────────────────────────────────────

def rolling_hash(text: str, k: int = DEFAULT_K) -> list[int]:
    """Compute Karp-Rabin rolling hashes for all k-grams. O(n)."""
    n = len(text)
    if n < k:
        return []

    high_order = pow(BASE, k - 1, MOD)
    h = 0
    for i in range(k):
        h = (h * BASE + ord(text[i])) % MOD

    hashes = [h]
    for i in range(1, n - k + 1):
        h = ((h - ord(text[i - 1]) * high_order) * BASE + ord(text[i + k - 1])) % MOD
        hashes.append(h)

    return hashes


# ── Winnowing ────────────────────────────────────────────────────

def winnow(hashes: list[int], w: int = DEFAULT_W) -> set[tuple[int, int]]:
    """Select fingerprints using the Winnowing algorithm.

    Returns set of (hash_value, position) tuples.
    Rightmost minimum on tie (per original paper).
    """
    n = len(hashes)
    if n == 0:
        return set()
    if n <= w:
        min_val = min(hashes)
        min_idx = len(hashes) - 1 - hashes[::-1].index(min_val)
        return {(min_val, min_idx)}

    fingerprints: set[tuple[int, int]] = set()
    prev_min_idx = -1

    for i in range(n - w + 1):
        window = hashes[i : i + w]
        min_val = min(window)
        # Rightmost minimum
        for j in range(w - 1, -1, -1):
            if window[j] == min_val:
                min_idx = i + j
                break
        if min_idx != prev_min_idx:
            fingerprints.add((min_val, min_idx))
            prev_min_idx = min_idx

    return fingerprints


# ── Full pipeline ────────────────────────────────────────────────

def document_fingerprint(
    text: str, k: int = DEFAULT_K, w: int = DEFAULT_W
) -> set[tuple[int, int]]:
    """Complete Winnowing pipeline: preprocess → hash → winnow."""
    cleaned = preprocess(text)
    if len(cleaned) < k:
        return set()
    hashes = rolling_hash(cleaned, k)
    return winnow(hashes, w)


# ── Similarity functions ─────────────────────────────────────────

def jaccard_similarity(fp_a: set[tuple[int, int]], fp_b: set[tuple[int, int]]) -> float:
    """Jaccard similarity between two fingerprint sets."""
    ha = {h for h, _ in fp_a}
    hb = {h for h, _ in fp_b}
    union = len(ha | hb)
    if union == 0:
        return 0.0
    return len(ha & hb) / union


def containment_similarity(
    fp_query: set[tuple[int, int]], fp_source: set[tuple[int, int]]
) -> float:
    """What fraction of query's fingerprints appear in source?"""
    hq = {h for h, _ in fp_query}
    hs = {h for h, _ in fp_source}
    if not hq:
        return 0.0
    return len(hq & hs) / len(hq)


# ── Incremental Fingerprint Index ────────────────────────────────

@dataclass
class MatchResult:
    source_id: str
    target_id: str
    jaccard: float
    containment: float
    shared_hashes: int
    source_total: int
    target_total: int


class FingerprintIndex:
    """Thread-safe inverted index for real-time cross-submission detection.

    Pattern: query FIRST (find matches), then insert (for future queries).
    """

    def __init__(
        self,
        k: int = DEFAULT_K,
        w: int = DEFAULT_W,
        similarity_threshold: float = 0.15,
    ):
        self.k = k
        self.w = w
        self.threshold = similarity_threshold

        self._lock = RLock()
        self._index: dict[int, set[str]] = defaultdict(set)
        self._doc_hashes: dict[str, set[int]] = {}

    @property
    def document_count(self) -> int:
        return len(self._doc_hashes)

    def submit(self, doc_id: str, text: str) -> list[MatchResult]:
        """Fingerprint text, query index for matches, then insert.

        Returns matches sorted by Jaccard descending.
        """
        fp = document_fingerprint(text, self.k, self.w)
        hash_values = {h for h, _ in fp}

        if not hash_values:
            return []

        with self._lock:
            # Query phase
            candidate_overlap: dict[str, int] = defaultdict(int)
            for h in hash_values:
                for existing_id in self._index.get(h, set()):
                    candidate_overlap[existing_id] += 1

            # Score candidates
            matches: list[MatchResult] = []
            min_overlap = max(1, int(self.threshold * len(hash_values)))

            for other_id, shared in candidate_overlap.items():
                if shared < min_overlap:
                    continue
                other_hashes = self._doc_hashes[other_id]
                union = len(hash_values | other_hashes)
                jacc = shared / union if union else 0.0
                cont = shared / len(hash_values)

                # Gate on containment, not Jaccard: Jaccard is symmetric and
                # collapses toward zero whenever the matched source document
                # is much longer than the copied excerpt, even when the
                # excerpt is 100% contained in the source (see
                # tier1_detector.py's own comment on this exact distinction).
                # Gating on Jaccard here silently discarded true containment
                # matches before tier1_detector.py ever got to read them.
                if cont >= self.threshold:
                    matches.append(
                        MatchResult(
                            source_id=doc_id,
                            target_id=other_id,
                            jaccard=jacc,
                            containment=cont,
                            shared_hashes=shared,
                            source_total=len(hash_values),
                            target_total=len(other_hashes),
                        )
                    )

            # Insert phase
            self._doc_hashes[doc_id] = hash_values
            for h in hash_values:
                self._index[h].add(doc_id)

        return sorted(matches, key=lambda m: -m.jaccard)

    def remove(self, doc_id: str) -> None:
        """Remove a document from the index."""
        with self._lock:
            if doc_id not in self._doc_hashes:
                return
            for h in self._doc_hashes[doc_id]:
                self._index[h].discard(doc_id)
                if not self._index[h]:
                    del self._index[h]
            del self._doc_hashes[doc_id]

    def get_fingerprint(self, doc_id: str) -> set[int] | None:
        """Get stored fingerprint hashes for a document."""
        return self._doc_hashes.get(doc_id)
