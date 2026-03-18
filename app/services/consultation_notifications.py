from __future__ import annotations

import logging

from fastapi import BackgroundTasks

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import create_consultation_magic_token
from app.models import Consultation, NotificationLog

logger = logging.getLogger(__name__)


def build_magic_link(consultation: Consultation) -> str:
    token = create_consultation_magic_token(
        consultation_id=consultation.id,
        tracking_id=consultation.tracking_id,
        email=consultation.email,
    )
    public_origin = settings.PUBLIC_SITE_URL.rstrip("/")
    return f"{public_origin}/track-consultation/?token={token}"


async def dispatch_notification(notification_log_id: int) -> None:
    async with AsyncSessionLocal() as db:
        notification_log = await db.get(NotificationLog, notification_log_id)
        if notification_log is None:
            return

        try:
            logger.info(
                "Simulated %s notification to %s: %s",
                notification_log.type,
                notification_log.recipient,
                notification_log.subject or "(no subject)",
            )
            logger.info("Notification body:\n%s", notification_log.body)
            notification_log.status = "sent"
            notification_log.error_message = None
        except Exception as exc:  # pragma: no cover
            notification_log.status = "failed"
            notification_log.error_message = str(exc)

        db.add(notification_log)
        await db.commit()


def queue_notification(
    background_tasks: BackgroundTasks,
    *,
    notification_log_id: int,
) -> None:
    background_tasks.add_task(dispatch_notification, notification_log_id)


def build_confirmation_notification(consultation: Consultation) -> tuple[str, str]:
    magic_link = build_magic_link(consultation)
    subject = f"Your Consultation Request – Tracking ID: {consultation.tracking_id}"
    body = (
        f"Hello {consultation.full_name},\n\n"
        f"Your consultation request has been received.\n"
        f"Tracking ID: {consultation.tracking_id}\n\n"
        f"Track your request here:\n{magic_link}\n"
    )
    return subject, body


def build_status_update_notification(
    consultation: Consultation,
    *,
    message: str | None = None,
) -> tuple[str, str]:
    magic_link = build_magic_link(consultation)
    body_parts = [
        f"Hello {consultation.full_name},",
        "",
        f"Your consultation status is now: {consultation.status}.",
    ]

    if message:
        body_parts.extend(["", message])
    elif consultation.public_notes:
        body_parts.extend(["", consultation.public_notes])

    body_parts.extend(["", "View details here:", magic_link])

    subject = f"Update on your consultation ({consultation.tracking_id})"
    return subject, "\n".join(body_parts)
