from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from abu_alia.config import get_settings
from abu_alia.db.models import Job, utcnow


def enqueue(
    session: Session,
    job_type: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    priority: int = 0,
    delay_seconds: int = 0,
    max_attempts: Optional[int] = None,
) -> Job:
    settings = get_settings()
    job = Job(
        job_type=job_type,
        payload=payload or {},
        status="queued",
        priority=priority,
        max_attempts=max_attempts or settings.job_max_attempts,
        run_after=utcnow() + timedelta(seconds=delay_seconds),
    )
    session.add(job)
    session.flush()
    return job


def claim_job(session: Session, worker_id: str) -> Optional[Job]:
    now = utcnow()
    stmt = (
        select(Job)
        .where(Job.status.in_(("queued", "retrying")))
        .where(Job.run_after <= now)
        .order_by(Job.priority.desc(), Job.id.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    try:
        job = session.execute(stmt).scalar_one_or_none()
    except Exception:
        # SQLite may not support skip_locked on all versions.
        job = session.execute(
            select(Job)
            .where(Job.status.in_(("queued", "retrying")))
            .where(Job.run_after <= now)
            .order_by(Job.priority.desc(), Job.id.asc())
            .limit(1)
        ).scalar_one_or_none()
    if job is None:
        return None
    job.status = "running"
    job.locked_at = now
    job.locked_by = worker_id
    job.attempts += 1
    session.flush()
    return job


def complete_job(session: Session, job: Job, result: Optional[Dict[str, Any]] = None) -> None:
    job.status = "done"
    job.progress = 1.0
    job.result = result or {}
    job.locked_at = None


def fail_job(session: Session, job: Job, error: str) -> None:
    job.last_error = error[:4000]
    if job.attempts >= job.max_attempts:
        job.status = "dead"
        job.locked_at = None
        return
    delay = min(3600, 2 ** job.attempts)
    job.status = "retrying"
    job.run_after = utcnow() + timedelta(seconds=delay)
    job.locked_at = None


def cancel_job(session: Session, job_id: int) -> bool:
    job = session.get(Job, job_id)
    if job is None or job.status in ("done", "dead"):
        return False
    job.status = "cancelled"
    job.locked_at = None
    return True
