from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Media


async def get_media_items(db: AsyncSession) -> list[Media]:
    result = await db.execute(select(Media).order_by(Media.uploaded_at.desc(), Media.id.desc()))
    return list(result.scalars().all())
