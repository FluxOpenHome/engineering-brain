"""`eb` command line: migrate, serve, worker, jobs."""

from __future__ import annotations

import typer

from eb.wiki.cli import wiki_app

app = typer.Typer(no_args_is_help=True, help="Engineering Brain")
jobs_app = typer.Typer(help="Job queue")
app.add_typer(jobs_app, name="jobs")
app.add_typer(wiki_app, name="wiki")


def _db_guard() -> None:
    from eb.db import DatabaseUnavailable, get_pool

    try:
        get_pool()
    except DatabaseUnavailable as e:
        typer.secho(str(e), fg="red", err=True)
        raise typer.Exit(2) from None


@app.command()
def migrate() -> None:
    """Apply database migrations."""
    from eb.db import close_pool
    from eb.db import migrate as _migrate

    _db_guard()
    applied = _migrate()
    close_pool()
    typer.echo(f"applied: {applied or 'nothing (up to date)'}")


@app.command()
def serve(host: str | None = None, port: int | None = None, reload: bool = False) -> None:
    """Run the API server."""
    import uvicorn

    from eb.config import get_settings

    s = get_settings()
    _db_guard()
    uvicorn.run("eb.main:app", host=host or s.api_host, port=port or s.api_port, reload=reload)


@app.command()
def worker(once: bool = typer.Option(False, help="Drain the queue and exit")) -> None:
    """Run a background worker."""
    from eb.jobs import run_worker

    _db_guard()
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
