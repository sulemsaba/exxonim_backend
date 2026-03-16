from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class NavigationItem(TimestampMixin, Base):
    __tablename__ = "navigation_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(String(50), default="link", nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("navigation_items.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    order: Mapped[int] = mapped_column("order", Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    parent: Mapped[NavigationItem | None] = relationship(
        "NavigationItem",
        remote_side="NavigationItem.id",
        back_populates="children",
    )
    children: Mapped[list[NavigationItem]] = relationship(
        "NavigationItem",
        back_populates="parent",
        cascade="all, delete-orphan",
        order_by="NavigationItem.order",
    )
