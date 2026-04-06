from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict
from app.workflow import ContentWorkflowStatus


class PageBase(BaseModel):
    title: str
    slug: str
    content: dict[str, Any]
    meta_title: str | None = None
    meta_description: str | None = None
    status: ContentWorkflowStatus | None = None
    is_published: bool = True


class PageCreate(PageBase):
    pass


class PageUpdate(BaseModel):
    title: str | None = None
    slug: str | None = None
    content: dict[str, Any] | None = None
    meta_title: str | None = None
    meta_description: str | None = None
    status: ContentWorkflowStatus | None = None
    is_published: bool | None = None


class PageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    slug: str
    content: dict[str, Any]
    meta_title: str | None = None
    meta_description: str | None = None
    status: ContentWorkflowStatus
    is_published: bool
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
