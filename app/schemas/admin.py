from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class AdminRefreshRequest(BaseModel):
    refresh_token: str


class AdminTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    admin: AdminUserOut


class AdminAccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AdminDashboardActivityEvent(BaseModel):
    id: str
    actor_name: str
    actor_role: str | None = None
    actor_type: Literal["admin", "editor", "system"]
    action_type: Literal[
        "published",
        "draft_created",
        "updated",
        "consultation_received",
        "settings_updated",
        "job_posted",
        "seo_warning",
    ]
    resource_type: Literal[
        "blog_post",
        "consultation",
        "page",
        "setting",
        "job",
        "navigation",
        "pricing",
        "testimonial",
        "seo",
    ]
    target_label: str
    target_url: str | None = None
    detail: str | None = None
    created_at: datetime


class AdminDashboardMetric(BaseModel):
    key: str
    label: str
    value: int
    helper: str | None = None
    href: str | None = None


class AdminDashboardAlert(BaseModel):
    id: str
    severity: Literal["info", "warning", "error"]
    title: str
    message: str
    href: str | None = None


class AdminDashboardPipelineItem(BaseModel):
    id: str
    title: str
    slug: str
    kind: Literal["blog_post", "page"]
    status: str
    seo_health: Literal["clean", "warning", "error"]
    completion_percent: int
    href: str | None = None


class AdminDashboardJobItem(BaseModel):
    id: int
    title: str
    slug: str
    department: str
    employment_type: str
    location: str
    status: str
    posted_at: datetime | None = None
    href: str | None = None


class AdminDashboardConsultationItem(BaseModel):
    id: int
    tracking_id: str
    full_name: str
    company: str | None = None
    status: str
    assigned_admin_label: str | None = None
    created_at: datetime
    updated_at: datetime
    href: str | None = None


class AdminDashboardSummary(BaseModel):
    metrics: list[AdminDashboardMetric]
    alerts: list[AdminDashboardAlert]
    recent_activity: list[AdminDashboardActivityEvent]
    content_pipeline: list[AdminDashboardPipelineItem]
    consultations: list[AdminDashboardConsultationItem]
    open_jobs: list[AdminDashboardJobItem]
