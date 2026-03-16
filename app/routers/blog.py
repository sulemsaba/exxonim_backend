from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import blog as blog_crud
from app.core.database import get_db
from app.schemas import BlogCategoryOut, BlogPostOut

router = APIRouter(prefix="/blog", tags=["blog"])


@router.get("/posts", response_model=list[BlogPostOut])
async def list_posts(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> list[BlogPostOut]:
    return await blog_crud.get_published_posts(db, skip=skip, limit=limit)


@router.get("/posts/{slug}", response_model=BlogPostOut)
async def get_post(slug: str, db: AsyncSession = Depends(get_db)) -> BlogPostOut:
    post = await blog_crud.get_post_by_slug(db, slug)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


@router.get("/categories", response_model=list[BlogCategoryOut])
async def list_categories(db: AsyncSession = Depends(get_db)) -> list[BlogCategoryOut]:
    return await blog_crud.get_all_categories(db)
