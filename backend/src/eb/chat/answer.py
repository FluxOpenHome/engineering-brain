"""Cited question answering over retrieved chunks (architecture 6.3)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from eb.auth import Principal
from eb.config import get_settings
from eb.llm import Completion, DocumentBlock, TextPart, get_llm
from eb.retrieval.search import Hit, Scope, search

SYSTEM_PROMPT = """You are Engineering Brain, an assistant for a multi-disciplinary engineering \
organisation (fluid systems, electrical, civil, structural, mechanical, chemical, materials).

Answer only from the provided sources. Cite the sources for every factual statement. Quote \
numbers, units, tolerances, clause identifiers and revision identifiers exactly as written in \
the source. If the sources do not contain the answer, say so plainly and say what document or \
information would be needed; never guess. When sources disagree (for example different \
revisions of the same document), say which is current and show both values. Keep answers \
concise and technical. Use SI units as written in the source; do not convert unless asked."""


@dataclass
class CitationOut:
    index: int
    chunk_id: str
    source: str
    title: str
    doc_number: str | None
    revision: str | None
    clause_id: str | None
    page_start: int | None
    page_end: int | None
    section_path: list[str]
    cited_text: str
    document_id: str | None = None
    page_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class Answer:
    text: str
    citations: list[CitationOut]
    hits: list[Hit]
    usage: dict[str, int] = field(default_factory=dict)
    model: str = ""


def _doc_title(h: Hit) -> str:
    bits = [h.doc_number or "", h.title or ""]
    if h.revision:
        bits.append(f"Rev {h.revision}")
    if h.clause_id:
        bits.append(f"clause {h.clause_id}")
    if h.page_start:
        bits.append(f"p.{h.page_start}")
    return " ".join(b for b in bits if b).strip() or h.source


def build_documents(hits: list[Hit]) -> list[DocumentBlock]:
    return [DocumentBlock(text=f"{h.context_prefix}\n{h.text}".strip(), title=_doc_title(h))
            for h in hits]


def _map_citations(parts: list[TextPart], hits: list[Hit]) -> list[CitationOut]:
    out: list[CitationOut] = []
    seen: set[tuple[int, str]] = set()
    for p in parts:
        for c in p.citations:
            if c.document_index >= len(hits):
                continue
            key = (c.document_index, c.cited_text[:80])
            if key in seen:
                continue
            seen.add(key)
            h = hits[c.document_index]
            out.append(
                CitationOut(
                    index=c.document_index, chunk_id=str(h.id), source=h.source, title=h.title,
                    doc_number=h.doc_number, revision=h.revision, clause_id=h.clause_id,
                    page_start=h.page_start, page_end=h.page_end, section_path=h.section_path,
                    cited_text=c.cited_text,
                    document_id=str(h.document_id) if h.document_id else None,
                    page_id=str(h.page_id) if h.page_id else None,
                )
            )
    return out


def _question_with_history(question: str, history: list[dict[str, str]] | None) -> str:
    if not history:
        return question
    lines = ["Conversation so far:"]
    for m in history[-8:]:
        lines.append(f"{m['role']}: {m['content'][:1500]}")
    lines.append("")
    lines.append(f"Current question: {question}")
    return "\n".join(lines)


def answer(question: str, *, user: Principal, scope: Scope | None = None,
           history: list[dict[str, str]] | None = None, k: int | None = None,
           model: str | None = None) -> Answer:
    s = get_settings()
    hits = search(question, user=user, scope=scope, k=k or s.rerank_top_k)
    if not hits:
        return Answer(text="No relevant sources were found for that question in the "
                      "documents you can access.", citations=[], hits=[])
    comp = get_llm().complete(
        system=SYSTEM_PROMPT, user=_question_with_history(question, history),
        documents=build_documents(hits), model=model or s.llm_model_answer,
    )
    return Answer(text=comp.text, citations=_map_citations(comp.parts, hits), hits=hits,
                  usage=comp.usage, model=comp.model)


def answer_stream(question: str, *, user: Principal, scope: Scope | None = None,
                  history: list[dict[str, str]] | None = None, k: int | None = None,
                  model: str | None = None) -> Iterator[dict[str, Any]]:
    """Yield SSE-ready events: sources, delta..., done."""
    s = get_settings()
    hits = search(question, user=user, scope=scope, k=k or s.rerank_top_k)
    yield {"event": "sources", "data": [h.to_dict() for h in hits]}
    if not hits:
        yield {"event": "delta", "data": "No relevant sources were found for that question."}
        yield {"event": "done", "data": {"citations": [], "usage": {}}}
        return
    final: Completion | None = None
    for item in get_llm().stream(system=SYSTEM_PROMPT,
                                 user=_question_with_history(question, history),
                                 documents=build_documents(hits),
                                 model=model or s.llm_model_answer):
        if isinstance(item, Completion):
            final = item
        else:
            yield {"event": "delta", "data": item.text}
    cites = _map_citations(final.parts, hits) if final else []
    yield {"event": "done", "data": {"citations": [c.to_dict() for c in cites],
                                     "usage": final.usage if final else {},
                                     "model": final.model if final else ""}}
