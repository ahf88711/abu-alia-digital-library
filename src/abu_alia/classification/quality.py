from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from abu_alia.arabic.normalize import normalize_search
from abu_alia.classification.reclassify import clean_display_title
from abu_alia.db.models import Author, Cover, Edition, FileAsset, SourceItem, Work, WorkCategory, WorkContributor


def repair_titles(session: Session) -> int:
    n = 0
    works = session.execute(select(Work).where(Work.publication_status == "published")).scalars().all()
    for work in works:
        cleaned = clean_display_title(work.title or "")
        if cleaned and cleaned != work.title:
            work.title = cleaned
            work.title_normalized = normalize_search(cleaned)
            n += 1
    return n


def duplicate_title_author(session: Session) -> List[dict]:
    rows = session.execute(
        select(Work.id, Work.title, Work.title_normalized, Author.name_normalized)
        .join(WorkContributor, WorkContributor.work_id == Work.id)
        .join(Author, Author.id == WorkContributor.author_id)
        .where(Work.publication_status == "published", WorkContributor.sort_order == 0)
    ).all()
    groups: Dict[tuple, List[tuple]] = defaultdict(list)
    for wid, title, tnorm, anorm in rows:
        groups[(tnorm, anorm)].append((wid, title))
    dups = []
    for (tnorm, anorm), items in groups.items():
        ids = {i[0] for i in items}
        if len(ids) > 1:
            dups.append(
                {
                    "title_normalized": tnorm,
                    "author_normalized": anorm,
                    "work_ids": sorted(ids),
                    "titles": [i[1] for i in items],
                }
            )
    return dups


def missing_authors(session: Session) -> int:
    return int(
        session.execute(
            select(func.count())
            .select_from(Work)
            .where(Work.publication_status == "published")
            .where(~Work.id.in_(select(WorkContributor.work_id)))
        ).scalar()
        or 0
    )


def works_without_files(session: Session) -> int:
    return int(
        session.execute(
            select(func.count())
            .select_from(Work)
            .where(Work.publication_status == "published")
            .where(
                ~Work.id.in_(
                    select(Edition.work_id).join(FileAsset, FileAsset.edition_id == Edition.id).where(
                        FileAsset.withdrawn.is_(False)
                    )
                )
            )
        ).scalar()
        or 0
    )


def missing_storage_files(session: Session, storage_root: Path, limit: int = 200) -> List[dict]:
    missing: List[dict] = []
    rows = session.execute(
        select(FileAsset.id, FileAsset.storage_key, FileAsset.format, Edition.work_id).join(
            Edition, Edition.id == FileAsset.edition_id
        )
    ).all()
    for fid, key, fmt, wid in rows:
        path = Path(storage_root) / key
        if not path.is_file():
            missing.append({"file_id": fid, "work_id": wid, "key": key, "format": fmt})
            if len(missing) >= limit:
                break
    return missing


def orphan_source_items(session: Session) -> int:
    return int(
        session.execute(
            select(func.count())
            .select_from(SourceItem)
            .where(SourceItem.work_id.is_not(None))
            .where(~SourceItem.work_id.in_(select(Work.id)))
        ).scalar()
        or 0
    )


def covers_missing_files(session: Session, storage_root: Path, limit: int = 50) -> int:
    n = 0
    rows = session.execute(select(Cover.storage_key)).scalars().all()
    for key in rows:
        if not (Path(storage_root) / key).is_file():
            n += 1
            if n >= limit:
                break
    return n


def audit_catalog(session: Session, storage_root: Optional[Path] = None) -> Dict[str, Any]:
    titles = repair_titles(session)
    dups = duplicate_title_author(session)
    missing_auth = missing_authors(session)
    no_files = works_without_files(session)
    orphans = orphan_source_items(session)
    published = session.execute(select(func.count()).select_from(Work).where(Work.publication_status == "published")).scalar()
    files = session.execute(select(func.count()).select_from(FileAsset)).scalar()
    missing_files: List[dict] = []
    missing_covers = 0
    if storage_root:
        missing_files = missing_storage_files(session, storage_root)
        missing_covers = covers_missing_files(session, storage_root)
    uncategorized = int(
        session.execute(
            select(func.count())
            .select_from(Work)
            .where(Work.publication_status == "published")
            .where(~Work.id.in_(select(WorkCategory.work_id)))
        ).scalar()
        or 0
    )
    return {
        "published": int(published or 0),
        "files": int(files or 0),
        "titles_repaired": titles,
        "duplicate_groups": len(dups),
        "duplicate_examples": dups[:10],
        "missing_authors": missing_auth,
        "works_without_files": no_files,
        "orphan_source_items": orphans,
        "missing_storage_files": len(missing_files),
        "missing_storage_examples": missing_files[:8],
        "missing_covers_sampled": missing_covers,
        "uncategorized": uncategorized,
    }
