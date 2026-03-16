from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SiteSetting


async def get_site_settings(db: AsyncSession) -> list[SiteSetting]:
    result = await db.execute(select(SiteSetting).order_by(SiteSetting.key.asc()))
    return list(result.scalars().all())


async def get_site_setting_by_key(db: AsyncSession, key: str) -> SiteSetting | None:
    result = await db.execute(select(SiteSetting).where(SiteSetting.key == key))
    return result.scalar_one_or_none()
