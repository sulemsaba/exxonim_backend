from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MediaBase(BaseModel):
    url: str
    alt_text: str | None = None
    file_size: int | None = None
    mime_type: str | None = None


class MediaCreate(MediaBase):
    pass


class MediaUpdate(BaseModel):
    url: str | None = None
    alt_text: str | None = None
    file_size: int | None = None
    mime_type: str | None = None


class MediaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    alt_text: str | None = None
    file_size: int | None = None
    mime_type: str | None = None
    uploaded_at: datetime
