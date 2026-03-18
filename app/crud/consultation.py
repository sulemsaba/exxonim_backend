from __future__ import annotations

import secrets
import string

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Consultation, ConsultationStatusHistory, NotificationLog
from app.schemas.consultation import ConsultationPublicCreate, ConsultationUpdate

TRACKING_ID_ALPHABET = string.ascii_uppercase + string.digits


def _consultation_select():
    return select(Consultation).options(
        selectinload(Consultation.assigned_admin),
        selectinload(Consultation.status_history).selectinload(
            ConsultationStatusHistory.changed_by_admin
        ),
        selectinload(Consultation.notification_logs),
    )


async def generate_tracking_id(db: AsyncSession) -> str:
    while True:
        candidate = "".join(secrets.choice(TRACKING_ID_ALPHABET) for _ in range(10))
        existing = await db.execute(
            select(Consultation.id).where(Consultation.tracking_id == candidate)
        )
        if existing.scalar_one_or_none() is None:
            return candidate


async def get_consultation_by_id(db: AsyncSession, consultation_id: int) -> Consultation | None:
    result = await db.execute(
        _consultation_select().where(Consultation.id == consultation_id)
    )
    return result.scalar_one_or_none()


async def get_consultation_by_tracking_id(
    db: AsyncSession,
    tracking_id: str,
) -> Consultation | None:
    result = await db.execute(
        _consultation_select().where(Consultation.tracking_id == tracking_id)
    )
    return result.scalar_one_or_none()


async def get_consultation_by_idempotency_key(
    db: AsyncSession,
    idempotency_key: str,
) -> Consultation | None:
    result = await db.execute(
        _consultation_select().where(Consultation.idempotency_key == idempotency_key)
    )
    return result.scalar_one_or_none()


async def list_consultations(
    db: AsyncSession,
    *,
    page: int,
    limit: int,
    status: str | None = None,
    assigned_to: int | None = None,
    search: str | None = None,
) -> tuple[list[Consultation], int]:
    filters = []

    if status:
        filters.append(Consultation.status == status)

    if assigned_to is not None:
        filters.append(Consultation.assigned_to == assigned_to)

    if search:
        term = f"%{search.strip()}%"
        filters.append(
            or_(
                Consultation.full_name.ilike(term),
                Consultation.email.ilike(term),
                Consultation.tracking_id.ilike(term),
            )
        )

    base_query = select(Consultation)
    count_query = select(func.count(Consultation.id))

    if filters:
        base_query = base_query.where(*filters)
        count_query = count_query.where(*filters)

    result = await db.execute(
        base_query.options(selectinload(Consultation.assigned_admin))
        .order_by(Consultation.created_at.desc(), Consultation.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    total = await db.scalar(count_query)
    return list(result.scalars().unique().all()), int(total or 0)


def build_consultation(
    payload: ConsultationPublicCreate,
    *,
    tracking_id: str,
    idempotency_key: str,
) -> Consultation:
    return Consultation(
        tracking_id=tracking_id,
        idempotency_key=idempotency_key,
        full_name=payload.full_name,
        email=str(payload.email).lower(),
        phone=payload.phone,
        company=payload.company,
        message=payload.message,
        status="pending",
    )


def apply_consultation_update(
    consultation: Consultation,
    payload: ConsultationUpdate,
) -> Consultation:
    for field, value in payload.model_dump(
        exclude_unset=True,
        exclude={"status_comment"},
    ).items():
        setattr(consultation, field, value)
    return consultation


def build_status_history(
    *,
    consultation_id: int,
    old_status: str | None,
    new_status: str,
    changed_by: int | None,
    comment: str | None,
) -> ConsultationStatusHistory:
    return ConsultationStatusHistory(
        consultation_id=consultation_id,
        old_status=old_status,
        new_status=new_status,
        changed_by=changed_by,
        comment=comment,
    )


def build_notification_log(
    *,
    consultation_id: int | None,
    notification_type: str,
    recipient: str,
    subject: str | None,
    body: str,
    status: str = "queued",
) -> NotificationLog:
    return NotificationLog(
        consultation_id=consultation_id,
        type=notification_type,
        recipient=recipient,
        subject=subject,
        body=body,
        status=status,
    )
