from sqlalchemy import select

from abu_alia.db.models import Job, SourceItem
from abu_alia.db.session import session_scope
from abu_alia.ingestion.pipeline import catalog_stats, requeue_failed, run_discovery


def test_requeue_failed_creates_jobs(tmp_env):
    with session_scope() as session:
        run_discovery(session, "fixture", limit=2)
        item = session.execute(select(SourceItem)).scalars().first()
        item.status = "failed"
        item.last_error = "connection reset"
        item_id = item.id
    with session_scope() as session:
        n = requeue_failed(session, limit=10)
        assert n >= 1
        item = session.get(SourceItem, item_id)
        assert item.status == "queued"
        jobs = session.execute(select(Job).where(Job.job_type == "ingest_item")).scalars().all()
        assert any((j.payload or {}).get("source_item_id") == item_id for j in jobs)
        stats = catalog_stats(session)
        assert "published" in stats


def test_requeue_skips_permanent_missing(tmp_env):
    with session_scope() as session:
        run_discovery(session, "fixture", limit=2)
        item = session.execute(select(SourceItem)).scalars().first()
        item.status = "failed"
        item.last_error = "permanent: all URLs missing: ['https://example.test/x']"
        item_id = item.id
    with session_scope() as session:
        n = requeue_failed(session, limit=10)
        item = session.get(SourceItem, item_id)
        assert item.status == "failed"
        assert n == 0
