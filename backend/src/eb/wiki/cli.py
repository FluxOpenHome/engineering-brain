"""`eb wiki ...`: sync the index from the files, lint, reindex, propose."""

from __future__ import annotations

import json

import typer

wiki_app = typer.Typer(help="Reviewed wiki", no_args_is_help=True)


@wiki_app.command()
def sync() -> None:
    """Upsert wiki_pages from the markdown files and index published pages."""
    from eb.wiki.service import sync_from_disk

    typer.echo(json.dumps(sync_from_disk()))


@wiki_app.command()
def lint() -> None:
    """Mark pages citing superseded revisions stale; list orphan citations."""
    from eb.wiki.service import lint as _lint

    typer.echo(json.dumps(_lint(), indent=2, default=str))


@wiki_app.command()
def reindex(force: bool = typer.Option(False, help="Re-embed even when the content hash is unchanged")
            ) -> None:
    """Rebuild wiki_chunks for every published page, inline (no worker needed)."""
    from eb.wiki import store
    from eb.wiki.index import index_page
    from eb.wiki.service import sync_from_disk

    result = sync_from_disk()
    if force:
        from eb.db import connection

        with connection() as conn:
            rows = conn.execute("SELECT id, slug FROM wiki_pages WHERE status = 'published'").fetchall()
        for r in rows:
            page = store.read_page(r["slug"])
            if page is not None:
                index_page(r["id"], r["slug"], page.title, page.body, force=True)
    typer.echo(json.dumps(result))


@wiki_app.command()
def propose(revision_id: str, inline: bool = typer.Option(False, help="Run now instead of enqueueing")
            ) -> None:
    """Draft wiki proposals from a document revision."""
    from uuid import UUID

    if inline:
        from eb.wiki.jobs import propose_for_revision

        rows = propose_for_revision(UUID(revision_id))
        typer.echo(f"created {len(rows)} proposal(s): " + ", ".join(r["slug"] for r in rows))
    else:
        from eb.jobs import enqueue

        typer.echo(f"job {enqueue('wiki.propose', {'revision_id': str(UUID(revision_id))})}")
