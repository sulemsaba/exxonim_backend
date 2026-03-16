from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


class PricingPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    badge: str | None = None
    description: str | None = None
    notes: str | None = None
    price: Decimal | None = None
    features: list[dict[str, Any]]
    recommended: bool
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
