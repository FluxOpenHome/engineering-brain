from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field

from eb.auth import CurrentUser, Principal
from eb.retrieval.search import Scope, search

router = APIRouter(prefix="/search", tags=["search"])


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    k: int = Field(default=20, ge=1, le=100)
    document_ids: list[UUID] | None = None
    revision_ids: list[UUID] | None = None
    project: str | None = None
    doc_types: list[str] | None = None
    disciplines: list[str] | None = None
    include_documents: bool = True
    include_wiki: bool = True
    active_only: bool = True


@router.post("")
def search_endpoint(req: SearchRequest, user: Principal = CurrentUser) -> dict[str, Any]:
    scope = Scope(
        document_ids=req.document_ids, revision_ids=req.revision_ids, project=req.project,
        doc_types=req.doc_types, disciplines=req.disciplines,
        include_documents=req.include_documents, include_wiki=req.include_wiki,
        active_only=req.active_only,
    )
    hits = search(req.query, user=user, scope=scope, k=req.k)
    return {"query": req.query, "hits": [h.to_dict() for h in hits]}
