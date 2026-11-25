import enum
import uuid

from sqlalchemy import Enum, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SubmissionStatus(str, enum.Enum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    DETECTING = "detecting"
    COMPLETED = "completed"
    FAILED = "failed"


class TierResolved(str, enum.Enum):
    TIER1 = "tier1"
    TIER2 = "tier2"


class Submission(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "submissions"

    # Moodle references
    external_id: Mapped[str | None] = mapped_column(String(255))
    course_id: Mapped[str | None] = mapped_column(String(100))
    assignment_id: Mapped[str | None] = mapped_column(String(100))
    user_id: Mapped[str | None] = mapped_column(String(100))

    # Processing state
    status: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus, values_callable=lambda e: [m.value for m in e]),
        default=SubmissionStatus.PENDING,
        nullable=False,
    )
    tier_resolved: Mapped[TierResolved | None] = mapped_column(
        Enum(TierResolved, values_callable=lambda e: [m.value for m in e]),
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(255))
    error_message: Mapped[str | None] = mapped_column(Text)

    # Relationships
    documents: Mapped[list["Document"]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
    )
    result: Mapped["DetectionResult | None"] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
        uselist=False,
    )
    ai_result: Mapped["AIDetectionResult | None"] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
        uselist=False,
    )
