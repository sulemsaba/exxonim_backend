"""add admin notifications

Revision ID: fa1b2c3d4e5f
Revises: f8a9b0c1d2e3
Create Date: 2026-04-06 09:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "fa1b2c3d4e5f"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_admin_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("href", sa.String(length=255), nullable=True),
        sa.Column("resource_type", sa.String(length=120), nullable=True),
        sa.Column("resource_id", sa.String(length=255), nullable=True),
        sa.Column("actor_admin_id", sa.Integer(), nullable=True),
        sa.Column("dedupe_key", sa.String(length=255), nullable=True),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "category IN ('request_ops', 'content_review', 'security', 'reporting', 'system')",
            name="ck_admin_notifications_category",
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'error')",
            name="ck_admin_notifications_severity",
        ),
        sa.ForeignKeyConstraint(["actor_admin_id"], ["admin_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recipient_admin_id"], ["admin_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_admin_notifications_recipient_admin_id",
        "admin_notifications",
        ["recipient_admin_id"],
        unique=False,
    )
    op.create_index(
        "ix_admin_notifications_event_type",
        "admin_notifications",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        "ix_admin_notifications_last_occurred_at",
        "admin_notifications",
        ["last_occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_admin_notifications_recipient_unread_last_occurred",
        "admin_notifications",
        ["recipient_admin_id", "is_read", sa.text("last_occurred_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_admin_notifications_recipient_category_last_occurred",
        "admin_notifications",
        ["recipient_admin_id", "category", sa.text("last_occurred_at DESC")],
        unique=False,
    )
    op.create_index(
        "uq_admin_notifications_active_dedupe",
        "admin_notifications",
        ["recipient_admin_id", "dedupe_key"],
        unique=True,
        postgresql_where=sa.text("dedupe_key IS NOT NULL AND is_read = false"),
    )

    op.create_table(
        "admin_notification_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("admin_user_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("in_app_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "category IN ('request_ops', 'content_review', 'security', 'reporting', 'system')",
            name="ck_admin_notification_preferences_category",
        ),
        sa.ForeignKeyConstraint(["admin_user_id"], ["admin_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "admin_user_id",
            "category",
            name="uq_admin_notification_preferences_admin_category",
        ),
    )
    op.create_index(
        "ix_admin_notification_preferences_admin_user_id",
        "admin_notification_preferences",
        ["admin_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_admin_notification_preferences_admin_user_id",
        table_name="admin_notification_preferences",
    )
    op.drop_table("admin_notification_preferences")

    op.drop_index(
        "uq_admin_notifications_active_dedupe",
        table_name="admin_notifications",
    )
    op.drop_index(
        "ix_admin_notifications_recipient_category_last_occurred",
        table_name="admin_notifications",
    )
    op.drop_index(
        "ix_admin_notifications_recipient_unread_last_occurred",
        table_name="admin_notifications",
    )
    op.drop_index(
        "ix_admin_notifications_last_occurred_at",
        table_name="admin_notifications",
    )
    op.drop_index(
        "ix_admin_notifications_event_type",
        table_name="admin_notifications",
    )
    op.drop_index(
        "ix_admin_notifications_recipient_admin_id",
        table_name="admin_notifications",
    )
    op.drop_table("admin_notifications")
