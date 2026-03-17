from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Testimonial
from app.schemas.testimonial import TestimonialCreate, TestimonialUpdate


async def get_active_testimonials(db: AsyncSession) -> list[Testimonial]:
    result = await db.execute(
        select(Testimonial)
        .where(Testimonial.is_active.is_(True))
        .order_by(Testimonial.sort_order.asc(), Testimonial.id.asc())
    )
    return list(result.scalars().all())


async def get_all_testimonials(db: AsyncSession) -> list[Testimonial]:
    result = await db.execute(
        select(Testimonial).order_by(Testimonial.sort_order.asc(), Testimonial.id.asc())
    )
    return list(result.scalars().all())


async def get_testimonial_by_id(
    db: AsyncSession,
    testimonial_id: int,
) -> Testimonial | None:
    result = await db.execute(
        select(Testimonial).where(Testimonial.id == testimonial_id)
    )
    return result.scalar_one_or_none()


def build_testimonial(payload: TestimonialCreate) -> Testimonial:
    return Testimonial(**payload.model_dump())


def apply_testimonial_update(
    testimonial: Testimonial,
    payload: TestimonialUpdate,
) -> Testimonial:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(testimonial, field, value)
    return testimonial
