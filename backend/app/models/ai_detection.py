import enum
import uuid

from sqlalchemy import Enum, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AIVerdict(str, enum.Enum):
    LIKELY_HUMAN = "likely_human"
    UNCERTAIN = "uncertain"
    LIKELY_AI = "likely_ai"


class AIDetectionResult(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Advisory AI-authorship signal for a submission.

    Deliberately a separate table from DetectionResult (not extra columns on
    it): source-matching plagiarism and AI-generated-authorship are
    independent axes, and this result must never be blended into
    final_score/is_plagiarised. See docs/2026-07-01/ai_detection_tier_1426.md.
    """
    __tablename__ = "ai_detection_results"

    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("submissions.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    ai_score: Mapped[float] = mapped_column(Float, nullable=False)
    verdict: Mapped[AIVerdict] = mapped_column(
        Enum(AIVerdict, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    processing_time_ms: Mapped[int | None] = mapped_column(Integer)

    # Relationships
    submission: Mapped["Submission"] = relationship(back_populates="ai_result")
