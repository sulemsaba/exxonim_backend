"""add reporting privacy and ops readiness foundation

Revision ID: bc23de45fa67
Revises: ab12cd34ef56
Create Date: 2026-04-06 15:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "bc23de45fa67"
down_revision = "ab12cd34ef56"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "privacy_consent_logs",
        sa.Column("consent_identifier", sa.String(length=64), nullable=False),
        sa.Column("policy_versions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("category_choices", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_path", sa.String(length=255), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_privacy_consent_logs_identifier", "privacy_consent_logs", ["consent_identifier"], unique=False)
    op.create_index("ix_privacy_consent_logs_created_at", "privacy_consent_logs", ["created_at"], unique=False)
    op.create_index(
        "ix_privacy_consent_logs_identifier_created_at",
        "privacy_consent_logs",
        ["consent_identifier", "created_at"],
        unique=False,
    )

    op.create_table(
        "privacy_requests",
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("request_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requester_name", sa.String(length=255), nullable=False),
        sa.Column("requester_email", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("internal_notes", sa.Text(), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("created_by_admin_id", sa.Integer(), nullable=False),
        sa.Column("completed_by_admin_id", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint(
            "request_type IN ('access', 'correction', 'deletion')",
            name="ck_privacy_requests_request_type",
        ),
        sa.CheckConstraint(
            "status IN ('received', 'verifying', 'in_progress', 'completed', 'rejected')",
            name="ck_privacy_requests_status",
        ),
        sa.ForeignKeyConstraint(["completed_by_admin_id"], ["admin_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_admin_id"], ["admin_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_privacy_requests_customer_id", "privacy_requests", ["customer_id"], unique=False)
    op.create_index("ix_privacy_requests_created_by_admin_id", "privacy_requests", ["created_by_admin_id"], unique=False)
    op.create_index("ix_privacy_requests_completed_by_admin_id", "privacy_requests", ["completed_by_admin_id"], unique=False)
    op.create_index("ix_privacy_requests_status", "privacy_requests", ["status"], unique=False)
    op.create_index("ix_privacy_requests_request_type", "privacy_requests", ["request_type"], unique=False)
    op.create_index("ix_privacy_requests_requester_email", "privacy_requests", ["requester_email"], unique=False)

    permission_statements = [
        (
            "report.read",
            "report",
            "read",
            "View operational reports in admin.",
        ),
        (
            "privacy_request.read",
            "privacy_request",
            "read",
            "View privacy requests.",
        ),
        (
            "privacy_request.manage",
            "privacy_request",
            "manage",
            "Create and update privacy requests.",
        ),
    ]
    for code, module, action, description in permission_statements:
        op.execute(
            sa.text(
                """
                INSERT INTO permissions (code, module, action, description, created_at, updated_at)
                SELECT :code, :module, :action, :description, now(), now()
                WHERE NOT EXISTS (
                    SELECT 1 FROM permissions WHERE code = :code
                )
                """
            ).bindparams(
                code=code,
                module=module,
                action=action,
                description=description,
            )
        )

    role_permissions = {
        "report.read": ("superuser", "administrator", "editor", "reviewer", "viewer"),
        "privacy_request.read": ("superuser", "administrator"),
        "privacy_request.manage": ("superuser", "administrator"),
    }
    for permission_code, role_codes in role_permissions.items():
        for role_code in role_codes:
            op.execute(
                sa.text(
                    """
                    INSERT INTO role_permissions (role_id, permission_id, created_at)
                    SELECT roles.id, permissions.id, now()
                    FROM roles
                    JOIN permissions ON permissions.code = :permission_code
                    WHERE roles.code = :role_code
                      AND NOT EXISTS (
                        SELECT 1
                        FROM role_permissions
                        WHERE role_permissions.role_id = roles.id
                          AND role_permissions.permission_id = permissions.id
                      )
                    """
                ).bindparams(permission_code=permission_code, role_code=role_code)
            )

    op.execute(
        sa.text(
            """
            INSERT INTO site_settings (key, value, created_at, updated_at)
            SELECT
              'policy_versions',
              '{"privacy_policy":"2026-04-v1","cookie_notice":"2026-04-v1","data_rights_notice":"2026-04-v1"}'::jsonb,
              now(),
              now()
            WHERE NOT EXISTS (
              SELECT 1 FROM site_settings WHERE key = 'policy_versions'
            )
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM role_permissions
            USING permissions
            WHERE role_permissions.permission_id = permissions.id
              AND permissions.code IN ('report.read', 'privacy_request.read', 'privacy_request.manage')
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM permissions
            WHERE code IN ('report.read', 'privacy_request.read', 'privacy_request.manage')
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM site_settings WHERE key = 'policy_versions'
            """
        )
    )

    op.drop_index("ix_privacy_requests_requester_email", table_name="privacy_requests")
    op.drop_index("ix_privacy_requests_request_type", table_name="privacy_requests")
    op.drop_index("ix_privacy_requests_status", table_name="privacy_requests")
    op.drop_index("ix_privacy_requests_completed_by_admin_id", table_name="privacy_requests")
    op.drop_index("ix_privacy_requests_created_by_admin_id", table_name="privacy_requests")
    op.drop_index("ix_privacy_requests_customer_id", table_name="privacy_requests")
    op.drop_table("privacy_requests")

    op.drop_index("ix_privacy_consent_logs_identifier_created_at", table_name="privacy_consent_logs")
    op.drop_index("ix_privacy_consent_logs_created_at", table_name="privacy_consent_logs")
    op.drop_index("ix_privacy_consent_logs_identifier", table_name="privacy_consent_logs")
    op.drop_table("privacy_consent_logs")
