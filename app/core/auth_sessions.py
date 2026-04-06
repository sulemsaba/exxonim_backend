from __future__ import annotations

from datetime import datetime
import secrets

from fastapi import HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import get_request_meta, log_audit
from app.core.config import settings
from app.core.security import (
    build_token_hash,
    create_access_token,
    generate_session_token,
    refresh_session_expires_at,
    utcnow,
    verify_token_hash,
)
from app.crud import admin as admin_crud
from app.models import AdminUser, RefreshSession
from app.schemas import AdminLogoutResponse, AdminRefreshResponse, AdminSessionResponse


def build_refresh_cookie_value(session: RefreshSession, raw_secret: str) -> str:
    return f"{session.id}.{raw_secret}"


def parse_refresh_cookie_value(raw_value: str | None) -> tuple[int, str] | None:
    if not raw_value:
        return None

    session_id_raw, separator, raw_secret = raw_value.partition(".")
    if not separator or not session_id_raw.isdigit() or not raw_secret:
        return None

    return int(session_id_raw), raw_secret


def add_no_store_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def set_auth_cookies(
    response: Response,
    *,
    access_token: str,
    refresh_cookie_value: str,
    csrf_token: str,
) -> None:
    cookie_kwargs = {
        "domain": settings.COOKIE_DOMAIN or None,
        "secure": settings.COOKIE_SECURE,
        "samesite": settings.COOKIE_SAMESITE,
        "path": "/",
    }

    response.set_cookie(
        settings.ACCESS_COOKIE_NAME,
        access_token,
        httponly=True,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        **cookie_kwargs,
    )
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        refresh_cookie_value,
        httponly=True,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        **cookie_kwargs,
    )
    response.set_cookie(
        settings.CSRF_COOKIE_NAME,
        csrf_token,
        httponly=False,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        **cookie_kwargs,
    )
    add_no_store_headers(response)


def clear_auth_cookies(response: Response) -> None:
    cookie_kwargs = {
        "domain": settings.COOKIE_DOMAIN or None,
        "secure": settings.COOKIE_SECURE,
        "samesite": settings.COOKIE_SAMESITE,
        "path": "/",
    }
    response.delete_cookie(settings.ACCESS_COOKIE_NAME, **cookie_kwargs)
    response.delete_cookie(settings.REFRESH_COOKIE_NAME, **cookie_kwargs)
    response.delete_cookie(settings.CSRF_COOKIE_NAME, **cookie_kwargs)
    add_no_store_headers(response)


def build_access_token_for_session(admin: AdminUser, session: RefreshSession) -> str:
    return create_access_token(
        subject=str(admin.id),
        extra_claims={
            "token_type": "access",
            "email": admin.email,
            "role": admin.role,
            "sid": str(session.id),
        },
    )


async def create_refresh_session(
    db: AsyncSession,
    *,
    admin: AdminUser,
    request: Request | None,
) -> tuple[RefreshSession, str, str]:
    ip, user_agent = get_request_meta(request)
    raw_refresh_secret = generate_session_token()
    csrf_token = generate_session_token(24)
    session = RefreshSession(
        admin_user_id=admin.id,
        refresh_token_hash="",
        csrf_token_hash=build_token_hash(csrf_token),
        expires_at=refresh_session_expires_at(),
        ip=ip,
        user_agent=user_agent,
    )
    db.add(session)
    await db.flush()
    session.refresh_token_hash = build_token_hash(raw_refresh_secret)
    db.add(session)
    return session, raw_refresh_secret, csrf_token


async def rotate_refresh_session(
    db: AsyncSession,
    *,
    session: RefreshSession,
    request: Request | None,
) -> tuple[RefreshSession, str, str]:
    ip, user_agent = get_request_meta(request)
    raw_refresh_secret = generate_session_token()
    csrf_token = generate_session_token(24)
    session.refresh_token_hash = build_token_hash(raw_refresh_secret)
    session.csrf_token_hash = build_token_hash(csrf_token)
    session.expires_at = refresh_session_expires_at()
    session.last_used_at = utcnow()
    session.ip = ip
    session.user_agent = user_agent
    db.add(session)
    await db.flush()
    return session, raw_refresh_secret, csrf_token


async def revoke_refresh_session(
    db: AsyncSession,
    *,
    session: RefreshSession,
) -> RefreshSession:
    session.revoked_at = utcnow()
    db.add(session)
    await db.flush()
    return session


def assert_valid_refresh_cookie(
    *,
    session: RefreshSession | None,
    raw_refresh_secret: str | None,
) -> None:
    if session is None or raw_refresh_secret is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh session.",
        )

    now = utcnow()
    if session.revoked_at is not None or session.expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh session has expired.",
        )

    if not verify_token_hash(raw_refresh_secret, session.refresh_token_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh session.",
        )


def assert_csrf_token(
    *,
    header_token: str | None,
    cookie_token: str | None,
    session: RefreshSession,
) -> None:
    if not header_token or not cookie_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing CSRF token.",
        )

    if not secrets.compare_digest(header_token, cookie_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid CSRF token.",
        )

    if not verify_token_hash(header_token, session.csrf_token_hash):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid CSRF token.",
        )


async def build_login_response(
    *,
    db: AsyncSession,
    admin: AdminUser,
    request: Request,
    response: Response,
) -> AdminSessionResponse:
    admin.last_login_at = utcnow()
    db.add(admin)
    session, raw_refresh_secret, csrf_token = await create_refresh_session(
        db,
        admin=admin,
        request=request,
    )
    await db.commit()
    refreshed = await admin_crud.get_admin_by_id(db, admin.id, include_access=True)
    if refreshed is None or not refreshed.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin account is inactive",
        )

    await log_audit(
        db,
        actor_id=refreshed.id,
        actor_email=refreshed.email,
        action="auth.login_succeeded",
        target_type="auth",
        target_id=str(refreshed.id),
        old_value=None,
        new_value={"success": True, "session_id": session.id},
        ip=session.ip,
        user_agent=session.user_agent,
    )

    set_auth_cookies(
        response,
        access_token=build_access_token_for_session(refreshed, session),
        refresh_cookie_value=build_refresh_cookie_value(session, raw_refresh_secret),
        csrf_token=csrf_token,
    )
    return AdminSessionResponse(admin=refreshed)


async def build_refresh_response(
    *,
    db: AsyncSession,
    admin: AdminUser,
    session: RefreshSession,
    request: Request,
    response: Response,
) -> AdminRefreshResponse:
    rotated_session, raw_refresh_secret, csrf_token = await rotate_refresh_session(
        db,
        session=session,
        request=request,
    )
    await db.commit()
    set_auth_cookies(
        response,
        access_token=build_access_token_for_session(admin, rotated_session),
        refresh_cookie_value=build_refresh_cookie_value(rotated_session, raw_refresh_secret),
        csrf_token=csrf_token,
    )
    return AdminRefreshResponse()


async def build_logout_response(
    *,
    db: AsyncSession,
    session: RefreshSession | None,
    response: Response,
) -> AdminLogoutResponse:
    if session is not None and session.revoked_at is None:
        await revoke_refresh_session(db, session=session)
        await db.commit()

    clear_auth_cookies(response)
    return AdminLogoutResponse()
