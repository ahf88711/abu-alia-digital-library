from sqlalchemy import select

from abu_alia.db.models import Work
from abu_alia.db.session import session_scope
from abu_alia.ingestion.pipeline import run_discovery, run_ingest_item
from abu_alia.web.helpers import page_ids


def test_books_sql_pagination(client, tmp_env):
    with session_scope() as session:
        run_discovery(session, "fixture", limit=2)
        from abu_alia.db.models import SourceItem

        items = session.execute(select(SourceItem)).scalars().all()
        for it in items:
            run_ingest_item(session, it.id)
    r = client.get("/كتب")
    assert r.status_code == 200
    assert "book-card" in r.text
    r2 = client.get("/كتب", params={"page": 1, "fmt": "epub"})
    assert r2.status_code == 200
    with session_scope() as session:
        stmt = select(Work.id).where(Work.publication_status == "published").order_by(Work.id)
        ids, page, pages, total = page_ids(session, stmt, 1, 1)
        assert total >= 1
        assert len(ids) == 1
        assert page == 1
