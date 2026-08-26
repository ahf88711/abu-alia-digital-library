from __future__ import annotations

from typing import List, Optional, Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from abu_alia.classification.integrity import nonempty_categories, rolled_counts
from abu_alia.db.models import Category, Cover, Edition, FileAsset, Work, WorkCategory, WorkContributor


def work_query(db: Session):
    return (
        select(Work)
        .where(Work.publication_status == "published")
        .options(
            selectinload(Work.contributors).selectinload(WorkContributor.author),
            selectinload(Work.editions).selectinload(Edition.files),
            selectinload(Work.editions).selectinload(Edition.publisher),
            selectinload(Work.editions).selectinload(Edition.license),
            selectinload(Work.categories).selectinload(WorkCategory.category),
            selectinload(Work.covers),
        )
    )


def formats_of(work: Work):
    return sorted({f.format for e in work.editions for f in e.files if not f.withdrawn})


def cover_of(work: Work) -> Optional[Cover]:
    return work.covers[0] if work.covers else None


def primary_author(work: Work) -> str:
    if not work.contributors:
        return "مؤلف غير معروف"
    return work.contributors[0].author.canonical_name


def primary_category(work: Work) -> Optional[Category]:
    for wc in work.categories:
        if wc.is_primary:
            return wc.category
    if work.categories:
        return work.categories[0].category
    return None


def paginate(total: int, page: int, per: int):
    pages = max(1, (total + per - 1) // per)
    page = max(1, min(page, pages))
    return page, pages


def count_ids(db: Session, id_stmt: Select) -> int:
    inner = id_stmt.order_by(None).subquery()
    return int(db.execute(select(func.count()).select_from(inner)).scalar() or 0)


def load_works_ordered(db: Session, ids: Sequence[int]) -> List[Work]:
    if not ids:
        return []
    rows = db.execute(work_query(db).where(Work.id.in_(list(ids)))).scalars().unique().all()
    by_id = {w.id: w for w in rows}
    return [by_id[i] for i in ids if i in by_id]


def page_ids(db: Session, id_stmt: Select, page: int, per: int):
    total = count_ids(db, id_stmt)
    page, pages = paginate(total, page, per)
    ids = list(db.execute(id_stmt.offset((page - 1) * per).limit(per)).scalars().all())
    return ids, page, pages, total


def public_category_index(db: Session):
    """Roots/children/counts for public navigation. Empty branches are omitted."""
    counts = rolled_counts(db)
    visible = nonempty_categories(db)
    visible_ids = {c.id for c in visible}
    roots = [c for c in visible if c.parent_id is None]
    by_parent = {}
    for c in visible:
        if c.parent_id is not None and c.parent_id in visible_ids:
            by_parent.setdefault(c.parent_id, []).append(c)
    return roots, by_parent, counts
