from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MediaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    alt_text: str | None = None
    file_size: int | None = None
    mime_type: str | None = None
    uploaded_at: datetime
