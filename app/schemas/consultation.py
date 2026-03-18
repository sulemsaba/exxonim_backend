from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, EmailStr, Field


class ConsultationStatus(StrEnum):
    PENDING = "pending"
    CONTACTED = "contacted"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class NotificationType(StrEnum):
    EMAIL = "email"
    SMS = "sms"


class ConsultationPublicCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=50)
    company: str | None = Field(default=None, max_length=255)
    message: str = Field(min_length=5)


class ConsultationMagicLinkRequest(BaseModel):
    email: EmailStr
    tracking_id: str = Field(min_length=4, max_length=50)


class ConsultationAssignedStaffOut(BaseModel):
    id: int
    full_name: str
    email: EmailStr


class ConsultationStatusHistoryPublicOut(BaseModel):
    new_status: ConsultationStatus
    changed_at: datetime
    comment: str | None = None


class ConsultationStatusHistoryAdminOut(BaseModel):
    id: int
    old_status: ConsultationStatus | None = None
    new_status: ConsultationStatus
    changed_at: datetime
    comment: str | None = None
    changed_by: ConsultationAssignedStaffOut | None = None


class NotificationLogOut(BaseModel):
    id: int
    type: NotificationType
    recipient: str
    subject: str | None = None
    body: str
    status: str
    error_message: str | None = None
    created_at: datetime


class ConsultationPublicOut(BaseModel):
    id: int
    tracking_id: str
    full_name: str
    email: EmailStr
    phone: str | None = None
    company: str | None = None
    message: str
    status: ConsultationStatus
    assigned_to: ConsultationAssignedStaffOut | None = None
    public_notes: str | None = None
    status_history: list[ConsultationStatusHistoryPublicOut]
    created_at: datetime
    updated_at: datetime


class ConsultationCreateResponse(BaseModel):
    id: int
    tracking_id: str
    full_name: str
    email: EmailStr
    phone: str | None = None
    company: str | None = None
    message: str
    status: ConsultationStatus
    created_at: datetime
    magic_link: str | None = None


class ConsultationMagicLinkResponse(BaseModel):
    ok: bool = True
    magic_link: str | None = None


class ConsultationAdminListItemOut(BaseModel):
    id: int
    tracking_id: str
    full_name: str
    email: EmailStr
    status: ConsultationStatus
    assigned_to: ConsultationAssignedStaffOut | None = None
    created_at: datetime


class ConsultationAdminListResponse(BaseModel):
    items: list[ConsultationAdminListItemOut]
    total: int
    page: int
    limit: int


class ConsultationAdminDetailOut(BaseModel):
    id: int
    tracking_id: str
    full_name: str
    email: EmailStr
    phone: str | None = None
    company: str | None = None
    message: str
    status: ConsultationStatus
    assigned_to: ConsultationAssignedStaffOut | None = None
    notes: str | None = None
    public_notes: str | None = None
    status_history: list[ConsultationStatusHistoryAdminOut]
    notification_logs: list[NotificationLogOut]
    created_at: datetime
    updated_at: datetime


class ConsultationUpdate(BaseModel):
    status: ConsultationStatus | None = None
    assigned_to: int | None = None
    notes: str | None = None
    public_notes: str | None = None
    status_comment: str | None = None


class ConsultationManualNotifyRequest(BaseModel):
    type: NotificationType
    subject: str | None = None
    message: str = Field(min_length=1)


class ConsultationManualNotifyResponse(BaseModel):
    id: int
    status: str


class AdminStaffOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    is_active: bool
