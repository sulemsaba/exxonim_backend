from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    AdminUser,
    AuditLog,
    Customer,
    InboxMessage,
    InboxThread,
    RecordDocument,
    RecordNote,
    ServiceRequest,
    ServiceRequestAssignment,
    ServiceRequestInboxState,
    ServiceRequestStatusHistory,
    ServiceType,
)
from app.schemas.service_request import (
    CustomerCreate,
    CustomerUpdate,
    InboxMessageCreate,
    RecordNoteCreate,
    ServiceRequestAssignmentCreate,
    ServiceRequestCreate,
    ServiceRequestMarkReadResponse,
    ServiceRequestPriority,
    ServiceRequestStatusUpdate,
    ServiceRequestUpdate,
)


COMPATIBILITY_STATUS_TO_REQUEST_STATUS = {
    "pending": "new",
    "contacted": "in_progress",
    "completed": "completed",
    "cancelled": "cancelled",
}

REQUEST_STATUS_TO_COMPATIBILITY_STATUS = {
    "new": "pending",
    "triaged": "contacted",
    "waiting_customer": "contacted",
    "in_progress": "contacted",
    "completed": "completed",
    "cancelled": "cancelled",
}

DEFAULT_SERVICE_TYPE_BY_KEYWORD = (
    ("registration", ("register", "registration", "company setup", "incorporation")),
    ("licensing", ("license", "licensing", "permit", "renewal")),
    ("tax_returns", ("tax", "vat", "return", "returns", "tin")),
    ("compliance", ("compliance", "filing", "annual return", "secretarial")),
)

ACTIVE_SERVICE_REQUEST_STATUSES = {
    "new",
    "triaged",
    "waiting_customer",
    "in_progress",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    return normalized or None


def normalize_phone(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D+", "", value)
    return digits or None


def compatibility_status_from_service_request_status(status: str) -> str:
    return REQUEST_STATUS_TO_COMPATIBILITY_STATUS.get(status, "pending")


def infer_service_type_code_from_text(*parts: str | None) -> str:
    haystack = " ".join(part for part in parts if isinstance(part, str)).lower()
    for code, keywords in DEFAULT_SERVICE_TYPE_BY_KEYWORD:
        if any(keyword in haystack for keyword in keywords):
            return code
    return "general_consultation"


def is_customer_message(message: InboxMessage) -> bool:
    return message.direction == "inbound"


def touch_service_request_activity(
    service_request: ServiceRequest,
    *,
    occurred_at: datetime | None = None,
    customer_message_at: datetime | None = None,
) -> None:
    timestamp = occurred_at or utcnow()
    service_request.last_activity_at = timestamp
    if customer_message_at is not None:
        current = service_request.last_customer_message_at
        if current is None or customer_message_at >= current:
            service_request.last_customer_message_at = customer_message_at


def get_primary_thread_for_request(service_request: ServiceRequest) -> InboxThread | None:
    threads = service_request.__dict__.get("threads")
    if threads is None:
        return None
    return next(
        (thread for thread in threads if thread.thread_kind == "primary"),
        None,
    )


def get_inbox_state(
    service_request: ServiceRequest,
    admin_user_id: int,
) -> ServiceRequestInboxState | None:
    inbox_states = service_request.__dict__.get("inbox_states") or []
    return next(
        (
            state
            for state in inbox_states
            if state.admin_user_id == admin_user_id
        ),
        None,
    )


def get_unread_customer_message_count(
    service_request: ServiceRequest,
    admin_user_id: int,
) -> int:
    primary_thread = get_primary_thread_for_request(service_request)
    inbox_state = get_inbox_state(service_request, admin_user_id)
    if primary_thread is None:
        if service_request.last_customer_message_at is None:
            return 0
        if inbox_state is None or inbox_state.last_read_at is None:
            return 1
        return 1 if inbox_state.last_read_at < service_request.last_customer_message_at else 0

    customer_messages = [
        message
        for message in (primary_thread.messages if primary_thread else [])
        if is_customer_message(message)
    ]
    if not customer_messages:
        return 0

    if inbox_state is None or inbox_state.last_read_at is None:
        return len(customer_messages)

    return sum(1 for message in customer_messages if message.created_at > inbox_state.last_read_at)


def get_unread_summary(
    service_request: ServiceRequest,
    admin_user_id: int,
) -> tuple[bool, int]:
    unread_count = get_unread_customer_message_count(service_request, admin_user_id)
    if unread_count:
        return True, unread_count

    inbox_state = get_inbox_state(service_request, admin_user_id)
    if service_request.last_customer_message_at is None:
        return False, 0
    if inbox_state is None or inbox_state.last_read_at is None:
        return True, 1
    if inbox_state.last_read_at < service_request.last_customer_message_at:
        return True, 1
    return False, 0


def _service_request_select(*, include_related: bool = False):
    statement = select(ServiceRequest).options(
        selectinload(ServiceRequest.customer),
        selectinload(ServiceRequest.service_type),
        selectinload(ServiceRequest.created_by_admin),
        selectinload(ServiceRequest.assignments).selectinload(ServiceRequestAssignment.admin_user),
        selectinload(ServiceRequest.assignments).selectinload(
            ServiceRequestAssignment.assigned_by_admin
        ),
        selectinload(ServiceRequest.inbox_states).selectinload(
            ServiceRequestInboxState.last_read_message
        ),
    )

    if include_related:
        statement = statement.options(
            selectinload(ServiceRequest.status_history).selectinload(
                ServiceRequestStatusHistory.changed_by_admin
            ),
            selectinload(ServiceRequest.threads)
            .selectinload(InboxThread.messages)
            .selectinload(InboxMessage.author_admin),
            selectinload(ServiceRequest.notes).selectinload(RecordNote.created_by_admin),
            selectinload(ServiceRequest.documents).selectinload(
                RecordDocument.uploaded_by_admin
            ),
        )

    return statement


async def get_service_types(db: AsyncSession) -> list[ServiceType]:
    result = await db.execute(
        select(ServiceType).order_by(ServiceType.sort_order.asc(), ServiceType.label.asc())
    )
    return list(result.scalars().all())


async def get_service_type_by_id(db: AsyncSession, service_type_id: UUID) -> ServiceType | None:
    result = await db.execute(select(ServiceType).where(ServiceType.id == service_type_id))
    return result.scalar_one_or_none()


async def get_service_type_by_code(db: AsyncSession, code: str) -> ServiceType | None:
    result = await db.execute(select(ServiceType).where(ServiceType.code == code))
    return result.scalar_one_or_none()


async def get_or_create_service_type_by_code(db: AsyncSession, code: str) -> ServiceType:
    existing = await get_service_type_by_code(db, code)
    if existing is not None:
        return existing

    label = code.replace("_", " ").title()
    service_type = ServiceType(code=code, label=label, is_active=True)
    db.add(service_type)
    await db.flush()
    return service_type


async def list_customers(
    db: AsyncSession,
    *,
    page: int = 1,
    limit: int = 20,
    search: str | None = None,
) -> tuple[list[Customer], int]:
    safe_page = max(page, 1)
    safe_limit = max(min(limit, 100), 1)
    base_query = select(Customer.id)

    if search:
        term = f"%{search.strip().lower()}%"
        base_query = base_query.where(
            or_(
                func.lower(Customer.display_name).like(term),
                func.lower(func.coalesce(Customer.primary_email, "")).like(term),
                func.lower(func.coalesce(Customer.company_name, "")).like(term),
            )
        )

    total = int(await db.scalar(select(func.count()).select_from(base_query.subquery())) or 0)
    result = await db.execute(
        select(Customer)
        .where(Customer.id.in_(base_query.offset((safe_page - 1) * safe_limit).limit(safe_limit)))
        .order_by(Customer.updated_at.desc(), Customer.created_at.desc())
    )
    return list(result.scalars().all()), total


async def get_customer_by_id(
    db: AsyncSession,
    customer_id: UUID,
    *,
    include_requests: bool = False,
) -> Customer | None:
    statement = select(Customer)
    if include_requests:
        statement = statement.options(
            selectinload(Customer.service_requests)
            .selectinload(ServiceRequest.service_type),
            selectinload(Customer.service_requests)
            .selectinload(ServiceRequest.assignments)
            .selectinload(ServiceRequestAssignment.admin_user),
            selectinload(Customer.notes).selectinload(RecordNote.created_by_admin),
            selectinload(Customer.documents).selectinload(RecordDocument.uploaded_by_admin),
        )

    result = await db.execute(statement.where(Customer.id == customer_id))
    return result.scalar_one_or_none()


async def get_customer_by_normalized_email(
    db: AsyncSession,
    normalized_email: str | None,
) -> Customer | None:
    if not normalized_email:
        return None
    result = await db.execute(
        select(Customer).where(Customer.normalized_email == normalized_email)
    )
    return result.scalar_one_or_none()


async def create_customer(db: AsyncSession, payload: CustomerCreate) -> Customer:
    customer = Customer(
        display_name=payload.display_name,
        primary_email=payload.primary_email,
        normalized_email=normalize_email(payload.primary_email),
        primary_phone=payload.primary_phone,
        normalized_phone=normalize_phone(payload.primary_phone),
        company_name=payload.company_name,
        customer_kind=payload.customer_kind,
        source=payload.source,
    )
    db.add(customer)
    await db.flush()
    return customer


async def update_customer(db: AsyncSession, customer: Customer, payload: CustomerUpdate) -> Customer:
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "primary_email":
            customer.primary_email = value
            customer.normalized_email = normalize_email(value)
            continue
        if field == "primary_phone":
            customer.primary_phone = value
            customer.normalized_phone = normalize_phone(value)
            continue
        setattr(customer, field, value)
    db.add(customer)
    await db.flush()
    return customer


async def list_service_requests(
    db: AsyncSession,
    *,
    page: int = 1,
    limit: int = 20,
    search: str | None = None,
    status: str | None = None,
    service_type_code: str | None = None,
    priority: str | None = None,
    assignee_id: int | None = None,
    source_channel: str | None = None,
    view: str | None = None,
    current_admin_id: int | None = None,
    sort: str = "last_activity",
    order: str = "desc",
    include_related: bool = False,
) -> tuple[list[ServiceRequest], int]:
    safe_page = max(page, 1)
    safe_limit = max(min(limit, 100), 1)

    base_query = select(ServiceRequest.id).join(Customer).join(ServiceType)
    active_assignment_condition = and_(
        ServiceRequestAssignment.service_request_id == ServiceRequest.id,
        ServiceRequestAssignment.unassigned_at.is_(None),
    )

    if assignee_id is not None:
        base_query = base_query.join(
            ServiceRequestAssignment,
            active_assignment_condition,
        ).where(ServiceRequestAssignment.admin_user_id == assignee_id)

    if status:
        base_query = base_query.where(ServiceRequest.status == status)
    if service_type_code:
        base_query = base_query.where(ServiceType.code == service_type_code)
    if priority:
        base_query = base_query.where(ServiceRequest.priority == priority)
    if source_channel:
        base_query = base_query.where(ServiceRequest.source_channel == source_channel)
    if search:
        term = f"%{search.strip().lower()}%"
        base_query = base_query.where(
            or_(
                func.lower(ServiceRequest.tracking_id).like(term),
                func.lower(ServiceRequest.title).like(term),
                func.lower(func.coalesce(ServiceRequest.intake_message, "")).like(term),
                func.lower(Customer.display_name).like(term),
                func.lower(func.coalesce(Customer.primary_email, "")).like(term),
                func.lower(func.coalesce(Customer.company_name, "")).like(term),
            )
        )

    if view == "mine" and current_admin_id is not None:
        base_query = base_query.where(
            select(ServiceRequestAssignment.id)
            .where(
                active_assignment_condition,
                ServiceRequestAssignment.admin_user_id == current_admin_id,
            )
            .exists()
        )
    elif view == "assigned":
        base_query = base_query.where(
            select(ServiceRequestAssignment.id)
            .where(active_assignment_condition)
            .exists()
        )
    elif view == "unassigned":
        base_query = base_query.where(
            ~select(ServiceRequestAssignment.id)
            .where(active_assignment_condition)
            .exists()
        )
    elif view == "completed":
        base_query = base_query.where(ServiceRequest.status.in_(("completed", "cancelled")))
    elif view == "all_active":
        base_query = base_query.where(ServiceRequest.status.in_(tuple(ACTIVE_SERVICE_REQUEST_STATUSES)))

    if view == "unread" and current_admin_id is not None:
        base_query = base_query.outerjoin(
            ServiceRequestInboxState,
            and_(
                ServiceRequestInboxState.service_request_id == ServiceRequest.id,
                ServiceRequestInboxState.admin_user_id == current_admin_id,
            ),
        ).where(
            ServiceRequest.last_customer_message_at.is_not(None),
            or_(
                ServiceRequestInboxState.id.is_(None),
                ServiceRequestInboxState.last_read_at.is_(None),
                ServiceRequestInboxState.last_read_at < ServiceRequest.last_customer_message_at,
            ),
        )

    base_query = base_query.distinct()

    if sort == "opened_at":
        sort_column = ServiceRequest.opened_at
    elif sort == "priority":
        sort_column = ServiceRequest.priority
    else:
        sort_column = ServiceRequest.last_activity_at

    order_by = sort_column.asc() if order == "asc" else sort_column.desc()
    total = int(await db.scalar(select(func.count()).select_from(base_query.subquery())) or 0)
    ids_result = await db.execute(
        base_query.order_by(order_by, ServiceRequest.created_at.desc())
        .offset((safe_page - 1) * safe_limit)
        .limit(safe_limit)
    )
    ids = list(ids_result.scalars().all())
    if not ids:
        return [], total

    result = await db.execute(
        _service_request_select(include_related=include_related)
        .where(ServiceRequest.id.in_(ids))
        .order_by(order_by, ServiceRequest.created_at.desc())
    )
    return list(result.scalars().unique().all()), total


async def get_service_request_by_id(
    db: AsyncSession,
    service_request_id: UUID,
    *,
    include_related: bool = False,
) -> ServiceRequest | None:
    result = await db.execute(
        _service_request_select(include_related=include_related).where(
            ServiceRequest.id == service_request_id
        )
    )
    return result.scalar_one_or_none()


async def get_service_request_by_legacy_consultation_id(
    db: AsyncSession,
    legacy_consultation_id: int,
    *,
    include_related: bool = False,
) -> ServiceRequest | None:
    result = await db.execute(
        _service_request_select(include_related=include_related).where(
            ServiceRequest.legacy_consultation_id == legacy_consultation_id
        )
    )
    return result.scalar_one_or_none()


async def _generate_tracking_id(db: AsyncSession) -> str:
    while True:
        candidate = f"SR-{uuid4().hex[:8].upper()}"
        existing = await db.scalar(
            select(func.count()).select_from(
                select(ServiceRequest.id)
                .where(ServiceRequest.tracking_id == candidate)
                .subquery()
            )
        )
        if not existing:
            return candidate


async def create_service_request(
    db: AsyncSession,
    *,
    payload: ServiceRequestCreate,
    created_by_admin: AdminUser | None = None,
    legacy_consultation_id: int | None = None,
) -> ServiceRequest:
    opened_at = utcnow()
    service_request = ServiceRequest(
        customer_id=payload.customer_id,
        tracking_id=await _generate_tracking_id(db),
        legacy_consultation_id=legacy_consultation_id,
        service_type_id=payload.service_type_id,
        title=payload.title,
        intake_message=payload.intake_message,
        source_channel=payload.source_channel,
        status=payload.status,
        priority=payload.priority,
        due_at=payload.due_at,
        target_response_at=payload.target_response_at,
        created_by_admin_id=created_by_admin.id if created_by_admin else None,
        opened_at=opened_at,
        last_activity_at=opened_at,
    )
    if service_request.status in {"completed", "cancelled"}:
        service_request.closed_at = opened_at

    db.add(service_request)
    await db.flush()
    return service_request


async def update_service_request(
    db: AsyncSession,
    service_request: ServiceRequest,
    payload: ServiceRequestUpdate,
) -> ServiceRequest:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(service_request, field, value)
    touch_service_request_activity(service_request)
    db.add(service_request)
    await db.flush()
    return service_request


async def add_status_history(
    db: AsyncSession,
    *,
    service_request: ServiceRequest,
    old_status: str | None,
    new_status: str,
    changed_by_admin: AdminUser | None,
    comment: str | None = None,
) -> ServiceRequestStatusHistory:
    entry = ServiceRequestStatusHistory(
        service_request_id=service_request.id,
        old_status=old_status,
        new_status=new_status,
        changed_by_admin_id=changed_by_admin.id if changed_by_admin else None,
        comment=comment,
    )
    db.add(entry)
    await db.flush()
    return entry


async def update_service_request_status(
    db: AsyncSession,
    *,
    service_request: ServiceRequest,
    payload: ServiceRequestStatusUpdate,
    changed_by_admin: AdminUser | None,
) -> ServiceRequestStatusHistory:
    old_status = service_request.status
    service_request.status = payload.status
    changed_at = utcnow()
    if payload.status in {"completed", "cancelled"}:
        service_request.closed_at = changed_at
    elif old_status in {"completed", "cancelled"} and payload.status not in {"completed", "cancelled"}:
        service_request.closed_at = None
    touch_service_request_activity(service_request, occurred_at=changed_at)
    db.add(service_request)
    await db.flush()
    return await add_status_history(
        db,
        service_request=service_request,
        old_status=old_status,
        new_status=payload.status,
        changed_by_admin=changed_by_admin,
        comment=payload.comment,
    )


def get_active_assignments(service_request: ServiceRequest) -> list[ServiceRequestAssignment]:
    return [assignment for assignment in service_request.assignments if assignment.unassigned_at is None]


def get_active_lead_assignment(
    service_request: ServiceRequest,
) -> ServiceRequestAssignment | None:
    return next(
        (
            assignment
            for assignment in service_request.assignments
            if assignment.unassigned_at is None and assignment.assignment_role == "lead"
        ),
        None,
    )


async def create_assignment(
    db: AsyncSession,
    *,
    service_request: ServiceRequest,
    payload: ServiceRequestAssignmentCreate,
    assigned_by_admin: AdminUser | None,
) -> ServiceRequestAssignment:
    assigned_at = utcnow()
    if payload.assignment_role == "lead":
        current_lead = get_active_lead_assignment(service_request)
        if current_lead is not None:
            current_lead.unassigned_at = assigned_at
            db.add(current_lead)

    assignment = ServiceRequestAssignment(
        service_request_id=service_request.id,
        admin_user_id=payload.admin_user_id,
        assignment_role=payload.assignment_role,
        assigned_by_admin_id=assigned_by_admin.id if assigned_by_admin else None,
        assigned_at=assigned_at,
    )
    db.add(assignment)
    touch_service_request_activity(service_request, occurred_at=assigned_at)
    await db.flush()
    return assignment


async def set_lead_assignment(
    db: AsyncSession,
    *,
    service_request: ServiceRequest,
    admin_user_id: int | None,
    assigned_by_admin: AdminUser | None,
) -> None:
    now = utcnow()
    for assignment in service_request.assignments:
        if assignment.assignment_role == "lead" and assignment.unassigned_at is None:
            assignment.unassigned_at = now
            db.add(assignment)

    if admin_user_id is None:
        touch_service_request_activity(service_request, occurred_at=now)
        await db.flush()
        return

    db.add(
        ServiceRequestAssignment(
            service_request_id=service_request.id,
            admin_user_id=admin_user_id,
            assignment_role="lead",
            assigned_by_admin_id=assigned_by_admin.id if assigned_by_admin else None,
            assigned_at=now,
        )
    )
    touch_service_request_activity(service_request, occurred_at=now)
    await db.flush()


async def get_primary_thread(
    db: AsyncSession,
    *,
    service_request_id: UUID,
) -> InboxThread | None:
    result = await db.execute(
        select(InboxThread).where(
            InboxThread.service_request_id == service_request_id,
            InboxThread.thread_kind == "primary",
        )
    )
    return result.scalar_one_or_none()


async def get_or_create_primary_thread(
    db: AsyncSession,
    *,
    service_request: ServiceRequest,
    subject: str | None = None,
) -> InboxThread:
    existing = await get_primary_thread(db, service_request_id=service_request.id)
    if existing is not None:
        existing.service_request = service_request
        return existing

    thread = InboxThread(
        service_request_id=service_request.id,
        thread_kind="primary",
        subject=subject,
    )
    thread.service_request = service_request
    db.add(thread)
    await db.flush()
    return thread


async def add_inbox_message(
    db: AsyncSession,
    *,
    thread: InboxThread,
    payload: InboxMessageCreate,
    author_admin: AdminUser | None,
    service_request: ServiceRequest | None = None,
) -> InboxMessage:
    created_at = utcnow()
    message = InboxMessage(
        thread_id=thread.id,
        direction=payload.direction,
        channel=payload.channel,
        body=payload.body,
        author_admin_id=author_admin.id if author_admin else None,
        customer_author_name=payload.customer_author_name,
        customer_author_email=payload.customer_author_email,
        created_at=created_at,
    )
    db.add(message)
    target_service_request = service_request or getattr(thread, "service_request", None)
    if target_service_request is not None:
        touch_service_request_activity(
            target_service_request,
            occurred_at=created_at,
            customer_message_at=created_at if payload.direction == "inbound" else None,
        )
        db.add(target_service_request)
    await db.flush()
    return message


async def add_note(
    db: AsyncSession,
    *,
    service_request_id: UUID | None = None,
    customer_id: UUID | None = None,
    payload: RecordNoteCreate,
    created_by_admin: AdminUser,
) -> RecordNote:
    created_at = utcnow()
    note = RecordNote(
        service_request_id=service_request_id,
        customer_id=customer_id,
        visibility=payload.visibility,
        body=payload.body,
        created_by_admin_id=created_by_admin.id,
        created_at=created_at,
    )
    db.add(note)
    if service_request_id is not None:
        service_request = await get_service_request_by_id(db, service_request_id)
        if service_request is not None:
            touch_service_request_activity(service_request, occurred_at=created_at)
            db.add(service_request)
    await db.flush()
    return note


async def replace_service_request_compatibility_note(
    db: AsyncSession,
    *,
    service_request: ServiceRequest,
    visibility: str,
    body: str | None,
    created_by_admin: AdminUser,
) -> None:
    existing_notes = [
        note
        for note in service_request.notes
        if note.visibility == visibility and note.service_request_id == service_request.id
    ]
    for note in existing_notes:
        await db.delete(note)
    await db.flush()

    if body and body.strip():
        await add_note(
            db,
            service_request_id=service_request.id,
            payload=RecordNoteCreate(visibility=visibility, body=body.strip()),
            created_by_admin=created_by_admin,
        )


async def get_document_by_id(db: AsyncSession, document_id: UUID) -> RecordDocument | None:
    result = await db.execute(
        select(RecordDocument)
        .options(selectinload(RecordDocument.uploaded_by_admin))
        .where(RecordDocument.id == document_id)
    )
    return result.scalar_one_or_none()


async def add_document(
    db: AsyncSession,
    *,
    service_request_id: UUID | None = None,
    customer_id: UUID | None = None,
    classification: str,
    storage_key: str,
    original_filename: str,
    mime_type: str,
    file_size: int,
    uploaded_by_admin: AdminUser,
) -> RecordDocument:
    created_at = utcnow()
    document = RecordDocument(
        service_request_id=service_request_id,
        customer_id=customer_id,
        classification=classification,
        storage_key=storage_key,
        original_filename=original_filename,
        mime_type=mime_type,
        file_size=file_size,
        uploaded_by_admin_id=uploaded_by_admin.id,
        created_at=created_at,
    )
    db.add(document)
    if service_request_id is not None:
        service_request = await get_service_request_by_id(db, service_request_id)
        if service_request is not None:
            touch_service_request_activity(service_request, occurred_at=created_at)
            db.add(service_request)
    await db.flush()
    return document


async def get_service_requests_by_ids(
    db: AsyncSession,
    request_ids: list[UUID],
    *,
    include_related: bool = False,
) -> list[ServiceRequest]:
    if not request_ids:
        return []
    result = await db.execute(
        _service_request_select(include_related=include_related)
        .where(ServiceRequest.id.in_(request_ids))
        .order_by(ServiceRequest.last_activity_at.desc(), ServiceRequest.created_at.desc())
    )
    return list(result.scalars().unique().all())


async def get_or_create_inbox_state_for_admin(
    db: AsyncSession,
    *,
    service_request: ServiceRequest,
    admin_user: AdminUser,
) -> ServiceRequestInboxState:
    existing = get_inbox_state(service_request, admin_user.id)
    if existing is not None:
        return existing

    state = ServiceRequestInboxState(
        service_request_id=service_request.id,
        admin_user_id=admin_user.id,
    )
    db.add(state)
    await db.flush()
    if "inbox_states" in service_request.__dict__:
        service_request.inbox_states.append(state)
    return state


async def mark_service_request_read(
    db: AsyncSession,
    *,
    service_request: ServiceRequest,
    admin_user: AdminUser,
) -> ServiceRequestMarkReadResponse:
    state = await get_or_create_inbox_state_for_admin(
        db,
        service_request=service_request,
        admin_user=admin_user,
    )
    primary_thread = get_primary_thread_for_request(service_request)
    latest_customer_message = None
    if primary_thread is not None:
        for message in reversed(primary_thread.messages):
            if is_customer_message(message):
                latest_customer_message = message
                break

    state.last_read_at = utcnow()
    state.last_read_message_id = latest_customer_message.id if latest_customer_message else None
    db.add(state)
    await db.flush()

    unread, unread_count = get_unread_summary(service_request, admin_user.id)
    return ServiceRequestMarkReadResponse(
        service_request_id=service_request.id,
        unread=unread,
        unread_count=unread_count,
        last_read_at=state.last_read_at,
    )


async def bulk_mark_service_requests_read(
    db: AsyncSession,
    *,
    request_ids: list[UUID],
    admin_user: AdminUser,
) -> int:
    requests = await get_service_requests_by_ids(db, request_ids, include_related=True)
    for service_request in requests:
        await mark_service_request_read(
            db,
            service_request=service_request,
            admin_user=admin_user,
        )
    return len(requests)


async def bulk_update_service_request_statuses(
    db: AsyncSession,
    *,
    request_ids: list[UUID],
    status: str,
    comment: str | None,
    changed_by_admin: AdminUser,
) -> int:
    requests = await get_service_requests_by_ids(db, request_ids, include_related=True)
    for service_request in requests:
        await update_service_request_status(
            db,
            service_request=service_request,
            payload=ServiceRequestStatusUpdate(status=status, comment=comment),
            changed_by_admin=changed_by_admin,
        )
    return len(requests)


async def bulk_assign_service_requests(
    db: AsyncSession,
    *,
    request_ids: list[UUID],
    admin_user_id: int,
    assignment_role: str,
    assigned_by_admin: AdminUser,
) -> list[ServiceRequest]:
    requests = await get_service_requests_by_ids(db, request_ids, include_related=True)
    for service_request in requests:
        await create_assignment(
            db,
            service_request=service_request,
            payload=ServiceRequestAssignmentCreate(
                admin_user_id=admin_user_id,
                assignment_role=assignment_role,
            ),
            assigned_by_admin=assigned_by_admin,
        )
    return requests


async def bulk_update_service_request_priorities(
    db: AsyncSession,
    *,
    request_ids: list[UUID],
    priority: ServiceRequestPriority,
) -> int:
    requests = await get_service_requests_by_ids(db, request_ids, include_related=True)
    for service_request in requests:
        service_request.priority = priority
        touch_service_request_activity(service_request)
        db.add(service_request)
    await db.flush()
    return len(requests)


async def build_service_request_timeline(
    db: AsyncSession,
    service_request: ServiceRequest,
) -> list[dict[str, object]]:
    timeline: list[dict[str, object]] = [
        {
            "id": f"service-request-created:{service_request.id}",
            "event_type": "service_request.created",
            "scope_type": "service_request",
            "scope_id": service_request.id,
            "actor_name": service_request.customer.display_name,
            "actor_type": "customer",
            "summary": "Request created",
            "body": service_request.intake_message,
            "created_at": service_request.created_at,
            "related_record_type": "service_request",
            "related_record_id": str(service_request.id),
        }
    ]

    for entry in service_request.status_history:
        timeline.append(
            {
                "id": f"status:{entry.id}",
                "event_type": "service_request.status_changed",
                "scope_type": "service_request",
                "scope_id": service_request.id,
                "actor_name": entry.changed_by_admin.email if entry.changed_by_admin else "System",
                "actor_type": "admin" if entry.changed_by_admin else "system",
                "summary": f"Status changed to {entry.new_status.replace('_', ' ')}",
                "body": entry.comment,
                "created_at": entry.created_at,
                "related_record_type": "service_request_status_history",
                "related_record_id": str(entry.id),
            }
        )

    for assignment in service_request.assignments:
        summary = (
            f"{assignment.assignment_role.title()} assignment ended"
            if assignment.unassigned_at
            else f"{assignment.assignment_role.title()} assigned"
        )
        timeline.append(
            {
                "id": f"assignment:{assignment.id}",
                "event_type": "service_request.assignment",
                "scope_type": "service_request",
                "scope_id": service_request.id,
                "actor_name": assignment.assigned_by_admin.email
                if assignment.assigned_by_admin
                else assignment.admin_user.email,
                "actor_type": "admin",
                "summary": summary,
                "body": assignment.admin_user.email,
                "created_at": assignment.unassigned_at or assignment.assigned_at,
                "related_record_type": "service_request_assignment",
                "related_record_id": str(assignment.id),
            }
        )

    for thread in service_request.threads:
        for message in thread.messages:
            actor_name = (
                message.author_admin.email
                if message.author_admin
                else message.customer_author_name
                or message.customer_author_email
                or service_request.customer.display_name
            )
            actor_type = "admin" if message.author_admin else "customer"
            timeline.append(
                {
                    "id": f"message:{message.id}",
                    "event_type": "service_request.message",
                    "scope_type": "service_request",
                    "scope_id": service_request.id,
                    "actor_name": actor_name,
                    "actor_type": actor_type,
                    "summary": f"{message.direction.replace('_', ' ').title()} message",
                    "body": message.body,
                    "created_at": message.created_at,
                    "related_record_type": "inbox_message",
                    "related_record_id": str(message.id),
                }
            )

    for note in service_request.notes:
        timeline.append(
            {
                "id": f"note:{note.id}",
                "event_type": "service_request.note",
                "scope_type": "service_request",
                "scope_id": service_request.id,
                "actor_name": note.created_by_admin.email,
                "actor_type": "admin",
                "summary": f"{note.visibility.replace('_', ' ').title()} note added",
                "body": note.body,
                "created_at": note.created_at,
                "related_record_type": "note",
                "related_record_id": str(note.id),
            }
        )

    for document in service_request.documents:
        timeline.append(
            {
                "id": f"document:{document.id}",
                "event_type": "service_request.document",
                "scope_type": "service_request",
                "scope_id": service_request.id,
                "actor_name": document.uploaded_by_admin.email,
                "actor_type": "admin",
                "summary": "Document uploaded",
                "body": document.original_filename,
                "created_at": document.created_at,
                "related_record_type": "document",
                "related_record_id": str(document.id),
            }
        )

    audit_result = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.target_type.in_(["customer", "service_request"]),
            AuditLog.target_id.in_([str(service_request.id), str(service_request.customer_id)]),
        )
        .order_by(AuditLog.created_at.desc())
        .limit(50)
    )
    for entry in audit_result.scalars().all():
        timeline.append(
            {
                "id": f"audit:{entry.id}",
                "event_type": "audit",
                "scope_type": "service_request"
                if entry.target_id == str(service_request.id)
                else "customer",
                "scope_id": service_request.id
                if entry.target_id == str(service_request.id)
                else service_request.customer_id,
                "actor_name": entry.actor_email or "System",
                "actor_type": "admin" if entry.actor_id else "system",
                "summary": entry.action,
                "body": None,
                "created_at": entry.created_at,
                "related_record_type": entry.target_type,
                "related_record_id": entry.target_id,
            }
        )

    timeline.sort(key=lambda item: item["created_at"], reverse=True)
    return timeline


async def build_customer_timeline(
    db: AsyncSession,
    customer: Customer,
) -> list[dict[str, object]]:
    service_request_result = await db.execute(
        _service_request_select(include_related=True)
        .where(ServiceRequest.customer_id == customer.id)
        .order_by(ServiceRequest.created_at.desc())
    )
    requests = list(service_request_result.scalars().unique().all())

    timeline: list[dict[str, object]] = []
    for service_request in requests:
        timeline.extend(await build_service_request_timeline(db, service_request))

    for note in customer.notes:
        timeline.append(
            {
                "id": f"customer-note:{note.id}",
                "event_type": "customer.note",
                "scope_type": "customer",
                "scope_id": customer.id,
                "actor_name": note.created_by_admin.email,
                "actor_type": "admin",
                "summary": f"{note.visibility.replace('_', ' ').title()} note added",
                "body": note.body,
                "created_at": note.created_at,
                "related_record_type": "note",
                "related_record_id": str(note.id),
            }
        )

    for document in customer.documents:
        timeline.append(
            {
                "id": f"customer-document:{document.id}",
                "event_type": "customer.document",
                "scope_type": "customer",
                "scope_id": customer.id,
                "actor_name": document.uploaded_by_admin.email,
                "actor_type": "admin",
                "summary": "Customer document uploaded",
                "body": document.original_filename,
                "created_at": document.created_at,
                "related_record_type": "document",
                "related_record_id": str(document.id),
            }
        )

    timeline.sort(key=lambda item: item["created_at"], reverse=True)
    return timeline
