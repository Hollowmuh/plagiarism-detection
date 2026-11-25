import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DetectionResult(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "detection_results"

    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("submissions.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    tier1_score: Mapped[float | None] = mapped_column(Float)
    tier2_score: Mapped[float | None] = mapped_column(Float)
    final_score: Mapped[float] = mapped_column(Float, nullable=False)
    is_plagiarised: Mapped[bool] = mapped_column(Boolean, nullable=False)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    escalation_reason: Mapped[str | None] = mapped_column(String(200))
    processing_time_ms: Mapped[int | None] = mapped_column(Integer)

    # Relationships
    submission: Mapped["Submission"] = relationship(back_populates="result")
    similarity_pairs: Mapped[list["SimilarityPair"]] = relationship(
        back_populates="result",
        cascade="all, delete-orphan",
    )


class SimilarityPair(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "similarity_pairs"

    result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("detection_results.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    match_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # Actual runtime shape is a list of MatchedSegment-shaped dicts (see
    # app.schemas.result.MatchedSegment / segment_extraction.py), not a
    # bare dict -- JSONB itself is untyped at the DB level so this is a
    # type-hint-only fix, no migration needed.
    matched_segments: Mapped[list[dict] | None] = mapped_column(JSONB)

    # Relationships
    result: Mapped["DetectionResult"] = relationship(back_populates="similarity_pairs")
