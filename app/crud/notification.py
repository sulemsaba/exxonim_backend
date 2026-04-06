from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    AdminNotification,
    AdminNotificationPreference,
    AdminUser,
    Role,
    ServiceRequest,
)


NOTIFICATION_CATEGORIES = (
    "request_ops",
    "content_review",
    "security",
    "reporting",
    "system",
)
NOTIFICATION_SEVERITIES = ("info", "success", "warning", "error")
NOTIFICATION_EVENT_TYPES = (
    "request.submitted",
    "request.inbound_message",
    "request.assigned",
    "request.overdue",
    "content.pending_review",
    "security.suspicious_login",
    "security.admin_role_changed",
    "security.admin_status_changed",
    "report.generated",
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def floor_to_fifteen_minute_window(value: datetime) -> datetime:
    minute_bucket = (value.minute // 15) * 15
    return value.replace(minute=minute_bucket, second=0, microsecond=0)


def _notification_actor_label(admin: AdminUser | None) -> str:
    if admin is None:
        return "An administrator"
    return (admin.full_name or admin.email).strip()


def _notification_target_label(admin: AdminUser) -> str:
    return (admin.full_name or admin.email).strip()


def _build_access_roles_notification_href(admin: AdminUser) -> str:
    return f"/admin/access/roles/?search={quote(admin.email, safe='')}"


def _build_service_request_notification_href(service_request: ServiceRequest) -> str:
    if service_request.legacy_consultation_id:
        return f"/admin/consultations/{service_request.legacy_consultation_id}/"
    return f"/admin/consultations/?search={quote(service_request.tracking_id, safe='')}"


def _notification_select():
    return select(AdminNotification).options(
        selectinload(AdminNotification.actor_admin),
    )


async def list_notifications(
    db: AsyncSession,
    *,
    recipient_admin_id: int,
    status: str = "all",
    category: str | None = None,
    severity: str | None = None,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[AdminNotification], int, int]:
    safe_page = max(page, 1)
    safe_limit = max(min(limit, 100), 1)
    base_query = select(AdminNotification.id).where(
        AdminNotification.recipient_admin_id == recipient_admin_id
    )

    if status == "unread":
        base_query = base_query.where(AdminNotification.is_read.is_(False))
    if category:
        base_query = base_query.where(AdminNotification.category == category)
    if severity:
        base_query = base_query.where(AdminNotification.severity == severity)

    total = int(await db.scalar(select(func.count()).select_from(base_query.subquery())) or 0)
    unread_total = int(
        await db.scalar(
            select(func.count())
            .select_from(AdminNotification)
            .where(
                AdminNotification.recipient_admin_id == recipient_admin_id,
                AdminNotification.is_read.is_(False),
            )
        )
        or 0
    )
    id_result = await db.execute(
        base_query.order_by(
            AdminNotification.last_occurred_at.desc(),
            AdminNotification.created_at.desc(),
        )
        .offset((safe_page - 1) * safe_limit)
        .limit(safe_limit)
    )
    ids = list(id_result.scalars().all())
    if not ids:
        return [], total, unread_total

    result = await db.execute(
        _notification_select()
        .where(AdminNotification.id.in_(ids))
        .order_by(
            AdminNotification.last_occurred_at.desc(),
            AdminNotification.created_at.desc(),
        )
    )
    return list(result.scalars().all()), total, unread_total


async def get_notification_for_admin(
    db: AsyncSession,
    *,
    notification_id: UUID,
    recipient_admin_id: int,
) -> AdminNotification | None:
    result = await db.execute(
        _notification_select().where(
            AdminNotification.id == notification_id,
            AdminNotification.recipient_admin_id == recipient_admin_id,
        )
    )
    return result.scalar_one_or_none()


async def mark_notification_read(
    db: AsyncSession,
    *,
    notification: AdminNotification,
) -> AdminNotification:
    if notification.is_read:
        return notification
    notification.is_read = True
    notification.read_at = utcnow()
    db.add(notification)
    await db.flush()
    return notification


async def mark_all_notifications_read(
    db: AsyncSession,
    *,
    recipient_admin_id: int,
    category: str | None = None,
) -> int:
    now = utcnow()
    conditions = [
        AdminNotification.recipient_admin_id == recipient_admin_id,
        AdminNotification.is_read.is_(False),
    ]
    if category:
        conditions.append(AdminNotification.category == category)

    result = await db.execute(_notification_select().where(*conditions))
    notifications = list(result.scalars().all())
    for notification in notifications:
        notification.is_read = True
        notification.read_at = now
        db.add(notification)
    await db.flush()
    return len(notifications)


async def get_notification_preferences_map(
    db: AsyncSession,
    *,
    admin_user_id: int,
) -> dict[str, bool]:
    result = await db.execute(
        select(AdminNotificationPreference).where(
            AdminNotificationPreference.admin_user_id == admin_user_id
        )
    )
    preferences = {
        preference.category: preference.in_app_enabled
        for preference in result.scalars().all()
    }
    for category in NOTIFICATION_CATEGORIES:
        preferences.setdefault(category, True)
    return preferences


async def list_notification_preferences(
    db: AsyncSession,
    *,
    admin_user_id: int,
) -> list[AdminNotificationPreference]:
    result = await db.execute(
        select(AdminNotificationPreference)
        .where(AdminNotificationPreference.admin_user_id == admin_user_id)
        .order_by(AdminNotificationPreference.category.asc())
    )
    existing = {preference.category: preference for preference in result.scalars().all()}
    for category in NOTIFICATION_CATEGORIES:
        existing.setdefault(
            category,
            AdminNotificationPreference(
                admin_user_id=admin_user_id,
                category=category,
                in_app_enabled=True,
            ),
        )
    return [existing[category] for category in NOTIFICATION_CATEGORIES]


async def upsert_notification_preferences(
    db: AsyncSession,
    *,
    admin_user: AdminUser,
    updates: Iterable[tuple[str, bool]],
) -> list[AdminNotificationPreference]:
    result = await db.execute(
        select(AdminNotificationPreference).where(
            AdminNotificationPreference.admin_user_id == admin_user.id
        )
    )
    existing = {preference.category: preference for preference in result.scalars().all()}

    for category, enabled in updates:
        preference = existing.get(category)
        if preference is None:
            preference = AdminNotificationPreference(
                admin_user_id=admin_user.id,
                category=category,
                in_app_enabled=enabled,
            )
            db.add(preference)
            existing[category] = preference
        else:
            preference.in_app_enabled = enabled
            db.add(preference)

    await db.flush()
    return await list_notification_preferences(db, admin_user_id=admin_user.id)


async def list_active_admins_with_permissions(
    db: AsyncSession,
    *,
    required_permissions: Iterable[str],
    category: str,
) -> list[AdminUser]:
    permission_set = set(required_permissions)
    if not permission_set:
        return []

    result = await db.execute(
        select(AdminUser)
        .options(
            selectinload(AdminUser.assigned_roles).selectinload(Role.granted_permissions),
            selectinload(AdminUser.notification_preferences),
        )
        .where(AdminUser.is_active.is_(True))
        .order_by(AdminUser.email.asc())
    )
    admins = list(result.scalars().all())
    recipients: list[AdminUser] = []
    for admin in admins:
        if not permission_set.intersection(admin.permissions):
            continue

        preference = next(
            (
                item
                for item in admin.notification_preferences
                if item.category == category
            ),
            None,
        )
        if preference is not None and not preference.in_app_enabled:
            continue
        recipients.append(admin)

    return recipients


async def create_or_bump_notification(
    db: AsyncSession,
    *,
    recipient_admin_id: int,
    category: str,
    event_type: str,
    severity: str,
    title: str,
    body: str | None = None,
    href: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    actor_admin_id: int | None = None,
    dedupe_key: str | None = None,
    occurred_at: datetime | None = None,
) -> AdminNotification:
    timestamp = occurred_at or utcnow()
    if dedupe_key:
        existing = await db.scalar(
            select(AdminNotification).where(
                AdminNotification.recipient_admin_id == recipient_admin_id,
                AdminNotification.dedupe_key == dedupe_key,
                AdminNotification.is_read.is_(False),
            )
        )
        if existing is not None:
            existing.category = category
            existing.event_type = event_type
            existing.severity = severity
            existing.title = title
            existing.body = body
            existing.href = href
            existing.resource_type = resource_type
            existing.resource_id = resource_id
            existing.actor_admin_id = actor_admin_id
            existing.last_occurred_at = timestamp
            existing.occurrence_count += 1
            db.add(existing)
            await db.flush()
            return existing

    notification = AdminNotification(
        recipient_admin_id=recipient_admin_id,
        category=category,
        event_type=event_type,
        severity=severity,
        title=title,
        body=body,
        href=href,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_admin_id=actor_admin_id,
        dedupe_key=dedupe_key,
        occurrence_count=1,
        is_read=False,
        last_occurred_at=timestamp,
    )
    db.add(notification)
    await db.flush()
    return notification


async def emit_request_submitted_notifications(
    db: AsyncSession,
    *,
    service_request: ServiceRequest,
    customer_name: str,
) -> int:
    recipients = await list_active_admins_with_permissions(
        db,
        required_permissions={"service_request.read"},
        category="request_ops",
    )
    href = _build_service_request_notification_href(service_request)
    for admin in recipients:
        await create_or_bump_notification(
            db,
            recipient_admin_id=admin.id,
            category="request_ops",
            event_type="request.submitted",
            severity="info",
            title="New request submitted",
            body=f"{customer_name} submitted request {service_request.tracking_id}.",
            href=href,
            resource_type="service_request",
            resource_id=str(service_request.id),
            dedupe_key=f"request-submitted:{service_request.id}",
            occurred_at=service_request.created_at,
        )
    return len(recipients)


def get_active_assignment_admin_ids(service_request: ServiceRequest) -> list[int]:
    return [
        assignment.admin_user_id
        for assignment in service_request.assignments
        if assignment.unassigned_at is None
    ]


async def emit_request_inbound_message_notifications(
    db: AsyncSession,
    *,
    service_request: ServiceRequest,
    customer_name: str,
    occurred_at: datetime,
) -> int:
    recipient_ids = list(dict.fromkeys(get_active_assignment_admin_ids(service_request)))
    if recipient_ids:
        result = await db.execute(
            select(AdminUser)
            .options(selectinload(AdminUser.notification_preferences))
            .where(
                AdminUser.id.in_(recipient_ids),
                AdminUser.is_active.is_(True),
            )
        )
        recipients = list(result.scalars().all())
        recipients = [
            admin
            for admin in recipients
            if next(
                (
                    preference.in_app_enabled
                    for preference in admin.notification_preferences
                    if preference.category == "request_ops"
                ),
                True,
            )
        ]
    else:
        recipients = await list_active_admins_with_permissions(
            db,
            required_permissions={"service_request.read"},
            category="request_ops",
        )

    href = _build_service_request_notification_href(service_request)
    for admin in recipients:
        await create_or_bump_notification(
            db,
            recipient_admin_id=admin.id,
            category="request_ops",
            event_type="request.inbound_message",
            severity="info",
            title="New customer reply",
            body=f"{customer_name} replied on request {service_request.tracking_id}.",
            href=href,
            resource_type="service_request",
            resource_id=str(service_request.id),
            dedupe_key=f"request-reply:{service_request.id}",
            occurred_at=occurred_at,
        )
    return len(recipients)


async def emit_request_assigned_notification(
    db: AsyncSession,
    *,
    service_request: ServiceRequest,
    recipient_admin: AdminUser,
    assigned_by_admin: AdminUser | None,
    occurred_at: datetime,
) -> AdminNotification | None:
    preferences = await get_notification_preferences_map(
        db,
        admin_user_id=recipient_admin.id,
    )
    if not preferences.get("request_ops", True):
        return None

    href = _build_service_request_notification_href(service_request)
    return await create_or_bump_notification(
        db,
        recipient_admin_id=recipient_admin.id,
        category="request_ops",
        event_type="request.assigned",
        severity="info",
        title="Request assigned to you",
        body=f"Request {service_request.tracking_id} was assigned to you.",
        href=href,
        resource_type="service_request",
        resource_id=str(service_request.id),
        actor_admin_id=assigned_by_admin.id if assigned_by_admin else None,
        dedupe_key=f"request-assigned:{service_request.id}:{recipient_admin.id}",
        occurred_at=occurred_at,
    )


async def emit_content_pending_review_notifications(
    db: AsyncSession,
    *,
    content_type: str,
    content_id: int,
    title: str,
    href: str,
    actor_admin: AdminUser | None,
) -> int:
    permission_map = {
        "page": {"page.approve", "page.reject"},
        "blog_post": {"blog_post.approve", "blog_post.reject"},
        "testimonial": {"testimonial.approve", "testimonial.reject"},
    }
    required_permissions = permission_map.get(content_type)
    if not required_permissions:
        return 0

    recipients = await list_active_admins_with_permissions(
        db,
        required_permissions=required_permissions,
        category="content_review",
    )
    event_type = "content.pending_review"
    for admin in recipients:
        await create_or_bump_notification(
            db,
            recipient_admin_id=admin.id,
            category="content_review",
            event_type=event_type,
            severity="info",
            title="Content awaiting review",
            body=f"{title} is waiting for approval.",
            href=href,
            resource_type=content_type,
            resource_id=str(content_id),
            actor_admin_id=actor_admin.id if actor_admin else None,
            dedupe_key=f"content-review:{content_type}:{content_id}",
        )
    return len(recipients)


async def emit_suspicious_login_notifications(
    db: AsyncSession,
    *,
    email: str,
    attempt_count: int,
    observed_at: datetime,
) -> int:
    recipients = await list_active_admins_with_permissions(
        db,
        required_permissions={"audit_log.read"},
        category="security",
    )
    window_start = floor_to_fifteen_minute_window(observed_at)
    normalized_email = email.strip().lower()
    for admin in recipients:
        await create_or_bump_notification(
            db,
            recipient_admin_id=admin.id,
            category="security",
            event_type="security.suspicious_login",
            severity="error",
            title="Suspicious login activity",
            body=f"{attempt_count} failed login attempts were detected for {email} within 15 minutes.",
            href=None,
            resource_type="auth",
            resource_id=normalized_email,
            dedupe_key=f"security-login-failed:{normalized_email}:{window_start.isoformat()}",
            occurred_at=observed_at,
        )
    return len(recipients)


async def emit_admin_role_changed_notifications(
    db: AsyncSession,
    *,
    target_admin: AdminUser,
    actor_admin: AdminUser | None,
    old_role: str | None,
    new_role: str | None,
    occurred_at: datetime | None = None,
) -> int:
    recipients = await list_active_admins_with_permissions(
        db,
        required_permissions={"audit_log.read"},
        category="security",
    )
    actor_label = _notification_actor_label(actor_admin)
    target_label = _notification_target_label(target_admin)
    href = _build_access_roles_notification_href(target_admin)
    previous_role = old_role or "unassigned"
    current_role = new_role or "unassigned"

    for admin in recipients:
        await create_or_bump_notification(
            db,
            recipient_admin_id=admin.id,
            category="security",
            event_type="security.admin_role_changed",
            severity="warning",
            title="Admin role changed",
            body=(
                f"{actor_label} changed {target_label}'s role "
                f"from {previous_role} to {current_role}."
            ),
            href=href,
            resource_type="admin_user",
            resource_id=str(target_admin.id),
            actor_admin_id=actor_admin.id if actor_admin else None,
            dedupe_key=None,
            occurred_at=occurred_at,
        )
    return len(recipients)


async def emit_admin_status_changed_notifications(
    db: AsyncSession,
    *,
    target_admin: AdminUser,
    actor_admin: AdminUser | None,
    is_active: bool,
    occurred_at: datetime | None = None,
) -> int:
    recipients = await list_active_admins_with_permissions(
        db,
        required_permissions={"audit_log.read"},
        category="security",
    )
    actor_label = _notification_actor_label(actor_admin)
    target_label = _notification_target_label(target_admin)
    href = _build_access_roles_notification_href(target_admin)

    if is_active:
        title = "Admin account activated"
        severity = "info"
        body = f"{target_label} was activated by {actor_label}."
    else:
        title = "Admin account deactivated"
        severity = "error"
        body = f"{target_label} was deactivated by {actor_label}."

    for admin in recipients:
        await create_or_bump_notification(
            db,
            recipient_admin_id=admin.id,
            category="security",
            event_type="security.admin_status_changed",
            severity=severity,
            title=title,
            body=body,
            href=href,
            resource_type="admin_user",
            resource_id=str(target_admin.id),
            actor_admin_id=actor_admin.id if actor_admin else None,
            dedupe_key=None,
            occurred_at=occurred_at,
        )
    return len(recipients)


async def emit_report_generated_notification(
    db: AsyncSession,
    *,
    recipient_admin: AdminUser,
    title: str,
    href: str | None = None,
    resource_type: str | None = "report",
    resource_id: str | None = None,
) -> AdminNotification | None:
    preferences = await get_notification_preferences_map(
        db,
        admin_user_id=recipient_admin.id,
    )
    if not preferences.get("reporting", True):
        return None
    return await create_or_bump_notification(
        db,
        recipient_admin_id=recipient_admin.id,
        category="reporting",
        event_type="report.generated",
        severity="info",
        title=title,
        body="Your report is ready.",
        href=href,
        resource_type=resource_type,
        resource_id=resource_id,
        dedupe_key=None,
    )


async def emit_overdue_notifications(
    db: AsyncSession,
    *,
    now: datetime | None = None,
) -> int:
    timestamp = now or utcnow()
    active_statuses = ("new", "triaged", "waiting_customer", "in_progress")
    result = await db.execute(
        select(ServiceRequest)
        .options(
            selectinload(ServiceRequest.customer),
            selectinload(ServiceRequest.assignments),
        )
        .where(
            ServiceRequest.due_at.is_not(None),
            ServiceRequest.due_at < timestamp,
            ServiceRequest.status.in_(active_statuses),
        )
    )
    requests = list(result.scalars().unique().all())
    emitted = 0
    for service_request in requests:
        recipient_ids = list(dict.fromkeys(get_active_assignment_admin_ids(service_request)))
        if recipient_ids:
            admin_result = await db.execute(
                select(AdminUser)
                .options(selectinload(AdminUser.notification_preferences))
                .where(
                    AdminUser.id.in_(recipient_ids),
                    AdminUser.is_active.is_(True),
                )
            )
            recipients = list(admin_result.scalars().all())
            recipients = [
                admin
                for admin in recipients
                if next(
                    (
                        preference.in_app_enabled
                        for preference in admin.notification_preferences
                        if preference.category == "request_ops"
                    ),
                    True,
                )
            ]
        else:
            recipients = await list_active_admins_with_permissions(
                db,
                required_permissions={"service_request.read"},
                category="request_ops",
            )

        href = _build_service_request_notification_href(service_request)
        date_key = timestamp.date().isoformat()
        for admin in recipients:
            await create_or_bump_notification(
                db,
                recipient_admin_id=admin.id,
                category="request_ops",
                event_type="request.overdue",
                severity="warning",
                title="Request is overdue",
                body=f"Request {service_request.tracking_id} is past its due date.",
                href=href,
                resource_type="service_request",
                resource_id=str(service_request.id),
                dedupe_key=f"request-overdue:{service_request.id}:{admin.id}:{date_key}",
                occurred_at=timestamp,
            )
            emitted += 1
    return emitted


async def count_recent_failed_logins_for_email(
    db: AsyncSession,
    *,
    email: str,
    within_minutes: int = 15,
    now: datetime | None = None,
) -> int:
    from app.models import AuditLog

    timestamp = now or utcnow()
    window_start = timestamp - timedelta(minutes=within_minutes)
    return int(
        await db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.action == "auth.login_failed",
                func.lower(func.coalesce(AuditLog.actor_email, "")) == email.strip().lower(),
                AuditLog.created_at >= window_start,
            )
        )
        or 0
    )
