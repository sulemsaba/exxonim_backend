from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CareerJob
from app.schemas.job import JobCreate, JobUpdate


def _job_order_clause():
    return (
        CareerJob.is_published.desc(),
        CareerJob.published_at.desc().nullslast(),
        CareerJob.updated_at.desc(),
        CareerJob.id.desc(),
    )


async def get_published_jobs(db: AsyncSession) -> list[CareerJob]:
    result = await db.execute(
        select(CareerJob)
        .where(CareerJob.is_published.is_(True))
        .order_by(*_job_order_clause())
    )
    return list(result.scalars().all())


async def get_all_jobs(db: AsyncSession) -> list[CareerJob]:
    result = await db.execute(select(CareerJob).order_by(*_job_order_clause()))
    return list(result.scalars().all())


async def get_job_by_id(db: AsyncSession, job_id: int) -> CareerJob | None:
    result = await db.execute(select(CareerJob).where(CareerJob.id == job_id))
    return result.scalar_one_or_none()


async def get_job_by_slug(
    db: AsyncSession,
    slug: str,
    *,
    published_only: bool = False,
) -> CareerJob | None:
    query = select(CareerJob).where(CareerJob.slug == slug)

    if published_only:
        query = query.where(CareerJob.is_published.is_(True))

    result = await db.execute(query)
    return result.scalar_one_or_none()


def build_job(payload: JobCreate) -> CareerJob:
    return CareerJob(**payload.model_dump())


def apply_job_update(job: CareerJob, payload: JobUpdate) -> CareerJob:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(job, field, value)
    return job
