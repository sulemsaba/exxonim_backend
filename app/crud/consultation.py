from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud import service_request as service_request_crud
from app.models import (
    AdminUser,
    Consultation,
    InboxMessage,
    InboxThread,
    RecordDocument,
    RecordNote,
    ServiceRequest,
    ServiceRequestAssignment,
    ServiceRequestStatusHistory,
)
from app.schemas.consultation import (
    ConsultationOut,
    ConsultationStatusHistoryOut,
    ConsultationUpdate,
)
from app.schemas.service_request import (
    CustomerOut,
    InboxMessageOut,
    RecordDocumentOut,
    RecordNoteOut,
    ServiceRequestStatusUpdate,
    ServiceRequestAssignmentOut,
    ServiceTypeOut,
    TimelineEventOut,
)


@dataclass
class CompatibilityConsultationHistoryEvent:
    id: str
    consultation: ConsultationOut | None
    old_status: str | None
    new_status: str
    comment: str | None
    created_at: datetime
    changed_by_admin: AdminUser | None = None


def _join_note_bodies(notes: Iterable, *, visibility: str) -> str | None:
    matching = [note.body.strip() for note in notes if note.visibility == visibility and note.body.strip()]
    if not matching:
        return None
    return "\n\n".join(reversed(matching))


async def _legacy_consultation_map(
    db: AsyncSession,
    legacy_ids: list[int],
) -> dict[int, Consultation]:
    if not legacy_ids:
        return {}
    result = await db.execute(
        select(Consultation).where(Consultation.id.in_(legacy_ids))
    )
    items = list(result.scalars().all())
    return {item.id: item for item in items}


async def _build_consultation_out(
    db: AsyncSession,
    service_request: ServiceRequest,
    *,
    include_related: bool = False,
    include_timeline: bool = False,
    current_admin_id: int | None = None,
    legacy: Consultation | None = None,
) -> ConsultationOut:
    lead_assignment = service_request_crud.get_active_lead_assignment(service_request)
    notes = _join_note_bodies(service_request.notes, visibility="internal") if include_related else None
    public_notes = (
        _join_note_bodies(service_request.notes, visibility="customer_safe")
        if include_related
        else None
    )
    primary_thread = (
        next((thread for thread in service_request.threads if thread.thread_kind == "primary"), None)
        if include_related
        else None
    )
    unread, unread_count = (
        service_request_crud.get_unread_summary(service_request, current_admin_id)
        if current_admin_id is not None
        else (False, 0)
    )

    payload = {
        "id": service_request.legacy_consultation_id or 0,
        "tracking_id": service_request.tracking_id,
        "idempotency_key": legacy.idempotency_key
        if legacy is not None
        else f"service-request:{service_request.id}",
        "full_name": service_request.customer.display_name,
        "email": service_request.customer.primary_email or "",
        "phone": service_request.customer.primary_phone,
        "company": service_request.customer.company_name,
        "message": service_request.intake_message or "",
        "status": service_request_crud.compatibility_status_from_service_request_status(
            service_request.status
        ),
        "assigned_to": lead_assignment.admin_user_id if lead_assignment else None,
        "notes": notes,
        "public_notes": public_notes,
        "created_at": service_request.created_at,
        "updated_at": service_request.updated_at,
        "assigned_admin": lead_assignment.admin_user if lead_assignment else None,
        "customer_id": service_request.customer_id,
        "service_request_id": service_request.id,
        "customer": CustomerOut.model_validate(service_request.customer),
        "service_type": ServiceTypeOut.model_validate(service_request.service_type),
        "priority": service_request.priority,
        "source_channel": service_request.source_channel,
        "opened_at": service_request.opened_at,
        "closed_at": service_request.closed_at,
        "last_activity_at": service_request.last_activity_at,
        "last_customer_message_at": service_request.last_customer_message_at,
        "unread": unread,
        "unread_count": unread_count,
        "assignments": [ServiceRequestAssignmentOut.model_validate(item) for item in service_request.assignments]
        if include_related
        else [],
        "messages": [],
        "notes_records": [RecordNoteOut.model_validate(item) for item in service_request.notes]
        if include_related
        else [],
        "documents": [RecordDocumentOut.model_validate(item) for item in service_request.documents]
        if include_related
        else [],
        "status_history": [],
        "timeline": [],
    }

    if include_related:
        payload["status_history"] = [
            ConsultationStatusHistoryOut(
                id=str(entry.id),
                old_status=service_request_crud.compatibility_status_from_service_request_status(entry.old_status)
                if entry.old_status
                else None,
                new_status=service_request_crud.compatibility_status_from_service_request_status(entry.new_status),
                comment=entry.comment,
                created_at=entry.created_at,
                changed_by_admin=entry.changed_by_admin,
            )
            for entry in service_request.status_history
        ]
        payload["messages"] = [
            InboxMessageOut.model_validate(message)
            for message in (primary_thread.messages if primary_thread else [])
        ]

    if include_timeline:
        payload["timeline"] = [
            TimelineEventOut.model_validate(item)
            for item in await service_request_crud.build_service_request_timeline(db, service_request)
        ]

    return ConsultationOut.model_validate(payload)


async def get_consultations(
    db: AsyncSession,
    *,
    page: int = 1,
    limit: int = 20,
    status: str | None = None,
    search: str | None = None,
    service_type: str | None = None,
    priority: str | None = None,
    assignee_id: int | None = None,
    source_channel: str | None = None,
    view: str | None = None,
    current_admin_id: int | None = None,
    include_history: bool = False,
) -> tuple[list[ConsultationOut], int]:
    mapped_status = (
        service_request_crud.COMPATIBILITY_STATUS_TO_REQUEST_STATUS.get(status)
        if status
        else None
    )
    requests, total = await service_request_crud.list_service_requests(
        db,
        page=page,
        limit=limit,
        status=mapped_status,
        search=search,
        service_type_code=service_type,
        priority=priority,
        assignee_id=assignee_id,
        source_channel=source_channel,
        view=view,
        current_admin_id=current_admin_id,
        include_related=include_history,
    )
    legacy_map = await _legacy_consultation_map(
        db,
        [
            request.legacy_consultation_id
            for request in requests
            if request.legacy_consultation_id is not None
        ],
    )
    items = [
        await _build_consultation_out(
            db,
            request,
            include_related=include_history,
            current_admin_id=current_admin_id,
            legacy=legacy_map.get(request.legacy_consultation_id or -1),
        )
        for request in requests
        if request.legacy_consultation_id is not None
    ]
    return items, total


async def get_consultation_by_id(
    db: AsyncSession,
    consultation_id: int,
    *,
    include_history: bool = False,
    current_admin_id: int | None = None,
) -> ConsultationOut | None:
    service_request = await service_request_crud.get_service_request_by_legacy_consultation_id(
        db,
        consultation_id,
        include_related=True,
    )
    if service_request is None:
        return None

    legacy = await db.get(Consultation, consultation_id)
    return await _build_consultation_out(
        db,
        service_request,
        include_related=include_history,
        include_timeline=include_history,
        current_admin_id=current_admin_id,
        legacy=legacy,
    )


async def get_recent_consultations(
    db: AsyncSession,
    *,
    limit: int = 4,
) -> list[ConsultationOut]:
    items, _ = await get_consultations(
        db,
        page=1,
        limit=limit,
        include_history=False,
    )
    return items


async def get_consultation_status_counts(db: AsyncSession) -> dict[str, int]:
    result = await db.execute(
        select(ServiceRequest.status, func.count(ServiceRequest.id))
        .where(ServiceRequest.legacy_consultation_id.is_not(None))
        .group_by(ServiceRequest.status)
    )
    counts: dict[str, int] = {"pending": 0, "contacted": 0, "completed": 0, "cancelled": 0}
    for status, count in result.all():
        compatibility_status = service_request_crud.compatibility_status_from_service_request_status(status)
        counts[compatibility_status] = counts.get(compatibility_status, 0) + int(count)
    return counts


async def get_recent_consultation_history(
    db: AsyncSession,
    *,
    limit: int = 8,
) -> list[CompatibilityConsultationHistoryEvent]:
    result = await db.execute(
        select(ServiceRequestStatusHistory)
        .join(ServiceRequest)
        .options(
            selectinload(ServiceRequestStatusHistory.changed_by_admin),
            selectinload(ServiceRequestStatusHistory.service_request)
            .selectinload(ServiceRequest.customer),
            selectinload(ServiceRequestStatusHistory.service_request)
            .selectinload(ServiceRequest.service_type),
            selectinload(ServiceRequestStatusHistory.service_request)
            .selectinload(ServiceRequest.assignments)
            .selectinload(ServiceRequestAssignment.admin_user),
            selectinload(ServiceRequestStatusHistory.service_request)
            .selectinload(ServiceRequest.notes)
            .selectinload(RecordNote.created_by_admin),
            selectinload(ServiceRequestStatusHistory.service_request)
            .selectinload(ServiceRequest.documents)
            .selectinload(RecordDocument.uploaded_by_admin),
            selectinload(ServiceRequestStatusHistory.service_request)
            .selectinload(ServiceRequest.threads)
            .selectinload(InboxThread.messages)
            .selectinload(InboxMessage.author_admin),
        )
        .where(ServiceRequest.legacy_consultation_id.is_not(None))
        .order_by(ServiceRequestStatusHistory.created_at.desc())
        .limit(limit)
    )
    entries = list(result.scalars().unique().all())
    legacy_map = await _legacy_consultation_map(
        db,
        [
            entry.service_request.legacy_consultation_id
            for entry in entries
            if entry.service_request and entry.service_request.legacy_consultation_id is not None
        ],
    )

    history: list[CompatibilityConsultationHistoryEvent] = []
    for entry in entries:
        service_request = entry.service_request
        if service_request is None or service_request.legacy_consultation_id is None:
            continue
        consultation = await _build_consultation_out(
            db,
            service_request,
            include_related=False,
            current_admin_id=None,
            legacy=legacy_map.get(service_request.legacy_consultation_id),
        )
        history.append(
            CompatibilityConsultationHistoryEvent(
                id=str(entry.id),
                consultation=consultation,
                old_status=service_request_crud.compatibility_status_from_service_request_status(entry.old_status)
                if entry.old_status
                else None,
                new_status=service_request_crud.compatibility_status_from_service_request_status(
                    entry.new_status
                ),
                comment=entry.comment,
                created_at=entry.created_at,
                changed_by_admin=entry.changed_by_admin,
            )
        )
    return history


async def update_consultation_from_compatibility(
    db: AsyncSession,
    *,
    consultation_id: int,
    payload: ConsultationUpdate,
    current_admin: AdminUser,
) -> ConsultationOut | None:
    service_request = await service_request_crud.get_service_request_by_legacy_consultation_id(
        db,
        consultation_id,
        include_related=True,
    )
    if service_request is None:
        return None

    if payload.status and payload.status != service_request_crud.compatibility_status_from_service_request_status(
        service_request.status
    ):
        await service_request_crud.update_service_request_status(
            db,
            service_request=service_request,
            payload=ServiceRequestStatusUpdate(
                status=service_request_crud.COMPATIBILITY_STATUS_TO_REQUEST_STATUS[payload.status],
                comment=payload.comment,
            ),
            changed_by_admin=current_admin,
        )

    current_lead = service_request_crud.get_active_lead_assignment(service_request)
    current_lead_id = current_lead.admin_user_id if current_lead else None
    if payload.assigned_to != current_lead_id:
        await service_request_crud.set_lead_assignment(
            db,
            service_request=service_request,
            admin_user_id=payload.assigned_to,
            assigned_by_admin=current_admin,
        )

    if "notes" in payload.model_fields_set:
        await service_request_crud.replace_service_request_compatibility_note(
            db,
            service_request=service_request,
            visibility="internal",
            body=payload.notes,
            created_by_admin=current_admin,
        )

    if "public_notes" in payload.model_fields_set:
        await service_request_crud.replace_service_request_compatibility_note(
            db,
            service_request=service_request,
            visibility="customer_safe",
            body=payload.public_notes,
            created_by_admin=current_admin,
        )

    await db.flush()
    refreshed = await service_request_crud.get_service_request_by_legacy_consultation_id(
        db,
        consultation_id,
        include_related=True,
    )
    if refreshed is None:
        return None

    legacy = await db.get(Consultation, consultation_id)
    return await _build_consultation_out(
        db,
        refreshed,
        include_related=True,
        include_timeline=True,
        current_admin_id=current_admin.id,
        legacy=legacy,
    )
