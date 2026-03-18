"""add consultation tracking

Revision ID: 7a9b3c4d5e6f
Revises: 6d5b6d7c8e9f
Create Date: 2026-03-17 00:00:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7a9b3c4d5e6f"
down_revision = "6d5b6d7c8e9f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consultations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tracking_id", sa.String(length=50), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("company", sa.String(length=255), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("assigned_to", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("public_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["assigned_to"], ["admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tracking_id", name="uq_consultations_tracking_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_consultations_idempotency_key"),
    )
    op.create_index(op.f("ix_consultations_tracking_id"), "consultations", ["tracking_id"], unique=False)
    op.create_index(op.f("ix_consultations_idempotency_key"), "consultations", ["idempotency_key"], unique=False)
    op.create_index(op.f("ix_consultations_email"), "consultations", ["email"], unique=False)
    op.create_index(op.f("ix_consultations_assigned_to"), "consultations", ["assigned_to"], unique=False)

    op.create_table(
        "consultation_status_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("consultation_id", sa.Integer(), nullable=False),
        sa.Column("old_status", sa.String(length=50), nullable=True),
        sa.Column("new_status", sa.String(length=50), nullable=False),
        sa.Column("changed_by", sa.Integer(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["changed_by"], ["admin_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["consultation_id"], ["consultations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_consultation_status_history_consultation_id"),
        "consultation_status_history",
        ["consultation_id"],
        unique=False,
    )

    op.create_table(
        "notification_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("consultation_id", sa.Integer(), nullable=True),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("recipient", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="queued"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["consultation_id"], ["consultations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_notification_logs_consultation_id"),
        "notification_logs",
        ["consultation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_notification_logs_consultation_id"), table_name="notification_logs")
    op.drop_table("notification_logs")

    op.drop_index(
        op.f("ix_consultation_status_history_consultation_id"),
        table_name="consultation_status_history",
    )
    op.drop_table("consultation_status_history")

    op.drop_index(op.f("ix_consultations_assigned_to"), table_name="consultations")
    op.drop_index(op.f("ix_consultations_email"), table_name="consultations")
    op.drop_index(op.f("ix_consultations_idempotency_key"), table_name="consultations")
    op.drop_index(op.f("ix_consultations_tracking_id"), table_name="consultations")
    op.drop_table("consultations")
