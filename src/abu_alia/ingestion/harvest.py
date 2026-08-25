from __future__ import annotations

import logging
import time

from abu_alia.config import get_settings
from abu_alia.db.session import init_db, session_scope
from abu_alia.ingestion.checkpoint import write_checkpoint
from abu_alia.ingestion.pipeline import catalog_stats, requeue_failed, run_discovery
from abu_alia.seed import seed_all
from abu_alia.worker import process_once

log = logging.getLogger("abu_alia.harvest")


def _stats():
    with session_scope() as session:
        return catalog_stats(session)


def _drain(max_jobs: int) -> int:
    n = 0
    idle = 0
    while n < max_jobs:
        try:
            did = process_once()
        except Exception:
            log.exception("job crashed")
            did = True
        if did:
            n += 1
            idle = 0
        else:
            idle += 1
            if idle >= 2:
                break
            time.sleep(0.2)
    return n


def harvest_loop(target: int, batch: int, source: str = "openiti") -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    settings.tmp_root.mkdir(parents=True, exist_ok=True)
    settings.cache_root.mkdir(parents=True, exist_ok=True)
    init_db(settings)
    with session_scope() as session:
        seed_all(session)
    empty_rounds = 0
    while True:
        stats = _stats()
        write_checkpoint(stats, phase="harvesting", note=f"source={source} batch={batch}")
        log.info("catalog %s", stats)
        if stats["published"] >= target:
            write_checkpoint(stats, phase="harvest-target-reached", note="stop; do not invent more books")
            log.info("reached target %s with %s published", target, stats["published"])
            return
        with session_scope() as session:
            requeued = requeue_failed(session, limit=batch, source_code=source)
        processed = _drain(batch * 3)
        if requeued == 0 and processed == 0:
            try:
                with session_scope() as session:
                    discovered = run_discovery(session, source, limit=batch)
            except Exception:
                log.exception("discovery failed; backing off")
                time.sleep(20)
                empty_rounds += 1
                if empty_rounds > 15:
                    stats = _stats()
                    write_checkpoint(stats, phase="harvest-blocked", note="discovery repeatedly failing")
                    return
                continue
            log.info("discovered %s new items", discovered)
            if discovered == 0:
                empty_rounds += 1
                if empty_rounds > 3:
                    stats = _stats()
                    write_checkpoint(
                        stats,
                        phase="harvest-no-more-eligible",
                        note="no further new items from this source without fabricating",
                    )
                    return
            else:
                empty_rounds = 0
                _drain(batch * 3)
        else:
            empty_rounds = 0
        stats = _stats()
        write_checkpoint(stats, phase="harvesting", note=f"processed={processed} requeued={requeued}")
