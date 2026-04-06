from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_csrf, require_permission
from app.crud import notification as notification_crud
from app.models import AdminNotification, AdminUser
from app.schemas import (
    AdminNotificationListResponse,
    AdminNotificationMarkAllReadPayload,
    AdminNotificationMarkAllReadResponse,
    AdminNotificationOut,
    AdminNotificationPreferenceListResponse,
    AdminNotificationPreferenceOut,
    AdminNotificationPreferenceUpdate,
    AdminNotificationReadResponse,
)

router = APIRouter(prefix="/admin/notifications", tags=["admin-notifications"])


def _not_found(detail: str = "Notification not found") -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _can_open_notification_link(notification: AdminNotification, current_admin: AdminUser) -> bool:
    resource_type = notification.resource_type
    if resource_type in {None, "", "auth", "report", "system"}:
        return True
    permission_map = {
        "service_request": {"service_request.read", "consultation.read"},
        "consultation": {"consultation.read", "service_request.read"},
        "admin_user": {"user.manage"},
        "page": {"page.read", "page.approve", "page.reject", "page.publish"},
        "blog_post": {
            "blog_post.read",
            "blog_post.approve",
            "blog_post.reject",
            "blog_post.publish",
        },
        "testimonial": {
            "testimonial.read",
            "testimonial.approve",
            "testimonial.reject",
            "testimonial.publish",
        },
    }
    required = permission_map.get(resource_type)
    if required is None:
        return True
    return bool(required.intersection(current_admin.permissions))


def _notification_out(notification: AdminNotification, current_admin: AdminUser) -> AdminNotificationOut:
    payload = AdminNotificationOut.model_validate(notification)
    href = notification.href if _can_open_notification_link(notification, current_admin) else None
    return payload.model_copy(update={"href": href})


@router.get("", response_model=AdminNotificationListResponse)
async def list_admin_notifications(
    status_value: str = Query(default="all", alias="status"),
    category: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("notification.read")),
) -> AdminNotificationListResponse:
    items, total, unread_total = await notification_crud.list_notifications(
        db,
        recipient_admin_id=current_admin.id,
        status=status_value,
        category=category,
        severity=severity,
        page=page,
        limit=limit,
    )
    return AdminNotificationListResponse.build(
        items=[_notification_out(item, current_admin) for item in items],
        page=page,
        limit=limit,
        total=total,
        unread_total=unread_total,
    )


@router.post("/mark-all-read", response_model=AdminNotificationMarkAllReadResponse)
async def mark_all_admin_notifications_read(
    payload: AdminNotificationMarkAllReadPayload | None = None,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("notification.update")),
    _: None = Depends(require_csrf),
) -> AdminNotificationMarkAllReadResponse:
    updated = await notification_crud.mark_all_notifications_read(
        db,
        recipient_admin_id=current_admin.id,
        category=payload.category if payload else None,
    )
    await db.commit()
    _, _, unread_total = await notification_crud.list_notifications(
        db,
        recipient_admin_id=current_admin.id,
        page=1,
        limit=1,
    )
    return AdminNotificationMarkAllReadResponse(
        updated=updated,
        unread_total=unread_total,
    )


@router.get("/preferences", response_model=AdminNotificationPreferenceListResponse)
async def get_admin_notification_preferences(
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("notification.preference.read")),
) -> AdminNotificationPreferenceListResponse:
    preferences = await notification_crud.list_notification_preferences(
        db,
        admin_user_id=current_admin.id,
    )
    return AdminNotificationPreferenceListResponse(
        items=[AdminNotificationPreferenceOut.model_validate(item) for item in preferences]
    )


@router.patch("/preferences", response_model=AdminNotificationPreferenceListResponse)
async def update_admin_notification_preferences(
    payload: list[AdminNotificationPreferenceUpdate],
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("notification.preference.update")),
    _: None = Depends(require_csrf),
) -> AdminNotificationPreferenceListResponse:
    preferences = await notification_crud.upsert_notification_preferences(
        db,
        admin_user=current_admin,
        updates=[(item.category, item.in_app_enabled) for item in payload],
    )
    await db.commit()
    return AdminNotificationPreferenceListResponse(
        items=[AdminNotificationPreferenceOut.model_validate(item) for item in preferences]
    )


@router.post("/{notification_id}/read", response_model=AdminNotificationReadResponse)
async def mark_admin_notification_read(
    notification_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("notification.update")),
    _: None = Depends(require_csrf),
) -> AdminNotificationReadResponse:
    notification = await notification_crud.get_notification_for_admin(
        db,
        notification_id=notification_id,
        recipient_admin_id=current_admin.id,
    )
    if notification is None:
        raise _not_found()
    notification = await notification_crud.mark_notification_read(db, notification=notification)
    await db.commit()
    assert notification.read_at is not None
    return AdminNotificationReadResponse(
        id=notification.id,
        is_read=notification.is_read,
        read_at=notification.read_at,
    )
