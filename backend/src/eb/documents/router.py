from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from eb.auth import CurrentUser, Principal
from eb.documents import service

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    doc_number: str | None = Form(None),
    revision: str | None = Form(None),
    doc_type: str = Form("unknown"),
    discipline: str = Form(""),
    project: str | None = Form(None),
    user: Principal = CurrentUser,
) -> dict[str, Any]:
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty file")
    res = service.upload(
        data=data,
        filename=file.filename or "upload",
        mime=file.content_type,
        user=user,
        title=title,
        doc_number=doc_number,
        revision=revision,
        doc_type=doc_type,
        discipline=[d.strip() for d in discipline.split(",") if d.strip()],
        project=project,
    )
    return {
        "document_id": str(res.document_id),
        "revision_id": str(res.revision_id),
        "duplicate": res.duplicate,
        "job_id": res.job_id,
    }


@router.get("")
def list_documents(q: str | None = None, project: str | None = None, limit: int = 50,
                   offset: int = 0, user: Principal = CurrentUser) -> list[dict[str, Any]]:
    return service.list_documents(user, q=q, project=project, limit=limit, offset=offset)


@router.get("/{document_id}")
def get_document(document_id: UUID, user: Principal = CurrentUser) -> dict[str, Any]:
    doc = service.get_document(document_id, user)
    if doc is None:
        raise HTTPException(404, "document not found")
    return doc


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: UUID, user: Principal = CurrentUser) -> None:
    if not service.delete_document(document_id, user):
        raise HTTPException(404, "document not found or not permitted")
