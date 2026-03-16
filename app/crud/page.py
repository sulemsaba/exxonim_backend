from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Page


async def get_published_pages(db: AsyncSession) -> list[Page]:
    result = await db.execute(
        select(Page)
        .where(Page.is_published.is_(True))
        .order_by(Page.title.asc())
    )
    return list(result.scalars().all())


async def get_page_by_slug(db: AsyncSession, slug: str) -> Page | None:
    result = await db.execute(
        select(Page).where(Page.slug == slug, Page.is_published.is_(True))
    )
    return result.scalar_one_or_none()
