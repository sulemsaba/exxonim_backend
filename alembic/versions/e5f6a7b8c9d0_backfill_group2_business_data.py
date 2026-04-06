"""backfill group2 business data

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-04-05 22:40:00.000000
"""

from __future__ import annotations

import re
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


STATUS_MAP = {
    "pending": "new",
    "contacted": "in_progress",
    "completed": "completed",
    "cancelled": "cancelled",
}

SERVICE_TYPE_KEYWORDS = (
    ("registration", ("register", "registration", "company setup", "incorporation")),
    ("licensing", ("license", "licensing", "permit", "renewal")),
    ("tax_returns", ("tax", "vat", "return", "returns", "tin")),
    ("compliance", ("compliance", "filing", "annual return", "secretarial")),
)


def _normalize_email(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _normalize_phone(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D+", "", value)
    return digits or None


def _infer_service_type_code(*parts: str | None) -> str:
    haystack = " ".join(part for part in parts if isinstance(part, str)).lower()
    for code, keywords in SERVICE_TYPE_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return code
    return "general_consultation"


def _build_title(row: dict[str, object]) -> str:
    company = (row.get("company") or "").strip() if isinstance(row.get("company"), str) else ""
    full_name = (row.get("full_name") or "Unknown customer").strip()
    if company:
        return f"{company} consultation request"
    return f"Consultation request from {full_name}"


def upgrade() -> None:
    connection = op.get_bind()
    fallback_admin_id = connection.execute(
        sa.text("SELECT id FROM admin_users ORDER BY id ASC LIMIT 1")
    ).scalar()

    service_types = {
        row["code"]: row["id"]
        for row in connection.execute(
            sa.text("SELECT id, code FROM service_types")
        ).mappings()
    }

    consultations = list(
        connection.execute(
            sa.text(
                """
                SELECT
                    id,
                    tracking_id,
                    full_name,
                    email,
                    phone,
                    company,
                    message,
                    status,
                    assigned_to,
                    notes,
                    public_notes,
                    created_at,
                    updated_at
                FROM consultations
                ORDER BY id ASC
                """
            )
        ).mappings()
    )

    consultation_history = list(
        connection.execute(
            sa.text(
                """
                SELECT
                    id,
                    consultation_id,
                    old_status,
                    new_status,
                    changed_by,
                    comment,
                    created_at
                FROM consultation_status_history
                ORDER BY created_at ASC, id ASC
                """
            )
        ).mappings()
    )
    consultations_with_history = {
        int(row["consultation_id"])
        for row in consultation_history
    }

    customers_table = sa.table(
        "customers",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("display_name", sa.String()),
        sa.column("primary_email", sa.String()),
        sa.column("normalized_email", sa.String()),
        sa.column("primary_phone", sa.String()),
        sa.column("normalized_phone", sa.String()),
        sa.column("company_name", sa.String()),
        sa.column("customer_kind", sa.String()),
        sa.column("source", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    service_requests_table = sa.table(
        "service_requests",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("customer_id", postgresql.UUID(as_uuid=True)),
        sa.column("tracking_id", sa.String()),
        sa.column("legacy_consultation_id", sa.Integer()),
        sa.column("service_type_id", postgresql.UUID(as_uuid=True)),
        sa.column("title", sa.String()),
        sa.column("intake_message", sa.Text()),
        sa.column("source_channel", sa.String()),
        sa.column("status", sa.String()),
        sa.column("priority", sa.String()),
        sa.column("opened_at", sa.DateTime(timezone=True)),
        sa.column("closed_at", sa.DateTime(timezone=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    assignments_table = sa.table(
        "service_request_assignments",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("service_request_id", postgresql.UUID(as_uuid=True)),
        sa.column("admin_user_id", sa.Integer()),
        sa.column("assignment_role", sa.String()),
        sa.column("assigned_at", sa.DateTime(timezone=True)),
    )
    status_history_table = sa.table(
        "service_request_status_history",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("service_request_id", postgresql.UUID(as_uuid=True)),
        sa.column("old_status", sa.String()),
        sa.column("new_status", sa.String()),
        sa.column("changed_by_admin_id", sa.Integer()),
        sa.column("comment", sa.Text()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    threads_table = sa.table(
        "inbox_threads",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("service_request_id", postgresql.UUID(as_uuid=True)),
        sa.column("thread_kind", sa.String()),
        sa.column("subject", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    messages_table = sa.table(
        "inbox_messages",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("thread_id", postgresql.UUID(as_uuid=True)),
        sa.column("direction", sa.String()),
        sa.column("channel", sa.String()),
        sa.column("body", sa.Text()),
        sa.column("customer_author_name", sa.String()),
        sa.column("customer_author_email", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    notes_table = sa.table(
        "notes",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("service_request_id", postgresql.UUID(as_uuid=True)),
        sa.column("visibility", sa.String()),
        sa.column("body", sa.Text()),
        sa.column("created_by_admin_id", sa.Integer()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )

    customer_ids_by_key: dict[str, object] = {}
    request_ids_by_consultation_id: dict[int, object] = {}

    for row in consultations:
        normalized_email = _normalize_email(row["email"])
        customer_lookup_key = normalized_email or f"legacy:{row['id']}"
        customer_id = customer_ids_by_key.get(customer_lookup_key)
        if customer_id is None:
            customer_id = uuid4()
            customer_ids_by_key[customer_lookup_key] = customer_id
            connection.execute(
                sa.insert(customers_table).values(
                    id=customer_id,
                    display_name=row["full_name"],
                    primary_email=row["email"],
                    normalized_email=normalized_email,
                    primary_phone=row["phone"],
                    normalized_phone=_normalize_phone(row["phone"]),
                    company_name=row["company"],
                    customer_kind="organization" if row["company"] else "individual",
                    source="migration_legacy",
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            )

        request_id = uuid4()
        request_ids_by_consultation_id[int(row["id"])] = request_id
        canonical_status = STATUS_MAP.get(row["status"], "new")
        closed_at = row["updated_at"] if canonical_status in {"completed", "cancelled"} else None
        service_type_code = _infer_service_type_code(
            row["company"],
            row["message"],
            row["notes"],
            row["public_notes"],
        )

        connection.execute(
            sa.insert(service_requests_table).values(
                id=request_id,
                customer_id=customer_id,
                tracking_id=row["tracking_id"],
                legacy_consultation_id=row["id"],
                service_type_id=service_types[service_type_code],
                title=_build_title(row),
                intake_message=row["message"],
                source_channel="migration_legacy",
                status=canonical_status,
                priority="normal",
                opened_at=row["created_at"],
                closed_at=closed_at,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        )

        if row["assigned_to"] is not None:
            connection.execute(
                sa.insert(assignments_table).values(
                    id=uuid4(),
                    service_request_id=request_id,
                    admin_user_id=row["assigned_to"],
                    assignment_role="lead",
                    assigned_at=row["updated_at"],
                )
            )

        thread_id = uuid4()
        connection.execute(
            sa.insert(threads_table).values(
                id=thread_id,
                service_request_id=request_id,
                thread_kind="primary",
                subject=_build_title(row),
                created_at=row["created_at"],
            )
        )
        if row["message"]:
            connection.execute(
                sa.insert(messages_table).values(
                    id=uuid4(),
                    thread_id=thread_id,
                    direction="inbound",
                    channel="system_seed",
                    body=row["message"],
                    customer_author_name=row["full_name"],
                    customer_author_email=row["email"],
                    created_at=row["created_at"],
                )
            )

        note_actor_id = row["assigned_to"] or fallback_admin_id
        if row["notes"] and note_actor_id is not None:
            connection.execute(
                sa.insert(notes_table).values(
                    id=uuid4(),
                    service_request_id=request_id,
                    visibility="internal",
                    body=row["notes"],
                    created_by_admin_id=note_actor_id,
                    created_at=row["updated_at"],
                )
            )
        if row["public_notes"] and note_actor_id is not None:
            connection.execute(
                sa.insert(notes_table).values(
                    id=uuid4(),
                    service_request_id=request_id,
                    visibility="customer_safe",
                    body=row["public_notes"],
                    created_by_admin_id=note_actor_id,
                    created_at=row["updated_at"],
                )
            )
        if int(row["id"]) not in consultations_with_history:
            connection.execute(
                sa.insert(status_history_table).values(
                    id=uuid4(),
                    service_request_id=request_id,
                    old_status=None,
                    new_status=canonical_status,
                    changed_by_admin_id=None,
                    comment="Initial request imported from legacy consultation.",
                    created_at=row["created_at"],
                )
            )

    for row in consultation_history:
        request_id = request_ids_by_consultation_id.get(int(row["consultation_id"]))
        if request_id is None:
            continue
        connection.execute(
            sa.insert(status_history_table).values(
                id=uuid4(),
                service_request_id=request_id,
                old_status=STATUS_MAP.get(row["old_status"]) if row["old_status"] else None,
                new_status=STATUS_MAP.get(row["new_status"], "new"),
                changed_by_admin_id=row["changed_by"],
                comment=row["comment"],
                created_at=row["created_at"],
            )
        )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM service_request_status_history"))
    op.execute(sa.text("DELETE FROM notes"))
    op.execute(sa.text("DELETE FROM inbox_messages"))
    op.execute(sa.text("DELETE FROM inbox_threads"))
    op.execute(sa.text("DELETE FROM service_request_assignments"))
    op.execute(sa.text("DELETE FROM service_requests"))
    op.execute(sa.text("DELETE FROM customers WHERE source = 'migration_legacy'"))
