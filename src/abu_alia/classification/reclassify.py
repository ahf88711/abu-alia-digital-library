from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from abu_alia.arabic.normalize import collapse_whitespace, normalize_search
from abu_alia.classification.engine import (
    CLASSIFICATION_VERSION,
    UNCLASSIFIED_SLUG,
    score_categories,
    select_assignments,
)
from abu_alia.db.models import Category, SourceItem, SystemSetting, Work, WorkCategory, WorkContributor

VERSION_KEY = "classification_version"


def prefer_arabic_segment(title: str) -> str:
    """Keep the Arabic side of OpenITI 'ar :: lat' titles. Does not invent text."""
    if not title or "::" not in title:
        return title
    parts = [p.strip() for p in title.split("::") if p.strip()]
    if not parts:
        return title

    def ar_count(s: str) -> int:
        return sum(1 for c in s if "\u0600" <= c <= "\u06FF")

    best = max(parts, key=ar_count)
    if ar_count(best) >= 3:
        return best
    return title


def clean_display_title(title: str) -> str:
    original = title or ""
    t = original.replace("¶", " ").replace("\x0b", " ").replace("\u2028", " ").replace("\u2029", " ")
    t = prefer_arabic_segment(t)
    t = collapse_whitespace(t)
    return t or original


def ensure_unclassified(session: Session) -> Category:
    row = session.execute(select(Category).where(Category.slug == UNCLASSIFIED_SLUG)).scalar_one_or_none()
    if row:
        return row
    row = Category(
        parent_id=None,
        slug=UNCLASSIFIED_SLUG,
        name_ar="غير مصنف",
        name_normalized=normalize_search("غير مصنف"),
        description="كتب لم يتوفر لها دليل موضوعي كافٍ.",
        path=UNCLASSIFIED_SLUG,
        sort_order=999,
        triggers=[],
    )
    session.add(row)
    session.flush()
    return row


def refresh_taxonomy_triggers(session: Session) -> None:
    from abu_alia.seed import sync_taxonomy

    sync_taxonomy(session)
    ensure_unclassified(session)


def _meta(item: Optional[SourceItem]) -> Dict[str, Any]:
    if item is None:
        return {}
    raw = item.raw_metadata or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    return raw if isinstance(raw, dict) else {}


def _tags_for(item: Optional[SourceItem]) -> List[str]:
    raw = _meta(item)
    tags = raw.get("tags") or ""
    if isinstance(tags, str):
        return [t.strip() for t in tags.replace("::", " ").split() if t.strip()]
    if isinstance(tags, list):
        return [str(t) for t in tags]
    return []


def _source_title(item: Optional[SourceItem]) -> str:
    raw = _meta(item)
    return str(raw.get("title_ar") or item.title or "") if item is not None else ""


def _set_version(session: Session) -> None:
    row = session.get(SystemSetting, VERSION_KEY)
    if row:
        row.value = CLASSIFICATION_VERSION
    else:
        session.add(SystemSetting(key=VERSION_KEY, value=CLASSIFICATION_VERSION))


def current_version(session: Session) -> Optional[int]:
    row = session.get(SystemSetting, VERSION_KEY)
    if row is None:
        return None
    try:
        return int(row.value)
    except (TypeError, ValueError):
        return None


def reclassify_catalog(session: Session) -> Dict[str, int]:
    refresh_taxonomy_triggers(session)
    unclassified = ensure_unclassified(session)
    cats = session.execute(select(Category)).scalars().all()
    works = session.execute(
        select(Work)
        .where(Work.publication_status == "published")
        .options(
            selectinload(Work.editions),
            selectinload(Work.contributors).selectinload(WorkContributor.author),
        )
    ).scalars().all()
    items_by_work = {
        it.work_id: it
        for it in session.execute(select(SourceItem)).scalars().all()
        if it.work_id
    }

    stats = {"works": 0, "assigned": 0, "unclassified": 0, "titles_cleaned": 0}
    ids = [w.id for w in works]
    if ids:
        session.execute(delete(WorkCategory).where(WorkCategory.work_id.in_(ids)))
        session.flush()

    for work in works:
        src_item = items_by_work.get(work.id)
        tags = _tags_for(src_item)
        cleaned = clean_display_title(work.title or "")
        if cleaned and cleaned != work.title:
            work.title = cleaned
            work.title_normalized = normalize_search(cleaned)
            stats["titles_cleaned"] += 1
        authors = [c.author.canonical_name for c in work.contributors if c.author]
        scored = score_categories(
            categories=cats,
            title=work.title or "",
            description=" ".join(
                p for p in (work.description or "", _source_title(src_item)) if p
            ),
            source_genres=tags,
            tags=tags,
            authors=authors,
        )
        chosen, _needs = select_assignments(scored)
        if not chosen:
            session.add(
                WorkCategory(
                    work_id=work.id,
                    category_id=unclassified.id,
                    confidence=0.0,
                    is_primary=True,
                    evidence={"signals": ["unclassified"]},
                )
            )
            stats["unclassified"] += 1
        else:
            for row in chosen:
                session.add(
                    WorkCategory(
                        work_id=work.id,
                        category_id=row["category_id"],
                        confidence=row["score"],
                        is_primary=row["is_primary"],
                        evidence={"signals": row["evidence"]},
                    )
                )
            stats["assigned"] += 1
        stats["works"] += 1
    _set_version(session)
    session.flush()
    return stats


def ensure_classification(session: Session, *, force: bool = False) -> Dict[str, Any]:
    if not force and current_version(session) == CLASSIFICATION_VERSION:
        return {"skipped": True, "version": CLASSIFICATION_VERSION}
    stats = reclassify_catalog(session)
    stats["skipped"] = False
    stats["version"] = CLASSIFICATION_VERSION
    return stats
