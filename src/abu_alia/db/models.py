from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from abu_alia.db.session import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    favorites: Mapped[list["Favorite"]] = relationship(back_populates="user")


class Author(Base, TimestampMixin):
    __tablename__ = "authors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(500), nullable=False)
    name_normalized: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    biography: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    birth_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    death_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    death_year_ah: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    extra: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    aliases: Mapped[list["AuthorAlias"]] = relationship(back_populates="author", cascade="all, delete-orphan")
    contributions: Mapped[list["WorkContributor"]] = relationship(back_populates="author")


class AuthorAlias(Base):
    __tablename__ = "author_aliases"
    __table_args__ = (UniqueConstraint("alias_normalized", name="uq_author_alias_norm"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("authors.id", ondelete="CASCADE"), nullable=False)
    alias: Mapped[str] = mapped_column(String(500), nullable=False)
    alias_normalized: Mapped[str] = mapped_column(String(500), nullable=False)

    author: Mapped[Author] = relationship(back_populates="aliases")


class Publisher(Base, TimestampMixin):
    __tablename__ = "publishers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(400), nullable=False)
    name_normalized: Mapped[str] = mapped_column(String(400), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)


class Category(Base, TimestampMixin):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"), nullable=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    name_ar: Mapped[str] = mapped_column(String(300), nullable=False)
    name_normalized: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    path: Mapped[str] = mapped_column(String(800), nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    triggers: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    parent: Mapped[Optional["Category"]] = relationship(remote_side="Category.id")
    children: Mapped[list["Category"]] = relationship(back_populates="parent")


class License(Base):
    __tablename__ = "licenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name_ar: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    allows_redistribution: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allows_commercial: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    requires_attribution: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    requires_share_alike: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    non_commercial_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Work(Base, TimestampMixin):
    __tablename__ = "works"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(800), nullable=False)
    title_normalized: Mapped[str] = mapped_column(String(800), nullable=False, index=True)
    subtitle: Mapped[Optional[str]] = mapped_column(String(800), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(16), default="ar", nullable=False)
    slug: Mapped[str] = mapped_column(String(220), unique=True, nullable=False)
    publication_status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    download_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    extra: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    editions: Mapped[list["Edition"]] = relationship(back_populates="work")
    contributors: Mapped[list["WorkContributor"]] = relationship(back_populates="work")
    categories: Mapped[list["WorkCategory"]] = relationship(back_populates="work")
    covers: Mapped[list["Cover"]] = relationship(back_populates="work")
    tags: Mapped[list["WorkTag"]] = relationship(back_populates="work")


class WorkContributor(Base):
    __tablename__ = "work_contributors"
    __table_args__ = (UniqueConstraint("work_id", "author_id", "role", name="uq_work_author_role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_id: Mapped[int] = mapped_column(ForeignKey("works.id", ondelete="CASCADE"), nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("authors.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(40), default="author", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    work: Mapped[Work] = relationship(back_populates="contributors")
    author: Mapped[Author] = relationship(back_populates="contributions")


class Edition(Base, TimestampMixin):
    __tablename__ = "editions"
    __table_args__ = (
        UniqueConstraint("isbn13", name="uq_edition_isbn13"),
        Index("ix_edition_work", "work_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_id: Mapped[int] = mapped_column(ForeignKey("works.id", ondelete="RESTRICT"), nullable=False)
    publisher_id: Mapped[Optional[int]] = mapped_column(ForeignKey("publishers.id"), nullable=True)
    license_id: Mapped[Optional[int]] = mapped_column(ForeignKey("licenses.id"), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(800), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    isbn10: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    isbn13: Mapped[Optional[str]] = mapped_column(String(17), nullable=True)
    page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    edition_statement: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    volume_number: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    language: Mapped[str] = mapped_column(String(16), default="ar", nullable=False)
    attribution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    work: Mapped[Work] = relationship(back_populates="editions")
    publisher: Mapped[Optional[Publisher]] = relationship()
    license: Mapped[Optional[License]] = relationship()
    files: Mapped[list["FileAsset"]] = relationship(back_populates="edition")


class FileAsset(Base, TimestampMixin):
    __tablename__ = "files"
    __table_args__ = (UniqueConstraint("sha256", name="uq_file_sha256"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    edition_id: Mapped[int] = mapped_column(ForeignKey("editions.id", ondelete="RESTRICT"), nullable=False)
    source_item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("source_items.id"), nullable=True)
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mime: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    validation_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    withdrawn: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    edition: Mapped[Edition] = relationship(back_populates="files")


class WorkCategory(Base):
    __tablename__ = "work_categories"
    __table_args__ = (UniqueConstraint("work_id", "category_id", name="uq_work_category"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_id: Mapped[int] = mapped_column(ForeignKey("works.id", ondelete="CASCADE"), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    evidence: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    work: Mapped[Work] = relationship(back_populates="categories")
    category: Mapped[Category] = relationship()


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    name_normalized: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)


class WorkTag(Base):
    __tablename__ = "work_tags"
    __table_args__ = (UniqueConstraint("work_id", "tag_id", name="uq_work_tag"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_id: Mapped[int] = mapped_column(ForeignKey("works.id", ondelete="CASCADE"), nullable=False)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id"), nullable=False)

    work: Mapped[Work] = relationship(back_populates="tags")
    tag: Mapped[Tag] = relationship()


class Cover(Base, TimestampMixin):
    __tablename__ = "covers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_id: Mapped[int] = mapped_column(ForeignKey("works.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), default="generated", nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    mime: Mapped[str] = mapped_column(String(80), default="image/jpeg", nullable=False)

    work: Mapped[Work] = relationship(back_populates="covers")


class Collection(Base, TimestampMixin):
    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class CollectionWork(Base):
    __tablename__ = "collection_works"
    __table_args__ = (UniqueConstraint("collection_id", "work_id", name="uq_collection_work"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id", ondelete="CASCADE"))
    work_id: Mapped[int] = mapped_column(ForeignKey("works.id", ondelete="CASCADE"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Source(Base, TimestampMixin):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    homepage: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    source_type: Mapped[str] = mapped_column(String(80), default="repository", nullable=False)
    language: Mapped[str] = mapped_column(String(40), default="ar", nullable=False)
    useful_size: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    formats: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    has_pdf: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_epub: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_api: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_direct_download: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    crawling_method: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    pagination_method: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    rate_limits: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    robots_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    license_information: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    redistribution_status: Mapped[str] = mapped_column(String(40), default="uncertain", nullable=False)
    connector_status: Mapped[str] = mapped_column(String(40), default="planned", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reliability: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False)
    last_success_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_failure_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    items: Mapped[list["SourceItem"]] = relationship(back_populates="source")


class SourceItem(Base, TimestampMixin):
    __tablename__ = "source_items"
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_source_external"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(400), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(800), nullable=True)
    eligibility: Mapped[str] = mapped_column(String(40), default="uncertain", index=True)
    status: Mapped[str] = mapped_column(String(40), default="discovered", index=True)
    raw_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    license_evidence: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    work_id: Mapped[Optional[int]] = mapped_column(ForeignKey("works.id"), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    source: Mapped[Source] = relationship(back_populates="items")
    events: Mapped[list["ImportEvent"]] = relationship(back_populates="source_item")


class ImportEvent(Base):
    __tablename__ = "import_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_item_id: Mapped[int] = mapped_column(
        ForeignKey("source_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    source_item: Mapped[SourceItem] = relationship(back_populates="events")


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_claim", "status", "run_after", "priority"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    run_after: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    locked_by: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class ReviewItem(Base, TimestampMixin):
    __tablename__ = "review_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    reason: Mapped[str] = mapped_column(String(400), nullable=False)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    source_item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("source_items.id"), nullable=True)
    work_id: Mapped[Optional[int]] = mapped_column(ForeignKey("works.id"), nullable=True)
    resolved_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class DuplicateCandidate(Base, TimestampMixin):
    __tablename__ = "duplicate_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    left_work_id: Mapped[int] = mapped_column(ForeignKey("works.id"), nullable=False)
    right_work_id: Mapped[int] = mapped_column(ForeignKey("works.id"), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    decision: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    signals: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class Favorite(Base, TimestampMixin):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "work_id", name="uq_favorite"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    work_id: Mapped[int] = mapped_column(ForeignKey("works.id", ondelete="CASCADE"), nullable=False)

    user: Mapped[User] = relationship(back_populates="favorites")
    work: Mapped[Work] = relationship()


class ReadingProgress(Base, TimestampMixin):
    __tablename__ = "reading_progress"
    __table_args__ = (UniqueConstraint("user_id", "edition_id", "fmt", name="uq_progress"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    edition_id: Mapped[int] = mapped_column(ForeignKey("editions.id", ondelete="CASCADE"), nullable=False)
    fmt: Mapped[str] = mapped_column(String(16), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    percent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    ip: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)


class SearchDocument(Base):
    __tablename__ = "search_documents"

    work_id: Mapped[int] = mapped_column(ForeignKey("works.id", ondelete="CASCADE"), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    authors: Mapped[str] = mapped_column(Text, default="", nullable=False)
    categories: Mapped[str] = mapped_column(Text, default="", nullable=False)
    publisher: Mapped[str] = mapped_column(Text, default="", nullable=False)
    identifiers: Mapped[str] = mapped_column(Text, default="", nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
