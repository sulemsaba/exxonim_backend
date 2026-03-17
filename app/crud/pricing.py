from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PricingPlan
from app.schemas.pricing import PricingPlanCreate, PricingPlanUpdate


async def get_active_pricing_plans(db: AsyncSession) -> list[PricingPlan]:
    result = await db.execute(
        select(PricingPlan)
        .where(PricingPlan.is_active.is_(True))
        .order_by(PricingPlan.sort_order.asc(), PricingPlan.id.asc())
    )
    return list(result.scalars().all())


async def get_all_pricing_plans(db: AsyncSession) -> list[PricingPlan]:
    result = await db.execute(
        select(PricingPlan).order_by(PricingPlan.sort_order.asc(), PricingPlan.id.asc())
    )
    return list(result.scalars().all())


async def get_pricing_plan_by_id(
    db: AsyncSession,
    plan_id: int,
) -> PricingPlan | None:
    result = await db.execute(select(PricingPlan).where(PricingPlan.id == plan_id))
    return result.scalar_one_or_none()


def build_pricing_plan(payload: PricingPlanCreate) -> PricingPlan:
    return PricingPlan(**payload.model_dump())


def apply_pricing_plan_update(
    plan: PricingPlan,
    payload: PricingPlanUpdate,
) -> PricingPlan:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(plan, field, value)
    return plan
