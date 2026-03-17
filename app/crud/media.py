from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Media
from app.schemas.media import MediaCreate, MediaUpdate


async def get_media_items(db: AsyncSession) -> list[Media]:
    result = await db.execute(select(Media).order_by(Media.uploaded_at.desc(), Media.id.desc()))
    return list(result.scalars().all())


async def get_media_item_by_id(db: AsyncSession, media_id: int) -> Media | None:
    result = await db.execute(select(Media).where(Media.id == media_id))
    return result.scalar_one_or_none()


def build_media_item(payload: MediaCreate) -> Media:
    return Media(**payload.model_dump())


def apply_media_item_update(media: Media, payload: MediaUpdate) -> Media:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(media, field, value)
    return media
