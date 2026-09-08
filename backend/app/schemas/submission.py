import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.submission import SubmissionStatus, TierResolved


class SubmissionCreate(BaseModel):
    course_id: str | None = None
    assignment_id: str | None = None
    user_id: str | None = None


class SubmissionResponse(BaseModel):
    id: uuid.UUID
    status: SubmissionStatus
    tier_resolved: TierResolved | None = None
    course_id: str | None = None
    assignment_id: str | None = None
    user_id: str | None = None
    celery_task_id: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class SubmissionStatusResponse(BaseModel):
    id: uuid.UUID
    status: SubmissionStatus
    tier_resolved: TierResolved | None = None
    processing_time_ms: int | None = None

    model_config = {"from_attributes": True}


class SubmissionAccepted(BaseModel):
    submission_id: uuid.UUID
    status: str = "pending"
    message: str = "Submission queued for processing"
