from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class CareerJob(TimestampMixin, Base):
    __tablename__ = "career_jobs"
    __table_args__ = (UniqueConstraint("slug", name="uq_career_jobs_slug"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    department: Mapped[str] = mapped_column(String(150), nullable=False)
    employment_type: Mapped[str] = mapped_column(String(80), nullable=False)
    location_mode: Mapped[str] = mapped_column(String(80), nullable=False)
    city: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    country: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    compensation_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    experience_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    requirements: Mapped[List[str]] = mapped_column(JSONB, nullable=False, default=list)
    responsibilities: Mapped[List[str]] = mapped_column(JSONB, nullable=False, default=list)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
