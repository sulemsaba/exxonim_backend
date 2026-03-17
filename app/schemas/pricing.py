from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PricingPlanBase(BaseModel):
    name: str
    badge: str | None = None
    description: str | None = None
    notes: str | None = None
    price: Decimal | None = None
    features: list[dict[str, Any]] = Field(default_factory=list)
    recommended: bool = False
    sort_order: int = 0
    is_active: bool = True


class PricingPlanCreate(PricingPlanBase):
    pass


class PricingPlanUpdate(BaseModel):
    name: str | None = None
    badge: str | None = None
    description: str | None = None
    notes: str | None = None
    price: Decimal | None = None
    features: list[dict[str, Any]] | None = None
    recommended: bool | None = None
    sort_order: int | None = None
    is_active: bool | None = None


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
