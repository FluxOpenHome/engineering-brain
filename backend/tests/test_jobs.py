from eb.jobs import enqueue, job, run_pending_once
from eb.jobs.queue import _HANDLERS


def test_jobs_retry_then_dead(db):
    calls = {"n": 0}

    @job("test.flaky")
    def flaky(payload):
        calls["n"] += 1
        raise RuntimeError("boom")

    try:
        jid = enqueue("test.flaky", {}, max_attempts=2)
        run_pending_once()
        with db() as conn:
            row = conn.execute("SELECT status, attempts FROM jobs WHERE id=%s", (jid,)).fetchone()
        assert row["status"] == "queued" and row["attempts"] == 1
        with db() as conn:
            conn.execute("UPDATE jobs SET run_after = now() WHERE id=%s", (jid,))
        run_pending_once()
        with db() as conn:
            row = conn.execute("SELECT status, attempts, error FROM jobs WHERE id=%s", (jid,)).fetchone()
        assert row["status"] == "dead" and row["attempts"] == 2 and "boom" in row["error"]
        assert calls["n"] == 2
    finally:
        _HANDLERS.pop("test.flaky", None)


def test_unknown_job_kind_is_recorded(db):
    jid = enqueue("test.unknown", {}, max_attempts=1)
    run_pending_once()
    with db() as conn:
        row = conn.execute("SELECT status, error FROM jobs WHERE id=%s", (jid,)).fetchone()
    assert row["status"] == "dead" and "no handler" in row["error"]
