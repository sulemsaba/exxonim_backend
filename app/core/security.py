from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return _create_token(subject=subject, expires_delta=expires_delta, extra_claims=extra_claims)


def create_refresh_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return _create_token(subject=subject, expires_delta=expires_delta, extra_claims=extra_claims)


def create_consultation_magic_token(
    *,
    consultation_id: int,
    tracking_id: str,
    email: str,
) -> str:
    return _create_token(
        subject=str(consultation_id),
        expires_delta=timedelta(days=7),
        extra_claims={
            "token_type": "consultation_magic",
            "tracking_id": tracking_id,
            "email": email,
        },
    )


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


def _create_token(
    subject: str,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def is_token_valid(token: str) -> bool:
    try:
        decode_token(token)
        return True
    except JWTError:
        return False
