"""add refresh sessions and media storage key

Revision ID: f7b6c5d4e3a2
Revises: e4c1b7f2a8d3
Create Date: 2026-04-05 18:10:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "f7b6c5d4e3a2"
down_revision = "e4c1b7f2a8d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_refresh_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("admin_user_id", sa.Integer(), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=128), nullable=False),
        sa.Column("csrf_token_hash", sa.String(length=128), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["admin_user_id"],
            ["admin_users.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_admin_refresh_sessions_admin_user_id",
        "admin_refresh_sessions",
        ["admin_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_admin_refresh_sessions_expires_at",
        "admin_refresh_sessions",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_admin_refresh_sessions_revoked_at",
        "admin_refresh_sessions",
        ["revoked_at"],
        unique=False,
    )

    op.add_column("media", sa.Column("storage_key", sa.String(length=255), nullable=True))
    op.create_index("ix_media_storage_key", "media", ["storage_key"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_media_storage_key", table_name="media")
    op.drop_column("media", "storage_key")

    op.drop_index("ix_admin_refresh_sessions_revoked_at", table_name="admin_refresh_sessions")
    op.drop_index("ix_admin_refresh_sessions_expires_at", table_name="admin_refresh_sessions")
    op.drop_index("ix_admin_refresh_sessions_admin_user_id", table_name="admin_refresh_sessions")
    op.drop_table("admin_refresh_sessions")
