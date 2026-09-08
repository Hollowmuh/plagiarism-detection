"""BM25 sparse retrieval service with incremental corpus management.

Uses rank_bm25 with periodic rebuild. Tokenization via simple regex
(avoids SpaCy dependency at runtime for lighter Docker image).
"""

from __future__ import annotations

import re
from threading import RLock

import numpy as np
from rank_bm25 import BM25Plus

from app.core.logging import get_logger

log = get_logger("bm25")

# ── English stop words (compact set, no SpaCy needed) ────────────
STOP_WORDS = frozenset(
    "a an the is was were be been being have has had do does did will would "
    "shall should may might can could am are at by for from in into of on to "
    "with and but or nor not so yet both either neither each every all any few "
    "more most other some such no only own same than too very that this these "
    "those it its he she they them their his her our your we you i me my us "
    "what which who whom whose when where how why if then else also just about "
    "up out over after before between through during above below under again "
    "further once here there".split()
)

# ── Tokenization ─────────────────────────────────────────────────

_WORD_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alphanumeric, remove stop words."""
    words = _WORD_RE.findall(text.lower())
    return [w for w in words if w not in STOP_WORDS and len(w) > 1]


# ── BM25 Index ───────────────────────────────────────────────────

class BM25Index:
    """Thread-safe BM25 index with incremental corpus management.

    The index is rebuilt on each query if the corpus has changed.
    For small corpora (<50K docs) this is fast enough.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b

        self._lock = RLock()
        self._corpus: list[list[str]] = []
        self._doc_ids: list[str] = []
        self._raw_texts: dict[str, str] = {}
        self._index: BM25Plus | None = None
        self._dirty = True

    @property
    def document_count(self) -> int:
        return len(self._doc_ids)

    def add_document(self, doc_id: str, text: str) -> None:
        """Add a document to the corpus. Index will rebuild on next query."""
        tokens = tokenize(text)
        if not tokens:
            return
        with self._lock:
            # Avoid duplicates
            if doc_id in self._raw_texts:
                return
            self._corpus.append(tokens)
            self._doc_ids.append(doc_id)
            self._raw_texts[doc_id] = text
            self._dirty = True

    def _rebuild_if_needed(self) -> None:
        """Rebuild BM25 index if corpus has changed."""
        if self._dirty and self._corpus:
            self._index = BM25Plus(self._corpus, k1=self.k1, b=self.b)
            self._dirty = False

    def search(
        self, query_text: str, top_k: int = 10,
        min_raw_score: float = 20.0,
        saturation_score: float = 1200.0,
    ) -> list[tuple[str, float, float]]:
        """Search for similar documents.

        Uses proportional scaling (raw / saturation, capped at 1.0) instead of
        per-query min-max normalization. This preserves absolute magnitude so
        weak matches don't inflate to 1.0 in small corpora.

        Args:
            query_text: Query document text.
            top_k: Max results to return.
            min_raw_score: Minimum raw BM25+ score to consider a real match.
                Below this, shared words are incidental (common academic vocab).
            saturation_score: Raw score that maps to 1.0. Calibrated for BM25Plus
                with academic documents. Set high (1200) so topical overlap
                (score ~200-500) normalizes to 0.2-0.4, while verbatim matches
                (score ~800-1200+) normalize to 0.7-1.0.

        Returns:
            List of (doc_id, raw_score, normalized_score) sorted by score desc.
        """
        tokens = tokenize(query_text)
        if not tokens:
            return []

        with self._lock:
            self._rebuild_if_needed()
            if self._index is None or not self._corpus:
                return []

            raw_scores = self._index.get_scores(tokens)

            # Proportional normalization: raw / saturation, capped at 1.0
            norm_scores = np.clip(raw_scores / saturation_score, 0.0, 1.0)

            # Get top-k indices
            if len(raw_scores) <= top_k:
                top_indices = np.argsort(raw_scores)[::-1]
            else:
                top_indices = np.argpartition(raw_scores, -top_k)[-top_k:]
                top_indices = top_indices[np.argsort(raw_scores[top_indices])[::-1]]

            results = []
            for idx in top_indices:
                if raw_scores[idx] >= min_raw_score:
                    results.append((
                        self._doc_ids[idx],
                        float(raw_scores[idx]),
                        float(norm_scores[idx]),
                    ))

            return results

    def get_max_score(self, query_text: str) -> tuple[str | None, float, float]:
        """Get the single best matching document and its scores.

        Returns (doc_id, raw_score, normalized_score) or (None, 0.0, 0.0).
        """
        results = self.search(query_text, top_k=1)
        if results:
            return results[0]
        return None, 0.0, 0.0

    def get_text(self, doc_id: str) -> str | None:
        """Retrieve stored text for a document."""
        return self._raw_texts.get(doc_id)

    def remove(self, doc_id: str) -> None:
        """Remove a document. Triggers rebuild on next query."""
        with self._lock:
            if doc_id not in self._raw_texts:
                return
            idx = self._doc_ids.index(doc_id)
            self._corpus.pop(idx)
            self._doc_ids.pop(idx)
            del self._raw_texts[doc_id]
            self._dirty = True
