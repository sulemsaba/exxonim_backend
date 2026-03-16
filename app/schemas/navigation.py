from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
