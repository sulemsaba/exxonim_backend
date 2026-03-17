from __future__ import annotations

from jose import JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import admin as admin_crud
from app.core.database import get_db
from app.core.security import decode_token
from app.models import AdminUser

bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()

    try:
        payload = decode_token(credentials.credentials)
    except JWTError as exc:
        raise _unauthorized("Invalid token") from exc

    if payload.get("token_type") != "access":
        raise _unauthorized("Invalid access token")

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.isdigit():
        raise _unauthorized("Invalid token subject")

    admin = await admin_crud.get_admin_by_id(db, int(subject))
    if admin is None or not admin.is_active:
        raise _unauthorized("Admin account is inactive")

    return admin
