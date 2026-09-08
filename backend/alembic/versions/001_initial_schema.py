"""Initial schema: submissions, documents, document_chunks, detection_results, similarity_pairs

Revision ID: 001
Revises:
Create Date: 2026-05-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- submissions --
    op.create_table(
        "submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("course_id", sa.String(100), nullable=True),
        sa.Column("assignment_id", sa.String(100), nullable=True),
        sa.Column("user_id", sa.String(100), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "extracting", "detecting", "completed", "failed", name="submissionstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "tier_resolved",
            sa.Enum("tier1", "tier2", name="tierresolved"),
            nullable=True,
        ),
        sa.Column("celery_task_id", sa.String(255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # -- documents --
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("file_hash", sa.String(64), nullable=True, index=True),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # -- document_chunks --
    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # -- detection_results --
    op.create_table(
        "detection_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("tier1_score", sa.Float(), nullable=True),
        sa.Column("tier2_score", sa.Float(), nullable=True),
        sa.Column("final_score", sa.Float(), nullable=False),
        sa.Column("is_plagiarised", sa.Boolean(), nullable=False),
        sa.Column("escalated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("escalation_reason", sa.String(200), nullable=True),
        sa.Column("processing_time_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # -- similarity_pairs --
    op.create_table(
        "similarity_pairs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("result_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("detection_results.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.Column("match_type", sa.String(20), nullable=False),
        sa.Column("matched_segments", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("similarity_pairs")
    op.drop_table("detection_results")
    op.drop_table("document_chunks")
    op.drop_table("documents")
    op.drop_table("submissions")
    op.execute("DROP TYPE IF EXISTS submissionstatus")
    op.execute("DROP TYPE IF EXISTS tierresolved")
