from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Consultation(TimestampMixin, Base):
    __tablename__ = "consultations"
    __table_args__ = (
        UniqueConstraint("tracking_id", name="uq_consultations_tracking_id"),
        UniqueConstraint("idempotency_key", name="uq_consultations_idempotency_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tracking_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    assigned_to: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    public_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    assigned_admin = relationship("AdminUser", lazy="joined")
    status_history: Mapped[list["ConsultationStatusHistory"]] = relationship(
        "ConsultationStatusHistory",
        back_populates="consultation",
        cascade="all, delete-orphan",
        order_by="desc(ConsultationStatusHistory.created_at)",
    )


class ConsultationStatusHistory(Base):
    __tablename__ = "consultation_status_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    consultation_id: Mapped[int] = mapped_column(
        ForeignKey("consultations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    old_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    new_status: Mapped[str] = mapped_column(String(50), nullable=False)
    changed_by: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    consultation: Mapped[Consultation] = relationship("Consultation", back_populates="status_history")
    changed_by_admin = relationship("AdminUser", lazy="joined")
