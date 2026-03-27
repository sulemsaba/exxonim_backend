from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import BlogAuthor, BlogCategory, BlogPost
from app.schemas.blog import (
    BlogAuthorCreate,
    BlogAuthorUpdate,
    BlogCategoryCreate,
    BlogCategoryUpdate,
    BlogPostCreate,
    BlogPostUpdate,
)


def _blog_post_select():
    return select(BlogPost).options(
        selectinload(BlogPost.category),
        selectinload(BlogPost.author),
    )


# Fetch posts that are published and featured on home
async def get_featured_posts(db: AsyncSession, limit: int = 5) -> list[BlogPost]:
    result = await db.execute(
        _blog_post_select()
        .where(BlogPost.is_published.is_(True), BlogPost.featured_on_home.is_(True))
        .order_by(BlogPost.featured_slot.asc(), BlogPost.published_at.desc(), BlogPost.id.desc())
        .limit(limit)
    )
    return list(result.scalars().unique().all())


async def get_published_posts(
    db: AsyncSession,
    *,
    skip: int = 0,
    limit: int = 10,
) -> list[BlogPost]:
    result = await db.execute(
        _blog_post_select()
        .where(BlogPost.is_published.is_(True))
        .order_by(BlogPost.published_at.desc(), BlogPost.id.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().unique().all())


async def get_post_by_slug(db: AsyncSession, slug: str) -> BlogPost | None:
    result = await db.execute(
        _blog_post_select()
        .where(BlogPost.slug == slug, BlogPost.is_published.is_(True))
    )
    return result.scalar_one_or_none()


async def get_all_posts(
    db: AsyncSession,
    *,
    skip: int = 0,
    limit: int = 100,
) -> list[BlogPost]:
    result = await db.execute(
        _blog_post_select()
        .order_by(BlogPost.published_at.desc(), BlogPost.id.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().unique().all())


async def get_post_by_id(db: AsyncSession, post_id: int) -> BlogPost | None:
    result = await db.execute(_blog_post_select().where(BlogPost.id == post_id))
    return result.scalar_one_or_none()


async def get_all_authors(db: AsyncSession) -> list[BlogAuthor]:
    result = await db.execute(select(BlogAuthor).order_by(BlogAuthor.name.asc()))
    return list(result.scalars().all())


async def get_author_by_slug(db: AsyncSession, slug: str) -> BlogAuthor | None:
    result = await db.execute(select(BlogAuthor).where(BlogAuthor.slug == slug))
    return result.scalar_one_or_none()


async def get_author_by_id(db: AsyncSession, author_id: int) -> BlogAuthor | None:
    result = await db.execute(select(BlogAuthor).where(BlogAuthor.id == author_id))
    return result.scalar_one_or_none()


def build_author(payload: BlogAuthorCreate) -> BlogAuthor:
    return BlogAuthor(**payload.model_dump())


def apply_author_update(author: BlogAuthor, payload: BlogAuthorUpdate) -> BlogAuthor:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(author, field, value)
    return author


async def get_all_categories(db: AsyncSession) -> list[BlogCategory]:
    result = await db.execute(select(BlogCategory).order_by(BlogCategory.name.asc()))
    return list(result.scalars().all())


async def get_category_by_id(
    db: AsyncSession,
    category_id: int,
) -> BlogCategory | None:
    result = await db.execute(
        select(BlogCategory).where(BlogCategory.id == category_id)
    )
    return result.scalar_one_or_none()


def build_category(payload: BlogCategoryCreate) -> BlogCategory:
    return BlogCategory(**payload.model_dump())


def apply_category_update(
    category: BlogCategory,
    payload: BlogCategoryUpdate,
) -> BlogCategory:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(category, field, value)
    return category


def build_post(payload: BlogPostCreate) -> BlogPost:
    return BlogPost(**payload.model_dump())


def apply_post_update(post: BlogPost, payload: BlogPostUpdate) -> BlogPost:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(post, field, value)
    return post
