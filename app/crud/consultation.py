from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Consultation, ConsultationStatusHistory
from app.schemas.consultation import ConsultationUpdate


def _consultation_select(*, include_history: bool = False):
    query = select(Consultation).options(selectinload(Consultation.assigned_admin))

    if include_history:
        query = query.options(
            selectinload(Consultation.status_history).selectinload(
                ConsultationStatusHistory.changed_by_admin
            )
        )

    return query


def _apply_filters(query, *, status: str | None = None, search: str | None = None):
    if status:
        query = query.where(Consultation.status == status)

    if search:
        normalized = f"%{search.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(Consultation.tracking_id).like(normalized),
                func.lower(Consultation.full_name).like(normalized),
                func.lower(Consultation.email).like(normalized),
                func.lower(func.coalesce(Consultation.company, "")).like(normalized),
            )
        )

    return query


async def get_consultations(
    db: AsyncSession,
    *,
    page: int = 1,
    limit: int = 20,
    status: str | None = None,
    search: str | None = None,
    include_history: bool = False,
) -> tuple[list[Consultation], int]:
    safe_page = max(page, 1)
    safe_limit = max(min(limit, 100), 1)
    base_query = _apply_filters(select(Consultation.id), status=status, search=search)
    total = int(await db.scalar(select(func.count()).select_from(base_query.subquery())) or 0)
    result = await db.execute(
        _apply_filters(
            _consultation_select(include_history=include_history),
            status=status,
            search=search,
        )
        .order_by(Consultation.updated_at.desc(), Consultation.id.desc())
        .offset((safe_page - 1) * safe_limit)
        .limit(safe_limit)
    )
    return list(result.scalars().unique().all()), total


async def get_consultation_by_id(
    db: AsyncSession,
    consultation_id: int,
    *,
    include_history: bool = False,
) -> Consultation | None:
    result = await db.execute(
        _consultation_select(include_history=include_history).where(Consultation.id == consultation_id)
    )
    return result.scalar_one_or_none()


async def get_recent_consultations(db: AsyncSession, *, limit: int = 4) -> list[Consultation]:
    result = await db.execute(
        _consultation_select()
        .order_by(Consultation.updated_at.desc(), Consultation.id.desc())
        .limit(limit)
    )
    return list(result.scalars().unique().all())


async def get_consultation_status_counts(db: AsyncSession) -> dict[str, int]:
    result = await db.execute(
        select(Consultation.status, func.count(Consultation.id))
        .group_by(Consultation.status)
    )
    return {status: count for status, count in result.all()}


async def get_recent_consultation_history(
    db: AsyncSession,
    *,
    limit: int = 8,
) -> list[ConsultationStatusHistory]:
    result = await db.execute(
        select(ConsultationStatusHistory)
        .options(
            selectinload(ConsultationStatusHistory.consultation),
            selectinload(ConsultationStatusHistory.changed_by_admin),
        )
        .order_by(ConsultationStatusHistory.created_at.desc(), ConsultationStatusHistory.id.desc())
        .limit(limit)
    )
    return list(result.scalars().unique().all())


def apply_consultation_update(
    consultation: Consultation,
    payload: ConsultationUpdate,
) -> Consultation:
    for field, value in payload.model_dump(exclude_unset=True, exclude={"comment"}).items():
        setattr(consultation, field, value)
    return consultation


def build_status_history(
    *,
    consultation_id: int,
    old_status: str | None,
    new_status: str,
    changed_by: int | None,
    comment: str | None = None,
) -> ConsultationStatusHistory:
    return ConsultationStatusHistory(
        consultation_id=consultation_id,
        old_status=old_status,
        new_status=new_status,
        changed_by=changed_by,
        comment=comment,
    )
