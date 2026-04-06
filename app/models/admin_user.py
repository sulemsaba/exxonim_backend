from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.rbac import resolve_primary_role, sort_role_codes
from app.models.base import Base, TimestampMixin


class AdminUser(TimestampMixin, Base):
    __tablename__ = "admin_users"
    __table_args__ = (UniqueConstraint("email", name="uq_admin_users_email"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    assigned_roles = relationship(
        "Role",
        secondary="user_roles",
        back_populates="assigned_users",
        lazy="selectin",
    )
    audit_logs = relationship("AuditLog", back_populates="actor", lazy="selectin")
    refresh_sessions = relationship(
        "RefreshSession",
        back_populates="admin",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    notifications = relationship(
        "AdminNotification",
        foreign_keys="AdminNotification.recipient_admin_id",
        back_populates="recipient_admin",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    notification_preferences = relationship(
        "AdminNotificationPreference",
        back_populates="admin",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    triggered_notifications = relationship(
        "AdminNotification",
        foreign_keys="AdminNotification.actor_admin_id",
        back_populates="actor_admin",
        lazy="selectin",
    )

    @property
    def roles(self) -> list[str]:
        return sort_role_codes(role.code for role in self.assigned_roles)

    @property
    def role(self) -> str | None:
        return resolve_primary_role(self.roles)

    @property
    def permissions(self) -> list[str]:
        permission_codes = {
            permission.code
            for role in self.assigned_roles
            for permission in role.granted_permissions
        }
        return sorted(permission_codes)
