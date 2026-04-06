"""add group2 status and assignments

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-05 22:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_request_status_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("old_status", sa.String(length=32), nullable=True),
        sa.Column("new_status", sa.String(length=32), nullable=False),
        sa.Column("changed_by_admin_id", sa.Integer(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "new_status IN ('new', 'triaged', 'waiting_customer', 'in_progress', 'completed', 'cancelled')",
            name="ck_service_request_status_history_new_status",
        ),
        sa.CheckConstraint(
            "old_status IS NULL OR old_status IN ('new', 'triaged', 'waiting_customer', 'in_progress', 'completed', 'cancelled')",
            name="ck_service_request_status_history_old_status",
        ),
        sa.ForeignKeyConstraint(["changed_by_admin_id"], ["admin_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["service_request_id"], ["service_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_service_request_status_history_service_request_id",
        "service_request_status_history",
        ["service_request_id"],
        unique=False,
    )
    op.create_index(
        "ix_service_request_status_history_created_at",
        "service_request_status_history",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_service_request_status_history_request_created_at",
        "service_request_status_history",
        ["service_request_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "service_request_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("admin_user_id", sa.Integer(), nullable=False),
        sa.Column("assignment_role", sa.String(length=32), nullable=False),
        sa.Column("assigned_by_admin_id", sa.Integer(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("unassigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "assignment_role IN ('lead', 'collaborator')",
            name="ck_service_request_assignments_role",
        ),
        sa.CheckConstraint(
            "unassigned_at IS NULL OR unassigned_at >= assigned_at",
            name="ck_service_request_assignments_unassigned_at",
        ),
        sa.ForeignKeyConstraint(["admin_user_id"], ["admin_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_by_admin_id"], ["admin_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["service_request_id"], ["service_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_service_request_assignments_service_request_id",
        "service_request_assignments",
        ["service_request_id"],
        unique=False,
    )
    op.create_index(
        "ix_service_request_assignments_admin_user_id",
        "service_request_assignments",
        ["admin_user_id"],
        unique=False,
    )
    op.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX uq_service_request_assignments_active_lead
            ON service_request_assignments (service_request_id)
            WHERE assignment_role = 'lead' AND unassigned_at IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE INDEX ix_service_request_assignments_active
            ON service_request_assignments (service_request_id, admin_user_id)
            WHERE unassigned_at IS NULL
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_service_request_assignments_active"))
    op.execute(sa.text("DROP INDEX IF EXISTS uq_service_request_assignments_active_lead"))
    op.drop_index("ix_service_request_assignments_admin_user_id", table_name="service_request_assignments")
    op.drop_index("ix_service_request_assignments_service_request_id", table_name="service_request_assignments")
    op.drop_table("service_request_assignments")

    op.drop_index(
        "ix_service_request_status_history_request_created_at",
        table_name="service_request_status_history",
    )
    op.drop_index("ix_service_request_status_history_created_at", table_name="service_request_status_history")
    op.drop_index(
        "ix_service_request_status_history_service_request_id",
        table_name="service_request_status_history",
    )
    op.drop_table("service_request_status_history")
