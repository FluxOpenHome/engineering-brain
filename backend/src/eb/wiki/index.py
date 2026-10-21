"""Chunk, embed and index published wiki pages into `wiki_chunks` (architecture P4).

Only pages with status=published get chunks. Removing a page's chunks is immediate and
unconditional on archive, because a citation to text a reviewer never approved (or retired)
is the worst failure the wiki can have.
"""

from __future__ import annotations

from uuid import UUID

import structlog
from pgvector import HalfVector

from eb.db import connection
from eb.embeddings import get_embedder
from eb.ingest.chunk import chunk_document
from eb.ingest.parse import parse_markdown_or_text
from eb.wiki.store import content_hash

log = structlog.get_logger(__name__)


def wiki_chunks_for(title: str, body: str):
    """Chunk a page body with the shared structure-aware chunker.

    The context prefix comes out as "Wiki: <title> > <section path>", which is embedded and
    keyword-indexed with each chunk's text.
    """
    parsed = parse_markdown_or_text(body.encode("utf-8"))
    return chunk_document(parsed, {"title": f"Wiki: {title}"})


def unindex_page(page_id: UUID, *, conn=None) -> int:
    sql = "DELETE FROM wiki_chunks WHERE page_id = %s"
    if conn is not None:
        return conn.execute(sql, (page_id,)).rowcount
    with connection() as c:
        n = c.execute(sql, (page_id,)).rowcount
    log.info("wiki.unindex", page_id=str(page_id), removed=n)
    return n


def index_page(page_id: UUID, slug: str, title: str, body: str, *, force: bool = False) -> int:
    """Replace the page's wiki_chunks rows in one transaction. Returns the number of chunks.

    Hash-gated: when `wiki_pages.content_hash` already equals the body hash and chunks exist,
    nothing is re-embedded. The row's content_hash is updated here, after the chunks are
    written, so a crash between the two cannot leave a stale index that looks current.
    Pages that are not published get their chunks removed instead.
    """
    new_hash = content_hash(body)
    with connection() as conn:
        row = conn.execute(
            "SELECT status::text AS status, content_hash FROM wiki_pages WHERE id = %s", (page_id,)
        ).fetchone()
        if row is None:
            raise RuntimeError(f"wiki page {page_id} ({slug}) has no wiki_pages row")
        existing = conn.execute(
            "SELECT count(*) AS n FROM wiki_chunks WHERE page_id = %s", (page_id,)
        ).fetchone()["n"]
        if row["status"] != "published":
            unindex_page(page_id, conn=conn)
            conn.execute(
                "UPDATE wiki_pages SET content_hash = %s WHERE id = %s", (new_hash, page_id)
            )
            log.info("wiki.index.skip_unpublished", slug=slug, status=row["status"], removed=existing)
            return 0
        if not force and row["content_hash"] == new_hash and existing > 0:
            log.debug("wiki.index.unchanged", slug=slug, chunks=existing)
            return existing

    chunks = wiki_chunks_for(title, body)
    emb = get_embedder()
    vectors = emb.embed([f"{c.context_prefix}\n{c.text}" for c in chunks]) if chunks else []

    with connection() as conn:
        conn.execute("DELETE FROM wiki_chunks WHERE page_id = %s", (page_id,))
        rows = [
            (page_id, c.ordinal, c.section_path, c.text, c.context_prefix, c.token_count,
             c.content_hash, HalfVector(v), emb.model_name)
            for c, v in zip(chunks, vectors, strict=True)
        ]
        if rows:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO wiki_chunks (page_id, ordinal, section_path, text, context_prefix,
                                             token_count, content_hash, embedding, embedding_model)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    rows,
                )
        conn.execute(
            "UPDATE wiki_pages SET content_hash = %s, updated_at = now() WHERE id = %s",
            (new_hash, page_id),
        )
    log.info("wiki.index", slug=slug, chunks=len(rows))
    return len(rows)
