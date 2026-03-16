from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import site_settings as settings_crud
from app.core.database import get_db
from app.schemas import SiteSettingOut

router = APIRouter(prefix="/site-settings", tags=["site-settings"])


@router.get("/", response_model=list[SiteSettingOut])
async def list_site_settings(db: AsyncSession = Depends(get_db)) -> list[SiteSettingOut]:
    return await settings_crud.get_site_settings(db)


@router.get("/{key}", response_model=SiteSettingOut)
async def get_site_setting(key: str, db: AsyncSession = Depends(get_db)) -> SiteSettingOut:
    setting = await settings_crud.get_site_setting_by_key(db, key)
    if setting is None:
        raise HTTPException(status_code=404, detail="Site setting not found")
    return setting
