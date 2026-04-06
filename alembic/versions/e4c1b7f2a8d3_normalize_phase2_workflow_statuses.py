"""normalize phase 2 workflow statuses

Revision ID: e4c1b7f2a8d3
Revises: c3f4a1b2d9e0
Create Date: 2026-04-04 15:35:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "e4c1b7f2a8d3"
down_revision = "c3f4a1b2d9e0"
branch_labels = None
depends_on = None


CONTENT_TABLES = ("pages", "blog_posts", "testimonials")


def upgrade() -> None:
    for table_name in CONTENT_TABLES:
        op.execute(
            sa.text(f"UPDATE {table_name} SET status = 'pending_review' WHERE status = 'in_review'")
        )
        op.execute(
            sa.text(f"UPDATE {table_name} SET status = 'draft' WHERE status = 'scheduled'")
        )


def downgrade() -> None:
    for table_name in CONTENT_TABLES:
        op.execute(
            sa.text(f"UPDATE {table_name} SET status = 'in_review' WHERE status = 'pending_review'")
        )
