"""add group3 queue read state

Revision ID: f8a9b0c1d2e3
Revises: e5f6a7b8c9d0
Create Date: 2026-04-05 23:55:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f8a9b0c1d2e3"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "service_requests",
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "service_requests",
        sa.Column(
            "last_customer_message_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_service_requests_last_activity_at",
        "service_requests",
        ["last_activity_at"],
        unique=False,
    )
    op.create_index(
        "ix_service_requests_last_customer_message_at",
        "service_requests",
        ["last_customer_message_at"],
        unique=False,
    )
    op.create_index(
        "ix_service_requests_status_priority_last_activity_at",
        "service_requests",
        ["status", "priority", sa.text("last_activity_at DESC")],
        unique=False,
    )

    op.create_table(
        "service_request_inbox_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("admin_user_id", sa.Integer(), nullable=False),
        sa.Column("last_read_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["admin_user_id"], ["admin_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["last_read_message_id"], ["inbox_messages.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["service_request_id"], ["service_requests.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "service_request_id",
            "admin_user_id",
            name="uq_service_request_inbox_states_request_admin",
        ),
    )
    op.create_index(
        "ix_service_request_inbox_states_service_request_id",
        "service_request_inbox_states",
        ["service_request_id"],
        unique=False,
    )
    op.create_index(
        "ix_service_request_inbox_states_admin_user_id",
        "service_request_inbox_states",
        ["admin_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_service_request_inbox_states_admin_updated_at",
        "service_request_inbox_states",
        ["admin_user_id", sa.text("updated_at DESC")],
        unique=False,
    )

    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE service_requests
            SET last_activity_at = COALESCE(updated_at, created_at, now())
            """
        )
    )
    connection.execute(
        sa.text(
            """
            WITH latest_customer_message AS (
                SELECT
                    thread.service_request_id,
                    MAX(message.created_at) AS last_customer_message_at
                FROM inbox_threads AS thread
                JOIN inbox_messages AS message
                  ON message.thread_id = thread.id
                WHERE message.direction = 'inbound'
                GROUP BY thread.service_request_id
            )
            UPDATE service_requests AS request
            SET
                last_customer_message_at = latest.last_customer_message_at,
                last_activity_at = GREATEST(
                    request.last_activity_at,
                    latest.last_customer_message_at
                )
            FROM latest_customer_message AS latest
            WHERE latest.service_request_id = request.id
            """
        )
    )

    op.alter_column("service_requests", "last_activity_at", server_default=None)


def downgrade() -> None:
    op.drop_index(
        "ix_service_request_inbox_states_admin_updated_at",
        table_name="service_request_inbox_states",
    )
    op.drop_index(
        "ix_service_request_inbox_states_admin_user_id",
        table_name="service_request_inbox_states",
    )
    op.drop_index(
        "ix_service_request_inbox_states_service_request_id",
        table_name="service_request_inbox_states",
    )
    op.drop_table("service_request_inbox_states")

    op.drop_index(
        "ix_service_requests_status_priority_last_activity_at",
        table_name="service_requests",
    )
    op.drop_index("ix_service_requests_last_customer_message_at", table_name="service_requests")
    op.drop_index("ix_service_requests_last_activity_at", table_name="service_requests")
    op.drop_column("service_requests", "last_customer_message_at")
    op.drop_column("service_requests", "last_activity_at")
