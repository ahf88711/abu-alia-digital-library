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

    from sqlalchemy import select
    from abu_alia.db.models import Category, Edition, FileAsset, WorkCategory
    from abu_alia.web.helpers import load_works_ordered

    allowed = set(
        session.execute(
            select(Work.id).where(Work.id.in_(ids), Work.publication_status == "published")
        ).scalars()
    )
    ids = [i for i in ids if i in allowed]
    if category_path:
        cat_ids = set(
            session.execute(
                select(WorkCategory.work_id)
                .join(Category, Category.id == WorkCategory.category_id)
                .where(
                    WorkCategory.work_id.in_(ids),
                    (Category.path == category_path) | (Category.path.startswith(category_path + "/")),
                )
            ).scalars()
        )
        ids = [i for i in ids if i in cat_ids]
    if format_filter:
        fmt_ids = set(
            session.execute(
                select(Edition.work_id)
                .join(FileAsset, FileAsset.edition_id == Edition.id)
                .where(
                    Edition.work_id.in_(ids),
                    FileAsset.format == format_filter,
                    FileAsset.withdrawn.is_(False),
                )
            ).scalars()
        )
        ids = [i for i in ids if i in fmt_ids]
    if year_from or year_to:
        year_rows = session.execute(select(Work.id, Work.year).where(Work.id.in_(ids))).all()
        years = {i: y for i, y in year_rows}
        if year_from:
            ids = [i for i in ids if (years.get(i) or 0) >= year_from]
        if year_to:
            ids = [i for i in ids if years.get(i) is None or years[i] <= year_to]
    if sort == "newest":
        rows = session.execute(select(Work.id, Work.published_at, Work.created_at).where(Work.id.in_(ids))).all()
        order = {i: (pub or created) for i, pub, created in rows}
        ids.sort(key=lambda i: order.get(i) or utcnow(), reverse=True)
    elif sort in ("downloads", "views"):
        col = Work.download_count if sort == "downloads" else Work.view_count
        scores = dict(session.execute(select(Work.id, col).where(Work.id.in_(ids))).all())
        ids.sort(key=lambda i: scores.get(i) or 0, reverse=True)
    total = len(ids)
    page_ids = ids[offset : offset + limit]
    page = load_works_ordered(session, page_ids)
    return {"total": total, "items": page, "query": query, "normalized": q}
