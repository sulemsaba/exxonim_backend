from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import page as page_crud
from app.core.database import get_db
from app.schemas import PageOut

router = APIRouter(prefix="/pages", tags=["pages"])


@router.get("/", response_model=list[PageOut])
async def list_pages(db: AsyncSession = Depends(get_db)) -> list[PageOut]:
    return await page_crud.get_published_pages(db)


@router.get("/{slug}", response_model=PageOut)
async def get_page(slug: str, db: AsyncSession = Depends(get_db)) -> PageOut:
    page = await page_crud.get_page_by_slug(db, slug)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")
    return page
