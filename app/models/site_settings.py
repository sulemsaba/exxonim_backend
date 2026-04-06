from typing import Any, Dict

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SiteSetting(TimestampMixin, Base):
    __tablename__ = "site_settings"
    __table_args__ = (UniqueConstraint("key", name="uq_site_settings_key"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    value: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
