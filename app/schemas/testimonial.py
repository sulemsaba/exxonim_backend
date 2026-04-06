from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict
from app.workflow import ContentWorkflowStatus


class TestimonialBase(BaseModel):
    eyebrow: str | None = None
    headline: str | None = None
    support: str | None = None
    author: str
    author_role: str | None = None
    initials: str | None = None
    content: str
    rating: int | None = None
    sort_order: int = 0
    status: ContentWorkflowStatus | None = None
    is_active: bool = True


class TestimonialCreate(TestimonialBase):
    pass


class TestimonialUpdate(BaseModel):
    eyebrow: str | None = None
    headline: str | None = None
    support: str | None = None
    author: str | None = None
    author_role: str | None = None
    initials: str | None = None
    content: str | None = None
    rating: int | None = None
    sort_order: int | None = None
    status: ContentWorkflowStatus | None = None
    is_active: bool | None = None


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
    status: ContentWorkflowStatus
    is_active: bool
    created_by_id: int | None = None
    updated_by_id: int | None = None
    submitted_at: datetime | None = None
    submitted_by_id: int | None = None
    reviewed_at: datetime | None = None
    reviewed_by_id: int | None = None
    published_at: datetime | None = None
    published_by_id: int | None = None
    created_at: datetime
    updated_at: datetime
