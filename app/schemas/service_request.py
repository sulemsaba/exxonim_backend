from __future__ import annotations

from datetime import datetime
from math import ceil
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.admin import AdminUserOut


CustomerKind = Literal["individual", "organization"]
CustomerSource = Literal[
    "public_consultation_form",
    "public_contact_form",
    "admin_created",
    "migration_legacy",
]
ServiceRequestStatus = Literal[
    "new",
    "triaged",
    "waiting_customer",
    "in_progress",
    "completed",
    "cancelled",
]
ServiceRequestPriority = Literal["low", "normal", "high", "urgent"]
ServiceRequestSourceChannel = Literal[
    "public_consultation_form",
    "public_contact_form",
    "admin_created",
    "migration_legacy",
]
ServiceRequestQueueView = Literal[
    "all_active",
    "mine",
    "assigned",
    "unassigned",
    "unread",
    "completed",
]
ServiceRequestSort = Literal["last_activity", "opened_at", "priority"]
SortOrder = Literal["asc", "desc"]
AssignmentRole = Literal["lead", "collaborator"]
InboxThreadKind = Literal["primary"]
MessageDirection = Literal["inbound", "outbound", "internal"]
MessageChannel = Literal["web_form", "admin_manual", "system_seed"]
NoteVisibility = Literal["internal", "customer_safe"]
DocumentClassification = Literal[
    "customer_upload",
    "internal_attachment",
    "generated_document",
    "compliance_proof",
]
TimelineScopeType = Literal["customer", "service_request"]


class ServiceTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    label: str
    is_active: bool
    sort_order: int
    created_at: datetime


class CustomerBase(BaseModel):
    display_name: str
    primary_email: str | None = None
    primary_phone: str | None = None
    company_name: str | None = None
    customer_kind: CustomerKind = "individual"
    source: CustomerSource = "admin_created"


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    display_name: str | None = None
    primary_email: str | None = None
    primary_phone: str | None = None
    company_name: str | None = None
    customer_kind: CustomerKind | None = None
    source: CustomerSource | None = None


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    display_name: str
    primary_email: str | None = None
    normalized_email: str | None = None
    primary_phone: str | None = None
    normalized_phone: str | None = None
    company_name: str | None = None
    customer_kind: CustomerKind
    source: CustomerSource
    created_at: datetime
    updated_at: datetime


class ServiceRequestAssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    assignment_role: AssignmentRole
    assigned_at: datetime
    unassigned_at: datetime | None = None
    admin_user: AdminUserOut
    assigned_by_admin: AdminUserOut | None = None


class ServiceRequestAssignmentCreate(BaseModel):
    admin_user_id: int
    assignment_role: AssignmentRole = "collaborator"


class ServiceRequestAssignmentUpdate(BaseModel):
    unassigned_at: datetime | None = None


class ServiceRequestStatusHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    old_status: ServiceRequestStatus | None = None
    new_status: ServiceRequestStatus
    comment: str | None = None
    created_at: datetime
    changed_by_admin: AdminUserOut | None = None


class InboxMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    direction: MessageDirection
    channel: MessageChannel
    body: str
    author_admin: AdminUserOut | None = None
    customer_author_name: str | None = None
    customer_author_email: str | None = None
    created_at: datetime


class InboxMessageCreate(BaseModel):
    direction: MessageDirection = "internal"
    channel: MessageChannel = "admin_manual"
    body: str
    customer_author_name: str | None = None
    customer_author_email: str | None = None


class InboxThreadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    thread_kind: InboxThreadKind
    subject: str | None = None
    created_at: datetime
    messages: list[InboxMessageOut] = Field(default_factory=list)


class RecordNoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID | None = None
    service_request_id: UUID | None = None
    visibility: NoteVisibility
    body: str
    created_at: datetime
    created_by_admin: AdminUserOut


class RecordNoteCreate(BaseModel):
    visibility: NoteVisibility = "internal"
    body: str


class RecordDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID | None = None
    service_request_id: UUID | None = None
    classification: DocumentClassification
    storage_key: str
    original_filename: str
    mime_type: str
    file_size: int
    created_at: datetime
    uploaded_by_admin: AdminUserOut
    download_url: str | None = None


class TimelineEventOut(BaseModel):
    id: str
    event_type: str
    scope_type: TimelineScopeType
    scope_id: UUID
    actor_name: str
    actor_type: str
    summary: str
    body: str | None = None
    created_at: datetime
    related_record_type: str | None = None
    related_record_id: str | None = None


class ServiceRequestBase(BaseModel):
    customer_id: UUID
    service_type_id: UUID
    title: str
    intake_message: str | None = None
    source_channel: ServiceRequestSourceChannel = "admin_created"
    priority: ServiceRequestPriority = "normal"
    due_at: datetime | None = None
    target_response_at: datetime | None = None


class ServiceRequestCreate(ServiceRequestBase):
    status: ServiceRequestStatus = "new"


class ServiceRequestUpdate(BaseModel):
    title: str | None = None
    service_type_id: UUID | None = None
    intake_message: str | None = None
    priority: ServiceRequestPriority | None = None
    due_at: datetime | None = None
    target_response_at: datetime | None = None
    closed_reason: str | None = None


class ServiceRequestStatusUpdate(BaseModel):
    status: ServiceRequestStatus
    comment: str | None = None


class ServiceRequestMarkReadResponse(BaseModel):
    service_request_id: UUID
    unread: bool
    unread_count: int
    last_read_at: datetime


class BulkAssignPayload(BaseModel):
    request_ids: list[UUID] = Field(default_factory=list)
    admin_user_id: int
    assignment_role: AssignmentRole = "lead"


class BulkPriorityPayload(BaseModel):
    request_ids: list[UUID] = Field(default_factory=list)
    priority: ServiceRequestPriority


class BulkStatusPayload(BaseModel):
    request_ids: list[UUID] = Field(default_factory=list)
    status: ServiceRequestStatus
    comment: str | None = None


class BulkMarkReadPayload(BaseModel):
    request_ids: list[UUID] = Field(default_factory=list)


class BulkActionResult(BaseModel):
    requested: int
    updated: int
    skipped: int
    request_ids: list[UUID] = Field(default_factory=list)


class DashboardWorklistItemOut(BaseModel):
    key: str
    label: str
    count: int
    href: str | None = None
    tone: Literal["default", "info", "warning", "error"] = "default"
    description: str | None = None


class ReviewQueueItemOut(BaseModel):
    id: str
    content_type: Literal["page", "blog_post", "testimonial"]
    title: str
    status: str
    submitted_at: datetime | None = None
    submitted_by: str | None = None
    href: str | None = None


class ServiceRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    tracking_id: str
    legacy_consultation_id: int | None = None
    service_type_id: UUID
    title: str
    intake_message: str | None = None
    source_channel: ServiceRequestSourceChannel
    status: ServiceRequestStatus
    priority: ServiceRequestPriority
    opened_at: datetime
    closed_at: datetime | None = None
    last_activity_at: datetime
    last_customer_message_at: datetime | None = None
    due_at: datetime | None = None
    target_response_at: datetime | None = None
    closed_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    customer: CustomerOut
    service_type: ServiceTypeOut
    created_by_admin: AdminUserOut | None = None
    status_history: list[ServiceRequestStatusHistoryOut] = Field(default_factory=list)
    assignments: list[ServiceRequestAssignmentOut] = Field(default_factory=list)
    threads: list[InboxThreadOut] = Field(default_factory=list)
    notes: list[RecordNoteOut] = Field(default_factory=list)
    documents: list[RecordDocumentOut] = Field(default_factory=list)
    timeline: list[TimelineEventOut] = Field(default_factory=list)
    unread: bool = False
    unread_count: int = 0


class CustomerListResponse(BaseModel):
    items: list[CustomerOut]
    page: int
    limit: int
    total: int
    total_pages: int

    @classmethod
    def build(
        cls,
        *,
        items: list[CustomerOut],
        page: int,
        limit: int,
        total: int,
    ) -> "CustomerListResponse":
        return cls(
            items=items,
            page=page,
            limit=limit,
            total=total,
            total_pages=0 if total == 0 else ceil(total / max(limit, 1)),
        )


class ServiceRequestListResponse(BaseModel):
    items: list[ServiceRequestOut]
    page: int
    limit: int
    total: int
    total_pages: int

    @classmethod
    def build(
        cls,
        *,
        items: list[ServiceRequestOut],
        page: int,
        limit: int,
        total: int,
    ) -> "ServiceRequestListResponse":
        return cls(
            items=items,
            page=page,
            limit=limit,
            total=total,
            total_pages=0 if total == 0 else ceil(total / max(limit, 1)),
        )
