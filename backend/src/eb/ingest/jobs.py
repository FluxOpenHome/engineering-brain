"""Ingest job handlers."""

from __future__ import annotations

from uuid import UUID

import structlog

from eb.config import get_settings
from eb.db import connection
from eb.ingest.chunk import chunk_document
from eb.ingest.index import index_revision
from eb.ingest.parse import parse_bytes
from eb.jobs import enqueue, has_handler, job
from eb.storage import get_store

log = structlog.get_logger(__name__)


def ingest_revision(revision_id: UUID) -> int:
    s = get_settings()
    with connection() as conn:
        rev = conn.execute(
            """
            SELECT r.id, r.document_id, r.revision, r.storage_key, r.filename, r.mime,
                   d.doc_number, d.title
            FROM document_revisions r JOIN documents d ON d.id = r.document_id
            WHERE r.id = %s
            """,
            (revision_id,),
        ).fetchone()
        if rev is None:
            raise RuntimeError(f"revision {revision_id} not found")
        conn.execute(
            "UPDATE document_revisions SET parse_status='running' WHERE id = %s", (revision_id,)
        )
    data = get_store().get(rev["storage_key"])
    parsed = parse_bytes(data, rev["filename"], rev["mime"])
    meta = {"doc_number": rev["doc_number"], "title": rev["title"], "revision": rev["revision"]}
    chunks = chunk_document(parsed, meta, target_tokens=s.chunk_target_tokens,
                            max_tokens=s.chunk_max_tokens)
    n = index_revision(revision_id, chunks, parse_pass=parsed.parse_pass,
                       page_count=parsed.page_count)
    return n


@job("ingest.parse")
def handle_parse(payload: dict) -> None:
    revision_id = UUID(payload["revision_id"])
    try:
        ingest_revision(revision_id)
    except Exception as e:
        with connection() as conn:
            conn.execute(
                "UPDATE document_revisions SET parse_status='failed', parse_error=%s WHERE id=%s",
                (str(e)[:2000], revision_id),
            )
        raise
    # Downstream: propose wiki updates for the newly active revision (when the wiki module exists).
    if has_handler("wiki.propose"):
        enqueue("wiki.propose", {"revision_id": str(revision_id)}, priority=200)
