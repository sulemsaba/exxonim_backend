from __future__ import annotations

import asyncio

from app.core.database import AsyncSessionLocal
from app.core.security import utcnow
from app.crud import admin as admin_crud


async def main() -> None:
    async with AsyncSessionLocal() as db:
        deleted = await admin_crud.purge_expired_refresh_sessions(db, now=utcnow())
    print(f"Deleted {deleted} expired refresh session(s).")


if __name__ == "__main__":
    asyncio.run(main())
