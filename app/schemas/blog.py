from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class BlogAuthorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    role: str | None = None
    avatar_src: str | None = None


class BlogCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    description: str | None = None
    created_at: datetime


class BlogPostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    slug: str
    excerpt: str | None = None
    content: dict[str, Any]
    featured_image: str | None = None
    cover_alt: str | None = None
    media_label: str | None = None
    featured_slot: str | None = None
    featured_on_home: bool
    read_time_minutes: int | None = None
    related_slugs: list[str]
    meta_title: str | None = None
    meta_description: str | None = None
    published_at: datetime | None = None
    is_published: bool
    created_at: datetime
    updated_at: datetime
    category: BlogCategoryOut | None = None
    author: BlogAuthorOut | None = None
