from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import NavigationItem


async def get_active_navigation(db: AsyncSession) -> list[NavigationItem]:
    result = await db.execute(
        select(NavigationItem)
        .where(NavigationItem.is_active.is_(True))
        .order_by(NavigationItem.order.asc(), NavigationItem.id.asc())
    )
    items = list(result.scalars().all())

    children_map: dict[int | None, list[NavigationItem]] = defaultdict(list)
    for item in items:
        item.children = []
        children_map[item.parent_id].append(item)

    for item in items:
        item.children = children_map.get(item.id, [])

    return children_map.get(None, [])
