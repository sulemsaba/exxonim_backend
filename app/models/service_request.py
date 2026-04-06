from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ServiceType(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "service_types"
    __table_args__ = (UniqueConstraint("code", name="uq_service_types_code"),)

    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    service_requests = relationship("ServiceRequest", back_populates="service_type", lazy="selectin")


class ServiceRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "service_requests"
    __table_args__ = (
        UniqueConstraint("tracking_id", name="uq_service_requests_tracking_id"),
        UniqueConstraint("legacy_consultation_id", name="uq_service_requests_legacy_consultation_id"),
        CheckConstraint(
            "status IN ('new', 'triaged', 'waiting_customer', 'in_progress', 'completed', 'cancelled')",
            name="ck_service_requests_status",
        ),
        CheckConstraint(
            "priority IN ('low', 'normal', 'high', 'urgent')",
            name="ck_service_requests_priority",
        ),
        CheckConstraint(
            "source_channel IN ('public_consultation_form', 'public_contact_form', 'admin_created', 'migration_legacy')",
            name="ck_service_requests_source_channel",
        ),
        CheckConstraint(
            "(status NOT IN ('completed', 'cancelled')) OR closed_at IS NOT NULL",
            name="ck_service_requests_closed_status",
        ),
        Index("ix_service_requests_customer_id", "customer_id"),
        Index("ix_service_requests_service_type_id", "service_type_id"),
        Index("ix_service_requests_status", "status"),
        Index("ix_service_requests_priority", "priority"),
        Index("ix_service_requests_opened_at", "opened_at"),
        Index("ix_service_requests_closed_at", "closed_at"),
        Index("ix_service_requests_last_activity_at", "last_activity_at"),
        Index("ix_service_requests_last_customer_message_at", "last_customer_message_at"),
        Index("ix_service_requests_legacy_consultation_id", "legacy_consultation_id"),
        Index(
            "ix_service_requests_status_priority_opened_at",
            "status",
            "priority",
            text("opened_at DESC"),
        ),
        Index(
            "ix_service_requests_status_priority_last_activity_at",
            "status",
            "priority",
            text("last_activity_at DESC"),
        ),
    )

    customer_id: Mapped[PGUUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    tracking_id: Mapped[str] = mapped_column(String(64), nullable=False)
    legacy_consultation_id: Mapped[int | None] = mapped_column(
        ForeignKey("consultations.id", ondelete="SET NULL"),
        nullable=True,
    )
    service_type_id: Mapped[PGUUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("service_types.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    intake_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_channel: Mapped[str] = mapped_column(String(64), nullable=False, default="migration_legacy")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="new")
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_customer_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    target_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    customer = relationship("Customer", back_populates="service_requests", lazy="joined")
    service_type = relationship("ServiceType", back_populates="service_requests", lazy="joined")
    created_by_admin = relationship("AdminUser", lazy="joined")
    status_history = relationship(
        "ServiceRequestStatusHistory",
        back_populates="service_request",
        cascade="all, delete-orphan",
        order_by="desc(ServiceRequestStatusHistory.created_at)",
        lazy="selectin",
    )
    assignments = relationship(
        "ServiceRequestAssignment",
        back_populates="service_request",
        cascade="all, delete-orphan",
        order_by="desc(ServiceRequestAssignment.assigned_at)",
        lazy="selectin",
    )
    threads = relationship(
        "InboxThread",
        back_populates="service_request",
        cascade="all, delete-orphan",
        order_by="InboxThread.created_at",
        lazy="selectin",
    )
    inbox_states = relationship(
        "ServiceRequestInboxState",
        back_populates="service_request",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    notes = relationship(
        "RecordNote",
        back_populates="service_request",
        cascade="all, delete-orphan",
        order_by="desc(RecordNote.created_at)",
        lazy="selectin",
    )
    documents = relationship(
        "RecordDocument",
        back_populates="service_request",
        cascade="all, delete-orphan",
        order_by="desc(RecordDocument.created_at)",
        lazy="selectin",
    )


class ServiceRequestStatusHistory(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "service_request_status_history"
    __table_args__ = (
        CheckConstraint(
            "new_status IN ('new', 'triaged', 'waiting_customer', 'in_progress', 'completed', 'cancelled')",
            name="ck_service_request_status_history_new_status",
        ),
        CheckConstraint(
            "old_status IS NULL OR old_status IN ('new', 'triaged', 'waiting_customer', 'in_progress', 'completed', 'cancelled')",
            name="ck_service_request_status_history_old_status",
        ),
        Index("ix_service_request_status_history_service_request_id", "service_request_id"),
        Index("ix_service_request_status_history_created_at", "created_at"),
        Index(
            "ix_service_request_status_history_request_created_at",
            "service_request_id",
            "created_at",
        ),
    )

    service_request_id: Mapped[PGUUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("service_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    old_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_status: Mapped[str] = mapped_column(String(32), nullable=False)
    changed_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    service_request = relationship("ServiceRequest", back_populates="status_history")
    changed_by_admin = relationship("AdminUser", lazy="joined")


class ServiceRequestAssignment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "service_request_assignments"
    __table_args__ = (
        CheckConstraint(
            "assignment_role IN ('lead', 'collaborator')",
            name="ck_service_request_assignments_role",
        ),
        CheckConstraint(
            "unassigned_at IS NULL OR unassigned_at >= assigned_at",
            name="ck_service_request_assignments_unassigned_at",
        ),
        Index("ix_service_request_assignments_service_request_id", "service_request_id"),
        Index("ix_service_request_assignments_admin_user_id", "admin_user_id"),
        Index(
            "ix_service_request_assignments_active",
            "service_request_id",
            "admin_user_id",
            postgresql_where=text("unassigned_at IS NULL"),
        ),
        Index(
            "uq_service_request_assignments_active_lead",
            "service_request_id",
            unique=True,
            postgresql_where=text("assignment_role = 'lead' AND unassigned_at IS NULL"),
        ),
    )

    service_request_id: Mapped[PGUUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("service_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    admin_user_id: Mapped[int] = mapped_column(
        ForeignKey("admin_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    assignment_role: Mapped[str] = mapped_column(String(32), nullable=False, default="collaborator")
    assigned_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    unassigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    service_request = relationship("ServiceRequest", back_populates="assignments")
    admin_user = relationship("AdminUser", foreign_keys=[admin_user_id], lazy="joined")
    assigned_by_admin = relationship("AdminUser", foreign_keys=[assigned_by_admin_id], lazy="joined")


class InboxThread(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "inbox_threads"
    __table_args__ = (
        CheckConstraint(
            "thread_kind IN ('primary')",
            name="ck_inbox_threads_thread_kind",
        ),
        UniqueConstraint("service_request_id", "thread_kind", name="uq_inbox_threads_request_kind"),
        Index("ix_inbox_threads_service_request_id", "service_request_id"),
    )

    service_request_id: Mapped[PGUUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("service_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    thread_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="primary")
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    service_request = relationship("ServiceRequest", back_populates="threads")
    messages = relationship(
        "InboxMessage",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="InboxMessage.created_at",
        lazy="selectin",
    )


class InboxMessage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "inbox_messages"
    __table_args__ = (
        CheckConstraint(
            "direction IN ('inbound', 'outbound', 'internal')",
            name="ck_inbox_messages_direction",
        ),
        CheckConstraint(
            "channel IN ('web_form', 'admin_manual', 'system_seed')",
            name="ck_inbox_messages_channel",
        ),
        Index("ix_inbox_messages_thread_id", "thread_id"),
        Index("ix_inbox_messages_thread_created_at", "thread_id", "created_at"),
    )

    thread_id: Mapped[PGUUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("inbox_threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    direction: Mapped[str] = mapped_column(String(32), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    customer_author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_author_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    thread = relationship("InboxThread", back_populates="messages")
    author_admin = relationship("AdminUser", lazy="joined")


class ServiceRequestInboxState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "service_request_inbox_states"
    __table_args__ = (
        UniqueConstraint(
            "service_request_id",
            "admin_user_id",
            name="uq_service_request_inbox_states_request_admin",
        ),
        Index("ix_service_request_inbox_states_service_request_id", "service_request_id"),
        Index("ix_service_request_inbox_states_admin_user_id", "admin_user_id"),
        Index(
            "ix_service_request_inbox_states_admin_updated_at",
            "admin_user_id",
            text("updated_at DESC"),
        ),
    )

    service_request_id: Mapped[PGUUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("service_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    admin_user_id: Mapped[int] = mapped_column(
        ForeignKey("admin_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    last_read_message_id: Mapped[PGUUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("inbox_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    service_request = relationship("ServiceRequest", back_populates="inbox_states")
    admin_user = relationship("AdminUser", lazy="joined")
    last_read_message = relationship("InboxMessage", foreign_keys=[last_read_message_id], lazy="joined")


class RecordNote(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "notes"
    __table_args__ = (
        CheckConstraint(
            "visibility IN ('internal', 'customer_safe')",
            name="ck_notes_visibility",
        ),
        CheckConstraint(
            "(customer_id IS NOT NULL) <> (service_request_id IS NOT NULL)",
            name="ck_notes_exactly_one_target",
        ),
        Index("ix_notes_customer_id", "customer_id"),
        Index("ix_notes_service_request_id", "service_request_id"),
        Index("ix_notes_created_at", "created_at"),
    )

    customer_id: Mapped[PGUUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=True,
    )
    service_request_id: Mapped[PGUUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("service_requests.id", ondelete="CASCADE"),
        nullable=True,
    )
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="internal")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_admin_id: Mapped[int] = mapped_column(
        ForeignKey("admin_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    customer = relationship("Customer", back_populates="notes")
    service_request = relationship("ServiceRequest", back_populates="notes")
    created_by_admin = relationship("AdminUser", lazy="joined")


class RecordDocument(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("storage_key", name="uq_documents_storage_key"),
        CheckConstraint(
            "classification IN ('customer_upload', 'internal_attachment', 'generated_document', 'compliance_proof')",
            name="ck_documents_classification",
        ),
        CheckConstraint(
            "(customer_id IS NOT NULL) <> (service_request_id IS NOT NULL)",
            name="ck_documents_exactly_one_target",
        ),
        CheckConstraint("file_size > 0", name="ck_documents_file_size"),
        Index("ix_documents_customer_id", "customer_id"),
        Index("ix_documents_service_request_id", "service_request_id"),
        Index("ix_documents_classification", "classification"),
        Index("ix_documents_created_at", "created_at"),
    )

    customer_id: Mapped[PGUUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=True,
    )
    service_request_id: Mapped[PGUUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("service_requests.id", ondelete="CASCADE"),
        nullable=True,
    )
    classification: Mapped[str] = mapped_column(String(32), nullable=False, default="internal_attachment")
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uploaded_by_admin_id: Mapped[int] = mapped_column(
        ForeignKey("admin_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    customer = relationship("Customer", back_populates="documents")
    service_request = relationship("ServiceRequest", back_populates="documents")
    uploaded_by_admin = relationship("AdminUser", lazy="joined")
