"""Quality control filters for the evaluation dataset.

Filters:
  1. Length: 500-5,000 words
  2. Language: English only (fastText lid218e, confidence > 0.95)
  3. Near-duplicate removal: SimHash with Hamming distance threshold
  4. Encoding: UTF-8 validation
"""

import hashlib
import re
from dataclasses import dataclass

import numpy as np


@dataclass
class QCResult:
    text: str
    passed: bool
    word_count: int
    language: str | None
    lang_confidence: float
    rejection_reason: str | None = None


# ── Length filter ────────────────────────────────────────────────

def check_length(text: str, min_words: int = 500, max_words: int = 5000) -> tuple[int, bool, str | None]:
    """Check if text is within the acceptable word count range."""
    words = text.split()
    count = len(words)
    if count < min_words:
        return count, False, f"too short ({count} < {min_words} words)"
    if count > max_words:
        return count, False, f"too long ({count} > {max_words} words)"
    return count, True, None


# ── Language detection ───────────────────────────────────────────

_ft_model = None


def _get_ft_model():
    """Lazy-load the fastText language identification model."""
    global _ft_model
    if _ft_model is None:
        try:
            import fasttext

            # Download lid218e if not present.
            import urllib.request
            import os

            model_path = os.path.join(os.path.dirname(__file__), "lid218e.bin")
            if not os.path.exists(model_path):
                print("Downloading fastText language ID model...")
                urllib.request.urlretrieve(
                    "https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid218e.bin",
                    model_path,
                )
            _ft_model = fasttext.load_model(model_path)
        except ImportError:
            return None
    return _ft_model


def check_language(
    text: str,
    expected_lang: str = "eng_Latn",
    min_confidence: float = 0.95,
) -> tuple[str | None, float, bool, str | None]:
    """Check if text is in the expected language.

    Uses fastText lid218e model. Falls back to a simple heuristic if
    fastText is not available.

    Returns:
        (detected_lang, confidence, passed, rejection_reason).
    """
    model = _get_ft_model()

    if model is not None:
        # FastText expects single-line input.
        clean = text.replace("\n", " ")[:5000]
        predictions = model.predict(clean, k=1)
        label = predictions[0][0].replace("__label__", "")
        confidence = float(predictions[1][0])

        passed = label == expected_lang and confidence >= min_confidence
        reason = None
        if not passed:
            reason = f"lang={label} conf={confidence:.3f} (need {expected_lang} >= {min_confidence})"
        return label, confidence, passed, reason

    # Fallback: check for high proportion of ASCII characters.
    ascii_ratio = sum(1 for c in text if ord(c) < 128) / max(len(text), 1)
    passed = ascii_ratio > 0.90
    reason = None if passed else f"low ASCII ratio {ascii_ratio:.2f} (fastText not available)"
    return "unknown", ascii_ratio, passed, reason


# ── SimHash near-duplicate detection ─────────────────────────────

def _simhash(text: str, hash_bits: int = 64) -> int:
    """Compute SimHash for near-duplicate detection."""
    tokens = re.findall(r"\w+", text.lower())
    v = [0] * hash_bits

    for token in tokens:
        token_hash = int(hashlib.md5(token.encode()).hexdigest(), 16)
        for i in range(hash_bits):
            if token_hash & (1 << i):
                v[i] += 1
            else:
                v[i] -= 1

    fingerprint = 0
    for i in range(hash_bits):
        if v[i] > 0:
            fingerprint |= 1 << i
    return fingerprint


def hamming_distance(a: int, b: int) -> int:
    """Count differing bits between two integers."""
    return bin(a ^ b).count("1")


def find_near_duplicates(
    texts: list[dict],
    max_hamming: int = 3,
) -> list[tuple[str, str, int]]:
    """Find near-duplicate pairs using SimHash.

    Args:
        texts: List of {"id": str, "text": str}.
        max_hamming: Maximum Hamming distance to flag as near-duplicate.

    Returns:
        List of (id_a, id_b, distance) duplicate pairs.
    """
    hashes = [(item["id"], _simhash(item["text"])) for item in texts]
    duplicates = []

    for i in range(len(hashes)):
        for j in range(i + 1, len(hashes)):
            dist = hamming_distance(hashes[i][1], hashes[j][1])
            if dist <= max_hamming:
                duplicates.append((hashes[i][0], hashes[j][0], dist))

    return duplicates


# ── Combined QC pipeline ─────────────────────────────────────────

def run_quality_control(
    text: str,
    min_words: int = 500,
    max_words: int = 5000,
    expected_lang: str = "eng_Latn",
    min_lang_confidence: float = 0.95,
) -> QCResult:
    """Run the full quality control pipeline on a single text.

    Returns QCResult with pass/fail status and diagnostics.
    """
    # UTF-8 validation.
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return QCResult(
            text=text, passed=False, word_count=0,
            language=None, lang_confidence=0.0,
            rejection_reason="invalid UTF-8 encoding",
        )

    # Length check.
    word_count, length_ok, length_reason = check_length(text, min_words, max_words)
    if not length_ok:
        return QCResult(
            text=text, passed=False, word_count=word_count,
            language=None, lang_confidence=0.0,
            rejection_reason=length_reason,
        )

    # Language check.
    lang, confidence, lang_ok, lang_reason = check_language(text, expected_lang, min_lang_confidence)
    if not lang_ok:
        return QCResult(
            text=text, passed=False, word_count=word_count,
            language=lang, lang_confidence=confidence,
            rejection_reason=lang_reason,
        )

    return QCResult(
        text=text, passed=True, word_count=word_count,
        language=lang, lang_confidence=confidence,
    )
