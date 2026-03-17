from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.models import AdminUser


async def get_admin_by_email(db: AsyncSession, email: str) -> AdminUser | None:
    result = await db.execute(
        select(AdminUser).where(AdminUser.email == email.strip().lower())
    )
    return result.scalar_one_or_none()


async def get_admin_by_id(db: AsyncSession, admin_id: int) -> AdminUser | None:
    result = await db.execute(select(AdminUser).where(AdminUser.id == admin_id))
    return result.scalar_one_or_none()


async def authenticate_admin(
    db: AsyncSession,
    *,
    email: str,
    password: str,
) -> AdminUser | None:
    admin = await get_admin_by_email(db, email)
    if admin is None or not admin.is_active:
        return None
    if not verify_password(password, admin.hashed_password):
        return None
    return admin
