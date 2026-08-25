from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from abu_alia.arabic.normalize import normalize_search, slugify_ar
from abu_alia.db.models import Collection, CollectionWork, Work, WorkCategory, Category


def _upsert_collection(session: Session, slug: str, title: str, description: str) -> Collection:
    row = session.execute(select(Collection).where(Collection.slug == slug)).scalar_one_or_none()
    if row is None:
        row = Collection(slug=slug, title=title, description=description, featured=True)
        session.add(row)
        session.flush()
    return row


def _set_members(session: Session, collection: Collection, work_ids: list) -> None:
    session.execute(delete(CollectionWork).where(CollectionWork.collection_id == collection.id))
    for i, wid in enumerate(work_ids[:48]):
        session.add(CollectionWork(collection_id=collection.id, work_id=wid, sort_order=i))


def refresh_featured_collections(session: Session) -> int:
    """Build small curated lists from the live catalog. Idempotent."""
    specs = [
        ("poetry", "دواوين الشعر", "مختارات من الدواوين العربية المنشورة في المكتبة.", "ديوان"),
        ("hadith", "كتب الحديث", "مؤلفات الحديث وعلومه في المجموعة.", None),
        ("new", "أحدث الإضافات", "آخر ما نُشر في المكتبة.", None),
    ]
    n = 0
    poetry_norm = f"%{normalize_search('ديوان')}%"
    poetry_ids = list(
        session.execute(
            select(Work.id)
            .where(Work.publication_status == "published", Work.title_normalized.like(poetry_norm))
            .order_by(Work.download_count.desc(), Work.id.desc())
            .limit(24)
        ).scalars()
    )
    hadith_ids = list(
        session.execute(
            select(Work.id)
            .join(WorkCategory)
            .join(Category)
            .where(Work.publication_status == "published", Category.slug == "hadith")
            .order_by(Work.id.desc())
            .limit(24)
        ).scalars()
    )
    new_ids = list(
        session.execute(
            select(Work.id)
            .where(Work.publication_status == "published")
            .order_by(Work.published_at.desc(), Work.id.desc())
            .limit(24)
        ).scalars()
    )
    mapping = {"poetry": poetry_ids, "hadith": hadith_ids, "new": new_ids}
    for slug, title, desc, _hint in specs:
        ids = mapping[slug]
        if not ids:
            continue
        col = _upsert_collection(session, slug, title, desc)
        _set_members(session, col, ids)
        n += 1
    return n
