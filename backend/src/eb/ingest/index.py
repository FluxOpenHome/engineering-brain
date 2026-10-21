"""Embed chunks and write them to Postgres; activate the revision atomically."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from pgvector import HalfVector

from eb.db import connection
from eb.embeddings import get_embedder
from eb.ingest.chunk import Chunk

log = structlog.get_logger(__name__)


def embed_chunks(chunks: list[Chunk]) -> list[list[float]]:
    emb = get_embedder()
    texts = [f"{c.context_prefix}\n{c.text}" if c.context_prefix else c.text for c in chunks]
    return emb.embed(texts) if texts else []


def write_chunks(revision_id: UUID, document_id: UUID, chunks: list[Chunk],
                 vectors: list[list[float]], *, conn) -> int:
    model = get_embedder().model_name
    conn.execute("DELETE FROM chunks WHERE revision_id = %s", (revision_id,))
    rows: list[tuple[Any, ...]] = []
    for c, v in zip(chunks, vectors, strict=True):
        rows.append(
            (
                document_id, revision_id, c.ordinal, c.kind, c.section_path, c.clause_id,
                c.page_start, c.page_end, None if c.bbox is None else __import__("json").dumps(c.bbox),
                c.text, c.context_prefix, c.token_count, c.content_hash, HalfVector(v), model,
            )
        )
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO chunks (document_id, revision_id, ordinal, kind, section_path, clause_id,
                                page_start, page_end, bbox, text, context_prefix, token_count,
                                content_hash, embedding, embedding_model)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
    return len(rows)


def activate_revision(revision_id: UUID, document_id: UUID, *, conn) -> None:
    """Make this revision current; supersede the previous active one. One transaction."""
    prev = conn.execute(
        "SELECT current_revision_id FROM documents WHERE id = %s", (document_id,)
    ).fetchone()["current_revision_id"]
    if prev and prev != revision_id:
        conn.execute(
            "UPDATE document_revisions SET status='superseded', superseded_by_id=%s "
            "WHERE id = %s AND status = 'active'",
            (revision_id, prev),
        )
    conn.execute(
        "UPDATE document_revisions SET status='active' WHERE id = %s", (revision_id,)
    )
    conn.execute(
        "UPDATE documents SET current_revision_id = %s, updated_at = now() WHERE id = %s",
        (revision_id, document_id),
    )


def index_revision(revision_id: UUID, chunks: list[Chunk], *, parse_pass: str,
                   page_count: int | None, title: str | None = None) -> int:
    vectors = embed_chunks(chunks)
    with connection() as conn:
        rev = conn.execute(
            "SELECT document_id FROM document_revisions WHERE id = %s", (revision_id,)
        ).fetchone()
        n = write_chunks(revision_id, rev["document_id"], chunks, vectors, conn=conn)
        conn.execute(
            """
            UPDATE document_revisions
            SET parse_status='done', parse_pass=%s, page_count=%s, parsed_at=now(), parse_error=NULL
            WHERE id = %s
            """,
            (parse_pass, page_count, revision_id),
        )
        if title:
            conn.execute(
                "UPDATE documents SET title = %s WHERE id = %s AND (title = '' OR title = %s)",
                (title, rev["document_id"], title),
            )
        activate_revision(revision_id, rev["document_id"], conn=conn)
    log.info("index.done", revision_id=str(revision_id), chunks=n, parse_pass=parse_pass)
    return n
