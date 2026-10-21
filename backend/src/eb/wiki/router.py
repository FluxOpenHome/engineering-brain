"""HTTP API for the wiki: pages (human edits publish immediately), proposals (review queue),
and maintenance jobs."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from eb.auth import CurrentUser, Principal
from eb.jobs import enqueue
from eb.wiki import service
from eb.wiki.store import SlugError, validate_slug

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/wiki", tags=["wiki"])


class PageIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(max_length=2_000_000)
    discipline: list[str] | None = None
    tags: list[str] | None = None
    message: str | None = Field(default=None, max_length=500)


class AcceptIn(BaseModel):
    content: str | None = Field(default=None, max_length=2_000_000)
    note: str | None = Field(default=None, max_length=5000)


class RejectIn(BaseModel):
    note: str | None = Field(default=None, max_length=5000)


class ProposeIn(BaseModel):
    revision_id: UUID


def _slug(slug: str) -> str:
    try:
        return validate_slug(slug)
    except SlugError as e:
        raise HTTPException(422, str(e)) from e


# ------------------------------------------------------------------------------ pages


@router.get("/pages")
def list_pages(q: str | None = None, status: str | None = None, discipline: str | None = None,
               user: Principal = CurrentUser) -> list[dict[str, Any]]:
    if status is not None and status not in ("proposed", "published", "stale", "archived"):
        raise HTTPException(422, "status must be one of proposed|published|stale|archived")
    return service.list_pages(q=q, status=status, discipline=discipline)


@router.get("/tree")
def tree(user: Principal = CurrentUser) -> list[dict[str, Any]]:
    return service.tree()


@router.get("/pages/{slug:path}")
def get_page(slug: str, user: Principal = CurrentUser) -> dict[str, Any]:
    page = service.get_page(_slug(slug))
    if page is None:
        raise HTTPException(404, "page not found")
    return page


@router.put("/pages/{slug:path}")
def put_page(slug: str, body: PageIn, user: Principal = CurrentUser) -> dict[str, Any]:
    return service.save_page(_slug(slug), body.title, body.content, user, discipline=body.discipline,
                             tags=body.tags, message=body.message)


@router.delete("/pages/{slug:path}", status_code=204)
def delete_page(slug: str, user: Principal = CurrentUser) -> Response:
    if not service.archive_page(_slug(slug), user):
        raise HTTPException(404, "page not found")
    return Response(status_code=204)


# ------------------------------------------------------------------------------ proposals


@router.get("/proposals")
def list_proposals(status: str | None = "open", user: Principal = CurrentUser) -> list[dict[str, Any]]:
    if status in ("", "all"):
        status = None
    if status is not None and status not in ("open", "accepted", "rejected", "superseded"):
        raise HTTPException(422, "status must be one of open|accepted|rejected|superseded|all")
    return service.list_proposals(status)


@router.get("/proposals/{proposal_id}")
def get_proposal(proposal_id: UUID, user: Principal = CurrentUser) -> dict[str, Any]:
    try:
        return service.get_proposal(proposal_id)
    except service.NotFound as e:
        raise HTTPException(404, str(e)) from e


@router.post("/proposals/{proposal_id}/accept")
def accept_proposal(proposal_id: UUID, body: AcceptIn | None = None,
                    user: Principal = CurrentUser) -> dict[str, Any]:
    body = body or AcceptIn()
    try:
        return service.accept_proposal(proposal_id, user, content_override=body.content, note=body.note)
    except service.NotFound as e:
        raise HTTPException(404, str(e)) from e
    except service.Conflict as e:
        raise HTTPException(409, str(e)) from e
    except SlugError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: UUID, body: RejectIn | None = None,
                    user: Principal = CurrentUser) -> dict[str, Any]:
    body = body or RejectIn()
    try:
        service.reject_proposal(proposal_id, user, body.note)
    except service.NotFound as e:
        raise HTTPException(404, str(e)) from e
    except service.Conflict as e:
        raise HTTPException(409, str(e)) from e
    return {"ok": True}


# ------------------------------------------------------------------------------ jobs & lint


@router.post("/propose")
def propose(body: ProposeIn, user: Principal = CurrentUser) -> dict[str, Any]:
    job_id = enqueue("wiki.propose", {"revision_id": str(body.revision_id)}, priority=150)
    log.info("wiki.propose.enqueued", job_id=job_id, revision_id=str(body.revision_id), user=user.email)
    return {"job_id": job_id}


@router.post("/reindex")
def reindex(user: Principal = CurrentUser) -> dict[str, Any]:
    job_id = enqueue("wiki.reindex", {"all": True}, priority=150)
    return {"job_id": job_id}


@router.get("/lint")
def lint(user: Principal = CurrentUser) -> dict[str, Any]:
    return service.lint()
