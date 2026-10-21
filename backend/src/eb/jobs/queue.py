from __future__ import annotations

import json
import socket
import time
import traceback
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import structlog

from eb.config import get_settings
from eb.db import connection

log = structlog.get_logger(__name__)

Handler = Callable[[dict[str, Any]], None]
_HANDLERS: dict[str, Handler] = {}


def job(kind: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        _HANDLERS[kind] = fn
        return fn

    return deco


def enqueue(
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    priority: int = 100,
    delay: timedelta | None = None,
    max_attempts: int = 3,
    conn=None,
) -> int:
    sql = """
        INSERT INTO jobs (kind, payload, priority, run_after, max_attempts)
        VALUES (%s, %s::jsonb, %s, now() + %s, %s) RETURNING id
    """
    args = (kind, json.dumps(payload or {}), priority, delay or timedelta(0), max_attempts)
    if conn is not None:
        return conn.execute(sql, args).fetchone()["id"]
    with connection() as c:
        return c.execute(sql, args).fetchone()["id"]


def _claim(worker_id: str) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute(
            """
            WITH next AS (
                SELECT id FROM jobs
                WHERE status = 'queued' AND run_after <= now()
                ORDER BY priority, run_after, id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE jobs j SET status = 'running', locked_by = %s, locked_at = now(),
                              started_at = now(), attempts = attempts + 1
            FROM next WHERE j.id = next.id
            RETURNING j.id, j.kind, j.payload, j.attempts, j.max_attempts
            """,
            (worker_id,),
        ).fetchone()
    return row


def _finish(job_id: int, *, error: str | None, attempts: int, max_attempts: int) -> None:
    with connection() as conn:
        if error is None:
            conn.execute(
                "UPDATE jobs SET status='done', finished_at=now(), locked_by=NULL WHERE id=%s",
                (job_id,),
            )
        elif attempts >= max_attempts:
            conn.execute(
                "UPDATE jobs SET status='dead', error=%s, finished_at=now(), locked_by=NULL "
                "WHERE id=%s",
                (error, job_id),
            )
        else:
            backoff = timedelta(seconds=min(300, 5 * 2**attempts))
            conn.execute(
                "UPDATE jobs SET status='queued', error=%s, run_after=now()+%s, locked_by=NULL "
                "WHERE id=%s",
                (error, backoff, job_id),
            )


def run_one(worker_id: str) -> bool:
    """Claim and run a single job. Returns False when the queue is empty."""
    row = _claim(worker_id)
    if row is None:
        return False
    handler = _HANDLERS.get(row["kind"])
    error: str | None = None
    t0 = time.monotonic()
    try:
        if handler is None:
            raise RuntimeError(f"no handler registered for job kind {row['kind']!r}")
        handler(row["payload"])
    except Exception:
        error = traceback.format_exc()[-4000:]
        log.error("job.failed", job_id=row["id"], kind=row["kind"], attempt=row["attempts"])
    finally:
        _finish(row["id"], error=error, attempts=row["attempts"], max_attempts=row["max_attempts"])
    log.info("job.done" if error is None else "job.error", job_id=row["id"], kind=row["kind"],
             seconds=round(time.monotonic() - t0, 3))
    return True


def has_handler(kind: str) -> bool:
    return kind in _HANDLERS


def run_pending_once(worker_id: str = "inline") -> int:
    """Drain the queue synchronously (used by tests and `eb jobs run-pending`)."""
    import eb.jobs.handlers  # noqa: F401  (registers handlers)

    n = 0
    while run_one(worker_id):
        n += 1
    return n


def run_worker(worker_id: str | None = None, *, stop_when_empty: bool = False) -> None:
    import eb.jobs.handlers  # noqa: F401  (registers handlers)

    s = get_settings()
    worker_id = worker_id or f"{socket.gethostname()}:{int(time.time())}"
    log.info("worker.start", worker_id=worker_id, kinds=sorted(_HANDLERS))
    while True:
        ran = run_one(worker_id)
        if not ran:
            if stop_when_empty:
                return
            time.sleep(s.worker_poll_seconds)
