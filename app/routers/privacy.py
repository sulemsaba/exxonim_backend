from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import get_request_meta, log_audit, serialize_for_audit
from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import require_csrf, require_permission
from app.crud import privacy as privacy_crud
from app.models import AdminUser
from app.schemas import (
    PrivacyConsentOut,
    PrivacyConsentUpdate,
    PrivacyRequestCreate,
    PrivacyRequestListResponse,
    PrivacyRequestOut,
    PrivacyRequestUpdate,
)

router = APIRouter(tags=["privacy"])


def _set_consent_cookie(response: Response, consent_identifier: str) -> None:
    response.set_cookie(
        settings.CONSENT_COOKIE_NAME,
        consent_identifier,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        domain=settings.COOKIE_DOMAIN or None,
        path="/",
        max_age=365 * 24 * 60 * 60,
    )


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


@router.get("/privacy/consent", response_model=PrivacyConsentOut)
async def get_privacy_consent(
    response: Response,
    db: AsyncSession = Depends(get_db),
    consent_identifier: str | None = Cookie(default=None, alias=settings.CONSENT_COOKIE_NAME),
) -> PrivacyConsentOut:
    effective_identifier = consent_identifier or privacy_crud.generate_consent_identifier()
    policy_versions = await privacy_crud.get_policy_versions(db)
    consent_log = await privacy_crud.get_latest_consent_log(db, effective_identifier)
    _set_consent_cookie(response, effective_identifier)
    return privacy_crud.build_consent_state(
        consent_log=consent_log,
        policy_versions=policy_versions,
    )


@router.post("/privacy/consent", response_model=PrivacyConsentOut)
async def update_privacy_consent(
    payload: PrivacyConsentUpdate,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    consent_identifier: str | None = Cookie(default=None, alias=settings.CONSENT_COOKIE_NAME),
) -> PrivacyConsentOut:
    effective_identifier = consent_identifier or privacy_crud.generate_consent_identifier()
    policy_versions = await privacy_crud.get_policy_versions(db)
    ip, user_agent = get_request_meta(request)
    consent_log = await privacy_crud.record_consent(
        db,
        consent_identifier=effective_identifier,
        payload=payload,
        policy_versions=policy_versions,
        ip=ip,
        user_agent=user_agent,
    )
    _set_consent_cookie(response, effective_identifier)
    return privacy_crud.build_consent_state(
        consent_log=consent_log,
        policy_versions=policy_versions,
    )


@router.get("/admin/privacy-requests", response_model=PrivacyRequestListResponse)
async def list_admin_privacy_requests(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    request_type: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(require_permission("privacy_request.read")),
) -> PrivacyRequestListResponse:
    items, total = await privacy_crud.list_privacy_requests(
        db,
        page=page,
        limit=limit,
        search=search,
        status=status,
        request_type=request_type,
    )
    return privacy_crud.build_privacy_request_list_response(
        items,
        page=page,
        limit=limit,
        total=total,
    )


@router.post("/admin/privacy-requests", response_model=PrivacyRequestOut)
async def create_admin_privacy_request(
    payload: PrivacyRequestCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("privacy_request.manage")),
    _: None = Depends(require_csrf),
) -> PrivacyRequestOut:
    created = await privacy_crud.create_privacy_request(
        db,
        payload=payload,
        created_by_admin=current_admin,
    )
    ip, user_agent = get_request_meta(request)
    await log_audit(
        db,
        actor_id=current_admin.id,
        actor_email=current_admin.email,
        action="privacy_request.create",
        target_type="privacy_request",
        target_id=created.id,
        old_value=None,
        new_value=serialize_for_audit(created),
        ip=ip,
        user_agent=user_agent,
    )
    return created


@router.patch("/admin/privacy-requests/{privacy_request_id}", response_model=PrivacyRequestOut)
async def update_admin_privacy_request(
    privacy_request_id: UUID,
    payload: PrivacyRequestUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin: AdminUser = Depends(require_permission("privacy_request.manage")),
    _: None = Depends(require_csrf),
) -> PrivacyRequestOut:
    existing = await privacy_crud.get_privacy_request_by_id(db, privacy_request_id)
    if existing is None:
        raise _not_found("Privacy request not found")

    old_value = serialize_for_audit(existing)
    updated = await privacy_crud.update_privacy_request(
        db,
        privacy_request=existing,
        payload=payload,
        updated_by_admin=current_admin,
    )
    ip, user_agent = get_request_meta(request)
    await log_audit(
        db,
        actor_id=current_admin.id,
        actor_email=current_admin.email,
        action="privacy_request.update",
        target_type="privacy_request",
        target_id=updated.id,
        old_value=old_value,
        new_value=serialize_for_audit(updated),
        ip=ip,
        user_agent=user_agent,
    )
    return updated
