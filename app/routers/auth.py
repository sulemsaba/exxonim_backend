from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import get_request_meta, log_audit
from app.core.auth_sessions import (
    add_no_store_headers,
    assert_valid_refresh_cookie,
    build_login_response,
    build_logout_response,
    build_refresh_response,
    parse_refresh_cookie_value,
)
from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_active_refresh_session, get_current_admin, require_csrf
from app.crud import admin as admin_crud
from app.crud import notification as notification_crud
from app.models import AdminUser, RefreshSession
from app.schemas import (
    AdminLoginRequest,
    AdminLogoutResponse,
    AdminRefreshResponse,
    AdminSessionResponse,
    AdminUserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


async def _authenticate_or_raise(
    *,
    db: AsyncSession,
    payload: AdminLoginRequest,
    request: Request,
) -> AdminUser:
    admin = await admin_crud.authenticate_admin(
        db,
        email=payload.email,
        password=payload.password,
    )
    ip, user_agent = get_request_meta(request)

    if admin is None:
        await log_audit(
            db,
            actor_id=None,
            actor_email=payload.email,
            action="auth.login_failed",
            target_type="auth",
            target_id=payload.email,
            old_value=None,
            new_value={"success": False},
            ip=ip,
            user_agent=user_agent,
        )
        failed_attempts = await notification_crud.count_recent_failed_logins_for_email(
            db,
            email=payload.email,
        )
        if failed_attempts >= 5:
            await notification_crud.emit_suspicious_login_notifications(
                db,
                email=payload.email,
                attempt_count=failed_attempts,
                observed_at=notification_crud.utcnow(),
            )
            await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    return admin


async def login_via_cookies(
    *,
    payload: AdminLoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession,
) -> AdminSessionResponse:
    admin = await _authenticate_or_raise(db=db, payload=payload, request=request)
    return await build_login_response(
        db=db,
        admin=admin,
        request=request,
        response=response,
    )


async def refresh_via_cookies(
    *,
    request: Request,
    response: Response,
    db: AsyncSession,
    refresh_cookie: str | None,
    csrf_cookie: str | None,
    csrf_header: str | None,
) -> AdminRefreshResponse:
    parsed_cookie = parse_refresh_cookie_value(refresh_cookie)
    if parsed_cookie is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh session.",
        )
    session_id, raw_refresh_secret = parsed_cookie
    refresh_session = await admin_crud.get_refresh_session_by_id(db, session_id)
    assert_valid_refresh_cookie(session=refresh_session, raw_refresh_secret=raw_refresh_secret)
    assert refresh_session is not None

    from app.core.auth_sessions import assert_csrf_token

    assert_csrf_token(
        header_token=csrf_header,
        cookie_token=csrf_cookie,
        session=refresh_session,
    )

    admin = await admin_crud.get_admin_by_id(
        db,
        refresh_session.admin_user_id,
        include_access=True,
    )
    if admin is None or not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin account is inactive",
        )

    return await build_refresh_response(
        db=db,
        admin=admin,
        session=refresh_session,
        request=request,
        response=response,
    )


async def logout_via_cookies(
    *,
    db: AsyncSession,
    response: Response,
    refresh_session: RefreshSession | None,
) -> AdminLogoutResponse:
    return await build_logout_response(
        db=db,
        session=refresh_session,
        response=response,
    )


@router.post("/login", response_model=AdminSessionResponse)
async def login(
    payload: AdminLoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AdminSessionResponse:
    return await login_via_cookies(
        payload=payload,
        request=request,
        response=response,
        db=db,
    )


@router.post("/refresh", response_model=AdminRefreshResponse)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    refresh_cookie: str | None = Cookie(default=None, alias=settings.REFRESH_COOKIE_NAME),
    csrf_cookie: str | None = Cookie(default=None, alias=settings.CSRF_COOKIE_NAME),
    csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> AdminRefreshResponse:
    return await refresh_via_cookies(
        request=request,
        response=response,
        db=db,
        refresh_cookie=refresh_cookie,
        csrf_cookie=csrf_cookie,
        csrf_header=request.headers.get("X-CSRF-Token"),
    )


@router.post("/logout", response_model=AdminLogoutResponse)
async def logout(
    response: Response,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_csrf),
    refresh_session: RefreshSession = Depends(get_active_refresh_session),
) -> AdminLogoutResponse:
    return await logout_via_cookies(
        db=db,
        response=response,
        refresh_session=refresh_session,
    )


@router.get("/me", response_model=AdminUserOut)
async def me(
    response: Response,
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminUserOut:
    add_no_store_headers(response)
    return current_admin
