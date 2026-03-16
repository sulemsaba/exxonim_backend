from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import pricing as pricing_crud
from app.core.database import get_db
from app.schemas import PricingPlanOut

router = APIRouter(prefix="/pricing", tags=["pricing"])


@router.get("/plans", response_model=list[PricingPlanOut])
async def list_pricing_plans(db: AsyncSession = Depends(get_db)) -> list[PricingPlanOut]:
    return await pricing_crud.get_active_pricing_plans(db)
