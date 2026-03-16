from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import navigation as navigation_crud
from app.core.database import get_db
from app.schemas import NavigationItemOut

router = APIRouter(prefix="/navigation", tags=["navigation"])


@router.get("/", response_model=list[NavigationItemOut])
async def get_navigation(db: AsyncSession = Depends(get_db)) -> list[NavigationItemOut]:
    return await navigation_crud.get_active_navigation(db)
