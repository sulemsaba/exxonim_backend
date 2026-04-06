"""add group2 inbox and notes

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-05 22:25:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inbox_threads",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thread_kind", sa.String(length=32), nullable=False, server_default="primary"),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "thread_kind IN ('primary')",
            name="ck_inbox_threads_thread_kind",
        ),
        sa.ForeignKeyConstraint(["service_request_id"], ["service_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_request_id", "thread_kind", name="uq_inbox_threads_request_kind"),
    )
    op.create_index("ix_inbox_threads_service_request_id", "inbox_threads", ["service_request_id"], unique=False)

    op.create_table(
        "inbox_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author_admin_id", sa.Integer(), nullable=True),
        sa.Column("customer_author_name", sa.String(length=255), nullable=True),
        sa.Column("customer_author_email", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "direction IN ('inbound', 'outbound', 'internal')",
            name="ck_inbox_messages_direction",
        ),
        sa.CheckConstraint(
            "channel IN ('web_form', 'admin_manual', 'system_seed')",
            name="ck_inbox_messages_channel",
        ),
        sa.ForeignKeyConstraint(["author_admin_id"], ["admin_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["thread_id"], ["inbox_threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inbox_messages_thread_id", "inbox_messages", ["thread_id"], unique=False)
    op.create_index(
        "ix_inbox_messages_thread_created_at",
        "inbox_messages",
        ["thread_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("service_request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("visibility", sa.String(length=32), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_by_admin_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "visibility IN ('internal', 'customer_safe')",
            name="ck_notes_visibility",
        ),
        sa.CheckConstraint(
            "(customer_id IS NOT NULL) <> (service_request_id IS NOT NULL)",
            name="ck_notes_exactly_one_target",
        ),
        sa.ForeignKeyConstraint(["created_by_admin_id"], ["admin_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["service_request_id"], ["service_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notes_customer_id", "notes", ["customer_id"], unique=False)
    op.create_index("ix_notes_service_request_id", "notes", ["service_request_id"], unique=False)
    op.create_index("ix_notes_created_at", "notes", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_notes_created_at", table_name="notes")
    op.drop_index("ix_notes_service_request_id", table_name="notes")
    op.drop_index("ix_notes_customer_id", table_name="notes")
    op.drop_table("notes")

    op.drop_index("ix_inbox_messages_thread_created_at", table_name="inbox_messages")
    op.drop_index("ix_inbox_messages_thread_id", table_name="inbox_messages")
    op.drop_table("inbox_messages")

    op.drop_index("ix_inbox_threads_service_request_id", table_name="inbox_threads")
    op.drop_table("inbox_threads")
