from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class PageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    slug: str
    content: dict[str, Any]
    meta_title: str | None = None
    meta_description: str | None = None
    is_published: bool
    created_at: datetime
    updated_at: datetime
