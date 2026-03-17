from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SiteSetting
from app.schemas.site_settings import SiteSettingCreate, SiteSettingUpdate


async def get_site_settings(db: AsyncSession) -> list[SiteSetting]:
    result = await db.execute(select(SiteSetting).order_by(SiteSetting.key.asc()))
    return list(result.scalars().all())


async def get_site_setting_by_key(db: AsyncSession, key: str) -> SiteSetting | None:
    result = await db.execute(select(SiteSetting).where(SiteSetting.key == key))
    return result.scalar_one_or_none()


async def get_site_setting_by_id(
    db: AsyncSession,
    setting_id: int,
) -> SiteSetting | None:
    result = await db.execute(select(SiteSetting).where(SiteSetting.id == setting_id))
    return result.scalar_one_or_none()


def build_site_setting(payload: SiteSettingCreate) -> SiteSetting:
    return SiteSetting(**payload.model_dump())


def apply_site_setting_update(
    setting: SiteSetting,
    payload: SiteSettingUpdate,
) -> SiteSetting:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(setting, field, value)
    return setting
