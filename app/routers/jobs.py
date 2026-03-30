from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import job as job_crud
from app.core.database import get_db
from app.schemas import JobOut

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/", response_model=list[JobOut])
async def list_jobs(db: AsyncSession = Depends(get_db)) -> list[JobOut]:
    return await job_crud.get_published_jobs(db)


@router.get("/{slug}", response_model=JobOut)
async def get_job(slug: str, db: AsyncSession = Depends(get_db)) -> JobOut:
    job = await job_crud.get_job_by_slug(db, slug, published_only=True)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
