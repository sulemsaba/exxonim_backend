from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.workflow import ContentWorkflowStatus


class BlogAuthor(Base):
    __tablename__ = "blog_authors"
    __table_args__ = (UniqueConstraint("slug", name="uq_blog_authors_slug"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    avatar_src: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    posts = relationship("BlogPost", back_populates="author")


class BlogCategory(Base):
    __tablename__ = "blog_categories"
    __table_args__ = (
        UniqueConstraint("name", name="uq_blog_categories_name"),
        UniqueConstraint("slug", name="uq_blog_categories_slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    posts = relationship("BlogPost", back_populates="category")


class BlogPost(TimestampMixin, Base):
    __tablename__ = "blog_posts"
    __table_args__ = (UniqueConstraint("slug", name="uq_blog_posts_slug"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    category_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("blog_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    author_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("blog_authors.id", ondelete="SET NULL"),
        nullable=True,
    )
    featured_image: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cover_alt: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    media_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    featured_slot: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    featured_on_home: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_time_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    related_slugs: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)
    meta_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    meta_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        default=ContentWorkflowStatus.DRAFT.value,
        nullable=False,
        index=True,
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    updated_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    published_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    category = relationship("BlogCategory", back_populates="posts")
    author = relationship("BlogAuthor", back_populates="posts")
