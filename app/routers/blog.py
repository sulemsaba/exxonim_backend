from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import blog as blog_crud
from app.services.blog_service import list_home_posts
from app.core.database import get_db
from app.schemas import BlogCategoryOut, BlogPostOut

router = APIRouter(prefix="/blog", tags=["blog"])


@router.get("/posts", response_model=list[BlogPostOut])
async def list_posts(
    response: Response,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=50),
    featured_on_home: bool = Query(False),
    db: AsyncSession = Depends(get_db),
) -> list[BlogPostOut]:
    try:
        result = await list_home_posts(db, skip=skip, limit=limit, featured_on_home=featured_on_home)
        if result.get("used_fallback"):
            response.headers["X-Used-Fallback"] = "1"
        return result["posts"]
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in list_posts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/posts/{slug}", response_model=BlogPostOut)
async def get_post(slug: str, db: AsyncSession = Depends(get_db)) -> BlogPostOut:
    post = await blog_crud.get_post_by_slug(db, slug)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


@router.get("/categories", response_model=list[BlogCategoryOut])
async def list_categories(db: AsyncSession = Depends(get_db)) -> list[BlogCategoryOut]:
    return await blog_crud.get_all_categories(db)
