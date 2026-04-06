from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import verify_password
from app.models import AdminUser, Permission, RefreshSession, Role


def _admin_select(*, include_access: bool = False):
    statement = select(AdminUser)

    if include_access:
        statement = statement.options(
            selectinload(AdminUser.assigned_roles).selectinload(Role.granted_permissions),
        )

    return statement


async def get_admin_by_email(
    db: AsyncSession,
    email: str,
    *,
    include_access: bool = False,
) -> AdminUser | None:
    result = await db.execute(
        _admin_select(include_access=include_access).where(
            AdminUser.email == email.strip().lower()
        )
    )
    return result.scalar_one_or_none()


async def get_admin_by_id(
    db: AsyncSession,
    admin_id: int,
    *,
    include_access: bool = False,
) -> AdminUser | None:
    result = await db.execute(
        _admin_select(include_access=include_access).where(AdminUser.id == admin_id)
    )
    return result.scalar_one_or_none()


async def get_all_admins(
    db: AsyncSession,
    *,
    include_access: bool = False,
    search: str | None = None,
    role_code: str | None = None,
) -> list[AdminUser]:
    statement = _admin_select(include_access=include_access).order_by(AdminUser.email.asc())

    if search:
        term = f"%{search.strip().lower()}%"
        statement = statement.where(AdminUser.email.ilike(term))

    if role_code:
        statement = statement.join(AdminUser.assigned_roles).where(Role.code == role_code)

    result = await db.execute(statement)
    return list(result.scalars().all())


async def get_all_roles(db: AsyncSession) -> list[Role]:
    result = await db.execute(
        select(Role)
        .options(selectinload(Role.granted_permissions))
        .order_by(Role.code.asc())
    )
    return list(result.scalars().all())


async def get_role_by_code(db: AsyncSession, role_code: str) -> Role | None:
    result = await db.execute(
        select(Role)
        .options(selectinload(Role.granted_permissions))
        .where(Role.code == role_code)
    )
    return result.scalar_one_or_none()


async def set_admin_roles(
    db: AsyncSession,
    *,
    admin: AdminUser,
    roles: list[Role],
) -> AdminUser:
    admin.assigned_roles = roles
    db.add(admin)
    await db.flush()
    return admin


async def authenticate_admin(
    db: AsyncSession,
    *,
    email: str,
    password: str,
) -> AdminUser | None:
    admin = await get_admin_by_email(db, email, include_access=True)
    if admin is None or not admin.is_active:
        return None
    if not verify_password(password, admin.hashed_password):
        return None
    return admin


async def get_refresh_session_by_id(
    db: AsyncSession,
    session_id: int,
) -> RefreshSession | None:
    result = await db.execute(
        select(RefreshSession).where(RefreshSession.id == session_id)
    )
    return result.scalar_one_or_none()


async def get_refresh_session_for_admin(
    db: AsyncSession,
    *,
    session_id: int,
    admin_id: int,
) -> RefreshSession | None:
    result = await db.execute(
        select(RefreshSession).where(
            RefreshSession.id == session_id,
            RefreshSession.admin_user_id == admin_id,
        )
    )
    return result.scalar_one_or_none()


async def get_active_refresh_session_for_admin(
    db: AsyncSession,
    *,
    session_id: int,
    admin_id: int,
    now: datetime,
) -> RefreshSession | None:
    result = await db.execute(
        select(RefreshSession).where(
            RefreshSession.id == session_id,
            RefreshSession.admin_user_id == admin_id,
            RefreshSession.revoked_at.is_(None),
            RefreshSession.expires_at > now,
        )
    )
    return result.scalar_one_or_none()


async def purge_expired_refresh_sessions(
    db: AsyncSession,
    *,
    now: datetime,
) -> int:
    result = await db.execute(
        delete(RefreshSession).where(RefreshSession.expires_at <= now)
    )
    await db.commit()
    return int(result.rowcount or 0)
