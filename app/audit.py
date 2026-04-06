from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect as sa_inspect

from app.models import AuditLog


def get_request_meta(request: Request | None) -> tuple[str | None, str | None]:
    if request is None:
        return None, None

    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return ip, user_agent


def serialize_for_audit(value: Any) -> dict[str, Any] | list[Any] | str | int | float | bool | None:
    if value is None:
        return None

    if isinstance(value, (dict, list, tuple, str, int, float, bool)):
        return jsonable_encoder(value)

    try:
        mapper = sa_inspect(value).mapper
    except Exception:
        return jsonable_encoder(value)

    payload = {
        column.key: getattr(value, column.key)
        for column in mapper.column_attrs
    }
    return jsonable_encoder(payload)


async def log_audit(
    db: AsyncSession,
    *,
    actor_id: int | None,
    actor_email: str | None,
    action: str,
    target_type: str | None = None,
    target_id: str | int | None = None,
    old_value: Any = None,
    new_value: Any = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    entry = AuditLog(
        actor_id=actor_id,
        actor_email=actor_email,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        old_value=serialize_for_audit(old_value),
        new_value=serialize_for_audit(new_value),
        ip=ip,
        user_agent=user_agent,
    )
    db.add(entry)

    try:
        await db.commit()
    except Exception:
        await db.rollback()
