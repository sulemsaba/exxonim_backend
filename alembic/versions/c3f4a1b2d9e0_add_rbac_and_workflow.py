"""add rbac and workflow

Revision ID: c3f4a1b2d9e0
Revises: 9a4c2e7f1b8d
Create Date: 2026-04-04 18:25:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c3f4a1b2d9e0"
down_revision: Union[str, None] = "9a4c2e7f1b8d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("admin_users", sa.Column("full_name", sa.String(length=255), nullable=True))
    op.add_column("admin_users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_roles_code"),
    )
    op.create_index(op.f("ix_roles_code"), "roles", ["code"], unique=False)

    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("module", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_permissions_code"),
    )
    op.create_index(op.f("ix_permissions_code"), "permissions", ["code"], unique=False)

    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["admin_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "role_id"),
    )

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("actor_email", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("target_type", sa.String(length=120), nullable=True),
        sa.Column("target_id", sa.String(length=255), nullable=True),
        sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_logs_actor_id"), "audit_logs", ["actor_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_action"), "audit_logs", ["action"], unique=False)
    op.create_index(op.f("ix_audit_logs_target_type"), "audit_logs", ["target_type"], unique=False)
    op.create_index(op.f("ix_audit_logs_created_at"), "audit_logs", ["created_at"], unique=False)

    _add_workflow_columns(
        "pages",
        status_default="published",
        existing_publish_flag_column="is_published",
        archive_when_inactive=False,
        has_existing_published_at=False,
    )
    _add_workflow_columns(
        "blog_posts",
        status_default="draft",
        existing_publish_flag_column="is_published",
        archive_when_inactive=False,
        has_existing_published_at=True,
    )
    _add_workflow_columns(
        "testimonials",
        status_default="published",
        existing_publish_flag_column="is_active",
        archive_when_inactive=True,
        has_existing_published_at=False,
    )


def downgrade() -> None:
    _drop_workflow_columns("testimonials", has_existing_published_at=False)
    _drop_workflow_columns("blog_posts", has_existing_published_at=True)
    _drop_workflow_columns("pages", has_existing_published_at=False)

    op.drop_index(op.f("ix_audit_logs_created_at"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_target_type"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_action"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_actor_id"), table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_table("role_permissions")
    op.drop_table("user_roles")
    op.drop_index(op.f("ix_permissions_code"), table_name="permissions")
    op.drop_table("permissions")
    op.drop_index(op.f("ix_roles_code"), table_name="roles")
    op.drop_table("roles")
    op.drop_column("admin_users", "last_login_at")
    op.drop_column("admin_users", "full_name")


def _add_workflow_columns(
    table_name: str,
    *,
    status_default: str,
    existing_publish_flag_column: str,
    archive_when_inactive: bool,
    has_existing_published_at: bool,
) -> None:
    op.add_column(table_name, sa.Column("status", sa.String(length=32), nullable=True))
    op.add_column(table_name, sa.Column("created_by_id", sa.Integer(), nullable=True))
    op.add_column(table_name, sa.Column("updated_by_id", sa.Integer(), nullable=True))
    op.add_column(table_name, sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(table_name, sa.Column("submitted_by_id", sa.Integer(), nullable=True))
    op.add_column(table_name, sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(table_name, sa.Column("reviewed_by_id", sa.Integer(), nullable=True))
    if not has_existing_published_at:
        op.add_column(table_name, sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(table_name, sa.Column("published_by_id", sa.Integer(), nullable=True))

    op.create_foreign_key(
        f"fk_{table_name}_created_by_id_admin_users",
        table_name,
        "admin_users",
        ["created_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        f"fk_{table_name}_updated_by_id_admin_users",
        table_name,
        "admin_users",
        ["updated_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        f"fk_{table_name}_submitted_by_id_admin_users",
        table_name,
        "admin_users",
        ["submitted_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        f"fk_{table_name}_reviewed_by_id_admin_users",
        table_name,
        "admin_users",
        ["reviewed_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        f"fk_{table_name}_published_by_id_admin_users",
        table_name,
        "admin_users",
        ["published_by_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(op.f(f"ix_{table_name}_status"), table_name, ["status"], unique=False)
    op.create_index(op.f(f"ix_{table_name}_created_by_id"), table_name, ["created_by_id"], unique=False)
    op.create_index(op.f(f"ix_{table_name}_updated_by_id"), table_name, ["updated_by_id"], unique=False)
    op.create_index(op.f(f"ix_{table_name}_reviewed_by_id"), table_name, ["reviewed_by_id"], unique=False)
    op.create_index(op.f(f"ix_{table_name}_published_by_id"), table_name, ["published_by_id"], unique=False)

    if archive_when_inactive:
        op.execute(
            sa.text(
                f"""
                UPDATE {table_name}
                SET status = CASE
                    WHEN {existing_publish_flag_column} IS TRUE THEN 'published'
                    ELSE 'archived'
                END
                """
            )
        )
    else:
        op.execute(
            sa.text(
                f"""
                UPDATE {table_name}
                SET status = CASE
                    WHEN {existing_publish_flag_column} IS TRUE THEN 'published'
                    ELSE 'draft'
                END
                """
            )
        )

    op.execute(
        sa.text(
            f"""
            UPDATE {table_name}
            SET published_at = COALESCE(published_at, created_at)
            WHERE status = 'published'
            """
        )
    )

    op.alter_column(
        table_name,
        "status",
        existing_type=sa.String(length=32),
        nullable=False,
        server_default=sa.text(f"'{status_default}'"),
    )


def _drop_workflow_columns(table_name: str, *, has_existing_published_at: bool) -> None:
    op.drop_index(op.f(f"ix_{table_name}_published_by_id"), table_name=table_name)
    op.drop_index(op.f(f"ix_{table_name}_reviewed_by_id"), table_name=table_name)
    op.drop_index(op.f(f"ix_{table_name}_updated_by_id"), table_name=table_name)
    op.drop_index(op.f(f"ix_{table_name}_created_by_id"), table_name=table_name)
    op.drop_index(op.f(f"ix_{table_name}_status"), table_name=table_name)

    op.drop_constraint(f"fk_{table_name}_published_by_id_admin_users", table_name, type_="foreignkey")
    op.drop_constraint(f"fk_{table_name}_reviewed_by_id_admin_users", table_name, type_="foreignkey")
    op.drop_constraint(f"fk_{table_name}_submitted_by_id_admin_users", table_name, type_="foreignkey")
    op.drop_constraint(f"fk_{table_name}_updated_by_id_admin_users", table_name, type_="foreignkey")
    op.drop_constraint(f"fk_{table_name}_created_by_id_admin_users", table_name, type_="foreignkey")

    op.drop_column(table_name, "published_by_id")
    if not has_existing_published_at:
        op.drop_column(table_name, "published_at")
    op.drop_column(table_name, "reviewed_by_id")
    op.drop_column(table_name, "reviewed_at")
    op.drop_column(table_name, "submitted_by_id")
    op.drop_column(table_name, "submitted_at")
    op.drop_column(table_name, "updated_by_id")
    op.drop_column(table_name, "created_by_id")
    op.drop_column(table_name, "status")
