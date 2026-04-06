from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Role(TimestampMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("code", name="uq_roles_code"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    assigned_users = relationship(
        "AdminUser",
        secondary="user_roles",
        back_populates="assigned_roles",
        lazy="selectin",
    )
    granted_permissions = relationship(
        "Permission",
        secondary="role_permissions",
        back_populates="granted_roles",
        lazy="selectin",
    )

    @property
    def permissions(self) -> list[str]:
        return sorted(permission.code for permission in self.granted_permissions)


class Permission(TimestampMixin, Base):
    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("code", name="uq_permissions_code"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    granted_roles = relationship(
        "Role",
        secondary="role_permissions",
        back_populates="granted_permissions",
        lazy="selectin",
    )


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("admin_users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    target_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    old_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    actor = relationship("AdminUser", back_populates="audit_logs", lazy="selectin")


class RefreshSession(Base):
    __tablename__ = "admin_refresh_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    admin_user_id: Mapped[int] = mapped_column(
        ForeignKey("admin_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    csrf_token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    admin = relationship("AdminUser", back_populates="refresh_sessions", lazy="selectin")


class AdminNotification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "admin_notifications"
    __table_args__ = (
        CheckConstraint(
            "category IN ('request_ops', 'content_review', 'security', 'reporting', 'system')",
            name="ck_admin_notifications_category",
        ),
        CheckConstraint(
            "severity IN ('info', 'success', 'warning', 'error')",
            name="ck_admin_notifications_severity",
        ),
        CheckConstraint(
            "event_type IN ("
            "'request.submitted', "
            "'request.inbound_message', "
            "'request.assigned', "
            "'request.overdue', "
            "'content.pending_review', "
            "'security.suspicious_login', "
            "'security.admin_role_changed', "
            "'security.admin_status_changed', "
            "'report.generated'"
            ")",
            name="ck_admin_notifications_event_type",
        ),
        Index(
            "ix_admin_notifications_recipient_unread_last_occurred",
            "recipient_admin_id",
            "is_read",
            text("last_occurred_at DESC"),
        ),
        Index(
            "ix_admin_notifications_recipient_category_last_occurred",
            "recipient_admin_id",
            "category",
            text("last_occurred_at DESC"),
        ),
        Index(
            "uq_admin_notifications_active_dedupe",
            "recipient_admin_id",
            "dedupe_key",
            unique=True,
            postgresql_where=text("dedupe_key IS NOT NULL AND is_read = false"),
        ),
    )

    recipient_admin_id: Mapped[int] = mapped_column(
        ForeignKey("admin_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    href: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resource_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    dedupe_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    recipient_admin = relationship(
        "AdminUser",
        foreign_keys=[recipient_admin_id],
        back_populates="notifications",
        lazy="joined",
    )
    actor_admin = relationship(
        "AdminUser",
        foreign_keys=[actor_admin_id],
        back_populates="triggered_notifications",
        lazy="joined",
    )


class AdminNotificationPreference(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "admin_notification_preferences"
    __table_args__ = (
        CheckConstraint(
            "category IN ('request_ops', 'content_review', 'security', 'reporting', 'system')",
            name="ck_admin_notification_preferences_category",
        ),
        UniqueConstraint(
            "admin_user_id",
            "category",
            name="uq_admin_notification_preferences_admin_category",
        ),
    )

    admin_user_id: Mapped[int] = mapped_column(
        ForeignKey("admin_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    admin = relationship(
        "AdminUser",
        back_populates="notification_preferences",
        lazy="joined",
    )
