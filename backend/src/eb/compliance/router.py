"""HTTP API for requirement sets, compliance runs, findings and the matrix export."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from eb.auth import CurrentUser, Principal
from eb.compliance import requirements as reqs
from eb.compliance.export import export_xlsx
from eb.compliance.models import ExtractIn, RequirementSetIn, RequirementsIn, ReviewIn, RunIn
from eb.db import connection
from eb.jobs import enqueue

router = APIRouter(prefix="/compliance", tags=["compliance"])


def _uuid(value: str, what: str) -> UUID:
    try:
        return UUID(str(value))
    except ValueError as e:
        raise HTTPException(422, f"invalid {what}") from e


def _readable_document(conn, document_id: UUID, user: Principal) -> dict[str, Any]:
    doc = conn.execute(
        """
        SELECT d.id, d.current_revision_id FROM documents d
        WHERE d.id = %s AND EXISTS (SELECT 1 FROM document_acl a WHERE a.document_id = d.id
                                    AND a.group_id = ANY(%s))
        """,
        (document_id, user.group_ids),
    ).fetchone()
    if doc is None:
        raise HTTPException(404, "document not found")
    return doc


_RUN_ACL = """
    EXISTS (SELECT 1 FROM document_acl a WHERE a.document_id = r.subject_document_id
            AND a.group_id = ANY(%s))
"""

_RUN_SELECT = """
    SELECT r.*, s.name AS set_name, d.doc_number AS subject_doc_number, d.title AS subject_title,
           rev.revision AS subject_revision,
           (SELECT count(*) FROM compliance_findings f WHERE f.run_id = r.id) AS finding_count
    FROM compliance_runs r
    JOIN requirement_sets s ON s.id = r.set_id
    JOIN documents d ON d.id = r.subject_document_id
    JOIN document_revisions rev ON rev.id = r.subject_revision_id
"""

_FINDING_SELECT = """
    SELECT f.id, f.run_id, f.verdict, f.llm_verdict, f.confidence, f.evidence, f.numeric_check, f.rationale,
           f.needs_review, f.reviewer_verdict, f.reviewer_note, f.reviewed_by, f.reviewed_at,
           q.id AS requirement_id, q.req_id, q.text AS requirement_text, q.kind::text AS requirement_kind,
           q.quantity
    FROM compliance_findings f JOIN requirements q ON q.id = f.requirement_id
"""


def _finding_out(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "run_id": row["run_id"],
        "requirement": {
            "id": row["requirement_id"],
            "req_id": row["req_id"],
            "text": row["requirement_text"],
            "kind": row["requirement_kind"],
            "quantity": row["quantity"],
        },
        "verdict": row["verdict"],
        "llm_verdict": row["llm_verdict"],
        "confidence": row["confidence"],
        "evidence": row["evidence"],
        "numeric_check": row["numeric_check"],
        "rationale": row["rationale"],
        "needs_review": row["needs_review"],
        "reviewer_verdict": row["reviewer_verdict"],
        "reviewer_note": row["reviewer_note"],
        "reviewed_by": row["reviewed_by"],
        "reviewed_at": row["reviewed_at"],
    }


# ------------------------------------------------------------------------- sets


@router.post("/sets", status_code=201)
def create_set(body: RequirementSetIn, user: Principal = CurrentUser) -> dict[str, Any]:
    return reqs.create_set(body.name, description=body.description, discipline=body.discipline, user=user)


@router.get("/sets")
def list_sets(user: Principal = CurrentUser) -> list[dict[str, Any]]:
    return reqs.list_sets()


@router.get("/sets/{set_id}")
def get_set(set_id: UUID, user: Principal = CurrentUser) -> dict[str, Any]:
    out = reqs.get_set(set_id)
    if out is None:
        raise HTTPException(404, "requirement set not found")
    return out


@router.delete("/sets/{set_id}", status_code=204)
def delete_set(set_id: UUID, user: Principal = CurrentUser) -> None:
    if not reqs.delete_set(set_id):
        raise HTTPException(404, "requirement set not found")


@router.post("/sets/{set_id}/requirements")
def add_requirements(set_id: UUID, body: RequirementsIn, user: Principal = CurrentUser) -> dict[str, Any]:
    try:
        n = reqs.add_requirements(set_id, body.requirements)
    except KeyError as e:
        raise HTTPException(404, "requirement set not found") from e
    return {"added": n}


@router.post("/sets/{set_id}/import")
async def import_requirements(
    set_id: UUID, file: UploadFile = File(...), user: Principal = CurrentUser
) -> dict[str, Any]:
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty file")
    try:
        n = reqs.import_table(set_id, data, file.filename or "requirements.csv")
    except KeyError as e:
        raise HTTPException(404, "requirement set not found") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"added": n}


@router.post("/sets/{set_id}/extract")
def extract_requirements(set_id: UUID, body: ExtractIn, user: Principal = CurrentUser) -> dict[str, Any]:
    document_id = _uuid(body.document_id, "document_id")
    if reqs.get_set(set_id) is None:
        raise HTTPException(404, "requirement set not found")
    try:
        n = reqs.extract_from_document(set_id, document_id, user)
    except KeyError as e:
        raise HTTPException(404, "document not found") from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    return {"added": n}


# ------------------------------------------------------------------------- runs


@router.post("/runs", status_code=201)
def create_run(body: RunIn, user: Principal = CurrentUser) -> dict[str, Any]:
    set_id = _uuid(body.set_id, "set_id")
    document_id = _uuid(body.document_id, "document_id")
    with connection() as conn:
        if conn.execute("SELECT 1 FROM requirement_sets WHERE id = %s", (set_id,)).fetchone() is None:
            raise HTTPException(404, "requirement set not found")
        doc = _readable_document(conn, document_id, user)
        if body.revision_id:
            revision_id = _uuid(body.revision_id, "revision_id")
            rev = conn.execute(
                "SELECT id FROM document_revisions WHERE id = %s AND document_id = %s",
                (revision_id, document_id),
            ).fetchone()
            if rev is None:
                raise HTTPException(404, "revision not found for this document")
        else:
            revision_id = doc["current_revision_id"]
            if revision_id is None:
                raise HTTPException(409, "document has no indexed revision yet")
        run = conn.execute(
            """
            INSERT INTO compliance_runs (set_id, subject_document_id, subject_revision_id, started_by)
            VALUES (%s, %s, %s, %s) RETURNING id
            """,
            (set_id, document_id, revision_id, user.id),
        ).fetchone()
        job_id = enqueue("compliance.run", {"run_id": str(run["id"])}, priority=80, conn=conn)
    return {"run_id": str(run["id"]), "job_id": job_id}


@router.get("/runs")
def list_runs(
    set_id: UUID | None = None, limit: int = 50, user: Principal = CurrentUser
) -> list[dict[str, Any]]:
    with connection() as conn:
        return conn.execute(
            _RUN_SELECT + f" WHERE {_RUN_ACL} AND (%s::uuid IS NULL OR r.set_id = %s)"
            " ORDER BY r.created_at DESC LIMIT %s",
            (user.group_ids, set_id, set_id, min(max(limit, 1), 500)),
        ).fetchall()


@router.get("/runs/{run_id}")
def get_run(run_id: UUID, user: Principal = CurrentUser) -> dict[str, Any]:
    with connection() as conn:
        run = conn.execute(
            _RUN_SELECT + f" WHERE r.id = %s AND {_RUN_ACL}", (run_id, user.group_ids)
        ).fetchone()
        if run is None:
            raise HTTPException(404, "run not found")
        rows = conn.execute(
            _FINDING_SELECT + " WHERE f.run_id = %s ORDER BY q.ordinal, q.created_at, q.req_id", (run_id,)
        ).fetchall()
    return {"run": run, "findings": [_finding_out(r) for r in rows], "summary": run["summary"]}


@router.get("/runs/{run_id}/export.xlsx")
def export_run(run_id: UUID, user: Principal = CurrentUser) -> Response:
    with connection() as conn:
        run = conn.execute(
            f"SELECT r.id FROM compliance_runs r WHERE r.id = %s AND {_RUN_ACL}", (run_id, user.group_ids)
        ).fetchone()
    if run is None:
        raise HTTPException(404, "run not found")
    data = export_xlsx(run_id)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="compliance-{run_id}.xlsx"'},
    )


# ------------------------------------------------------------------------- findings


@router.post("/findings/{finding_id}/review")
def review_finding(finding_id: UUID, body: ReviewIn, user: Principal = CurrentUser) -> dict[str, Any]:
    with connection() as conn:
        row = conn.execute(
            f"""
            SELECT f.id FROM compliance_findings f JOIN compliance_runs r ON r.id = f.run_id
            WHERE f.id = %s AND {_RUN_ACL}
            """,
            (finding_id, user.group_ids),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "finding not found")
        conn.execute(
            """
            UPDATE compliance_findings
            SET reviewer_verdict = %s, reviewer_note = %s, reviewed_by = %s, reviewed_at = now(),
                needs_review = false
            WHERE id = %s
            """,
            (body.verdict, body.note, user.id, finding_id),
        )
        out = conn.execute(_FINDING_SELECT + " WHERE f.id = %s", (finding_id,)).fetchone()
    return _finding_out(out)
