from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import NavigationItem
from app.schemas.navigation import NavigationItemCreate, NavigationItemUpdate


def serialize_navigation_item(
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
            serialize_navigation_item(child, children_map)
            for child in children_map.get(item.id, [])
        ],
    }


async def get_navigation_tree(
    db: AsyncSession,
    *,
    active_only: bool | None = True,
) -> list[dict[str, Any]]:
    statement = select(NavigationItem).order_by(
        NavigationItem.order.asc(),
        NavigationItem.id.asc(),
    )
    if active_only is True:
        statement = statement.where(NavigationItem.is_active.is_(True))
    elif active_only is False:
        statement = statement.where(NavigationItem.is_active.is_(False))

    result = await db.execute(statement)
    items = list(result.scalars().all())

    children_map: dict[int | None, list[NavigationItem]] = defaultdict(list)
    for item in items:
        children_map[item.parent_id].append(item)
    return [
        serialize_navigation_item(item, children_map)
        for item in children_map.get(None, [])
    ]


async def get_active_navigation(db: AsyncSession) -> list[dict[str, Any]]:
    return await get_navigation_tree(db, active_only=True)


async def get_navigation_item_by_id(
    db: AsyncSession,
    item_id: int,
) -> NavigationItem | None:
    result = await db.execute(
        select(NavigationItem).where(NavigationItem.id == item_id)
    )
    return result.scalar_one_or_none()


def build_navigation_item(payload: NavigationItemCreate) -> NavigationItem:
    return NavigationItem(**payload.model_dump())


def apply_navigation_item_update(
    item: NavigationItem,
    payload: NavigationItemUpdate,
) -> NavigationItem:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    return item
