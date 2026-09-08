import uuid
from datetime import datetime

from pydantic import BaseModel


class MatchedSegment(BaseModel):
    source_text: str
    submitted_text: str
    source_offset: list[int]
    submitted_offset: list[int]


class SimilarityPairResponse(BaseModel):
    source_document_id: uuid.UUID | None
    similarity_score: float
    match_type: str
    matched_segments: list[MatchedSegment] | None = None

    model_config = {"from_attributes": True}


class AIDetectionResultResponse(BaseModel):
    """Advisory AI-authorship signal. Independent of the plagiarism score
    above -- never treat this as a misconduct verdict on its own (see
    docs/2026-07-01/ai_detection_tier_1426.md for the false-positive/ESL-bias
    caveats behind this design)."""
    ai_score: float
    verdict: str
    model_name: str
    processing_time_ms: int | None

    model_config = {"from_attributes": True}


class DetectionResultResponse(BaseModel):
    submission_id: uuid.UUID
    tier1_score: float | None
    tier2_score: float | None
    final_score: float
    is_plagiarised: bool
    escalated: bool
    escalation_reason: str | None
    processing_time_ms: int | None
    matches: list[SimilarityPairResponse] = []
    ai_detection: AIDetectionResultResponse | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
