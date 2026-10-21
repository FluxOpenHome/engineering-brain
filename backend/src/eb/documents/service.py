"""Document and revision lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from eb.auth import Principal
from eb.db import connection
from eb.jobs import enqueue
from eb.storage import get_store, object_key, sha256_of

MIME_BY_EXT = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


@dataclass
class UploadResult:
    document_id: UUID
    revision_id: UUID
    duplicate: bool
    job_id: int | None


def guess_mime(filename: str, declared: str | None) -> str:
    if declared and declared != "application/octet-stream":
        return declared
    from pathlib import Path

    return MIME_BY_EXT.get(Path(filename).suffix.lower(), "application/octet-stream")


def upload(
    *,
    data: bytes,
    filename: str,
    mime: str | None,
    user: Principal,
    title: str | None = None,
    doc_number: str | None = None,
    revision: str | None = None,
    doc_type: str = "unknown",
    discipline: list[str] | None = None,
    project: str | None = None,
    group_ids: list[UUID] | None = None,
) -> UploadResult:
    """Store bytes, create document + revision, queue parsing.

    Same bytes under the same doc_number -> no-op duplicate. A new revision of an existing
    doc_number creates a new revision row; it becomes active when indexing completes.
    """
    sha = sha256_of(data)
    key = object_key(sha, filename)
    mime = guess_mime(filename, mime)
    title = title or filename.rsplit(".", 1)[0]

    with connection() as conn:
        dup = conn.execute(
            """
            SELECT r.id AS revision_id, r.document_id FROM document_revisions r
            JOIN documents d ON d.id = r.document_id
            WHERE r.source_sha256 = %s AND (%s::text IS NULL OR d.doc_number = %s)
            LIMIT 1
            """,
            (sha, doc_number, doc_number),
        ).fetchone()
        if dup:
            return UploadResult(dup["document_id"], dup["revision_id"], True, None)

        doc = None
        if doc_number:
            doc = conn.execute(
                "SELECT id FROM documents WHERE doc_number = %s", (doc_number,)
            ).fetchone()
        if doc is None:
            doc = conn.execute(
                """
                INSERT INTO documents (doc_number, title, doc_type, discipline, project, created_by)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
                """,
                (doc_number, title, doc_type, discipline or [], project, user.id),
            ).fetchone()
            everyone = conn.execute("SELECT id FROM groups WHERE name='everyone'").fetchone()["id"]
            for gid in group_ids or [everyone]:
                conn.execute(
                    "INSERT INTO document_acl (document_id, group_id, perm) VALUES (%s, %s, 'read')",
                    (doc["id"], gid),
                )
        if revision is None:
            n = conn.execute(
                "SELECT count(*) AS n FROM document_revisions WHERE document_id = %s", (doc["id"],)
            ).fetchone()["n"]
            revision = str(n)
        rev = conn.execute(
            """
            INSERT INTO document_revisions
              (document_id, revision, source_sha256, storage_key, filename, mime, size_bytes, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """,
            (doc["id"], revision, sha, key, filename, mime, len(data), user.id),
        ).fetchone()
        job_id = enqueue("ingest.parse", {"revision_id": str(rev["id"])}, priority=50, conn=conn)

    get_store().put(key, data)
    return UploadResult(doc["id"], rev["id"], False, job_id)


def get_document(document_id: UUID, user: Principal) -> dict[str, Any] | None:
    with connection() as conn:
        doc = conn.execute(
            """
            SELECT d.*, r.revision AS current_revision, r.status AS revision_status,
                   r.parse_status, r.parse_pass, r.page_count, r.filename, r.mime
            FROM documents d
            LEFT JOIN document_revisions r ON r.id = d.current_revision_id
            WHERE d.id = %s AND EXISTS (
                SELECT 1 FROM document_acl a WHERE a.document_id = d.id AND a.group_id = ANY(%s)
            )
            """,
            (document_id, user.group_ids),
        ).fetchone()
        if doc is None:
            return None
        doc["revisions"] = conn.execute(
            "SELECT id, revision, status, parse_status, parse_pass, page_count, created_at "
            "FROM document_revisions WHERE document_id = %s ORDER BY created_at",
            (document_id,),
        ).fetchall()
    return doc


def list_documents(user: Principal, *, q: str | None = None, project: str | None = None,
                   limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    with connection() as conn:
        return conn.execute(
            """
            SELECT d.id, d.doc_number, d.title, d.doc_type, d.discipline, d.project, d.created_at,
                   r.revision AS current_revision, r.parse_status, r.parse_pass, r.page_count
            FROM documents d
            LEFT JOIN document_revisions r ON r.id = d.current_revision_id
            WHERE EXISTS (SELECT 1 FROM document_acl a WHERE a.document_id = d.id
                          AND a.group_id = ANY(%s))
              AND (%s::text IS NULL OR d.title ILIKE '%%' || %s || '%%'
                   OR d.doc_number ILIKE '%%' || %s || '%%')
              AND (%s::text IS NULL OR d.project = %s)
            ORDER BY d.created_at DESC LIMIT %s OFFSET %s
            """,
            (user.group_ids, q, q, q, project, project, limit, offset),
        ).fetchall()


def delete_document(document_id: UUID, user: Principal) -> bool:
    with connection() as conn:
        row = conn.execute(
            """
            DELETE FROM documents d WHERE d.id = %s AND EXISTS (
                SELECT 1 FROM document_acl a WHERE a.document_id = d.id AND a.group_id = ANY(%s)
                AND a.perm IN ('write','admin')
            ) RETURNING id
            """,
            (document_id, user.group_ids),
        ).fetchone()
    return row is not None
