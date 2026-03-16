from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import NavigationItem


def _serialize_node(
    item: NavigationItem, children_map: dict[int | None, list[NavigationItem]]
) -> dict[str, Any]:
    return {
        "id": item.id,
        "title": item.title,
        "url": item.url,
        "description": item.description,
        "kind": item.kind,
        "order": item.order,
        "is_active": item.is_active,
        "parent_id": item.parent_id,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "children": [
            _serialize_node(child, children_map)
            for child in children_map.get(item.id, [])
        ],
    }


async def get_active_navigation(db: AsyncSession) -> list[dict[str, Any]]:
    result = await db.execute(
        select(NavigationItem)
        .where(NavigationItem.is_active.is_(True))
        .order_by(NavigationItem.order.asc(), NavigationItem.id.asc())
    )
    items = list(result.scalars().all())

    children_map: dict[int | None, list[NavigationItem]] = defaultdict(list)
    for item in items:
        children_map[item.parent_id].append(item)
    return [
        _serialize_node(item, children_map)
        for item in children_map.get(None, [])
    ]
