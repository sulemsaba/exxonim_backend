from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_admin
from app.crud import admin as admin_crud
from app.crud import consultation as consultation_crud
from app.models import AdminUser
from app.schemas.consultation import (
    AdminStaffOut,
    ConsultationAdminDetailOut,
    ConsultationAdminListItemOut,
    ConsultationAdminListResponse,
    ConsultationAssignedStaffOut,
    ConsultationManualNotifyRequest,
    ConsultationManualNotifyResponse,
    ConsultationStatusHistoryAdminOut,
    ConsultationUpdate,
    NotificationLogOut,
)
from app.services.consultation_notifications import (
    build_status_update_notification,
    queue_notification,
)

router = APIRouter(prefix="/admin/consultations", tags=["admin-consultations"])
staff_router = APIRouter(prefix="/admin/staff", tags=["admin-staff"])


def _serialize_staff(admin: AdminUser | None) -> ConsultationAssignedStaffOut | None:
    if admin is None:
        return None

    return ConsultationAssignedStaffOut(
        id=admin.id,
        full_name=admin.email,
        email=admin.email,
    )


def _serialize_status_history(item) -> ConsultationStatusHistoryAdminOut:
    return ConsultationStatusHistoryAdminOut(
        id=item.id,
        old_status=item.old_status,
        new_status=item.new_status,
        changed_at=item.created_at,
        comment=item.comment,
        changed_by=_serialize_staff(item.changed_by_admin),
    )


def _serialize_notification_log(item) -> NotificationLogOut:
    return NotificationLogOut(
        id=item.id,
        type=item.type,
        recipient=item.recipient,
        subject=item.subject,
        body=item.body,
        status=item.status,
        error_message=item.error_message,
        created_at=item.created_at,
    )


def _serialize_detail(consultation) -> ConsultationAdminDetailOut:
    return ConsultationAdminDetailOut(
        id=consultation.id,
        tracking_id=consultation.tracking_id,
        full_name=consultation.full_name,
        email=consultation.email,
        phone=consultation.phone,
        company=consultation.company,
        message=consultation.message,
        status=consultation.status,
        assigned_to=_serialize_staff(consultation.assigned_admin),
        notes=consultation.notes,
        public_notes=consultation.public_notes,
        status_history=[_serialize_status_history(item) for item in consultation.status_history],
        notification_logs=[
            _serialize_notification_log(item) for item in consultation.notification_logs
        ],
        created_at=consultation.created_at,
        updated_at=consultation.updated_at,
    )


@router.get("", response_model=ConsultationAdminListResponse)
async def list_consultations(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    assigned_to: int | None = Query(default=None),
    search: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> ConsultationAdminListResponse:
    items, total = await consultation_crud.list_consultations(
        db,
        page=page,
        limit=limit,
        status=status_filter,
        assigned_to=assigned_to,
        search=search,
    )

    return ConsultationAdminListResponse(
        items=[
            ConsultationAdminListItemOut(
                id=item.id,
                tracking_id=item.tracking_id,
                full_name=item.full_name,
                email=item.email,
                status=item.status,
                assigned_to=_serialize_staff(item.assigned_admin),
                created_at=item.created_at,
            )
            for item in items
        ],
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/{consultation_id}", response_model=ConsultationAdminDetailOut)
async def get_consultation(
    consultation_id: int,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> ConsultationAdminDetailOut:
    consultation = await consultation_crud.get_consultation_by_id(db, consultation_id)
    if consultation is None:
        raise HTTPException(status_code=404, detail="Consultation not found")
    return _serialize_detail(consultation)


@router.put("/{consultation_id}", response_model=ConsultationAdminDetailOut)
async def update_consultation(
    consultation_id: int,
    payload: ConsultationUpdate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> ConsultationAdminDetailOut:
    consultation = await consultation_crud.get_consultation_by_id(db, consultation_id)
    if consultation is None:
        raise HTTPException(status_code=404, detail="Consultation not found")

    update_data = payload.model_dump(exclude_unset=True)
    assigned_to = update_data.get("assigned_to")
    if assigned_to is not None:
        assigned_admin = await admin_crud.get_admin_by_id(db, assigned_to)
        if assigned_admin is None:
            raise HTTPException(status_code=404, detail="Assigned staff user not found")

    old_status = consultation.status
    consultation_crud.apply_consultation_update(consultation, payload)
    db.add(consultation)
    await db.flush()

    notification_log = None
    if payload.status is not None and payload.status != old_status:
        db.add(
            consultation_crud.build_status_history(
                consultation_id=consultation.id,
                old_status=old_status,
                new_status=payload.status,
                changed_by=current_admin.id,
                comment=payload.status_comment,
            )
        )

        subject, body = build_status_update_notification(
            consultation,
            message=payload.public_notes or payload.status_comment,
        )
        notification_log = consultation_crud.build_notification_log(
            consultation_id=consultation.id,
            notification_type="email",
            recipient=consultation.email,
            subject=subject,
            body=body,
        )
        db.add(notification_log)

    await db.commit()

    if notification_log is not None:
        await db.refresh(notification_log)
        queue_notification(background_tasks, notification_log_id=notification_log.id)

    refreshed = await consultation_crud.get_consultation_by_id(db, consultation.id)
    if refreshed is None:
        raise HTTPException(status_code=404, detail="Consultation not found")
    return _serialize_detail(refreshed)


@router.post("/{consultation_id}/notify", response_model=ConsultationManualNotifyResponse)
async def notify_consultation_customer(
    consultation_id: int,
    payload: ConsultationManualNotifyRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> ConsultationManualNotifyResponse:
    consultation = await consultation_crud.get_consultation_by_id(db, consultation_id)
    if consultation is None:
        raise HTTPException(status_code=404, detail="Consultation not found")

    if payload.type == "email" and not payload.subject:
        raise HTTPException(status_code=422, detail="Email notifications require a subject")

    recipient = consultation.email if payload.type == "email" else (consultation.phone or "")
    if not recipient:
        raise HTTPException(status_code=422, detail="Consultation has no valid recipient")

    notification_log = consultation_crud.build_notification_log(
        consultation_id=consultation.id,
        notification_type=payload.type,
        recipient=recipient,
        subject=payload.subject,
        body=payload.message,
    )
    db.add(notification_log)
    await db.commit()
    await db.refresh(notification_log)
    queue_notification(background_tasks, notification_log_id=notification_log.id)

    return ConsultationManualNotifyResponse(id=notification_log.id, status="queued")


@staff_router.get("", response_model=list[AdminStaffOut])
async def list_staff(
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> list[AdminStaffOut]:
    admins = await admin_crud.get_all_admins(db)
    return [
        AdminStaffOut(
            id=admin.id,
            email=admin.email,
            full_name=admin.email,
            is_active=admin.is_active,
        )
        for admin in admins
    ]
