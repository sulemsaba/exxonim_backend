from __future__ import annotations

from sqlalchemy import CheckConstraint, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Customer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint(
            "customer_kind IN ('individual', 'organization')",
            name="ck_customers_customer_kind",
        ),
        CheckConstraint(
            "source IN ('public_consultation_form', 'public_contact_form', 'admin_created', 'migration_legacy')",
            name="ck_customers_source",
        ),
        Index("ix_customers_normalized_email", "normalized_email"),
        Index("ix_customers_normalized_phone", "normalized_phone"),
        Index("ix_customers_company_name", "company_name"),
        Index("ix_customers_created_at", "created_at"),
    )

    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    primary_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    primary_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    normalized_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="individual")
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="migration_legacy")

    service_requests = relationship(
        "ServiceRequest",
        back_populates="customer",
        lazy="selectin",
    )
    notes = relationship("RecordNote", back_populates="customer", lazy="selectin")
    documents = relationship("RecordDocument", back_populates="customer", lazy="selectin")
