from __future__ import annotations

from datetime import datetime
from math import ceil
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.admin import AdminUserOut


ConsultationStatus = Literal["pending", "contacted", "completed", "cancelled"]


class ConsultationStatusHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    old_status: ConsultationStatus | None = None
    new_status: ConsultationStatus
    comment: str | None = None
    created_at: datetime
    changed_by_admin: AdminUserOut | None = None


class ConsultationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tracking_id: str
    idempotency_key: str
    full_name: str
    email: str
    phone: str | None = None
    company: str | None = None
    message: str
    status: ConsultationStatus
    assigned_to: int | None = None
    notes: str | None = None
    public_notes: str | None = None
    created_at: datetime
    updated_at: datetime
    assigned_admin: AdminUserOut | None = None
    status_history: list[ConsultationStatusHistoryOut] = []


class ConsultationUpdate(BaseModel):
    status: ConsultationStatus | None = None
    assigned_to: int | None = None
    notes: str | None = None
    public_notes: str | None = None
    comment: str | None = None


class ConsultationListResponse(BaseModel):
    items: list[ConsultationOut]
    page: int
    limit: int
    total: int
    total_pages: int

    @classmethod
    def build(
        cls,
        *,
        items: list[ConsultationOut],
        page: int,
        limit: int,
        total: int,
    ) -> "ConsultationListResponse":
        return cls(
            items=items,
            page=page,
            limit=limit,
            total=total,
            total_pages=0 if total == 0 else ceil(total / max(limit, 1)),
        )
