from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.service_request import ServiceRequestSourceChannel, ServiceRequestStatus


ReportGrain = Literal["day", "week", "month"]


class ReportFiltersOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_date: date = Field(alias="from")
    to_date: date = Field(alias="to")
    grain: ReportGrain
    timezone: str = "Africa/Dar_es_Salaam"
    service_type_id: str | None = None
    assignee_id: int | None = None
    source_channel: ServiceRequestSourceChannel | None = None
    status: ServiceRequestStatus | None = None


class ReportSummaryCard(BaseModel):
    key: str
    label: str
    value: float | int
    helper: str | None = None
    href: str | None = None


class ReportSeriesPoint(BaseModel):
    key: str
    label: str
    bucket_start: date
    value: int


class ReportBreakdownRow(BaseModel):
    key: str
    label: str
    value: int
    helper: str | None = None
    href: str | None = None


class ReportOpenResolvedPoint(BaseModel):
    key: str
    label: str
    bucket_start: date
    open_value: int
    resolved_value: int


class ReportWorkloadRow(BaseModel):
    admin_id: int
    admin_label: str
    active_open_assignments: int
    unread_count: int
    overdue_count: int
    completions_in_range: int
    href: str | None = None


class ReportTransitionRow(BaseModel):
    key: str
    from_status: str | None = None
    to_status: str
    count: int


class ReportResponseTimeSummary(BaseModel):
    first_handled_average_hours: float | None = None
    first_handled_samples: int = 0
    first_customer_response_average_hours: float | None = None
    first_customer_response_samples: int = 0


class OperationsReportOut(BaseModel):
    filters: ReportFiltersOut
    summary_cards: list[ReportSummaryCard]
    enquiry_series: list[ReportSeriesPoint]
    source_channel_breakdown: list[ReportBreakdownRow]
    service_type_breakdown: list[ReportBreakdownRow]
    open_vs_resolved_trend: list[ReportOpenResolvedPoint]
    aging_buckets: list[ReportBreakdownRow]
    staff_workload: list[ReportWorkloadRow]
    funnel_current_status: list[ReportBreakdownRow]
    funnel_transition_counts: list[ReportTransitionRow]
    repeat_customer_breakdown: list[ReportBreakdownRow]
    response_times: ReportResponseTimeSummary


class AdminActivityRow(BaseModel):
    key: str
    actor_label: str
    action: str
    count: int
    href: str | None = None


class AdminActivityReportOut(BaseModel):
    filters: ReportFiltersOut
    summary_cards: list[ReportSummaryCard]
    activity_series: list[ReportSeriesPoint]
    actor_breakdown: list[ReportBreakdownRow]
    action_breakdown: list[ReportBreakdownRow]
    rows: list[AdminActivityRow]


class ContentActivityRow(BaseModel):
    key: str
    content_type: Literal["page", "blog_post", "testimonial"]
    action: Literal["create", "submit", "approve", "reject", "publish", "archive"]
    count: int
    href: str | None = None


class ContentActivityReportOut(BaseModel):
    filters: ReportFiltersOut
    summary_cards: list[ReportSummaryCard]
    activity_series: list[ReportSeriesPoint]
    content_type_breakdown: list[ReportBreakdownRow]
    action_breakdown: list[ReportBreakdownRow]
    rows: list[ContentActivityRow]
