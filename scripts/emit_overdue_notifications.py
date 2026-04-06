from __future__ import annotations

import asyncio

from app.core.database import AsyncSessionLocal
from app.crud import notification as notification_crud


async def main() -> int:
    async with AsyncSessionLocal() as db:
        emitted = await notification_crud.emit_overdue_notifications(db)
        await db.commit()
        print(f"Emitted {emitted} overdue notification(s).")
        return emitted


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
