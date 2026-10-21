from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from eb.auth import CurrentUser, Principal
from eb.chat.answer import answer, answer_stream
from eb.db import connection
from eb.retrieval.search import Scope

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=8000)
    conversation_id: UUID | None = None
    document_ids: list[UUID] | None = None
    revision_ids: list[UUID] | None = None
    project: str | None = None
    doc_types: list[str] | None = None
    disciplines: list[str] | None = None
    include_documents: bool = True
    include_wiki: bool = True
    k: int | None = Field(default=None, ge=1, le=50)
    model: str | None = None


def _scope(req: ChatRequest) -> Scope:
    return Scope(document_ids=req.document_ids, revision_ids=req.revision_ids,
                 project=req.project, doc_types=req.doc_types, disciplines=req.disciplines,
                 include_documents=req.include_documents, include_wiki=req.include_wiki)


def _load_or_create_conversation(req: ChatRequest, user: Principal) -> tuple[UUID, list[dict]]:
    with connection() as conn:
        if req.conversation_id:
            row = conn.execute(
                "SELECT id FROM conversations WHERE id=%s AND user_id=%s",
                (req.conversation_id, user.id),
            ).fetchone()
            if row:
                hist = conn.execute(
                    "SELECT role, content FROM messages WHERE conversation_id=%s "
                    "ORDER BY created_at",
                    (req.conversation_id,),
                ).fetchall()
                return row["id"], [dict(h) for h in hist]
        row = conn.execute(
            "INSERT INTO conversations (user_id, title, scope) VALUES (%s, %s, %s::jsonb) "
            "RETURNING id",
            (user.id, req.question[:120], json.dumps(_scope(req).__dict__, default=str)),
        ).fetchone()
        return row["id"], []


def _save(conversation_id: UUID, question: str, text: str, citations: list[dict],
          usage: dict) -> None:
    with connection() as conn:
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES (%s, 'user', %s)",
            (conversation_id, question),
        )
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, citations, usage) "
            "VALUES (%s, 'assistant', %s, %s::jsonb, %s::jsonb)",
            (conversation_id, text, json.dumps(citations), json.dumps(usage)),
        )


@router.post("")
def chat(req: ChatRequest, user: Principal = CurrentUser) -> dict[str, Any]:
    conv_id, history = _load_or_create_conversation(req, user)
    a = answer(req.question, user=user, scope=_scope(req), history=history, k=req.k,
               model=req.model)
    cites = [c.to_dict() for c in a.citations]
    _save(conv_id, req.question, a.text, cites, a.usage)
    return {"conversation_id": str(conv_id), "answer": a.text, "citations": cites,
            "sources": [h.to_dict() for h in a.hits], "usage": a.usage, "model": a.model}


@router.post("/stream")
def chat_stream(req: ChatRequest, user: Principal = CurrentUser):
    conv_id, history = _load_or_create_conversation(req, user)

    def gen():
        yield {"event": "conversation", "data": json.dumps({"conversation_id": str(conv_id)})}
        text_parts: list[str] = []
        for ev in answer_stream(req.question, user=user, scope=_scope(req), history=history,
                                k=req.k, model=req.model):
            if ev["event"] == "delta":
                text_parts.append(ev["data"])
                yield {"event": "delta", "data": json.dumps({"text": ev["data"]})}
            elif ev["event"] == "done":
                _save(conv_id, req.question, "".join(text_parts), ev["data"]["citations"],
                      ev["data"].get("usage", {}))
                yield {"event": "done", "data": json.dumps(ev["data"], default=str)}
            else:
                yield {"event": ev["event"], "data": json.dumps(ev["data"], default=str)}

    return EventSourceResponse(gen())


@router.get("/conversations")
def list_conversations(user: Principal = CurrentUser) -> list[dict[str, Any]]:
    with connection() as conn:
        return conn.execute(
            "SELECT id, title, created_at FROM conversations WHERE user_id=%s "
            "ORDER BY created_at DESC LIMIT 100",
            (user.id,),
        ).fetchall()


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: UUID, user: Principal = CurrentUser) -> dict[str, Any]:
    with connection() as conn:
        conv = conn.execute(
            "SELECT id, title, scope, created_at FROM conversations WHERE id=%s AND user_id=%s",
            (conversation_id, user.id),
        ).fetchone()
        msgs = conn.execute(
            "SELECT id, role, content, citations, usage, created_at FROM messages "
            "WHERE conversation_id=%s ORDER BY created_at",
            (conversation_id,),
        ).fetchall()
    return {"conversation": conv, "messages": msgs}
