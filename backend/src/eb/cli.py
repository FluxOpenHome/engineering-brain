"""`eb` command line: migrate, serve, worker, jobs."""

from __future__ import annotations

import typer

app = typer.Typer(no_args_is_help=True, help="Engineering Brain")
jobs_app = typer.Typer(help="Job queue")
app.add_typer(jobs_app, name="jobs")


@app.command()
def migrate() -> None:
    """Apply database migrations."""
    from eb.db import close_pool
    from eb.db import migrate as _migrate

    applied = _migrate()
    close_pool()
    typer.echo(f"applied: {applied or 'nothing (up to date)'}")


@app.command()
def serve(host: str | None = None, port: int | None = None, reload: bool = False) -> None:
    """Run the API server."""
    import uvicorn

    from eb.config import get_settings

    s = get_settings()
    uvicorn.run("eb.main:app", host=host or s.api_host, port=port or s.api_port, reload=reload)


@app.command()
def worker(once: bool = typer.Option(False, help="Drain the queue and exit")) -> None:
    """Run a background worker."""
    from eb.jobs import run_worker

    run_worker(stop_when_empty=once)


@jobs_app.command("run-pending")
def jobs_run_pending() -> None:
    import eb.jobs.handlers  # noqa: F401
    from eb.jobs import run_pending_once

    typer.echo(f"ran {run_pending_once()} job(s)")


@jobs_app.command("stats")
def jobs_stats() -> None:
    from eb.db import connection

    with connection() as conn:
        rows = conn.execute(
            "SELECT kind, status, count(*) AS n FROM jobs GROUP BY 1, 2 ORDER BY 1, 2"
        ).fetchall()
    for r in rows:
        typer.echo(f"{r['kind']:<24} {r['status']:<8} {r['n']}")


if __name__ == "__main__":
    app()
