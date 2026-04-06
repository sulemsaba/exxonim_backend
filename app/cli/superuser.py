from __future__ import annotations

import argparse
import asyncio
import os

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.crud import admin as admin_crud
from app.models import AdminUser, Role


async def has_superuser(db) -> bool:
    result = await db.execute(
        select(AdminUser.id)
        .join(AdminUser.assigned_roles)
        .where(Role.code == "superuser")
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def create_superuser(
    email: str,
    password: str,
    *,
    full_name: str | None = None,
    force: bool = False,
    is_active: bool = True,
) -> AdminUser:
    normalized_email = email.strip().lower()

    if not normalized_email:
        raise SystemExit("Email is required.")

    if not password:
        raise SystemExit("Password is required.")

    async with AsyncSessionLocal() as db:
        existing_admin = await admin_crud.get_admin_by_email(
            db,
            normalized_email,
            include_access=True,
        )
        if existing_admin is not None:
            raise SystemExit(f"Admin user already exists for {normalized_email}.")

        if not force and await has_superuser(db):
            raise SystemExit(
                "A superuser already exists. Re-run with --force if you really need another one."
            )

        superuser_role = await admin_crud.get_role_by_code(db, "superuser")
        if superuser_role is None:
            raise SystemExit("Role 'superuser' was not found. Run the role seed script first.")

        admin = AdminUser(
            email=normalized_email,
            full_name=full_name.strip() or None if isinstance(full_name, str) else None,
            hashed_password=get_password_hash(password),
            is_active=is_active,
        )
        admin.assigned_roles = [superuser_role]
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
        return admin


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an Exxonim superuser.")
    parser.add_argument("--email", help="Superuser email address.")
    parser.add_argument("--password", help="Superuser password.")
    parser.add_argument("--full-name", dest="full_name", help="Optional display name.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow creation even if another superuser already exists.",
    )
    parser.add_argument(
        "--inactive",
        action="store_true",
        help="Create the superuser in an inactive state.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    email = args.email or os.getenv("EXXONIM_SUPERUSER_EMAIL")
    password = args.password or os.getenv("EXXONIM_SUPERUSER_PASSWORD")
    full_name = args.full_name or os.getenv("EXXONIM_SUPERUSER_FULL_NAME")

    admin = await create_superuser(
        email=email or "",
        password=password or "",
        full_name=full_name,
        force=args.force,
        is_active=not args.inactive,
    )
    print(f"Created superuser: {admin.email}")


if __name__ == "__main__":
    asyncio.run(main())
