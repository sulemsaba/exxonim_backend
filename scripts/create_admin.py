from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.crud import admin as admin_crud
from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.models import AdminUser


async def create_admin(email: str, password: str, is_active: bool = True) -> None:
    normalized_email = email.strip().lower()

    async with AsyncSessionLocal() as db:
        existing_admin = await admin_crud.get_admin_by_email(db, normalized_email)
        if existing_admin is not None:
            raise SystemExit(f"Admin user already exists for {normalized_email}.")

        admin = AdminUser(
            email=normalized_email,
            hashed_password=get_password_hash(password),
            is_active=is_active,
        )
        db.add(admin)
        await db.commit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an Exxonim admin user.")
    parser.add_argument("--email", required=True, help="Admin email address.")
    parser.add_argument("--password", required=True, help="Admin password.")
    parser.add_argument(
        "--inactive",
        action="store_true",
        help="Create the admin user in an inactive state.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(
        create_admin(
            email=args.email,
            password=args.password,
            is_active=not args.inactive,
        )
    )
