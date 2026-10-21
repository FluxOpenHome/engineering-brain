"""Hybrid retrieval: keyword (tsvector) + dense (pgvector HNSW) fused with RRF, then rerank.

ACL and revision filters are WHERE clauses evaluated before ranking (principle P2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from pgvector import HalfVector

from eb.auth import Principal
from eb.config import get_settings
from eb.db import connection
from eb.embeddings import get_embedder, get_reranker


@dataclass
class Scope:
    document_ids: list[UUID] | None = None
    revision_ids: list[UUID] | None = None  # explicit revisions (history / compliance subject)
    project: str | None = None
    doc_types: list[str] | None = None
    disciplines: list[str] | None = None
    include_documents: bool = True
    include_wiki: bool = True
    active_only: bool = True


@dataclass
class Hit:
    id: UUID
    source: str  # document | wiki
    text: str
    context_prefix: str
    score: float
    rank_keyword: int | None = None
    rank_dense: int | None = None
    rerank_score: float | None = None
    document_id: UUID | None = None
    revision_id: UUID | None = None
    page_id: UUID | None = None
    title: str = ""
    doc_number: str | None = None
    revision: str | None = None
    section_path: list[str] = field(default_factory=list)
    clause_id: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    kind: str = "text"

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        for k in ("id", "document_id", "revision_id", "page_id"):
            if d[k] is not None:
                d[k] = str(d[k])
        return d


def _doc_filters(scope: Scope, user: Principal) -> tuple[str, list[Any]]:
    where = [
        "EXISTS (SELECT 1 FROM document_acl a WHERE a.document_id = c.document_id "
        "AND a.group_id = ANY(%s))"
    ]
    args: list[Any] = [user.group_ids]
    if scope.revision_ids:
        where.append("c.revision_id = ANY(%s)")
        args.append(scope.revision_ids)
    elif scope.active_only:
        where.append("r.status = 'active'")
    if scope.document_ids:
        where.append("c.document_id = ANY(%s)")
        args.append(scope.document_ids)
    if scope.project:
        where.append("d.project = %s")
        args.append(scope.project)
    if scope.doc_types:
        where.append("d.doc_type = ANY(%s)")
        args.append(scope.doc_types)
    if scope.disciplines:
        where.append("d.discipline && %s")
        args.append(scope.disciplines)
    return " AND ".join(where), args


_DOC_COLS = """
    c.id, c.text, c.context_prefix, c.document_id, c.revision_id, c.section_path,
    c.clause_id, c.page_start, c.page_end, c.kind::text AS kind,
    d.title, d.doc_number, r.revision
"""
_DOC_FROM = """
    FROM chunks c
    JOIN document_revisions r ON r.id = c.revision_id
    JOIN documents d ON d.id = c.document_id
"""

_WIKI_COLS = "c.id, c.text, c.context_prefix, c.page_id, c.section_path, p.title, p.slug"
_WIKI_FROM = " FROM wiki_chunks c JOIN wiki_pages p ON p.id = c.page_id WHERE p.status = 'published'"


def _keyword(conn, query: str, scope: Scope, user: Principal, k: int) -> list[dict]:
    """Keyword candidates. First pass ANDs all terms (websearch syntax); if that yields fewer
    than k/4 hits (typical for natural-language questions), a second pass ORs the terms so a
    question like "How fast must the valve close?" still reaches the clause about valve closure."""
    hits: list[dict] = []
    for tsq in ("websearch_to_tsquery('english', %s)",
                "replace(plainto_tsquery('english', %s)::text, '&', '|')::tsquery"):
        seen = {h["id"] for h in hits}
        if scope.include_documents:
            where, args = _doc_filters(scope, user)
            rows = conn.execute(
                f"SELECT {_DOC_COLS} {_DOC_FROM} WHERE {where} AND c.tsv @@ {tsq}"
                f" ORDER BY ts_rank_cd(c.tsv, {tsq}) DESC LIMIT %s",
                (*args, query, query, k),
            ).fetchall()
            hits += [dict(r, source="document") for r in rows if r["id"] not in seen]
        if scope.include_wiki:
            rows = conn.execute(
                f"SELECT {_WIKI_COLS} {_WIKI_FROM} AND c.tsv @@ {tsq}"
                f" ORDER BY ts_rank_cd(c.tsv, {tsq}) DESC LIMIT %s",
                (query, query, k),
            ).fetchall()
            hits += [dict(r, source="wiki") for r in rows if r["id"] not in seen]
        if len(hits) >= max(1, k // 4):
            break
    return hits[:k]


def _dense(conn, qvec: list[float], scope: Scope, user: Principal, k: int) -> list[dict]:
    hits: list[dict] = []
    v = HalfVector(qvec)
    conn.execute("SET LOCAL hnsw.ef_search = 200")
    conn.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")
    if scope.include_documents:
        where, args = _doc_filters(scope, user)
        rows = conn.execute(
            f"SELECT {_DOC_COLS}, (c.embedding <=> %s) AS dist {_DOC_FROM} WHERE {where}"
            " AND c.embedding IS NOT NULL ORDER BY c.embedding <=> %s LIMIT %s",
            (v, *args, v, k),
        ).fetchall()
        hits += [dict(r, source="document") for r in rows]
    if scope.include_wiki:
        rows = conn.execute(
            f"SELECT {_WIKI_COLS}, (c.embedding <=> %s) AS dist {_WIKI_FROM}"
            " AND c.embedding IS NOT NULL ORDER BY c.embedding <=> %s LIMIT %s",
            (v, v, k),
        ).fetchall()
        hits += [dict(r, source="wiki") for r in rows]
    return hits


def _to_hit(r: dict) -> Hit:
    return Hit(
        id=r["id"], source=r["source"], text=r["text"], context_prefix=r["context_prefix"],
        score=0.0, document_id=r.get("document_id"), revision_id=r.get("revision_id"),
        page_id=r.get("page_id"), title=r.get("title", ""), doc_number=r.get("doc_number"),
        revision=r.get("revision"), section_path=list(r.get("section_path") or []),
        clause_id=r.get("clause_id"), page_start=r.get("page_start"), page_end=r.get("page_end"),
        kind=r.get("kind", "text"),
    )


def search(query: str, *, user: Principal, scope: Scope | None = None, k: int = 20,
           candidates: int | None = None, rerank: bool | None = None) -> list[Hit]:
    """Hybrid search returning the top-k fused (and optionally reranked) hits."""
    s = get_settings()
    scope = scope or Scope()
    n = candidates or s.rerank_candidates
    qvec = get_embedder().embed([query])[0]
    with connection() as conn:
        kw = _keyword(conn, query, scope, user, n)
        dn = _dense(conn, qvec, scope, user, n)

    # Reciprocal rank fusion. k=60 is the standard constant.
    fused: dict[UUID, Hit] = {}
    for rank, r in enumerate(kw, start=1):
        h = fused.setdefault(r["id"], _to_hit(r))
        h.rank_keyword = rank
        h.score += 1.0 / (60 + rank)
    for rank, r in enumerate(dn, start=1):
        h = fused.setdefault(r["id"], _to_hit(r))
        h.rank_dense = rank
        h.score += 1.0 / (60 + rank)
    ranked = sorted(fused.values(), key=lambda h: h.score, reverse=True)[:n]

    reranker = get_reranker() if (rerank if rerank is not None else True) else None
    if reranker and ranked:
        scores = reranker.rerank(query, [f"{h.context_prefix}\n{h.text}" for h in ranked])
        for h, sc in zip(ranked, scores, strict=True):
            h.rerank_score = sc
        ranked.sort(key=lambda h: h.rerank_score or 0.0, reverse=True)
    return ranked[:k]
