from __future__ import annotations

from datetime import datetime
from math import ceil
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.admin import AdminUserOut


AdminNotificationCategory = Literal[
    "request_ops",
    "content_review",
    "security",
    "reporting",
    "system",
]
AdminNotificationEventType = Literal[
    "request.submitted",
    "request.inbound_message",
    "request.assigned",
    "request.overdue",
    "content.pending_review",
    "security.suspicious_login",
    "security.admin_role_changed",
    "security.admin_status_changed",
    "report.generated",
]
AdminNotificationSeverity = Literal["info", "success", "warning", "error"]
AdminNotificationStatus = Literal["all", "unread"]


class AdminNotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category: AdminNotificationCategory
    event_type: AdminNotificationEventType
    severity: AdminNotificationSeverity
    title: str
    body: str | None = None
    href: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    actor_admin: AdminUserOut | None = None
    occurrence_count: int
    is_read: bool
    read_at: datetime | None = None
    last_occurred_at: datetime
    created_at: datetime
    updated_at: datetime


class AdminNotificationPreferenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category: AdminNotificationCategory
    in_app_enabled: bool = True


class AdminNotificationPreferenceUpdate(BaseModel):
    category: AdminNotificationCategory
    in_app_enabled: bool


class AdminNotificationPreferenceListResponse(BaseModel):
    items: list[AdminNotificationPreferenceOut] = Field(default_factory=list)


class AdminNotificationListResponse(BaseModel):
    items: list[AdminNotificationOut] = Field(default_factory=list)
    page: int = 1
    limit: int = 20
    total: int = 0
    pages: int = 0
    unread_total: int = 0

    @classmethod
    def build(
        cls,
        *,
        items: list[AdminNotificationOut],
        page: int,
        limit: int,
        total: int,
        unread_total: int,
    ) -> "AdminNotificationListResponse":
        safe_limit = max(limit, 1)
        pages = ceil(total / safe_limit) if total else 0
        return cls(
            items=items,
            page=page,
            limit=safe_limit,
            total=total,
            pages=pages,
            unread_total=unread_total,
        )


class AdminNotificationReadResponse(BaseModel):
    id: UUID
    is_read: bool = True
    read_at: datetime


class AdminNotificationMarkAllReadPayload(BaseModel):
    category: AdminNotificationCategory | None = None


class AdminNotificationMarkAllReadResponse(BaseModel):
    updated: int
    unread_total: int = 0
