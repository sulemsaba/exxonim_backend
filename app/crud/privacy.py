from __future__ import annotations

import secrets
from math import ceil
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import utcnow
from app.crud import site_settings as site_settings_crud
from app.models import AdminUser, PrivacyConsentLog, PrivacyRequest
from app.schemas.privacy import (
    PrivacyConsentCategories,
    PrivacyConsentOut,
    PrivacyConsentUpdate,
    PrivacyPolicyVersions,
    PrivacyRequestCreate,
    PrivacyRequestListResponse,
    PrivacyRequestUpdate,
)

POLICY_VERSIONS_SETTING_KEY = "policy_versions"
DEFAULT_POLICY_VERSIONS = PrivacyPolicyVersions(
    privacy_policy="2026-04-v1",
    cookie_notice="2026-04-v1",
    data_rights_notice="2026-04-v1",
)


def generate_consent_identifier() -> str:
    return secrets.token_urlsafe(24)


def normalize_policy_versions(value: Any) -> PrivacyPolicyVersions:
    if isinstance(value, dict):
        try:
            return PrivacyPolicyVersions.model_validate(value)
        except Exception:
            return DEFAULT_POLICY_VERSIONS
    return DEFAULT_POLICY_VERSIONS


async def get_policy_versions(db: AsyncSession) -> PrivacyPolicyVersions:
    setting = await site_settings_crud.get_site_setting_by_key(db, POLICY_VERSIONS_SETTING_KEY)
    if setting is None:
        return DEFAULT_POLICY_VERSIONS
    return normalize_policy_versions(setting.value)


async def get_latest_consent_log(
    db: AsyncSession,
    consent_identifier: str | None,
) -> PrivacyConsentLog | None:
    if not consent_identifier:
        return None
    result = await db.execute(
        select(PrivacyConsentLog)
        .where(PrivacyConsentLog.consent_identifier == consent_identifier)
        .order_by(PrivacyConsentLog.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def build_consent_state(
    *,
    consent_log: PrivacyConsentLog | None,
    policy_versions: PrivacyPolicyVersions,
) -> PrivacyConsentOut:
    if consent_log is None:
        return PrivacyConsentOut(
            policy_versions=policy_versions,
            categories=PrivacyConsentCategories(necessary=True, preferences=False),
            consent_recorded=False,
            recorded_at=None,
        )

    choices = consent_log.category_choices if isinstance(consent_log.category_choices, dict) else {}
    return PrivacyConsentOut(
        policy_versions=policy_versions,
        categories=PrivacyConsentCategories(
            necessary=bool(choices.get("necessary", True)),
            preferences=bool(choices.get("preferences", False)),
        ),
        consent_recorded=True,
        recorded_at=consent_log.created_at,
    )


async def record_consent(
    db: AsyncSession,
    *,
    consent_identifier: str,
    payload: PrivacyConsentUpdate,
    policy_versions: PrivacyPolicyVersions,
    ip: str | None,
    user_agent: str | None,
) -> PrivacyConsentLog:
    entry = PrivacyConsentLog(
        consent_identifier=consent_identifier,
        policy_versions=policy_versions.model_dump(),
        category_choices={
            "necessary": True,
            "preferences": bool(payload.preferences),
        },
        source_path=payload.source_path,
        ip=ip,
        user_agent=user_agent,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def list_privacy_requests(
    db: AsyncSession,
    *,
    page: int = 1,
    limit: int = 20,
    search: str | None = None,
    status: str | None = None,
    request_type: str | None = None,
) -> tuple[list[PrivacyRequest], int]:
    safe_page = max(page, 1)
    safe_limit = max(min(limit, 100), 1)

    base_query = select(PrivacyRequest)

    if status:
        base_query = base_query.where(PrivacyRequest.status == status)
    if request_type:
        base_query = base_query.where(PrivacyRequest.request_type == request_type)
    if search:
        term = f"%{search.strip().lower()}%"
        base_query = base_query.where(
            or_(
                func.lower(PrivacyRequest.requester_name).like(term),
                func.lower(PrivacyRequest.requester_email).like(term),
                func.lower(PrivacyRequest.summary).like(term),
            )
        )

    total = int(
        await db.scalar(select(func.count()).select_from(base_query.order_by(None).subquery()))
        or 0
    )
    result = await db.execute(
        base_query.order_by(PrivacyRequest.created_at.desc())
        .offset((safe_page - 1) * safe_limit)
        .limit(safe_limit)
    )
    return list(result.scalars().all()), total


def build_privacy_request_list_response(
    items: list[PrivacyRequest],
    *,
    page: int,
    limit: int,
    total: int,
) -> PrivacyRequestListResponse:
    return PrivacyRequestListResponse(
        items=items,
        page=page,
        limit=limit,
        total=total,
        total_pages=max(ceil(total / limit), 1) if limit else 1,
    )


async def get_privacy_request_by_id(
    db: AsyncSession,
    privacy_request_id: UUID,
) -> PrivacyRequest | None:
    result = await db.execute(
        select(PrivacyRequest).where(PrivacyRequest.id == privacy_request_id)
    )
    return result.scalar_one_or_none()


async def create_privacy_request(
    db: AsyncSession,
    *,
    payload: PrivacyRequestCreate,
    created_by_admin: AdminUser,
) -> PrivacyRequest:
    record = PrivacyRequest(
        customer_id=payload.customer_id,
        request_type=payload.request_type,
        status="received",
        requester_name=payload.requester_name.strip(),
        requester_email=payload.requester_email.strip().lower(),
        summary=payload.summary.strip(),
        internal_notes=payload.internal_notes.strip() if payload.internal_notes else None,
        created_by_admin_id=created_by_admin.id,
    )
    db.add(record)
    await db.commit()
    refreshed = await get_privacy_request_by_id(db, record.id)
    return refreshed or record


async def update_privacy_request(
    db: AsyncSession,
    *,
    privacy_request: PrivacyRequest,
    payload: PrivacyRequestUpdate,
    updated_by_admin: AdminUser,
) -> PrivacyRequest:
    changes = payload.model_dump(exclude_unset=True)

    if "status" in changes:
        privacy_request.status = changes["status"]
        if changes["status"] in {"completed", "rejected"}:
            privacy_request.completed_at = utcnow()
            privacy_request.completed_by_admin_id = updated_by_admin.id
        elif changes["status"] in {"received", "verifying", "in_progress"}:
            privacy_request.completed_at = None
            privacy_request.completed_by_admin_id = None

    if "internal_notes" in changes:
        privacy_request.internal_notes = changes["internal_notes"]
    if "resolution_notes" in changes:
        privacy_request.resolution_notes = changes["resolution_notes"]

    db.add(privacy_request)
    await db.commit()
    refreshed = await get_privacy_request_by_id(db, privacy_request.id)
    return refreshed or privacy_request
