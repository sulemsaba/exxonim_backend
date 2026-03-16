from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import media as media_crud
from app.core.database import get_db
from app.schemas import MediaOut

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/", response_model=list[MediaOut])
async def list_media(db: AsyncSession = Depends(get_db)) -> list[MediaOut]:
    return await media_crud.get_media_items(db)
