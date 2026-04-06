from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import get_request_meta, log_audit, serialize_for_audit
from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import require_csrf, require_permission
from app.crud import admin as admin_crud
from app.crud import notification as notification_crud
from app.crud import service_request as service_request_crud
from app.models import (
    AdminUser,
    BlogPost,
    Customer,
    Page,
    RecordDocument,
    ServiceRequest,
    ServiceRequestAssignment,
    ServiceRequestInboxState,
    Testimonial,
)
from app.schemas import (
    BulkActionResult,
    BulkAssignPayload,
    BulkMarkReadPayload,
    BulkPriorityPayload,
    BulkStatusPayload,
    CustomerCreate,
    CustomerListResponse,
    CustomerOut,
    CustomerUpdate,
    DashboardWorklistItemOut,
    InboxMessageCreate,
    InboxMessageOut,
    InboxThreadOut,
    RecordDocumentOut,
    RecordNoteCreate,
    RecordNoteOut,
    ReviewQueueItemOut,
    ServiceRequestAssignmentCreate,
    ServiceRequestAssignmentOut,
    ServiceRequestAssignmentUpdate,
    ServiceRequestCreate,
    ServiceRequestListResponse,
    ServiceRequestMarkReadResponse,
    ServiceRequestOut,
    ServiceRequestStatusUpdate,
    ServiceRequestUpdate,
    ServiceTypeOut,
    TimelineEventOut,
)

router = APIRouter(prefix="/admin", tags=["admin-operations"])
documents_dir = settings.documents_root_path
documents_dir.mkdir(parents=True, exist_ok=True)

ALLOWED_DOCUMENT_MIME_TYPES: dict[str, tuple[str, bytes | tuple[bytes, ...]]] = {
    "application/pdf": ("pdf", b"%PDF-"),
    "image/jpeg": ("jpg", b"\xff\xd8\xff"),
    "image/png": ("png", b"\x89PNG\r\n\x1a\n"),
    "image/webp": ("webp", (b"RIFF", b"WEBP")),
}


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _conflict(detail: str = "Resource conflict") -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _document_download_url(request: Request, document_id: UUID) -> str:
    return f"{str(request.base_url).rstrip('/')}/api/v1/admin/documents/{document_id}/download"


def _consultation_href(consultation_id: int | None) -> str | None:
    if consultation_id is None:
        return None
    return f"/admin/consultations/{consultation_id}/"


def _page_href(page_id: int) -> str:
    return f"/admin/pages/{page_id}/edit/"


def _blog_post_href(post_id: int) -> str:
    return f"/admin/blog/posts/{post_id}/edit/"


def _testimonial_href(testimonial_id: int) -> str:
    return f"/admin/testimonials/"


def _validated_request_ids(request_ids: list[UUID]) -> list[UUID]:
    ids = list(dict.fromkeys(request_ids))
    if not ids:
        raise _bad_request("At least one service request must be selected.")
    return ids


async def _commit_with_conflict(db: AsyncSession, *, detail: str = "Resource conflict") -> None:
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _conflict(detail) from exc


async def _log_route_audit(
    db: AsyncSession,
    *,
    request: Request | None,
    current_admin: AdminUser | None,
    action: str,
    target_type: str,
    target_id: UUID | int | str | None,
    old_value: Any = None,
    new_value: Any = None,
) -> None:
    ip, user_agent = get_request_meta(request)
    await log_audit(
        db,
        actor_id=current_admin.id if current_admin else None,
        actor_email=current_admin.email if current_admin else None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        old_value=old_value,
        new_value=new_value,
        ip=ip,
        user_agent=user_agent,
    )


def _document_out(document: RecordDocument, request: Request) -> RecordDocumentOut:
    payload = RecordDocumentOut.model_validate(document)
    return payload.model_copy(
        update={"download_url": _document_download_url(request, document.id)}
    )


async def _service_request_out(
    db: AsyncSession,
    service_request: ServiceRequest,
    request: Request,
    *,
    include_timeline: bool = False,
    current_admin: AdminUser | None = None,
) -> ServiceRequestOut:
    payload = ServiceRequestOut.model_validate(service_request)
    unread, unread_count = (
        service_request_crud.get_unread_summary(service_request, current_admin.id)
        if current_admin is not None
        else (False, 0)
    )
    timeline = (
        [
            TimelineEventOut.model_validate(item)
            for item in await service_request_crud.build_service_request_timeline(db, service_request)
        ]
        if include_timeline
        else []
    )
    return payload.model_copy(
        update={
            "documents": [_document_out(document, request) for document in service_request.documents],
            "timeline": timeline,
            "unread": unread,
            "unread_count": unread_count,
        }
    )


async def _read_document_upload(file: UploadFile) -> tuple[bytes, str]:
    content = await file.read()
    if not content:
        raise _bad_request("Uploaded document is empty.")
    if len(content) > settings.MAX_DOCUMENT_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Document exceeds the configured size limit.",
        )

    allowed = ALLOWED_DOCUMENT_MIME_TYPES.get(file.content_type or "")
    if allowed is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF, JPEG, PNG, and WebP documents are allowed.",
        )

    extension, signature = allowed
    if isinstance(signature, tuple):
        if not (content.startswith(signature[0]) and signature[1] in content[:32]):
            raise _bad_request("The uploaded document content does not match its file type.")
    elif not content.startswith(signature):
        raise _bad_request("The uploaded document content does not match its file type.")

    return content, extension


@router.get("/service-types", response_model=list[ServiceTypeOut])
async def list_admin_service_types(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("service_request.read")),
) -> list[ServiceTypeOut]:
    return await service_request_crud.get_service_types(db)


@router.get("/dashboard/worklists", response_model=list[DashboardWorklistItemOut])
async def get_admin_dashboard_worklists(
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("dashboard.read")),
) -> list[DashboardWorklistItemOut]:
    active_statuses = tuple(service_request_crud.ACTIVE_SERVICE_REQUEST_STATUSES)

    unassigned_count = int(
        await db.scalar(
            select(func.count(ServiceRequest.id)).where(
                ServiceRequest.status.in_(active_statuses),
                ~select(ServiceRequestAssignment.id)
                .where(
                    ServiceRequestAssignment.service_request_id == ServiceRequest.id,
                    ServiceRequestAssignment.unassigned_at.is_(None),
                )
                .exists(),
            )
        )
        or 0
    )

    unread_count = int(
        await db.scalar(
            select(func.count(ServiceRequest.id))
            .select_from(ServiceRequest)
            .outerjoin(
                ServiceRequestInboxState,
                (
                    (ServiceRequestInboxState.service_request_id == ServiceRequest.id)
                    & (ServiceRequestInboxState.admin_user_id == current_admin.id)
                ),
            )
            .where(
                ServiceRequest.last_customer_message_at.is_not(None),
                ServiceRequest.status.in_(active_statuses),
                (
                    (ServiceRequestInboxState.id.is_(None))
                    | (ServiceRequestInboxState.last_read_at.is_(None))
                    | (ServiceRequestInboxState.last_read_at < ServiceRequest.last_customer_message_at)
                ),
            )
        )
        or 0
    )

    high_priority_count = int(
        await db.scalar(
            select(func.count(ServiceRequest.id)).where(
                ServiceRequest.status.in_(active_statuses),
                ServiceRequest.priority.in_(("high", "urgent")),
            )
        )
        or 0
    )

    pending_review_count = 0
    if "review_queue.read" in current_admin.permissions:
        pending_review_count = int(
            (await db.scalar(select(func.count(Page.id)).where(Page.status == "pending_review")) or 0)
            + (await db.scalar(select(func.count(BlogPost.id)).where(BlogPost.status == "pending_review")) or 0)
            + (
                await db.scalar(
                    select(func.count(Testimonial.id)).where(Testimonial.status == "pending_review")
                )
                or 0
            )
        )

    return [
        DashboardWorklistItemOut(
            key="mine-unread",
            label="Unread customer replies",
            count=unread_count,
            href="/admin/consultations/?view=unread",
            tone="warning" if unread_count else "default",
            description="Requests that have new customer activity for the current admin.",
        ),
        DashboardWorklistItemOut(
            key="unassigned",
            label="Unassigned requests",
            count=unassigned_count,
            href="/admin/consultations/?view=unassigned",
            tone="error" if unassigned_count else "default",
            description="Open requests that still need an owner.",
        ),
        DashboardWorklistItemOut(
            key="high-priority",
            label="High-priority active work",
            count=high_priority_count,
            href="/admin/consultations/?priority=high&view=all_active",
            tone="info" if high_priority_count else "default",
            description="High and urgent requests that are still in progress.",
        ),
        DashboardWorklistItemOut(
            key="review-queue",
            label="Pending content review",
            count=pending_review_count,
            href="/admin/review-queue/" if "review_queue.read" in current_admin.permissions else None,
            tone="warning" if pending_review_count else "default",
            description="Pages, blog posts, and testimonials waiting for approval.",
        ),
    ]


@router.get("/review-queue", response_model=list[ReviewQueueItemOut])
async def get_admin_review_queue(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("review_queue.read")),
) -> list[ReviewQueueItemOut]:
    pages = (
        await db.execute(
            select(Page)
            .where(Page.status == "pending_review")
            .order_by(Page.submitted_at.desc().nullslast(), Page.updated_at.desc())
        )
    ).scalars().all()
    posts = (
        await db.execute(
            select(BlogPost)
            .where(BlogPost.status == "pending_review")
            .order_by(BlogPost.submitted_at.desc().nullslast(), BlogPost.updated_at.desc())
        )
    ).scalars().all()
    testimonials = (
        await db.execute(
            select(Testimonial)
            .where(Testimonial.status == "pending_review")
            .order_by(Testimonial.submitted_at.desc().nullslast(), Testimonial.updated_at.desc())
        )
    ).scalars().all()

    queue = [
        ReviewQueueItemOut(
            id=f"page-{item.id}",
            content_type="page",
            title=item.title,
            status=item.status,
            submitted_at=item.submitted_at,
            submitted_by=None,
            href=_page_href(item.id),
        )
        for item in pages
    ] + [
        ReviewQueueItemOut(
            id=f"blog_post-{item.id}",
            content_type="blog_post",
            title=item.title,
            status=item.status,
            submitted_at=item.submitted_at,
            submitted_by=None,
            href=_blog_post_href(item.id),
        )
        for item in posts
    ] + [
        ReviewQueueItemOut(
            id=f"testimonial-{item.id}",
            content_type="testimonial",
            title=item.headline or item.author,
            status=item.status,
            submitted_at=item.submitted_at,
            submitted_by=None,
            href=_testimonial_href(item.id),
        )
        for item in testimonials
    ]

    queue.sort(
        key=lambda item: item.submitted_at.timestamp() if item.submitted_at else 0,
        reverse=True,
    )
    return queue


@router.get("/customers", response_model=CustomerListResponse)
async def list_admin_customers(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("customer.read")),
) -> CustomerListResponse:
    items, total = await service_request_crud.list_customers(
        db,
        page=page,
        limit=limit,
        search=search,
    )
    return CustomerListResponse.build(
        items=[CustomerOut.model_validate(item) for item in items],
        page=page,
        limit=limit,
        total=total,
    )


@router.post("/customers", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
async def create_admin_customer(
    payload: CustomerCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("customer.create")),
    _: None = Depends(require_csrf),
) -> CustomerOut:
    customer = await service_request_crud.create_customer(db, payload)
    await _commit_with_conflict(db, detail="Customer already exists.")
    await _log_route_audit(
        db,
        request=request,
        current_admin=current_admin,
        action="customer.create",
        target_type="customer",
        target_id=customer.id,
        new_value=customer,
    )
    return CustomerOut.model_validate(customer)


@router.get("/customers/{customer_id}", response_model=CustomerOut)
async def get_admin_customer(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("customer.read")),
) -> CustomerOut:
    customer = await service_request_crud.get_customer_by_id(
        db,
        customer_id,
        include_requests=True,
    )
    if customer is None:
        raise _not_found("Customer not found")
    return CustomerOut.model_validate(customer)


@router.patch("/customers/{customer_id}", response_model=CustomerOut)
async def update_admin_customer(
    customer_id: UUID,
    payload: CustomerUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("customer.update")),
    _: None = Depends(require_csrf),
) -> CustomerOut:
    customer = await service_request_crud.get_customer_by_id(db, customer_id)
    if customer is None:
        raise _not_found("Customer not found")
    old_value = serialize_for_audit(customer)
    await service_request_crud.update_customer(db, customer, payload)
    await _commit_with_conflict(db, detail="Customer update conflicted with existing data.")
    refreshed = await service_request_crud.get_customer_by_id(db, customer_id)
    if refreshed is None:
        raise _not_found("Customer not found")
    await _log_route_audit(
        db,
        request=request,
        current_admin=current_admin,
        action="customer.update",
        target_type="customer",
        target_id=customer_id,
        old_value=old_value,
        new_value=refreshed,
    )
    return CustomerOut.model_validate(refreshed)


@router.get("/customers/{customer_id}/timeline", response_model=list[TimelineEventOut])
async def get_admin_customer_timeline(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("customer.read")),
) -> list[TimelineEventOut]:
    customer = await service_request_crud.get_customer_by_id(
        db,
        customer_id,
        include_requests=True,
    )
    if customer is None:
        raise _not_found("Customer not found")
    return [
        TimelineEventOut.model_validate(item)
        for item in await service_request_crud.build_customer_timeline(db, customer)
    ]


@router.get("/service-requests", response_model=ServiceRequestListResponse)
async def list_admin_service_requests(
    request: Request,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    service_type: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    assignee_id: int | None = Query(default=None),
    source_channel: str | None = Query(default=None),
    view: str | None = Query(default=None),
    sort: str = Query(default="last_activity"),
    order: str = Query(default="desc"),
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("service_request.read")),
) -> ServiceRequestListResponse:
    items, total = await service_request_crud.list_service_requests(
        db,
        page=page,
        limit=limit,
        search=search,
        status=status_value,
        service_type_code=service_type,
        priority=priority,
        assignee_id=assignee_id,
        source_channel=source_channel,
        view=view,
        current_admin_id=current_admin.id,
        sort=sort,
        order=order,
        include_related=False,
    )
    return ServiceRequestListResponse.build(
        items=[
            await _service_request_out(
                db,
                item,
                request,
                include_timeline=False,
                current_admin=current_admin,
            )
            for item in items
        ],
        page=page,
        limit=limit,
        total=total,
    )


@router.post("/service-requests", response_model=ServiceRequestOut, status_code=status.HTTP_201_CREATED)
async def create_admin_service_request(
    payload: ServiceRequestCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("service_request.create")),
    _: None = Depends(require_csrf),
) -> ServiceRequestOut:
    customer = await service_request_crud.get_customer_by_id(db, payload.customer_id)
    if customer is None:
        raise _not_found("Customer not found")
    service_type = await service_request_crud.get_service_type_by_id(db, payload.service_type_id)
    if service_type is None:
        raise _not_found("Service type not found")

    service_request = await service_request_crud.create_service_request(
        db,
        payload=payload,
        created_by_admin=current_admin,
    )
    await service_request_crud.add_status_history(
        db,
        service_request=service_request,
        old_status=None,
        new_status=service_request.status,
        changed_by_admin=current_admin,
        comment="Service request created.",
    )
    thread = await service_request_crud.get_or_create_primary_thread(
        db,
        service_request=service_request,
        subject=payload.title,
    )
    if payload.intake_message:
        await service_request_crud.add_inbox_message(
            db,
            thread=thread,
            payload=InboxMessageCreate(
                direction="inbound",
                channel="system_seed",
                body=payload.intake_message,
                customer_author_name=customer.display_name,
                customer_author_email=customer.primary_email,
            ),
            author_admin=None,
            service_request=service_request,
        )

    await _commit_with_conflict(db, detail="Service request already exists.")
    refreshed = await service_request_crud.get_service_request_by_id(
        db,
        service_request.id,
        include_related=True,
    )
    if refreshed is None:
        raise _not_found("Service request not found")
    await _log_route_audit(
        db,
        request=request,
        current_admin=current_admin,
        action="service_request.create",
        target_type="service_request",
        target_id=service_request.id,
        new_value=refreshed,
    )
    return await _service_request_out(
        db,
        refreshed,
        request,
        include_timeline=True,
        current_admin=current_admin,
    )


@router.get("/service-requests/{service_request_id}", response_model=ServiceRequestOut)
async def get_admin_service_request(
    service_request_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("service_request.read")),
) -> ServiceRequestOut:
    service_request = await service_request_crud.get_service_request_by_id(
        db,
        service_request_id,
        include_related=True,
    )
    if service_request is None:
        raise _not_found("Service request not found")
    return await _service_request_out(
        db,
        service_request,
        request,
        include_timeline=True,
        current_admin=current_admin,
    )


@router.post(
    "/service-requests/{service_request_id}/mark-read",
    response_model=ServiceRequestMarkReadResponse,
)
async def mark_admin_service_request_read(
    service_request_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("service_request.mark_read")),
    _: None = Depends(require_csrf),
) -> ServiceRequestMarkReadResponse:
    service_request = await service_request_crud.get_service_request_by_id(
        db,
        service_request_id,
        include_related=True,
    )
    if service_request is None:
        raise _not_found("Service request not found")
    result = await service_request_crud.mark_service_request_read(
        db,
        service_request=service_request,
        admin_user=current_admin,
    )
    await _commit_with_conflict(db, detail="Unable to update the read state.")
    return result


@router.post("/service-requests/bulk/mark-read", response_model=BulkActionResult)
async def bulk_mark_admin_service_requests_read(
    payload: BulkMarkReadPayload,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("service_request.bulk_update")),
    _: None = Depends(require_csrf),
) -> BulkActionResult:
    request_ids = _validated_request_ids(payload.request_ids)
    updated = await service_request_crud.bulk_mark_service_requests_read(
        db,
        request_ids=request_ids,
        admin_user=current_admin,
    )
    await _commit_with_conflict(db, detail="Unable to update the selected read states.")
    return BulkActionResult(
        requested=len(request_ids),
        updated=updated,
        skipped=max(len(request_ids) - updated, 0),
        request_ids=request_ids,
    )


@router.post("/service-requests/bulk/status", response_model=BulkActionResult)
async def bulk_update_admin_service_request_statuses(
    payload: BulkStatusPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("service_request.bulk_update")),
    _: None = Depends(require_csrf),
) -> BulkActionResult:
    request_ids = _validated_request_ids(payload.request_ids)
    updated = await service_request_crud.bulk_update_service_request_statuses(
        db,
        request_ids=request_ids,
        status=payload.status,
        comment=payload.comment,
        changed_by_admin=current_admin,
    )
    await _commit_with_conflict(db, detail="Unable to update the selected request statuses.")
    await _log_route_audit(
        db,
        request=request,
        current_admin=current_admin,
        action="service_request.bulk_status_update",
        target_type="service_request",
        target_id="bulk",
        new_value=payload.model_dump(),
    )
    return BulkActionResult(
        requested=len(request_ids),
        updated=updated,
        skipped=max(len(request_ids) - updated, 0),
        request_ids=request_ids,
    )


@router.post("/service-requests/bulk/assign", response_model=BulkActionResult)
async def bulk_assign_admin_service_requests(
    payload: BulkAssignPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("service_request.bulk_update")),
    _: None = Depends(require_csrf),
) -> BulkActionResult:
    assigned_admin = await admin_crud.get_admin_by_id(db, payload.admin_user_id, include_access=True)
    if assigned_admin is None:
        raise _not_found("Assigned admin not found")
    request_ids = _validated_request_ids(payload.request_ids)
    requests = await service_request_crud.bulk_assign_service_requests(
        db,
        request_ids=request_ids,
        admin_user_id=payload.admin_user_id,
        assignment_role=payload.assignment_role,
        assigned_by_admin=current_admin,
    )
    for service_request in requests:
        if assigned_admin.is_active:
            await notification_crud.emit_request_assigned_notification(
                db,
                service_request=service_request,
                recipient_admin=assigned_admin,
                assigned_by_admin=current_admin,
                occurred_at=service_request.last_activity_at,
            )
    await _commit_with_conflict(db, detail="Unable to update the selected assignments.")
    await _log_route_audit(
        db,
        request=request,
        current_admin=current_admin,
        action="service_request.bulk_assign",
        target_type="service_request",
        target_id="bulk",
        new_value=payload.model_dump(),
    )
    return BulkActionResult(
        requested=len(request_ids),
        updated=len(requests),
        skipped=max(len(request_ids) - len(requests), 0),
        request_ids=request_ids,
    )


@router.post("/service-requests/bulk/priority", response_model=BulkActionResult)
async def bulk_update_admin_service_request_priorities(
    payload: BulkPriorityPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("service_request.bulk_update")),
    _: None = Depends(require_csrf),
) -> BulkActionResult:
    request_ids = _validated_request_ids(payload.request_ids)
    updated = await service_request_crud.bulk_update_service_request_priorities(
        db,
        request_ids=request_ids,
        priority=payload.priority,
    )
    await _commit_with_conflict(db, detail="Unable to update the selected priorities.")
    await _log_route_audit(
        db,
        request=request,
        current_admin=current_admin,
        action="service_request.bulk_priority_update",
        target_type="service_request",
        target_id="bulk",
        new_value=payload.model_dump(),
    )
    return BulkActionResult(
        requested=len(request_ids),
        updated=updated,
        skipped=max(len(request_ids) - updated, 0),
        request_ids=request_ids,
    )


@router.patch("/service-requests/{service_request_id}", response_model=ServiceRequestOut)
async def update_admin_service_request(
    service_request_id: UUID,
    payload: ServiceRequestUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("service_request.update")),
    _: None = Depends(require_csrf),
) -> ServiceRequestOut:
    service_request = await service_request_crud.get_service_request_by_id(
        db,
        service_request_id,
        include_related=True,
    )
    if service_request is None:
        raise _not_found("Service request not found")
    if payload.service_type_id is not None and await service_request_crud.get_service_type_by_id(
        db, payload.service_type_id
    ) is None:
        raise _not_found("Service type not found")

    old_value = serialize_for_audit(service_request)
    await service_request_crud.update_service_request(db, service_request, payload)
    await _commit_with_conflict(db, detail="Service request update conflicted with existing data.")
    refreshed = await service_request_crud.get_service_request_by_id(
        db,
        service_request_id,
        include_related=True,
    )
    if refreshed is None:
        raise _not_found("Service request not found")
    await _log_route_audit(
        db,
        request=request,
        current_admin=current_admin,
        action="service_request.update",
        target_type="service_request",
        target_id=service_request_id,
        old_value=old_value,
        new_value=refreshed,
    )
    return await _service_request_out(
        db,
        refreshed,
        request,
        include_timeline=True,
        current_admin=current_admin,
    )


@router.post("/service-requests/{service_request_id}/status", response_model=ServiceRequestOut)
async def update_admin_service_request_status(
    service_request_id: UUID,
    payload: ServiceRequestStatusUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("service_request.status_update")),
    _: None = Depends(require_csrf),
) -> ServiceRequestOut:
    service_request = await service_request_crud.get_service_request_by_id(
        db,
        service_request_id,
        include_related=True,
    )
    if service_request is None:
        raise _not_found("Service request not found")

    old_value = serialize_for_audit(service_request)
    await service_request_crud.update_service_request_status(
        db,
        service_request=service_request,
        payload=payload,
        changed_by_admin=current_admin,
    )
    await _commit_with_conflict(db, detail="Service request status update conflicted.")
    refreshed = await service_request_crud.get_service_request_by_id(
        db,
        service_request_id,
        include_related=True,
    )
    if refreshed is None:
        raise _not_found("Service request not found")
    await _log_route_audit(
        db,
        request=request,
        current_admin=current_admin,
        action="service_request.status_update",
        target_type="service_request",
        target_id=service_request_id,
        old_value=old_value,
        new_value=refreshed,
    )
    return await _service_request_out(
        db,
        refreshed,
        request,
        include_timeline=True,
        current_admin=current_admin,
    )


@router.get("/service-requests/{service_request_id}/assignments", response_model=list[ServiceRequestAssignmentOut])
async def list_admin_service_request_assignments(
    service_request_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("service_request.read")),
) -> list[ServiceRequestAssignmentOut]:
    service_request = await service_request_crud.get_service_request_by_id(
        db,
        service_request_id,
        include_related=True,
    )
    if service_request is None:
        raise _not_found("Service request not found")
    return [ServiceRequestAssignmentOut.model_validate(item) for item in service_request.assignments]


@router.post("/service-requests/{service_request_id}/assignments", response_model=ServiceRequestOut)
async def create_admin_service_request_assignment(
    service_request_id: UUID,
    payload: ServiceRequestAssignmentCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("service_request.assign")),
    _: None = Depends(require_csrf),
) -> ServiceRequestOut:
    service_request = await service_request_crud.get_service_request_by_id(
        db,
        service_request_id,
        include_related=True,
    )
    if service_request is None:
        raise _not_found("Service request not found")
    assigned_admin = await admin_crud.get_admin_by_id(db, payload.admin_user_id, include_access=True)
    if assigned_admin is None:
        raise _not_found("Assigned admin not found")

    old_value = serialize_for_audit(service_request)
    assignment = await service_request_crud.create_assignment(
        db,
        service_request=service_request,
        payload=payload,
        assigned_by_admin=current_admin,
    )
    if assigned_admin.is_active:
        await notification_crud.emit_request_assigned_notification(
            db,
            service_request=service_request,
            recipient_admin=assigned_admin,
            assigned_by_admin=current_admin,
            occurred_at=assignment.assigned_at,
        )
    await _commit_with_conflict(db, detail="Service request assignment conflicted.")
    refreshed = await service_request_crud.get_service_request_by_id(
        db,
        service_request_id,
        include_related=True,
    )
    if refreshed is None:
        raise _not_found("Service request not found")
    await _log_route_audit(
        db,
        request=request,
        current_admin=current_admin,
        action="service_request.assign",
        target_type="service_request",
        target_id=service_request_id,
        old_value=old_value,
        new_value=refreshed,
    )
    return await _service_request_out(
        db,
        refreshed,
        request,
        include_timeline=True,
        current_admin=current_admin,
    )


@router.patch("/service-requests/{service_request_id}/assignments/{assignment_id}", response_model=ServiceRequestOut)
async def update_admin_service_request_assignment(
    service_request_id: UUID,
    assignment_id: UUID,
    payload: ServiceRequestAssignmentUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("service_request.assign")),
    _: None = Depends(require_csrf),
) -> ServiceRequestOut:
    service_request = await service_request_crud.get_service_request_by_id(
        db,
        service_request_id,
        include_related=True,
    )
    if service_request is None:
        raise _not_found("Service request not found")
    assignment = next((item for item in service_request.assignments if item.id == assignment_id), None)
    if assignment is None:
        raise _not_found("Assignment not found")

    old_value = serialize_for_audit(assignment)
    assignment.unassigned_at = payload.unassigned_at
    service_request_crud.touch_service_request_activity(service_request)
    db.add(assignment)
    db.add(service_request)
    await _commit_with_conflict(db, detail="Assignment update conflicted.")
    refreshed = await service_request_crud.get_service_request_by_id(
        db,
        service_request_id,
        include_related=True,
    )
    if refreshed is None:
        raise _not_found("Service request not found")
    await _log_route_audit(
        db,
        request=request,
        current_admin=current_admin,
        action="service_request.assignment_update",
        target_type="service_request_assignment",
        target_id=assignment_id,
        old_value=old_value,
        new_value=assignment,
    )
    return await _service_request_out(
        db,
        refreshed,
        request,
        include_timeline=True,
        current_admin=current_admin,
    )


@router.get("/service-requests/{service_request_id}/threads", response_model=list[InboxThreadOut])
async def list_admin_service_request_threads(
    service_request_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("service_request.thread.read")),
) -> list[InboxThreadOut]:
    service_request = await service_request_crud.get_service_request_by_id(
        db,
        service_request_id,
        include_related=True,
    )
    if service_request is None:
        raise _not_found("Service request not found")
    return [InboxThreadOut.model_validate(thread) for thread in service_request.threads]


@router.get("/service-requests/{service_request_id}/messages", response_model=list[InboxMessageOut])
async def list_admin_service_request_messages(
    service_request_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("service_request.thread.read")),
) -> list[InboxMessageOut]:
    service_request = await service_request_crud.get_service_request_by_id(
        db,
        service_request_id,
        include_related=True,
    )
    if service_request is None:
        raise _not_found("Service request not found")
    primary_thread = next((thread for thread in service_request.threads if thread.thread_kind == "primary"), None)
    return [InboxMessageOut.model_validate(item) for item in (primary_thread.messages if primary_thread else [])]


@router.post("/service-requests/{service_request_id}/messages", response_model=ServiceRequestOut)
async def create_admin_service_request_message(
    service_request_id: UUID,
    payload: InboxMessageCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("service_request.message.create")),
    _: None = Depends(require_csrf),
) -> ServiceRequestOut:
    service_request = await service_request_crud.get_service_request_by_id(
        db,
        service_request_id,
        include_related=True,
    )
    if service_request is None:
        raise _not_found("Service request not found")
    thread = await service_request_crud.get_or_create_primary_thread(
        db,
        service_request=service_request,
        subject=service_request.title,
    )
    message = await service_request_crud.add_inbox_message(
        db,
        thread=thread,
        payload=payload,
        author_admin=current_admin if payload.direction != "inbound" else None,
        service_request=service_request,
    )
    if payload.direction == "inbound":
        await notification_crud.emit_request_inbound_message_notifications(
            db,
            service_request=service_request,
            customer_name=service_request.customer.display_name,
            occurred_at=message.created_at,
        )
    await _commit_with_conflict(db, detail="Message creation conflicted.")
    refreshed = await service_request_crud.get_service_request_by_id(
        db,
        service_request_id,
        include_related=True,
    )
    if refreshed is None:
        raise _not_found("Service request not found")
    await _log_route_audit(
        db,
        request=request,
        current_admin=current_admin,
        action="service_request.message.create",
        target_type="service_request",
        target_id=service_request_id,
        new_value=payload.model_dump(),
    )
    return await _service_request_out(
        db,
        refreshed,
        request,
        include_timeline=True,
        current_admin=current_admin,
    )


@router.get("/service-requests/{service_request_id}/notes", response_model=list[RecordNoteOut])
async def list_admin_service_request_notes(
    service_request_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("service_request.read")),
) -> list[RecordNoteOut]:
    service_request = await service_request_crud.get_service_request_by_id(
        db,
        service_request_id,
        include_related=True,
    )
    if service_request is None:
        raise _not_found("Service request not found")
    return [RecordNoteOut.model_validate(item) for item in service_request.notes]


@router.post("/service-requests/{service_request_id}/notes", response_model=ServiceRequestOut)
async def create_admin_service_request_note(
    service_request_id: UUID,
    payload: RecordNoteCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("service_request.note.create")),
    _: None = Depends(require_csrf),
) -> ServiceRequestOut:
    service_request = await service_request_crud.get_service_request_by_id(
        db,
        service_request_id,
        include_related=True,
    )
    if service_request is None:
        raise _not_found("Service request not found")
    await service_request_crud.add_note(
        db,
        service_request_id=service_request.id,
        payload=payload,
        created_by_admin=current_admin,
    )
    await _commit_with_conflict(db, detail="Note creation conflicted.")
    refreshed = await service_request_crud.get_service_request_by_id(
        db,
        service_request_id,
        include_related=True,
    )
    if refreshed is None:
        raise _not_found("Service request not found")
    await _log_route_audit(
        db,
        request=request,
        current_admin=current_admin,
        action="service_request.note.create",
        target_type="service_request",
        target_id=service_request_id,
        new_value=payload.model_dump(),
    )
    return await _service_request_out(
        db,
        refreshed,
        request,
        include_timeline=True,
        current_admin=current_admin,
    )


@router.get("/service-requests/{service_request_id}/documents", response_model=list[RecordDocumentOut])
async def list_admin_service_request_documents(
    service_request_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("service_request.document.read")),
) -> list[RecordDocumentOut]:
    service_request = await service_request_crud.get_service_request_by_id(
        db,
        service_request_id,
        include_related=True,
    )
    if service_request is None:
        raise _not_found("Service request not found")
    return [_document_out(item, request) for item in service_request.documents]


@router.post("/service-requests/{service_request_id}/documents", response_model=ServiceRequestOut)
async def upload_admin_service_request_document(
    service_request_id: UUID,
    request: Request,
    classification: str = Form(default="internal_attachment"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("service_request.document.create")),
    _: None = Depends(require_csrf),
) -> ServiceRequestOut:
    service_request = await service_request_crud.get_service_request_by_id(
        db,
        service_request_id,
        include_related=True,
    )
    if service_request is None:
        raise _not_found("Service request not found")

    content, extension = await _read_document_upload(file)
    storage_key = f"{uuid4().hex}.{extension}"
    destination = documents_dir / storage_key
    destination.write_bytes(content)

    await service_request_crud.add_document(
        db,
        service_request_id=service_request.id,
        classification=classification,
        storage_key=storage_key,
        original_filename=file.filename or f"document.{extension}",
        mime_type=file.content_type or "application/octet-stream",
        file_size=len(content),
        uploaded_by_admin=current_admin,
    )
    await _commit_with_conflict(db, detail="Document upload conflicted.")
    refreshed = await service_request_crud.get_service_request_by_id(
        db,
        service_request_id,
        include_related=True,
    )
    if refreshed is None:
        raise _not_found("Service request not found")
    await _log_route_audit(
        db,
        request=request,
        current_admin=current_admin,
        action="service_request.document.create",
        target_type="service_request",
        target_id=service_request_id,
        new_value={"storage_key": storage_key, "classification": classification},
    )
    return await _service_request_out(
        db,
        refreshed,
        request,
        include_timeline=True,
        current_admin=current_admin,
    )


@router.get("/documents/{document_id}/download", name="download_admin_document")
async def download_admin_document(
    document_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("service_request.document.read")),
) -> FileResponse:
    document = await service_request_crud.get_document_by_id(db, document_id)
    if document is None:
        raise _not_found("Document not found")
    file_path = documents_dir / Path(document.storage_key).name
    if not file_path.exists():
        raise _not_found("Document file not found")

    await _log_route_audit(
        db,
        request=request,
        current_admin=current_admin,
        action="service_request.document.download",
        target_type="document",
        target_id=document_id,
        new_value={"storage_key": document.storage_key},
    )

    return FileResponse(
        path=file_path,
        filename=document.original_filename,
        media_type=document.mime_type,
    )
