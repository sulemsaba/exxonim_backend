from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BlogAuthorBase(BaseModel):
    slug: str
    name: str
    role: str | None = None
    avatar_src: str | None = None


class BlogAuthorCreate(BlogAuthorBase):
    pass


class BlogAuthorUpdate(BaseModel):
    slug: str | None = None
    name: str | None = None
    role: str | None = None
    avatar_src: str | None = None


class BlogAuthorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    role: str | None = None
    avatar_src: str | None = None


class BlogCategoryBase(BaseModel):
    name: str
    slug: str
    description: str | None = None


class BlogCategoryCreate(BlogCategoryBase):
    pass


class BlogCategoryUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    description: str | None = None


class BlogCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    description: str | None = None
    created_at: datetime


class BlogPostBase(BaseModel):
    title: str
    slug: str
    excerpt: str | None = None
    content: dict[str, Any]
    category_id: int | None = None
    author_id: int | None = None
    featured_image: str | None = None
    cover_alt: str | None = None
    media_label: str | None = None
    featured_slot: str | None = None
    featured_on_home: bool = False
    read_time_minutes: int | None = None
    related_slugs: list[str] = Field(default_factory=list)
    meta_title: str | None = None
    meta_description: str | None = None
    published_at: datetime | None = None
    is_published: bool = False


class BlogPostCreate(BlogPostBase):
    pass


class BlogPostUpdate(BaseModel):
    title: str | None = None
    slug: str | None = None
    excerpt: str | None = None
    content: dict[str, Any] | None = None
    category_id: int | None = None
    author_id: int | None = None
    featured_image: str | None = None
    cover_alt: str | None = None
    media_label: str | None = None
    featured_slot: str | None = None
    featured_on_home: bool | None = None
    read_time_minutes: int | None = None
    related_slugs: list[str] | None = None
    meta_title: str | None = None
    meta_description: str | None = None
    published_at: datetime | None = None
    is_published: bool | None = None


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
