from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select, func

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
