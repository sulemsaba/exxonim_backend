"""Add career jobs table

Revision ID: 9a4c2e7f1b8d
Revises: 7a9b3c4d5e6f
Create Date: 2026-03-28 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "9a4c2e7f1b8d"
down_revision: Union[str, None] = "7a9b3c4d5e6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "career_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("department", sa.String(length=150), nullable=False),
        sa.Column("employment_type", sa.String(length=80), nullable=False),
        sa.Column("location_mode", sa.String(length=80), nullable=False),
        sa.Column("city", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("country", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("compensation_label", sa.String(length=255), nullable=True),
        sa.Column("experience_label", sa.String(length=255), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("requirements", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("responsibilities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_career_jobs_slug"),
    )
    op.create_index(op.f("ix_career_jobs_slug"), "career_jobs", ["slug"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_career_jobs_slug"), table_name="career_jobs")
    op.drop_table("career_jobs")
