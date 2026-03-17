from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Page
from app.schemas.page import PageCreate, PageUpdate


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


async def get_all_pages(db: AsyncSession) -> list[Page]:
    result = await db.execute(select(Page).order_by(Page.title.asc(), Page.id.asc()))
    return list(result.scalars().all())


async def get_page_by_id(db: AsyncSession, page_id: int) -> Page | None:
    result = await db.execute(select(Page).where(Page.id == page_id))
    return result.scalar_one_or_none()


def build_page(payload: PageCreate) -> Page:
    return Page(**payload.model_dump())


def apply_page_update(page: Page, payload: PageUpdate) -> Page:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(page, field, value)
    return page
