from __future__ import annotations

import logging
import time
import traceback

from abu_alia.config import get_settings
from abu_alia.db.session import init_db, session_scope
from abu_alia.ingestion.pipeline import run_discovery, run_ingest_item
from abu_alia.jobs.queue import claim_job, complete_job, fail_job
from abu_alia.seed import seed_all

log = logging.getLogger("abu_alia.worker")


HANDLERS = {
    "discover_source": lambda session, payload: run_discovery(
        session, payload["source_code"], payload.get("limit")
    ),
    "ingest_item": lambda session, payload: run_ingest_item(session, int(payload["source_item_id"])),
}


def process_once() -> bool:
    settings = get_settings()
    with session_scope() as session:
        job = claim_job(session, settings.worker_id)
        if job is None:
            return False
        handler = HANDLERS.get(job.job_type)
        try:
            if handler is None:
                raise RuntimeError(f"unknown job type {job.job_type}")
            result = handler(session, job.payload or {})
            complete_job(session, job, {"result": result})
            log.info("job %s %s done %s", job.id, job.job_type, result)
        except Exception as exc:
            log.exception("job %s failed", job.id)
            fail_job(session, job, traceback.format_exc()[-1500:] or str(exc))
        return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    settings.tmp_root.mkdir(parents=True, exist_ok=True)
    init_db(settings)
    with session_scope() as session:
        seed_all(session)
    log.info("worker started")
    while True:
        did = process_once()
        if not did:
            time.sleep(settings.job_poll_seconds)


if __name__ == "__main__":
    main()
