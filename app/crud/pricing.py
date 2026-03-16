from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PricingPlan


async def get_active_pricing_plans(db: AsyncSession) -> list[PricingPlan]:
    result = await db.execute(
        select(PricingPlan)
        .where(PricingPlan.is_active.is_(True))
        .order_by(PricingPlan.sort_order.asc(), PricingPlan.id.asc())
    )
    return list(result.scalars().all())
