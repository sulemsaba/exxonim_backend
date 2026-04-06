from __future__ import annotations

from datetime import date, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_permission
from app.crud import reporting as reporting_crud
from app.models import AdminUser
from app.schemas import (
    AdminActivityReportOut,
    ContentActivityReportOut,
    OperationsReportOut,
    ReportFiltersOut,
)

router = APIRouter(prefix="/admin/reports", tags=["admin-reports"])


def _resolve_filters(
    *,
    from_date: date | None,
    to_date: date | None,
    grain: str | None,
    service_type_id: UUID | None,
    assignee_id: int | None,
    source_channel: str | None,
    status: str | None,
) -> ReportFiltersOut:
    today = datetime.now(reporting_crud.BUSINESS_TIMEZONE).date()
    safe_to = to_date or today
    safe_from = from_date or (safe_to - timedelta(days=29))
    if safe_from > safe_to:
        safe_from, safe_to = safe_to, safe_from

    resolved_grain = grain
    if resolved_grain is None:
        delta_days = (safe_to - safe_from).days
        if delta_days <= 62:
            resolved_grain = "day"
        elif delta_days <= 366:
            resolved_grain = "week"
        else:
            resolved_grain = "month"

    return ReportFiltersOut(
        **{
            "from": safe_from,
            "to": safe_to,
            "grain": resolved_grain,
            "service_type_id": str(service_type_id) if service_type_id else None,
            "assignee_id": assignee_id,
            "source_channel": source_channel,
            "status": status,
        }
    )


@router.get("/operations", response_model=OperationsReportOut)
async def get_operations_report(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    grain: str | None = Query(default=None),
    service_type_id: UUID | None = Query(default=None),
    assignee_id: int | None = Query(default=None),
    source_channel: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("report.read")),
) -> OperationsReportOut:
    filters = _resolve_filters(
        from_date=from_date,
        to_date=to_date,
        grain=grain,
        service_type_id=service_type_id,
        assignee_id=assignee_id,
        source_channel=source_channel,
        status=status,
    )
    service_requests = await reporting_crud.list_reporting_service_requests(
        db,
        service_type_id=service_type_id,
        assignee_id=assignee_id,
        source_channel=source_channel,
        status=status,
    )
    return reporting_crud.build_operations_report(service_requests, filters=filters)


@router.get("/activity/admin", response_model=AdminActivityReportOut)
async def get_admin_activity_report(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    grain: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("report.read")),
) -> AdminActivityReportOut:
    filters = _resolve_filters(
        from_date=from_date,
        to_date=to_date,
        grain=grain,
        service_type_id=None,
        assignee_id=None,
        source_channel=None,
        status=None,
    )
    audit_logs = await reporting_crud.list_audit_logs_for_window(db, filters=filters)
    return reporting_crud.build_admin_activity_report(audit_logs, filters=filters)


@router.get("/activity/content", response_model=ContentActivityReportOut)
async def get_content_activity_report(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    grain: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("report.read")),
) -> ContentActivityReportOut:
    filters = _resolve_filters(
        from_date=from_date,
        to_date=to_date,
        grain=grain,
        service_type_id=None,
        assignee_id=None,
        source_channel=None,
        status=None,
    )
    audit_logs = await reporting_crud.list_audit_logs_for_window(db, filters=filters)
    return reporting_crud.build_content_activity_report(audit_logs, filters=filters)
