from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from statistics import mean
from typing import Iterable
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    AuditLog,
    InboxMessage,
    InboxThread,
    RecordNote,
    ServiceRequest,
    ServiceRequestAssignment,
    ServiceRequestInboxState,
    ServiceRequestStatusHistory,
)
from app.schemas.reporting import (
    AdminActivityReportOut,
    AdminActivityRow,
    ContentActivityReportOut,
    ContentActivityRow,
    OperationsReportOut,
    ReportBreakdownRow,
    ReportFiltersOut,
    ReportOpenResolvedPoint,
    ReportResponseTimeSummary,
    ReportSeriesPoint,
    ReportSummaryCard,
    ReportTransitionRow,
    ReportWorkloadRow,
)
from app.schemas.service_request import ServiceRequestSourceChannel, ServiceRequestStatus

BUSINESS_TIMEZONE = ZoneInfo("Africa/Dar_es_Salaam")
REPORTABLE_CONTENT_ACTIONS = {"create", "submit_review", "approve", "reject", "publish", "archive"}
RESOLVED_STATUSES = {"completed", "cancelled"}
AGING_BUCKETS = (
    ("0-2", 0, 2),
    ("3-7", 3, 7),
    ("8-14", 8, 14),
    ("15-30", 15, 30),
    ("31+", 31, None),
)
CONSULTATION_STATUS_BY_REQUEST_STATUS = {
    "new": "pending",
    "triaged": "contacted",
    "waiting_customer": "contacted",
    "in_progress": "contacted",
    "completed": "completed",
    "cancelled": "cancelled",
}


@dataclass(frozen=True)
class ReportWindow:
    start_business_date: date
    end_business_date: date
    start_utc: datetime
    end_utc: datetime


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _to_business_date(value: datetime) -> date:
    return _ensure_utc(value).astimezone(BUSINESS_TIMEZONE).date()


def build_report_window(filters: ReportFiltersOut) -> ReportWindow:
    start_utc = datetime.combine(
        filters.from_date,
        time.min,
        tzinfo=BUSINESS_TIMEZONE,
    ).astimezone(timezone.utc)
    end_utc = datetime.combine(
        filters.to_date,
        time.max,
        tzinfo=BUSINESS_TIMEZONE,
    ).astimezone(timezone.utc)
    return ReportWindow(
        start_business_date=filters.from_date,
        end_business_date=filters.to_date,
        start_utc=start_utc,
        end_utc=end_utc,
    )


def _bucket_start(value: date, grain: str) -> date:
    if grain == "week":
        return value - timedelta(days=value.weekday())
    if grain == "month":
        return value.replace(day=1)
    return value


def _next_bucket_start(value: date, grain: str) -> date:
    if grain == "day":
        return value + timedelta(days=1)
    if grain == "week":
        return value + timedelta(days=7)
    if value.month == 12:
        return value.replace(year=value.year + 1, month=1, day=1)
    return value.replace(month=value.month + 1, day=1)


def _bucket_label(value: date, grain: str) -> str:
    if grain == "week":
        year, week_number, _ = value.isocalendar()
        return f"{year}-W{week_number:02d}"
    if grain == "month":
        return value.strftime("%Y-%m")
    return value.isoformat()


def build_bucket_index(start: date, end: date, grain: str) -> list[date]:
    cursor = _bucket_start(start, grain)
    last = _bucket_start(end, grain)
    buckets: list[date] = []
    while cursor <= last:
        buckets.append(cursor)
        cursor = _next_bucket_start(cursor, grain)
    return buckets


def _request_opened_in_window(request: ServiceRequest, window: ReportWindow) -> bool:
    opened_at = _ensure_utc(request.opened_at)
    return window.start_utc <= opened_at <= window.end_utc


def _assignment_active_at(assignment: ServiceRequestAssignment, when: datetime) -> bool:
    assigned_at = _ensure_utc(assignment.assigned_at)
    if assigned_at > when:
        return False
    if assignment.unassigned_at is None:
        return True
    return _ensure_utc(assignment.unassigned_at) >= when


def _latest_customer_message_at(request: ServiceRequest) -> datetime | None:
    return _ensure_utc(request.last_customer_message_at) if request.last_customer_message_at else None


def _get_inbox_state_for_admin(
    request: ServiceRequest,
    admin_id: int,
) -> ServiceRequestInboxState | None:
    return next((state for state in request.inbox_states if state.admin_user_id == admin_id), None)


def get_unread_count_for_admin(request: ServiceRequest, admin_id: int) -> int:
    latest_customer_message = _latest_customer_message_at(request)
    if latest_customer_message is None:
        return 0

    inbound_messages = [
        message
        for thread in request.threads
        for message in thread.messages
        if message.direction == "inbound"
    ]
    inbox_state = _get_inbox_state_for_admin(request, admin_id)
    if inbox_state is None or inbox_state.last_read_at is None:
        return len(inbound_messages) if inbound_messages else 1

    last_read_at = _ensure_utc(inbox_state.last_read_at)
    return sum(1 for message in inbound_messages if _ensure_utc(message.created_at) > last_read_at)


def get_first_handled_at(request: ServiceRequest) -> datetime | None:
    candidates: list[datetime] = []
    candidates.extend(_ensure_utc(assignment.assigned_at) for assignment in request.assignments)
    candidates.extend(
        _ensure_utc(history.created_at)
        for history in request.status_history
        if history.changed_by_admin_id is not None
    )
    candidates.extend(_ensure_utc(note.created_at) for note in request.notes)
    candidates.extend(
        _ensure_utc(message.created_at)
        for thread in request.threads
        for message in thread.messages
        if message.direction == "outbound" and message.author_admin_id is not None
    )
    return min(candidates) if candidates else None


def get_first_outbound_response_at(request: ServiceRequest) -> datetime | None:
    candidates = [
        _ensure_utc(message.created_at)
        for thread in request.threads
        for message in thread.messages
        if message.direction == "outbound" and message.author_admin_id is not None
    ]
    return min(candidates) if candidates else None


def build_operations_report(
    service_requests: Iterable[ServiceRequest],
    *,
    filters: ReportFiltersOut,
) -> OperationsReportOut:
    requests = list(service_requests)
    window = build_report_window(filters)
    bucket_starts = build_bucket_index(window.start_business_date, window.end_business_date, filters.grain)
    enquiry_counter: Counter[date] = Counter()
    source_counter: Counter[str] = Counter()
    service_type_counter: Counter[tuple[str, str, str]] = Counter()
    open_resolved_counter: dict[date, dict[str, int]] = {
        bucket: {"open": 0, "resolved": 0} for bucket in bucket_starts
    }
    status_counter: Counter[str] = Counter()
    transition_counter: Counter[tuple[str | None, str]] = Counter()
    repeat_customers = 0
    repeat_customer_ids: set[UUID] = set()
    new_customer_ids: set[UUID] = set()
    response_hours: list[float] = []
    first_response_hours: list[float] = []

    requests_in_window = [request for request in requests if _request_opened_in_window(request, window)]
    prior_request_by_customer: dict[UUID, bool] = {}
    for request in requests:
        if request.customer_id is None:
            continue
        if _ensure_utc(request.opened_at) < window.start_utc:
            prior_request_by_customer[request.customer_id] = True

    for request in requests_in_window:
        business_open_date = _to_business_date(request.opened_at)
        bucket = _bucket_start(business_open_date, filters.grain)
        enquiry_counter[bucket] += 1
        source_counter[request.source_channel] += 1
        service_type_counter[
            (
                str(request.service_type_id),
                request.service_type.label,
                request.service_type.code,
            )
        ] += 1
        if request.status in RESOLVED_STATUSES:
            open_resolved_counter[bucket]["resolved"] += 1
        else:
            open_resolved_counter[bucket]["open"] += 1
        status_counter[request.status] += 1

        if request.customer_id in prior_request_by_customer:
            repeat_customer_ids.add(request.customer_id)
        else:
            new_customer_ids.add(request.customer_id)

        first_handled_at = get_first_handled_at(request)
        if first_handled_at is not None:
            response_hours.append((_ensure_utc(first_handled_at) - _ensure_utc(request.opened_at)).total_seconds() / 3600)
        first_outbound_response_at = get_first_outbound_response_at(request)
        if first_outbound_response_at is not None:
            first_response_hours.append(
                (_ensure_utc(first_outbound_response_at) - _ensure_utc(request.opened_at)).total_seconds() / 3600
            )

    repeat_customers = len(repeat_customer_ids)
    new_customers = len(new_customer_ids)

    for request in requests:
        for history in request.status_history:
            created_at = _ensure_utc(history.created_at)
            if window.start_utc <= created_at <= window.end_utc:
                transition_counter[(history.old_status, history.new_status)] += 1

    report_end = window.end_utc
    aging_counter: Counter[str] = Counter()
    workload: dict[int, dict[str, int | str | None]] = {}

    completion_events: list[tuple[ServiceRequest, datetime]] = []
    for request in requests:
        for history in request.status_history:
            if history.new_status != "completed":
                continue
            created_at = _ensure_utc(history.created_at)
            if window.start_utc <= created_at <= window.end_utc:
                completion_events.append((request, created_at))

    for request in requests:
        is_open = request.status not in RESOLVED_STATUSES
        if is_open:
            age_days = max((report_end.date() - _to_business_date(request.opened_at)).days, 0)
            for bucket_key, lower, upper in AGING_BUCKETS:
                if upper is None and age_days >= lower:
                    aging_counter[bucket_key] += 1
                    break
                if upper is not None and lower <= age_days <= upper:
                    aging_counter[bucket_key] += 1
                    break

        current_assignments = [
            assignment
            for assignment in request.assignments
            if _assignment_active_at(assignment, report_end)
        ]

        for assignment in current_assignments:
            admin = assignment.admin_user
            if admin is None:
                continue
            row = workload.setdefault(
                admin.id,
                {
                    "admin_label": admin.full_name or admin.email,
                    "active_open_assignments": 0,
                    "unread_count": 0,
                    "overdue_count": 0,
                    "completions_in_range": 0,
                },
            )
            if is_open:
                row["active_open_assignments"] += 1
                row["unread_count"] += get_unread_count_for_admin(request, admin.id)
                if request.due_at and _ensure_utc(request.due_at) < report_end:
                    row["overdue_count"] += 1

    for request, completed_at in completion_events:
        for assignment in request.assignments:
            if not _assignment_active_at(assignment, completed_at):
                continue
            admin = assignment.admin_user
            if admin is None:
                continue
            row = workload.setdefault(
                admin.id,
                {
                    "admin_label": admin.full_name or admin.email,
                    "active_open_assignments": 0,
                    "unread_count": 0,
                    "overdue_count": 0,
                    "completions_in_range": 0,
                },
            )
            row["completions_in_range"] += 1

    open_count = sum(1 for request in requests_in_window if request.status not in RESOLVED_STATUSES)
    resolved_count = sum(1 for request in requests_in_window if request.status in RESOLVED_STATUSES)
    overdue_count = sum(
        1
        for request in requests
        if request.status not in RESOLVED_STATUSES
        and request.due_at is not None
        and _ensure_utc(request.due_at) < report_end
    )

    summary_cards = [
        ReportSummaryCard(
            key="open",
            label="Open items",
            value=open_count,
            helper="Requests opened in the selected range that are still active.",
            href="/admin/consultations/?view=all_active",
        ),
        ReportSummaryCard(
            key="resolved",
            label="Resolved items",
            value=resolved_count,
            helper="Requests opened in the selected range that are completed or cancelled.",
            href="/admin/consultations/?view=completed",
        ),
        ReportSummaryCard(
            key="overdue",
            label="Currently overdue",
            value=overdue_count,
            helper="Open requests past their due date.",
            href="/admin/consultations/?view=all_active",
        ),
        ReportSummaryCard(
            key="repeat_customers",
            label="Repeat customers",
            value=repeat_customers,
            helper="Customers with at least one request before the selected range.",
            href="/admin/consultations/",
        ),
    ]

    return OperationsReportOut(
        filters=filters,
        summary_cards=summary_cards,
        enquiry_series=[
            ReportSeriesPoint(
                key=_bucket_label(bucket, filters.grain),
                label=_bucket_label(bucket, filters.grain),
                bucket_start=bucket,
                value=enquiry_counter.get(bucket, 0),
            )
            for bucket in bucket_starts
        ],
        source_channel_breakdown=[
            ReportBreakdownRow(
                key=key,
                label=key.replace("_", " "),
                value=value,
                href=f"/admin/consultations/?source_channel={key}",
            )
            for key, value in source_counter.most_common()
        ],
        service_type_breakdown=[
            ReportBreakdownRow(
                key=service_type_id,
                label=label,
                value=value,
                href=f"/admin/consultations/?service_type={service_type_code}",
            )
            for (service_type_id, label, service_type_code), value in sorted(
                service_type_counter.items(),
                key=lambda item: (-item[1], item[0][1].lower()),
            )
        ],
        open_vs_resolved_trend=[
            ReportOpenResolvedPoint(
                key=_bucket_label(bucket, filters.grain),
                label=_bucket_label(bucket, filters.grain),
                bucket_start=bucket,
                open_value=open_resolved_counter[bucket]["open"],
                resolved_value=open_resolved_counter[bucket]["resolved"],
            )
            for bucket in bucket_starts
        ],
        aging_buckets=[
            ReportBreakdownRow(
                key=bucket_key,
                label=f"{bucket_key} days",
                value=aging_counter.get(bucket_key, 0),
                href="/admin/consultations/?view=all_active",
            )
            for bucket_key, _, _ in AGING_BUCKETS
        ],
        staff_workload=[
            ReportWorkloadRow(
                admin_id=admin_id,
                admin_label=str(values["admin_label"]),
                active_open_assignments=int(values["active_open_assignments"]),
                unread_count=int(values["unread_count"]),
                overdue_count=int(values["overdue_count"]),
                completions_in_range=int(values["completions_in_range"]),
                href=f"/admin/consultations/?assignee={admin_id}&view=assigned",
            )
            for admin_id, values in sorted(
                workload.items(),
                key=lambda item: (-int(item[1]["active_open_assignments"]), str(item[1]["admin_label"]).lower()),
            )
        ],
        funnel_current_status=[
            ReportBreakdownRow(
                key=status,
                label=status.replace("_", " "),
                value=count,
                href=f"/admin/consultations/?status={CONSULTATION_STATUS_BY_REQUEST_STATUS.get(status, 'contacted')}",
            )
            for status, count in sorted(status_counter.items(), key=lambda item: (-item[1], item[0]))
        ],
        funnel_transition_counts=[
            ReportTransitionRow(
                key=f"{old_status or 'none'}->{new_status}",
                from_status=old_status,
                to_status=new_status,
                count=count,
            )
            for (old_status, new_status), count in sorted(
                transition_counter.items(),
                key=lambda item: (-item[1], item[0][1]),
            )
        ],
        repeat_customer_breakdown=[
            ReportBreakdownRow(key="repeat", label="Repeat customers", value=repeat_customers),
            ReportBreakdownRow(key="new", label="New customers", value=new_customers),
        ],
        response_times=ReportResponseTimeSummary(
            first_handled_average_hours=round(mean(response_hours), 2) if response_hours else None,
            first_handled_samples=len(response_hours),
            first_customer_response_average_hours=round(mean(first_response_hours), 2) if first_response_hours else None,
            first_customer_response_samples=len(first_response_hours),
        ),
    )


def _build_activity_series(
    entries: Iterable[AuditLog],
    *,
    filters: ReportFiltersOut,
) -> list[ReportSeriesPoint]:
    window = build_report_window(filters)
    bucket_starts = build_bucket_index(window.start_business_date, window.end_business_date, filters.grain)
    counter: Counter[date] = Counter(
        _bucket_start(_to_business_date(entry.created_at), filters.grain)
        for entry in entries
    )
    return [
        ReportSeriesPoint(
            key=_bucket_label(bucket, filters.grain),
            label=_bucket_label(bucket, filters.grain),
            bucket_start=bucket,
            value=counter.get(bucket, 0),
        )
        for bucket in bucket_starts
    ]


def build_admin_activity_report(
    entries: Iterable[AuditLog],
    *,
    filters: ReportFiltersOut,
) -> AdminActivityReportOut:
    logs = list(entries)
    actor_counter: Counter[str] = Counter()
    action_counter: Counter[str] = Counter()
    combo_counter: Counter[tuple[str, str]] = Counter()

    for entry in logs:
        actor_label = entry.actor_email or "System"
        actor_counter[actor_label] += 1
        action_counter[entry.action] += 1
        combo_counter[(actor_label, entry.action)] += 1

    summary_cards = [
        ReportSummaryCard(key="total_events", label="Total events", value=len(logs)),
        ReportSummaryCard(key="unique_actors", label="Unique actors", value=len(actor_counter)),
        ReportSummaryCard(
            key="governance_events",
            label="Governance events",
            value=sum(1 for entry in logs if entry.action.startswith("user.")),
            helper="Role, status, and other admin-user mutations.",
            href="/admin/access/roles/",
        ),
    ]

    return AdminActivityReportOut(
        filters=filters,
        summary_cards=summary_cards,
        activity_series=_build_activity_series(logs, filters=filters),
        actor_breakdown=[
            ReportBreakdownRow(key=label, label=label, value=count)
            for label, count in actor_counter.most_common()
        ],
        action_breakdown=[
            ReportBreakdownRow(key=action, label=action.replace(".", " / "), value=count)
            for action, count in action_counter.most_common()
        ],
        rows=[
            AdminActivityRow(
                key=f"{actor_label}:{action}",
                actor_label=actor_label,
                action=action,
                count=count,
                href="/admin/access/roles/" if action.startswith("user.") else None,
            )
            for (actor_label, action), count in combo_counter.most_common()
        ],
    )


def _content_href_for_type(content_type: str) -> str:
    if content_type == "page":
        return "/admin/pages/"
    if content_type == "blog_post":
        return "/admin/blog/posts/"
    return "/admin/testimonials/"


def build_content_activity_report(
    entries: Iterable[AuditLog],
    *,
    filters: ReportFiltersOut,
) -> ContentActivityReportOut:
    logs: list[AuditLog] = []
    for entry in entries:
        if entry.target_type not in {"page", "blog_post", "testimonial"}:
            continue
        _, _, action_suffix = entry.action.partition(".")
        if action_suffix not in REPORTABLE_CONTENT_ACTIONS:
            continue
        logs.append(entry)

    content_counter: Counter[str] = Counter()
    action_counter: Counter[str] = Counter()
    combo_counter: Counter[tuple[str, str]] = Counter()

    for entry in logs:
        _, _, action_suffix = entry.action.partition(".")
        normalized_action = "submit" if action_suffix == "submit_review" else action_suffix
        content_counter[entry.target_type] += 1
        action_counter[normalized_action] += 1
        combo_counter[(entry.target_type, normalized_action)] += 1

    summary_cards = [
        ReportSummaryCard(key="total_events", label="Total events", value=sum(combo_counter.values())),
        ReportSummaryCard(
            key="publish_events",
            label="Publish events",
            value=action_counter.get("publish", 0),
            helper="Published pages, posts, and testimonials.",
        ),
        ReportSummaryCard(
            key="review_events",
            label="Review actions",
            value=action_counter.get("approve", 0) + action_counter.get("reject", 0),
            helper="Approve and reject actions across content workflows.",
        ),
    ]

    return ContentActivityReportOut(
        filters=filters,
        summary_cards=summary_cards,
        activity_series=_build_activity_series(logs, filters=filters),
        content_type_breakdown=[
            ReportBreakdownRow(
                key=content_type,
                label=content_type.replace("_", " "),
                value=count,
                href=_content_href_for_type(content_type),
            )
            for content_type, count in content_counter.most_common()
        ],
        action_breakdown=[
            ReportBreakdownRow(key=action, label=action.replace("_", " "), value=count)
            for action, count in action_counter.most_common()
        ],
        rows=[
            ContentActivityRow(
                key=f"{content_type}:{action}",
                content_type=content_type,  # type: ignore[arg-type]
                action=action,  # type: ignore[arg-type]
                count=count,
                href=_content_href_for_type(content_type),
            )
            for (content_type, action), count in combo_counter.most_common()
        ],
    )


async def list_reporting_service_requests(
    db: AsyncSession,
    *,
    service_type_id: UUID | None = None,
    assignee_id: int | None = None,
    source_channel: ServiceRequestSourceChannel | None = None,
    status: ServiceRequestStatus | None = None,
) -> list[ServiceRequest]:
    statement = (
        select(ServiceRequest)
        .options(
            selectinload(ServiceRequest.customer),
            selectinload(ServiceRequest.service_type),
            selectinload(ServiceRequest.assignments).selectinload(ServiceRequestAssignment.admin_user),
            selectinload(ServiceRequest.inbox_states).selectinload(ServiceRequestInboxState.last_read_message),
            selectinload(ServiceRequest.status_history).selectinload(ServiceRequestStatusHistory.changed_by_admin),
            selectinload(ServiceRequest.notes).selectinload(RecordNote.created_by_admin),
            selectinload(ServiceRequest.threads)
            .selectinload(InboxThread.messages)
            .selectinload(InboxMessage.author_admin),
        )
        .order_by(ServiceRequest.opened_at.asc())
    )

    if service_type_id is not None:
        statement = statement.where(ServiceRequest.service_type_id == service_type_id)
    if source_channel is not None:
        statement = statement.where(ServiceRequest.source_channel == source_channel)
    if status is not None:
        statement = statement.where(ServiceRequest.status == status)
    if assignee_id is not None:
        statement = statement.where(
            select(ServiceRequestAssignment.id)
            .where(
                ServiceRequestAssignment.service_request_id == ServiceRequest.id,
                ServiceRequestAssignment.admin_user_id == assignee_id,
                ServiceRequestAssignment.unassigned_at.is_(None),
            )
            .exists()
        )

    result = await db.execute(statement)
    return list(result.scalars().unique().all())


async def list_audit_logs_for_window(
    db: AsyncSession,
    *,
    filters: ReportFiltersOut,
) -> list[AuditLog]:
    window = build_report_window(filters)
    result = await db.execute(
        select(AuditLog)
        .options(selectinload(AuditLog.actor))
        .where(AuditLog.created_at >= window.start_utc, AuditLog.created_at <= window.end_utc)
        .order_by(AuditLog.created_at.desc())
    )
    return list(result.scalars().all())
