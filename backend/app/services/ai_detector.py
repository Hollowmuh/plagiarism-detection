"""AI-generated-text detection service.

Answers a different question than the tier1/tier2 pipeline: not "was this
copied from an existing source" but "does this read like LLM output".
Advisory only -- see docs/2026-07-01/ai_detection_tier_1426.md for why this
must never be treated as a standalone plagiarism/misconduct verdict (false
positive rates against non-native English writers are well documented in
the published literature this recommendation is based on).

Model is loaded ONCE per worker process and reused, same pattern as
embedding_service.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import settings
from app.core.logging import get_logger

log = get_logger("ai_detector")

# ── Singleton model holder ───────────────────────────────────────
_tokenizer = None
_model = None
_ai_label_index: int | None = None


def _resolve_ai_label_index(model) -> int:
    """Find which output index corresponds to "AI-generated" for this checkpoint.

    Looked up from the model's own id2label config rather than hardcoded,
    since AI_DETECTOR_MODEL is swappable (see plan doc, Phase 2). Falls back
    to index 1 (the convention for every checkpoint checked so far) with a
    warning if no label text matches.
    """
    id2label = getattr(model.config, "id2label", None) or {}
    ai_markers = ("ai", "gpt", "generated", "machine", "chatgpt", "llm")
    for idx, label in id2label.items():
        if any(marker in str(label).lower() for marker in ai_markers):
            return int(idx)

    log.warning(
        "ai_detector_label_index_fallback",
        model=settings.AI_DETECTOR_MODEL,
        id2label=id2label,
    )
    return 1


def _get_model():
    global _tokenizer, _model, _ai_label_index
    if _model is None:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        log.info("loading_ai_detector_model", model=settings.AI_DETECTOR_MODEL)
        _tokenizer = AutoTokenizer.from_pretrained(settings.AI_DETECTOR_MODEL)
        _model = AutoModelForSequenceClassification.from_pretrained(
            settings.AI_DETECTOR_MODEL
        )
        _model.to(settings.AI_DETECTOR_DEVICE)
        _model.eval()
        _ai_label_index = _resolve_ai_label_index(_model)
        log.info(
            "ai_detector_model_loaded",
            model=settings.AI_DETECTOR_MODEL,
            ai_label_index=_ai_label_index,
        )
    return _tokenizer, _model, _ai_label_index


def _verdict_for(score: float) -> str:
    if score < settings.AI_DETECTOR_TAU_LOW:
        return "likely_human"
    if score > settings.AI_DETECTOR_TAU_HIGH:
        return "likely_ai"
    return "uncertain"


@dataclass
class AIDetectionOutcome:
    score: float  # 0..1, probability of AI authorship
    verdict: str  # "likely_human" | "uncertain" | "likely_ai"
    model_name: str


def detect(text: str) -> AIDetectionOutcome:
    """Score a document for likelihood of AI-generated authorship.

    Advisory only: never gate submission completion or plagiarism status on
    this. Long documents are truncated to AI_DETECTOR_MAX_LENGTH tokens
    (classifier limitation, not a design choice -- Phase 2 could chunk and
    aggregate per-section scores if that turns out to matter in practice).
    """
    import torch

    tokenizer, model, ai_index = _get_model()

    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=settings.AI_DETECTOR_MAX_LENGTH,
    ).to(settings.AI_DETECTOR_DEVICE)

    with torch.no_grad():
        logits = model(**inputs).logits
        probs = torch.softmax(logits, dim=-1)[0]

    ai_score = float(probs[ai_index].item())

    return AIDetectionOutcome(
        score=ai_score,
        verdict=_verdict_for(ai_score),
        model_name=settings.AI_DETECTOR_MODEL,
    )
