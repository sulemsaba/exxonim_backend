from __future__ import annotations

from datetime import datetime

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


class BlogAuthor(Base):
    __tablename__ = "blog_authors"
    __table_args__ = (UniqueConstraint("slug", name="uq_blog_authors_slug"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str | None] = mapped_column(String(150), nullable=True)
    avatar_src: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    posts: Mapped[list[BlogPost]] = relationship("BlogPost", back_populates="author")


class BlogCategory(Base):
    __tablename__ = "blog_categories"
    __table_args__ = (
        UniqueConstraint("name", name="uq_blog_categories_name"),
        UniqueConstraint("slug", name="uq_blog_categories_slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    posts: Mapped[list[BlogPost]] = relationship("BlogPost", back_populates="category")


class BlogPost(TimestampMixin, Base):
    __tablename__ = "blog_posts"
    __table_args__ = (UniqueConstraint("slug", name="uq_blog_posts_slug"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("blog_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    author_id: Mapped[int | None] = mapped_column(
        ForeignKey("blog_authors.id", ondelete="SET NULL"),
        nullable=True,
    )
    featured_image: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_alt: Mapped[str | None] = mapped_column(String(255), nullable=True)
    media_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    featured_slot: Mapped[str | None] = mapped_column(String(50), nullable=True)
    featured_on_home: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    related_slugs: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    meta_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    category: Mapped[BlogCategory | None] = relationship("BlogCategory", back_populates="posts")
    author: Mapped[BlogAuthor | None] = relationship("BlogAuthor", back_populates="posts")
