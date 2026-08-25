from __future__ import annotations

import argparse
import logging

from abu_alia.config import get_settings
from abu_alia.db.session import init_db, session_scope
from abu_alia.ingestion.pipeline import enqueue_discovery, run_discovery, run_ingest_item
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
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
