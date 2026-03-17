from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NavigationItemBase(BaseModel):
    title: str
    url: str
    description: str | None = None
    kind: str = "link"
    parent_id: int | None = None
    order: int = 0
    is_active: bool = True


class NavigationItemCreate(NavigationItemBase):
    pass


class NavigationItemUpdate(BaseModel):
    title: str | None = None
    url: str | None = None
    description: str | None = None
    kind: str | None = None
    parent_id: int | None = None
    order: int | None = None
    is_active: bool | None = None


class NavigationItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    url: str
    description: str | None = None
    kind: str
    order: int
    is_active: bool
    parent_id: int | None = None
    created_at: datetime
    updated_at: datetime
    children: list["NavigationItemOut"] = Field(default_factory=list)


NavigationItemOut.model_rebuild()
