from __future__ import annotations

import argparse
import logging

from abu_alia.config import get_settings
from abu_alia.db.session import init_db, session_scope
from abu_alia.ingestion.pipeline import catalog_stats, enqueue_discovery, requeue_failed, run_discovery, run_ingest_item
from abu_alia.jobs.queue import claim_job, complete_job, fail_job
from abu_alia.seed import seed_all
from abu_alia.worker import HANDLERS, process_once


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "abu_alia.web.app:app",
        host=args.host or settings.bind_host,
        port=args.port or settings.bind_port,
        reload=args.reload,
    )


def cmd_worker(_args: argparse.Namespace) -> None:
    from abu_alia.worker import main

    main()


def cmd_ingest(args: argparse.Namespace) -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    init_db(settings)
    with session_scope() as session:
        seed_all(session)
        n = run_discovery(session, args.source, limit=args.limit)
        print(f"discovered {n} new items from {args.source}")
    processed = 0
    while processed < args.limit:
        if not process_once():
            break
        processed += 1
    print(f"processed {processed} jobs")


def cmd_init(_args: argparse.Namespace) -> None:
    settings = get_settings()
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    init_db(settings)
    with session_scope() as session:
        seed_all(session)
    print("initialized")


def cmd_retry_failed(args: argparse.Namespace) -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    init_db(settings)
    with session_scope() as session:
        n = requeue_failed(session, limit=args.limit, source_code=args.source)
        print(f"requeued {n} failed items")
    processed = 0
    while processed < args.limit:
        if not process_once():
            break
        processed += 1
    print(f"processed {processed} jobs")
    with session_scope() as session:
        print(catalog_stats(session))


def cmd_harvest(args: argparse.Namespace) -> None:
    from abu_alia.ingestion.harvest import harvest_loop

    settings = get_settings()
    harvest_loop(target=args.target or settings.harvest_target, batch=args.batch, source=args.source)


def cmd_stats(_args: argparse.Namespace) -> None:
    settings = get_settings()
    init_db(settings)
    with session_scope() as session:
        print(catalog_stats(session))


def cmd_validate_storage(args: argparse.Namespace) -> None:
    from abu_alia.storage.audit import sample_storage

    settings = get_settings()
    result = sample_storage(settings.storage_root, limit=args.limit)
    print(result)


def cmd_collections(_args: argparse.Namespace) -> None:
    from abu_alia.catalog.collections import refresh_featured_collections

    settings = get_settings()
    init_db(settings)
    with session_scope() as session:
        n = refresh_featured_collections(session)
        print(f"refreshed {n} collections")


def main() -> None:
    parser = argparse.ArgumentParser(prog="abu-alia")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_serve = sub.add_parser("serve")
    p_serve.add_argument("--host", default=None)
    p_serve.add_argument("--port", type=int, default=None)
    p_serve.add_argument("--reload", action="store_true")
    p_serve.set_defaults(func=cmd_serve)
    p_w = sub.add_parser("worker")
    p_w.set_defaults(func=cmd_worker)
    p_i = sub.add_parser("ingest")
    p_i.add_argument("source")
    p_i.add_argument("--limit", type=int, default=20)
    p_i.set_defaults(func=cmd_ingest)
    p_init = sub.add_parser("init")
    p_init.set_defaults(func=cmd_init)
    p_r = sub.add_parser("retry-failed")
    p_r.add_argument("--source", default=None)
    p_r.add_argument("--limit", type=int, default=50)
    p_r.set_defaults(func=cmd_retry_failed)
    p_h = sub.add_parser("harvest")
    p_h.add_argument("--source", default="openiti")
    p_h.add_argument("--target", type=int, default=None)
    p_h.add_argument("--batch", type=int, default=40)
    p_h.set_defaults(func=cmd_harvest)
    p_s = sub.add_parser("stats")
    p_s.set_defaults(func=cmd_stats)
    p_c = sub.add_parser("collections")
    p_c.set_defaults(func=cmd_collections)
    p_v = sub.add_parser("validate-storage")
    p_v.add_argument("--limit", type=int, default=40)
    p_v.set_defaults(func=cmd_validate_storage)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
