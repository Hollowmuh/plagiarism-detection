"""Sentence embedding service using all-MiniLM-L6-v2 (384 dimensions).

Model is loaded ONCE and reused. Designed for CPU inference.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from app.config import settings
from app.core.logging import get_logger

log = get_logger("embedding")

# ── Singleton model holder ───────────────────────────────────────
_model = None


def get_model():
    """Lazy-load the sentence-transformers model (once per process)."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        log.info("loading_model", model=settings.EMBEDDING_MODEL)
        _model = SentenceTransformer(
            settings.EMBEDDING_MODEL,
            device=settings.EMBEDDING_DEVICE,
        )
        log.info("model_loaded", model=settings.EMBEDDING_MODEL)
    return _model


# ── Text chunking ────────────────────────────────────────────────

@dataclass
class TextChunk:
    """A chunk of text with position tracking back to source."""
    index: int
    text: str
    char_start: int
    char_end: int


def split_sentences(text: str) -> list[str]:
    """Split text into sentences. Shared by chunk_text() and any caller
    needing sentence-level (not word-budget-level) granularity."""
    return re.split(r"(?<=[.!?])\s+", text.strip())


def chunk_text(
    text: str,
    max_tokens: int | None = None,
    overlap_tokens: int | None = None,
) -> list[TextChunk]:
    """Split text into overlapping chunks, respecting sentence boundaries.

    Args:
        text: Full document text.
        max_tokens: Max words per chunk (default from settings.CHUNK_SIZE).
        overlap_tokens: Overlap in words (default from settings.CHUNK_OVERLAP).

    Returns:
        List of TextChunk with position tracking.
    """
    max_tokens = max_tokens or settings.CHUNK_SIZE
    overlap_tokens = overlap_tokens or settings.CHUNK_OVERLAP

    if not text.strip():
        return []

    # Split into sentences
    sentences = split_sentences(text)
    if not sentences:
        return []

    chunks: list[TextChunk] = []
    current_sentences: list[str] = []
    current_word_count = 0
    chunk_char_start = 0
    char_pos = 0

    # Track character positions for each sentence
    sentence_positions: list[tuple[int, int]] = []
    pos = 0
    for sent in sentences:
        start = text.find(sent, pos)
        if start == -1:
            start = pos
        end = start + len(sent)
        sentence_positions.append((start, end))
        pos = end

    for i, sentence in enumerate(sentences):
        word_count = len(sentence.split())

        if current_word_count + word_count > max_tokens and current_sentences:
            # Emit chunk
            chunk_text_str = " ".join(current_sentences)
            chunk_end = sentence_positions[i - 1][1] if i > 0 else sentence_positions[0][1]
            chunks.append(TextChunk(
                index=len(chunks),
                text=chunk_text_str,
                char_start=chunk_char_start,
                char_end=chunk_end,
            ))

            # Overlap: keep trailing sentences within overlap budget
            overlap_count = 0
            overlap_sents: list[str] = []
            overlap_start_idx = i
            for j in range(len(current_sentences) - 1, -1, -1):
                s_words = len(current_sentences[j].split())
                if overlap_count + s_words <= overlap_tokens:
                    overlap_sents.insert(0, current_sentences[j])
                    overlap_count += s_words
                    overlap_start_idx = (i - len(current_sentences)) + j
                else:
                    break

            current_sentences = overlap_sents
            current_word_count = overlap_count
            if overlap_sents and overlap_start_idx >= 0 and overlap_start_idx < len(sentence_positions):
                chunk_char_start = sentence_positions[max(0, overlap_start_idx)][0]
            else:
                chunk_char_start = sentence_positions[i][0]

        current_sentences.append(sentence)
        current_word_count += word_count

    # Emit final chunk
    if current_sentences:
        chunk_text_str = " ".join(current_sentences)
        chunk_end = sentence_positions[-1][1] if sentence_positions else len(text)
        chunks.append(TextChunk(
            index=len(chunks),
            text=chunk_text_str,
            char_start=chunk_char_start,
            char_end=chunk_end,
        ))

    return chunks


# ── Encoding ─────────────────────────────────────────────────────

def encode_texts(texts: list[str], batch_size: int = 32) -> np.ndarray:
    """Encode a list of texts into 384-dim normalized embeddings.

    Args:
        texts: List of text strings.
        batch_size: Batch size for inference (32 recommended for CPU).

    Returns:
        numpy array of shape (len(texts), 384), dtype float32.
    """
    model = get_model()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return embeddings


def encode_single(text: str) -> np.ndarray:
    """Encode a single text into a 384-dim normalized embedding."""
    return encode_texts([text])[0]
