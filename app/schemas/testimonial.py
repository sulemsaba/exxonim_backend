from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TestimonialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    eyebrow: str | None = None
    headline: str | None = None
    support: str | None = None
    author: str
    author_role: str | None = None
    initials: str | None = None
    content: str
    rating: int | None = None
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
