"""add group2 core entities

Revision ID: a1b2c3d4e5f6
Revises: f7b6c5d4e3a2
Create Date: 2026-04-05 22:10:00.000000
"""

from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "a1b2c3d4e5f6"
down_revision = "f7b6c5d4e3a2"
branch_labels = None
depends_on = None


SERVICE_TYPE_SEEDS = [
    ("registration", "Registration", 10),
    ("licensing", "Licensing", 20),
    ("tax_returns", "Tax Returns", 30),
    ("compliance", "Compliance", 40),
    ("general_consultation", "General Consultation", 50),
]


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("primary_email", sa.String(length=255), nullable=True),
        sa.Column("normalized_email", sa.String(length=255), nullable=True),
        sa.Column("primary_phone", sa.String(length=64), nullable=True),
        sa.Column("normalized_phone", sa.String(length=64), nullable=True),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("customer_kind", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "customer_kind IN ('individual', 'organization')",
            name="ck_customers_customer_kind",
        ),
        sa.CheckConstraint(
            "source IN ('public_consultation_form', 'public_contact_form', 'admin_created', 'migration_legacy')",
            name="ck_customers_source",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_customers_normalized_email", "customers", ["normalized_email"], unique=False)
    op.create_index("ix_customers_normalized_phone", "customers", ["normalized_phone"], unique=False)
    op.create_index("ix_customers_company_name", "customers", ["company_name"], unique=False)
    op.create_index("ix_customers_created_at", "customers", ["created_at"], unique=False)

    op.create_table(
        "service_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_service_types_code"),
    )
    op.create_index("ix_service_types_code", "service_types", ["code"], unique=False)

    op.create_table(
        "service_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tracking_id", sa.String(length=64), nullable=False),
        sa.Column("legacy_consultation_id", sa.Integer(), nullable=True),
        sa.Column("service_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("intake_message", sa.Text(), nullable=True),
        sa.Column("source_channel", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="normal"),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("target_response_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_reason", sa.Text(), nullable=True),
        sa.Column("created_by_admin_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('new', 'triaged', 'waiting_customer', 'in_progress', 'completed', 'cancelled')",
            name="ck_service_requests_status",
        ),
        sa.CheckConstraint(
            "priority IN ('low', 'normal', 'high', 'urgent')",
            name="ck_service_requests_priority",
        ),
        sa.CheckConstraint(
            "source_channel IN ('public_consultation_form', 'public_contact_form', 'admin_created', 'migration_legacy')",
            name="ck_service_requests_source_channel",
        ),
        sa.CheckConstraint(
            "(status NOT IN ('completed', 'cancelled')) OR closed_at IS NOT NULL",
            name="ck_service_requests_closed_status",
        ),
        sa.ForeignKeyConstraint(["created_by_admin_id"], ["admin_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["legacy_consultation_id"], ["consultations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["service_type_id"], ["service_types.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tracking_id", name="uq_service_requests_tracking_id"),
        sa.UniqueConstraint("legacy_consultation_id", name="uq_service_requests_legacy_consultation_id"),
    )
    op.create_index("ix_service_requests_customer_id", "service_requests", ["customer_id"], unique=False)
    op.create_index("ix_service_requests_service_type_id", "service_requests", ["service_type_id"], unique=False)
    op.create_index("ix_service_requests_status", "service_requests", ["status"], unique=False)
    op.create_index("ix_service_requests_priority", "service_requests", ["priority"], unique=False)
    op.create_index("ix_service_requests_opened_at", "service_requests", ["opened_at"], unique=False)
    op.create_index("ix_service_requests_closed_at", "service_requests", ["closed_at"], unique=False)
    op.create_index(
        "ix_service_requests_legacy_consultation_id",
        "service_requests",
        ["legacy_consultation_id"],
        unique=False,
    )
    op.execute(
        sa.text(
            """
            CREATE INDEX ix_service_requests_status_priority_opened_at
            ON service_requests (status, priority, opened_at DESC)
            """
        )
    )

    service_types = sa.table(
        "service_types",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String()),
        sa.column("label", sa.String()),
        sa.column("is_active", sa.Boolean()),
        sa.column("sort_order", sa.Integer()),
    )
    connection = op.get_bind()
    connection.execute(
        sa.insert(service_types),
        [
            {
                "id": uuid4(),
                "code": code,
                "label": label,
                "is_active": True,
                "sort_order": sort_order,
            }
            for code, label, sort_order in SERVICE_TYPE_SEEDS
        ],
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_service_requests_status_priority_opened_at"))
    op.drop_index("ix_service_requests_legacy_consultation_id", table_name="service_requests")
    op.drop_index("ix_service_requests_closed_at", table_name="service_requests")
    op.drop_index("ix_service_requests_opened_at", table_name="service_requests")
    op.drop_index("ix_service_requests_priority", table_name="service_requests")
    op.drop_index("ix_service_requests_status", table_name="service_requests")
    op.drop_index("ix_service_requests_service_type_id", table_name="service_requests")
    op.drop_index("ix_service_requests_customer_id", table_name="service_requests")
    op.drop_table("service_requests")

    op.drop_index("ix_service_types_code", table_name="service_types")
    op.drop_table("service_types")

    op.drop_index("ix_customers_created_at", table_name="customers")
    op.drop_index("ix_customers_company_name", table_name="customers")
    op.drop_index("ix_customers_normalized_phone", table_name="customers")
    op.drop_index("ix_customers_normalized_email", table_name="customers")
    op.drop_table("customers")
