from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.crud import admin as admin_crud
from app.models import AdminUser


def normalize_optional_name(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


async def create_or_update_admin(
    email: str,
    password: str,
    *,
    full_name: str | None = None,
    is_active: bool = True,
    role: str | None = "administrator",
    upsert: bool = False,
) -> AdminUser:
    normalized_email = email.strip().lower()

    if not normalized_email:
        raise SystemExit("Email is required.")

    if not password:
        raise SystemExit("Password is required.")

    normalized_full_name = normalize_optional_name(full_name)

    async with AsyncSessionLocal() as db:
        assigned_role = None
        if role:
            assigned_role = await admin_crud.get_role_by_code(db, role)
            if assigned_role is None:
                raise SystemExit(f"Role '{role}' was not found. Run the role seed script first.")

        existing_admin = await admin_crud.get_admin_by_email(
            db,
            normalized_email,
            include_access=True,
        )
        if existing_admin is not None:
            if not upsert:
                raise SystemExit(f"Admin user already exists for {normalized_email}.")

            existing_admin.full_name = normalized_full_name
            existing_admin.hashed_password = get_password_hash(password)
            existing_admin.is_active = is_active
            if assigned_role is not None:
                existing_admin.assigned_roles = [assigned_role]
            db.add(existing_admin)
            await db.commit()
            await db.refresh(existing_admin)
            return existing_admin

        admin = AdminUser(
            email=normalized_email,
            full_name=normalized_full_name,
            hashed_password=get_password_hash(password),
            is_active=is_active,
        )
        if assigned_role is not None:
            admin.assigned_roles = [assigned_role]
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
        return admin


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an Exxonim admin user.")
    parser.add_argument("--email", required=True, help="Admin email address.")
    parser.add_argument("--password", required=True, help="Admin password.")
    parser.add_argument("--full-name", dest="full_name", help="Optional display name.")
    parser.add_argument(
        "--inactive",
        action="store_true",
        help="Create the admin user in an inactive state.",
    )
    parser.add_argument(
        "--role",
        default="administrator",
        help="Role code to assign, for example superuser, administrator, editor, reviewer, or viewer.",
    )
    parser.add_argument(
        "--upsert",
        action="store_true",
        help="Create the admin if missing, or update the existing admin in place.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    admin = asyncio.run(
        create_or_update_admin(
            email=args.email,
            password=args.password,
            full_name=args.full_name,
            is_active=not args.inactive,
            role=args.role,
            upsert=args.upsert,
        )
    )
    print(f"Admin ready: {admin.email}")
