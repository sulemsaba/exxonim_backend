from __future__ import annotations

from datetime import datetime
from math import ceil
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.admin import AdminUserOut
from app.schemas.service_request import CustomerOut


PrivacyRequestType = Literal["access", "correction", "deletion"]
PrivacyRequestStatus = Literal["received", "verifying", "in_progress", "completed", "rejected"]


class PrivacyPolicyVersions(BaseModel):
    privacy_policy: str
    cookie_notice: str
    data_rights_notice: str


class PrivacyConsentCategories(BaseModel):
    necessary: bool = True
    preferences: bool = False


class PrivacyConsentOut(BaseModel):
    policy_versions: PrivacyPolicyVersions
    categories: PrivacyConsentCategories
    consent_recorded: bool
    recorded_at: datetime | None = None


class PrivacyConsentUpdate(BaseModel):
    preferences: bool = False
    source_path: str | None = None


class PrivacyRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID | None = None
    request_type: PrivacyRequestType
    status: PrivacyRequestStatus
    requester_name: str
    requester_email: EmailStr
    summary: str
    internal_notes: str | None = None
    resolution_notes: str | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    customer: CustomerOut | None = None
    created_by_admin: AdminUserOut
    completed_by_admin: AdminUserOut | None = None


class PrivacyRequestCreate(BaseModel):
    customer_id: UUID | None = None
    request_type: PrivacyRequestType
    requester_name: str
    requester_email: EmailStr
    summary: str
    internal_notes: str | None = None


class PrivacyRequestUpdate(BaseModel):
    status: PrivacyRequestStatus | None = None
    internal_notes: str | None = None
    resolution_notes: str | None = None


class PrivacyRequestListResponse(BaseModel):
    items: list[PrivacyRequestOut]
    page: int
    limit: int
    total: int
    total_pages: int
