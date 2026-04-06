from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PrivacyConsentLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "privacy_consent_logs"
    __table_args__ = (
        Index("ix_privacy_consent_logs_identifier", "consent_identifier"),
        Index("ix_privacy_consent_logs_created_at", "created_at"),
        Index(
            "ix_privacy_consent_logs_identifier_created_at",
            "consent_identifier",
            "created_at",
        ),
    )

    consent_identifier: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_versions: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    category_choices: Mapped[dict[str, bool]] = mapped_column(JSONB, nullable=False)
    source_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class PrivacyRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "privacy_requests"
    __table_args__ = (
        CheckConstraint(
            "request_type IN ('access', 'correction', 'deletion')",
            name="ck_privacy_requests_request_type",
        ),
        CheckConstraint(
            "status IN ('received', 'verifying', 'in_progress', 'completed', 'rejected')",
            name="ck_privacy_requests_status",
        ),
        Index("ix_privacy_requests_customer_id", "customer_id"),
        Index("ix_privacy_requests_created_by_admin_id", "created_by_admin_id"),
        Index("ix_privacy_requests_completed_by_admin_id", "completed_by_admin_id"),
        Index("ix_privacy_requests_status", "status"),
        Index("ix_privacy_requests_request_type", "request_type"),
        Index("ix_privacy_requests_requester_email", "requester_email"),
    )

    customer_id: Mapped[PGUUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
    )
    request_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="received")
    requester_name: Mapped[str] = mapped_column(String(255), nullable=False)
    requester_email: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    internal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_admin_id: Mapped[int] = mapped_column(
        ForeignKey("admin_users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    completed_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer = relationship("Customer", lazy="joined")
    created_by_admin = relationship(
        "AdminUser",
        foreign_keys=[created_by_admin_id],
        lazy="joined",
    )
    completed_by_admin = relationship(
        "AdminUser",
        foreign_keys=[completed_by_admin_id],
        lazy="joined",
    )
