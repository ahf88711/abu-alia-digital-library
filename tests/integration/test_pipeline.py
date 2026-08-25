from sqlalchemy import select

from abu_alia.db.models import FileAsset, SourceItem, Work
from abu_alia.db.session import session_scope
from abu_alia.ingestion.pipeline import run_discovery, run_ingest_item
from abu_alia.search.backend import search_works


def test_fixture_ingest_publishes_and_searchable(tmp_env):
    with session_scope() as session:
        n = run_discovery(session, "fixture")
        assert n >= 1
        items = session.execute(select(SourceItem)).scalars().all()
        assert items
        first_id = items[0].id
    with session_scope() as session:
        status = run_ingest_item(session, first_id)
        assert status in ("published", "requires_review", "duplicate")
        works = session.execute(select(Work).where(Work.publication_status == "published")).scalars().all()
        assert works
        files = session.execute(select(FileAsset)).scalars().all()
        assert files
        fmts = {f.format for f in files}
        assert "epub" in fmts
        found = search_works(session, works[0].title[:4])
        assert found["total"] >= 1
