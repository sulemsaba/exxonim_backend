from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import testimonial as testimonial_crud
from app.core.database import get_db
from app.schemas import TestimonialOut

router = APIRouter(prefix="/testimonials", tags=["testimonials"])


@router.get("/", response_model=list[TestimonialOut])
async def list_testimonials(db: AsyncSession = Depends(get_db)) -> list[TestimonialOut]:
    return await testimonial_crud.get_active_testimonials(db)
