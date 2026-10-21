"""HTTP API for specification authoring: templates, requirement rule checks, drafts."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from eb.auth import CurrentUser, Principal
from eb.specs import rules
from eb.specs.draft import draft_spec
from eb.specs.templates import list_templates

router = APIRouter(prefix="/specs", tags=["specs"])


class CheckIn(BaseModel):
    text: str = Field(min_length=1, max_length=200_000)


class DraftIn(BaseModel):
    template_key: str
    project: str | None = None
    context: str | None = None
    document_ids: list[UUID] | None = None


@router.get("/templates")
def templates(user: Principal = CurrentUser) -> list[dict[str, Any]]:
    return list_templates()


@router.post("/check")
def check(body: CheckIn, user: Principal = CurrentUser) -> dict[str, Any]:
    results = rules.check_text(body.text)
    return {"requirements": results, "summary": rules.summarise(results)}


@router.post("/draft")
def draft(body: DraftIn, user: Principal = CurrentUser) -> dict[str, Any]:
    try:
        return draft_spec(
            body.template_key,
            user,
            project=body.project,
            context=body.context,
            document_ids=body.document_ids,
        )
    except KeyError as e:
        raise HTTPException(404, str(e.args[0]) if e.args else "unknown template") from e
