from __future__ import annotations

import secrets

from jose import JWTError
from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import admin as admin_crud
from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_token, utcnow
from app.models import AdminUser, RefreshSession


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
    )


def _forbidden(detail: str = "You do not have permission to perform this action.") -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


async def get_current_admin(
    access_token: str | None = Cookie(default=None, alias=settings.ACCESS_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    if not access_token:
        raise _unauthorized()

    try:
        payload = decode_token(access_token)
    except JWTError as exc:
        raise _unauthorized("Invalid token") from exc

    if payload.get("token_type") != "access":
        raise _unauthorized("Invalid access token")

    subject = payload.get("sub")
    session_id_raw = payload.get("sid")
    if not isinstance(subject, str) or not subject.isdigit():
        raise _unauthorized("Invalid token subject")
    if not isinstance(session_id_raw, str) or not session_id_raw.isdigit():
        raise _unauthorized("Invalid token session")

    admin_id = int(subject)
    session_id = int(session_id_raw)
    refresh_session = await admin_crud.get_active_refresh_session_for_admin(
        db,
        session_id=session_id,
        admin_id=admin_id,
        now=utcnow(),
    )
    if refresh_session is None:
        raise _unauthorized("Session is no longer active")

    admin = await admin_crud.get_admin_by_id(db, admin_id, include_access=True)
    if admin is None or not admin.is_active:
        raise _unauthorized("Admin account is inactive")

    setattr(admin, "_refresh_session", refresh_session)
    return admin


def get_active_refresh_session(current_admin: AdminUser = Depends(get_current_admin)) -> RefreshSession:
    refresh_session = getattr(current_admin, "_refresh_session", None)
    if refresh_session is None:
        raise _unauthorized("Session is no longer active")
    return refresh_session


async def require_csrf(
    csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
    csrf_cookie: str | None = Cookie(default=None, alias=settings.CSRF_COOKIE_NAME),
    refresh_session: RefreshSession = Depends(get_active_refresh_session),
) -> None:
    if not csrf_header or not csrf_cookie:
        raise _forbidden("Missing CSRF token.")

    if not secrets.compare_digest(csrf_header, csrf_cookie):
        raise _forbidden("Invalid CSRF token.")

    from app.core.auth_sessions import assert_csrf_token

    assert_csrf_token(
        header_token=csrf_header,
        cookie_token=csrf_cookie,
        session=refresh_session,
    )


def has_permission(admin: AdminUser, permission_code: str) -> bool:
    return permission_code in admin.permissions


def has_any_permission(admin: AdminUser, *permission_codes: str) -> bool:
    return any(has_permission(admin, permission_code) for permission_code in permission_codes)


def require_permission(permission_code: str):
    async def dependency(current_admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
        if not has_permission(current_admin, permission_code):
            raise _forbidden()
        return current_admin

    return dependency


def require_any_permission(*permission_codes: str):
    async def dependency(current_admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
        if not has_any_permission(current_admin, *permission_codes):
            raise _forbidden()
        return current_admin

    return dependency


async def require_admin_api_key(_: None = Depends(require_csrf)) -> None:
    # Compatibility shim while older route signatures are migrated away from the
    # browser-exposed API key model. Mutating admin routes now rely on CSRF.
    return None
