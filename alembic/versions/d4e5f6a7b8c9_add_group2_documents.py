"""add group2 documents

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-05 22:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("service_request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("classification", sa.String(length=32), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=127), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("uploaded_by_admin_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "classification IN ('customer_upload', 'internal_attachment', 'generated_document', 'compliance_proof')",
            name="ck_documents_classification",
        ),
        sa.CheckConstraint(
            "(customer_id IS NOT NULL) <> (service_request_id IS NOT NULL)",
            name="ck_documents_exactly_one_target",
        ),
        sa.CheckConstraint("file_size > 0", name="ck_documents_file_size"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["service_request_id"], ["service_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_admin_id"], ["admin_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key", name="uq_documents_storage_key"),
    )
    op.create_index("ix_documents_customer_id", "documents", ["customer_id"], unique=False)
    op.create_index("ix_documents_service_request_id", "documents", ["service_request_id"], unique=False)
    op.create_index("ix_documents_classification", "documents", ["classification"], unique=False)
    op.create_index("ix_documents_created_at", "documents", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_documents_created_at", table_name="documents")
    op.drop_index("ix_documents_classification", table_name="documents")
    op.drop_index("ix_documents_service_request_id", table_name="documents")
    op.drop_index("ix_documents_customer_id", table_name="documents")
    op.drop_table("documents")
