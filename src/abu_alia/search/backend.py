from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from abu_alia.arabic.normalize import normalize_search
from abu_alia.db.models import SearchDocument, Work, utcnow


def index_work(session: Session, work: Work) -> None:
    authors = " ".join(
        normalize_search(c.author.canonical_name) for c in work.contributors if c.author
    )
    cats = " ".join(normalize_search(wc.category.name_ar) for wc in work.categories if wc.category)
    publisher = ""
    identifiers = ""
    year = work.year
    if work.editions:
        ed = work.editions[0]
        if ed.publisher:
            publisher = normalize_search(ed.publisher.name)
        ids = [x for x in (ed.isbn13, ed.isbn10) if x]
        identifiers = " ".join(ids)
        year = year or ed.year
    title = normalize_search(work.title + " " + (work.subtitle or ""))
    body = normalize_search((work.description or "")[:2000])
    doc = session.get(SearchDocument, work.id)
    if doc is None:
        doc = SearchDocument(work_id=work.id)
        session.add(doc)
    doc.title = title
    doc.authors = authors
    doc.categories = cats
    doc.publisher = publisher
    doc.identifiers = identifiers
    doc.body = body
    doc.year = year
    doc.updated_at = utcnow()
    session.flush()
    session.execute(text("DELETE FROM search_fts WHERE work_id = :id"), {"id": work.id})
    session.execute(
        text(
            "INSERT INTO search_fts(work_id, title, authors, categories, publisher, identifiers, body) "
            "VALUES (:work_id, :title, :authors, :categories, :publisher, :identifiers, :body)"
        ),
        {
            "work_id": work.id,
            "title": title,
            "authors": authors,
            "categories": cats,
            "publisher": publisher,
            "identifiers": identifiers,
            "body": body,
        },
    )


def delete_work_index(session: Session, work_id: int) -> None:
    session.execute(text("DELETE FROM search_fts WHERE work_id = :id"), {"id": work_id})
    doc = session.get(SearchDocument, work_id)
    if doc is not None:
        session.delete(doc)


def search_works(
    session: Session,
    query: str,
    *,
    limit: int = 24,
    offset: int = 0,
    category_path: Optional[str] = None,
    format_filter: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    sort: str = "relevance",
) -> Dict[str, Any]:
    q = normalize_search(query)
    if not q:
        return {"total": 0, "items": [], "query": query}
    # prefix: append * to each token for FTS5
    tokens = [t for t in q.split() if t]
    fts_q = " AND ".join(t + "*" if len(t) > 1 else t for t in tokens)
    # bm25: title heaviest
    sql = """
        SELECT search_fts.work_id AS work_id,
               bm25(search_fts, 6.0, 4.0, 2.0, 1.5, 3.0, 0.5) AS rank
        FROM search_fts
        WHERE search_fts MATCH :q
    """
    rows = session.execute(text(sql), {"q": fts_q}).mappings().all()
    ranked = [(int(r["work_id"]), float(r["rank"])) for r in rows]
    # FTS5 bm25: lower is better
    ranked.sort(key=lambda x: x[1])
    ids = [w for w, _ in ranked]
    if not ids:
        return {"total": 0, "items": [], "query": query, "normalized": q}

    from sqlalchemy.orm import selectinload
    from sqlalchemy import select
    from abu_alia.db.models import FileAsset, Edition, WorkCategory, Category

    stmt = (
        select(Work)
        .where(Work.id.in_(ids))
        .where(Work.publication_status == "published")
        .options(
            selectinload(Work.contributors),
            selectinload(Work.editions).selectinload(Edition.files),
            selectinload(Work.editions).selectinload(Edition.publisher),
            selectinload(Work.categories).selectinload(WorkCategory.category),
            selectinload(Work.covers),
        )
    )
    works = {w.id: w for w in session.execute(stmt).scalars().unique().all()}
    ordered: List[Work] = []
    for wid, _ in ranked:
        w = works.get(wid)
        if not w:
            continue
        if category_path:
            if not any(
                wc.category and (wc.category.path == category_path or wc.category.path.startswith(category_path + "/"))
                for wc in w.categories
            ):
                continue
        if format_filter:
            fmts = {f.format for e in w.editions for f in e.files if not f.withdrawn}
            if format_filter not in fmts:
                continue
        if year_from and (w.year or 0) < year_from:
            continue
        if year_to and w.year and w.year > year_to:
            continue
        ordered.append(w)
    if sort == "newest":
        ordered.sort(key=lambda w: w.published_at or w.created_at, reverse=True)
    elif sort == "downloads":
        ordered.sort(key=lambda w: w.download_count, reverse=True)
    elif sort == "views":
        ordered.sort(key=lambda w: w.view_count, reverse=True)
    total = len(ordered)
    page = ordered[offset : offset + limit]
    return {"total": total, "items": page, "query": query, "normalized": q}
