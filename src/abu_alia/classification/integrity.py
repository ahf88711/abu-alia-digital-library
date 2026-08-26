from __future__ import annotations

from typing import Dict, List, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from abu_alia.classification.engine import UNCLASSIFIED_SLUG, contradictions
from abu_alia.db.models import Category, SourceItem, Work, WorkCategory


def category_counts(session: Session) -> Dict[str, int]:
    rows = session.execute(
        select(Category.slug, func.count(Work.id))
        .select_from(Category)
        .outerjoin(WorkCategory, WorkCategory.category_id == Category.id)
        .outerjoin(Work, (Work.id == WorkCategory.work_id) & (Work.publication_status == "published"))
        .group_by(Category.slug)
    ).all()
    return {slug: int(n or 0) for slug, n in rows}


def rolled_counts(session: Session) -> Dict[int, int]:
    cats = session.execute(select(Category)).scalars().all()
    direct = dict(
        session.execute(
            select(WorkCategory.category_id, func.count())
            .join(Work, Work.id == WorkCategory.work_id)
            .where(Work.publication_status == "published")
            .group_by(WorkCategory.category_id)
        ).all()
    )
    rolled: Dict[int, int] = {}
    for cat in cats:
        n = 0
        for other in cats:
            if other.path == cat.path or other.path.startswith(cat.path + "/"):
                n += int(direct.get(other.id, 0))
        rolled[cat.id] = n
    return rolled


def nonempty_categories(session: Session) -> List[Category]:
    counts = rolled_counts(session)
    cats = session.execute(select(Category).order_by(Category.sort_order, Category.path)).scalars().all()
    return [c for c in cats if counts.get(c.id, 0) > 0]


def empty_category_slugs(session: Session) -> List[str]:
    counts = rolled_counts(session)
    cats = session.execute(select(Category)).scalars().all()
    return [c.slug for c in cats if counts.get(c.id, 0) == 0]


def find_misplaced(session: Session, limit: int = 200) -> List[dict]:
    rows = session.execute(
        select(Work.id, Work.title, Category.slug, Category.name_ar)
        .join(WorkCategory, WorkCategory.work_id == Work.id)
        .join(Category, Category.id == WorkCategory.category_id)
        .where(Work.publication_status == "published", WorkCategory.is_primary.is_(True))
    ).all()
    items = session.execute(select(SourceItem.work_id, SourceItem.raw_metadata)).all()
    tag_cache: Dict[int, List[str]] = {}
    for wid, raw in items:
        if not wid:
            continue
        tags = ""
        if isinstance(raw, dict):
            tags = raw.get("tags") or ""
        if isinstance(tags, str):
            tag_cache[wid] = [t.strip() for t in tags.replace("::", " ").split() if t.strip()]
        elif isinstance(tags, list):
            tag_cache[wid] = [str(t) for t in tags]
    bad = []
    for wid, title, slug, name in rows:
        if slug == UNCLASSIFIED_SLUG:
            continue
        issues = contradictions(title or "", slug, tags=tag_cache.get(wid) or [])
        if issues:
            bad.append({"work_id": wid, "title": title, "slug": slug, "name": name, "issues": issues})
            if len(bad) >= limit:
                break
    return bad


def samples_by_category(session: Session, per: int = 5) -> List[Tuple[str, str, List[str]]]:
    cats = nonempty_categories(session)
    out = []
    for cat in cats:
        titles = session.execute(
            select(Work.title)
            .join(WorkCategory, WorkCategory.work_id == Work.id)
            .where(
                Work.publication_status == "published",
                WorkCategory.category_id == cat.id,
                WorkCategory.is_primary.is_(True),
            )
            .limit(per)
        ).scalars().all()
        out.append((cat.slug, cat.name_ar, list(titles)))
    return out
