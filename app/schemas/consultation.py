from __future__ import annotations

from datetime import datetime
from math import ceil
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.admin import AdminUserOut
from app.schemas.service_request import (
    CustomerOut,
    InboxMessageOut,
    RecordDocumentOut,
    RecordNoteOut,
    ServiceRequestAssignmentOut,
    ServiceTypeOut,
    TimelineEventOut,
)


ConsultationStatus = Literal["pending", "contacted", "completed", "cancelled"]


class ConsultationStatusHistoryOut(BaseModel):
    id: str
    old_status: ConsultationStatus | None = None
    new_status: ConsultationStatus
    comment: str | None = None
    created_at: datetime
    changed_by_admin: AdminUserOut | None = None


class ConsultationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tracking_id: str
    idempotency_key: str
    full_name: str
    email: str
    phone: str | None = None
    company: str | None = None
    message: str
    status: ConsultationStatus
    assigned_to: int | None = None
    notes: str | None = None
    public_notes: str | None = None
    created_at: datetime
    updated_at: datetime
    assigned_admin: AdminUserOut | None = None
    status_history: list[ConsultationStatusHistoryOut] = Field(default_factory=list)
    customer_id: UUID | None = None
    service_request_id: UUID | None = None
    customer: CustomerOut | None = None
    service_type: ServiceTypeOut | None = None
    priority: str | None = None
    source_channel: str | None = None
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    last_activity_at: datetime | None = None
    last_customer_message_at: datetime | None = None
    unread: bool = False
    unread_count: int = 0
    assignments: list[ServiceRequestAssignmentOut] = Field(default_factory=list)
    messages: list[InboxMessageOut] = Field(default_factory=list)
    notes_records: list[RecordNoteOut] = Field(default_factory=list)
    documents: list[RecordDocumentOut] = Field(default_factory=list)
    timeline: list[TimelineEventOut] = Field(default_factory=list)


class ConsultationUpdate(BaseModel):
    status: ConsultationStatus | None = None
    assigned_to: int | None = None
    notes: str | None = None
    public_notes: str | None = None
    comment: str | None = None


class PublicConsultationCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    email: str = Field(min_length=5, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    company: str | None = Field(default=None, max_length=255)
    service_type_code: str | None = Field(default=None, max_length=100)
    message: str = Field(min_length=12, max_length=5000)
    idempotency_key: str | None = Field(default=None, max_length=255)
    source_channel: Literal["public_consultation_form", "public_contact_form"] = (
        "public_contact_form"
    )


class PublicConsultationCreateResponse(BaseModel):
    consultation_id: int
    service_request_id: UUID
    tracking_id: str
    status: ConsultationStatus
    message: str
    received_at: datetime


class ConsultationListResponse(BaseModel):
    items: list[ConsultationOut]
    page: int
    limit: int
    total: int
    total_pages: int

    @classmethod
    def build(
        cls,
        *,
        items: list[ConsultationOut],
        page: int,
        limit: int,
        total: int,
    ) -> "ConsultationListResponse":
        return cls(
            items=items,
            page=page,
            limit=limit,
            total=total,
            total_pages=0 if total == 0 else ceil(total / max(limit, 1)),
        )
