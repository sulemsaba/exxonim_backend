from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import BlogCategory, BlogPost


async def get_published_posts(
    db: AsyncSession,
    *,
    skip: int = 0,
    limit: int = 10,
) -> list[BlogPost]:
    result = await db.execute(
        select(BlogPost)
        .options(
            selectinload(BlogPost.category),
            selectinload(BlogPost.author),
        )
        .where(BlogPost.is_published.is_(True))
        .order_by(BlogPost.published_at.desc(), BlogPost.id.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().unique().all())


async def get_post_by_slug(db: AsyncSession, slug: str) -> BlogPost | None:
    result = await db.execute(
        select(BlogPost)
        .options(
            selectinload(BlogPost.category),
            selectinload(BlogPost.author),
        )
        .where(BlogPost.slug == slug, BlogPost.is_published.is_(True))
    )
    return result.scalar_one_or_none()


async def get_all_categories(db: AsyncSession) -> list[BlogCategory]:
    result = await db.execute(select(BlogCategory).order_by(BlogCategory.name.asc()))
    return list(result.scalars().all())
