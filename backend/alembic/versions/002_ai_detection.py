"""AI-generated-text detection: ai_detection_results

Independent from detection_results (source-matching plagiarism) — a
submission's plagiarism score and its AI-authorship likelihood are separate
axes. See docs/2026-07-01/ai_detection_tier_1426.md.

Revision ID: 002
Revises: 001
Create Date: 2026-07-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_detection_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "submission_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("submissions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("ai_score", sa.Float(), nullable=False),
        sa.Column(
            "verdict",
            sa.Enum("likely_human", "uncertain", "likely_ai", name="aiverdict"),
            nullable=False,
        ),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("processing_time_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("ai_detection_results")
    op.execute("DROP TYPE IF EXISTS aiverdict")
