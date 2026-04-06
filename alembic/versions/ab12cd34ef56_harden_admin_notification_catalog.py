"""harden admin notification catalog

Revision ID: ab12cd34ef56
Revises: fa1b2c3d4e5f
Create Date: 2026-04-06 13:15:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "ab12cd34ef56"
down_revision = "fa1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_admin_notifications_severity",
        "admin_notifications",
        type_="check",
    )
    op.create_check_constraint(
        "ck_admin_notifications_severity",
        "admin_notifications",
        "severity IN ('info', 'success', 'warning', 'error')",
    )
    op.create_check_constraint(
        "ck_admin_notifications_event_type",
        "admin_notifications",
        "event_type IN ("
        "'request.submitted', "
        "'request.inbound_message', "
        "'request.assigned', "
        "'request.overdue', "
        "'content.pending_review', "
        "'security.suspicious_login', "
        "'security.admin_role_changed', "
        "'security.admin_status_changed', "
        "'report.generated'"
        ")",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_admin_notifications_event_type",
        "admin_notifications",
        type_="check",
    )
    op.drop_constraint(
        "ck_admin_notifications_severity",
        "admin_notifications",
        type_="check",
    )
    op.create_check_constraint(
        "ck_admin_notifications_severity",
        "admin_notifications",
        "severity IN ('info', 'warning', 'error')",
    )
