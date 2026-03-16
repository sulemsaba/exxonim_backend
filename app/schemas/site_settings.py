from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class SiteSettingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    value: dict[str, Any] | list[Any] | str | int | float | bool | None
    created_at: datetime
    updated_at: datetime
