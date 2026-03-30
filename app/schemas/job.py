from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class JobBase(BaseModel):
    title: str
    slug: str
    department: str
    employment_type: str
    location_mode: str
    city: str = ""
    country: str = ""
    compensation_label: str | None = None
    experience_label: str | None = None
    summary: str
    description: str
    requirements: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    published_at: datetime | None = None
    is_published: bool = False


class JobCreate(JobBase):
    pass


class JobUpdate(BaseModel):
    title: str | None = None
    slug: str | None = None
    department: str | None = None
    employment_type: str | None = None
    location_mode: str | None = None
    city: str | None = None
    country: str | None = None
    compensation_label: str | None = None
    experience_label: str | None = None
    summary: str | None = None
    description: str | None = None
    requirements: list[str] | None = None
    responsibilities: list[str] | None = None
    published_at: datetime | None = None
    is_published: bool | None = None


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    slug: str
    department: str
    employment_type: str
    location_mode: str
    city: str
    country: str
    compensation_label: str | None = None
    experience_label: str | None = None
    summary: str
    description: str
    requirements: list[str]
    responsibilities: list[str]
    published_at: datetime | None = None
    is_published: bool
    created_at: datetime
    updated_at: datetime
