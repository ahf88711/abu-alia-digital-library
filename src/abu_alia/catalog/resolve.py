from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from abu_alia.arabic.normalize import normalize_search, slugify_ar
from abu_alia.db.models import Author, AuthorAlias, Publisher, Work


def unique_slug(session: Session, model, base: str) -> str:
    slug = slugify_ar(base) or "item"
    n = 2
    candidate = slug
    while session.execute(select(model.id).where(model.slug == candidate)).scalar_one_or_none():
        candidate = f"{slug}-{n}"
        n += 1
        if n > 500:
            raise RuntimeError("slug collision overflow")
    return candidate


def resolve_author(session: Session, name: str, *, death_year_ah: Optional[int] = None) -> Author:
    display = (name or "").strip() or "مؤلف غير معروف"
    norm = normalize_search(display)
    alias = session.execute(
        select(AuthorAlias).where(AuthorAlias.alias_normalized == norm)
    ).scalar_one_or_none()
    if alias:
        return alias.author
    author = session.execute(select(Author).where(Author.name_normalized == norm)).scalar_one_or_none()
    if author:
        return author
    author = Author(
        canonical_name=display,
        name_normalized=norm,
        slug=unique_slug(session, Author, display),
        death_year_ah=death_year_ah,
    )
    session.add(author)
    session.flush()
    session.add(AuthorAlias(author_id=author.id, alias=display, alias_normalized=norm))
    session.flush()
    return author


def resolve_publisher(session: Session, name: Optional[str]) -> Optional[Publisher]:
    if not name or not name.strip():
        return None
    display = name.strip()
    norm = normalize_search(display)
    pub = session.execute(select(Publisher).where(Publisher.name_normalized == norm)).scalar_one_or_none()
    if pub:
        return pub
    pub = Publisher(
        name=display,
        name_normalized=norm,
        slug=unique_slug(session, Publisher, display),
    )
    session.add(pub)
    session.flush()
    return pub


def find_work_by_title_author(session: Session, title_norm: str, author_norm: str) -> Optional[Work]:
    from abu_alia.db.models import WorkContributor

    stmt = (
        select(Work)
        .join(WorkContributor, WorkContributor.work_id == Work.id)
        .join(Author, Author.id == WorkContributor.author_id)
        .where(Work.title_normalized == title_norm)
        .where(Author.name_normalized == author_norm)
        .where(WorkContributor.role == "author")
    )
    return session.execute(stmt).scalars().first()
