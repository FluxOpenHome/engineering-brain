"""Wiki job handlers: `wiki.propose` drafts review proposals from a document revision;
`wiki.reindex` rebuilds wiki_chunks.

The propose job never writes files and never publishes (architecture 6.4, P3, P4): its only
output is `wiki_proposals(status=open)` rows for a reviewer.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from pydantic import BaseModel, Field

from eb.auth import ensure_user
from eb.config import get_settings
from eb.db import connection
from eb.embeddings import approx_tokens
from eb.jobs import job
from eb.llm import DocumentBlock, get_llm
from eb.retrieval.search import Scope, search
from eb.wiki import service, store
from eb.wiki.index import index_page
from eb.wiki.store import SlugError, validate_slug

log = structlog.get_logger(__name__)

AGENT_EMAIL = "agent@engineering-brain.local"
MAX_CHUNKS = 40
MAX_TOKENS = 12_000
MAX_RELATED_PAGES = 6
MAX_PAGE_CHARS = 8_000
_KIND_PRIORITY = {"requirement": 0, "clause": 1, "table": 2, "text": 3}


class Proposal(BaseModel):
    slug: str = Field(description="Lowercase kebab-case path; folders by discipline, "
                      "e.g. mechanical/centrifugal-pumps")
    kind: str = Field(description="create | update")
    title: str
    content: str = Field(description="Full markdown body of the page, encyclopedia style, with "
                         "footnote citations like [^1] that reference source indices")
    rationale: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source_indices: list[int] = Field(default_factory=list,
                                      description="Indices of the sources this page is built from")
    discipline: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class ProposalBatch(BaseModel):
    proposals: list[Proposal] = Field(default_factory=list)


SYSTEM_PROMPT = """You are the wiki editor of Engineering Brain, an internal knowledge base for a \
multi-disciplinary engineering organisation (fluid systems, electrical, civil, structural, \
mechanical, chemical, materials). You draft and update wiki pages from newly ingested documents. \
Every draft goes to a human reviewer; nothing you write is published without review.

Write for engineers. Encyclopedia style: a short lead that defines the topic, then sections with \
headings; tables for parameters. Be precise and terse.

Rules:
- Keep every fact traceable. Each factual statement carries a footnote citation like [^1] whose \
number is the index of the source it came from (the sources are numbered from 0 in the order \
given). List the footnotes at the end of the page as "[^n]: <document number or title>, \
<clause or page>". Put every source index you used in source_indices.
- Include numbers, units, tolerances, clause identifiers and revision identifiers exactly as they \
appear in the sources. Never convert units. Never round.
- Do not invent. If the sources do not state something, leave it out. Do not fill gaps from \
general knowledge; a reviewer cannot verify what has no source.
- One page per equipment class, system, standard or topic. Prefer updating an existing related \
page (kind=update, same slug, return the complete revised body) over creating a near-duplicate. \
When updating, preserve the existing content that is still correct and integrate the new facts.
- Create a new page (kind=create) only for a topic the existing pages do not cover. Slugs are \
lowercase kebab-case with a discipline folder, e.g. "mechanical/centrifugal-pumps", \
"electrical/lv-motors", "standards/iso-9906".
- Pages describe engineering knowledge (what a thing is, how it is specified, typical values, \
applicable standards, interfaces to other disciplines). Project-specific values are stated as \
such, with the document they come from.
- Return zero proposals if the document adds nothing worth recording.
- Give a one-paragraph rationale per proposal explaining what changed and why a reviewer should \
accept it, and a confidence between 0 and 1."""


def _agent_principal():
    return ensure_user(AGENT_EMAIL, "Engineering Brain agent")


def _load_revision(revision_id: UUID) -> dict[str, Any]:
    with connection() as conn:
        rev = conn.execute(
            """
            SELECT r.id, r.document_id, r.revision, r.status::text AS status,
                   d.title, d.doc_number, d.doc_type, d.discipline, d.project
            FROM document_revisions r JOIN documents d ON d.id = r.document_id
            WHERE r.id = %s
            """,
            (revision_id,),
        ).fetchone()
        if rev is None:
            raise RuntimeError(f"revision {revision_id} not found")
        chunks = conn.execute(
            """
            SELECT id, ordinal, kind::text AS kind, section_path, clause_id, page_start, page_end,
                   text, context_prefix, token_count
            FROM chunks WHERE revision_id = %s AND kind IN ('clause', 'requirement', 'table', 'text')
            ORDER BY ordinal
            """,
            (revision_id,),
        ).fetchall()
    return {"revision": rev, "chunks": chunks}


def select_chunks(chunks: list[dict], *, max_chunks: int = MAX_CHUNKS, max_tokens: int = MAX_TOKENS
                  ) -> list[dict]:
    """Prefer requirement/clause/table chunks, cap by count and tokens, keep document order."""
    ranked = sorted(chunks, key=lambda c: (_KIND_PRIORITY.get(c["kind"], 9), c["ordinal"]))
    picked: list[dict] = []
    budget = 0
    for c in ranked:
        t = c["token_count"] or approx_tokens(c["text"])
        if len(picked) >= max_chunks or budget + t > max_tokens:
            if picked:
                continue
        picked.append(c)
        budget += t
    picked.sort(key=lambda c: c["ordinal"])
    return picked


def _chunk_title(rev: dict, c: dict) -> str:
    bits = [rev["doc_number"] or "", rev["title"] or "", f"Rev {rev['revision']}"]
    if c["clause_id"]:
        bits.append(f"clause {c['clause_id']}")
    elif c["section_path"]:
        bits.append(" > ".join(c["section_path"]))
    if c["page_start"]:
        bits.append(f"p.{c['page_start']}")
    return " | ".join(b for b in bits if b)


def related_pages(rev: dict, chunks: list[dict], principal) -> list[dict[str, Any]]:
    """Published wiki pages about the same topic, found through the normal retrieval path."""
    headings: list[str] = []
    for c in chunks:
        for h in c["section_path"] or []:
            if h not in headings:
                headings.append(h)
    query = " ".join(x for x in [rev["doc_number"] or "", rev["title"] or "", *headings[:8]] if x)
    if not query.strip():
        return []
    try:
        hits = search(query[:2000], user=principal,
                      scope=Scope(include_documents=False, include_wiki=True), k=20, rerank=False)
    except Exception as e:  # retrieval failures must not block drafting
        log.warning("wiki.propose.search_failed", error=str(e))
        return []
    pages: list[dict[str, Any]] = []
    seen: set[UUID] = set()
    with connection() as conn:
        for h in hits:
            if h.page_id is None or h.page_id in seen:
                continue
            seen.add(h.page_id)
            row = conn.execute(
                "SELECT id, slug, title FROM wiki_pages WHERE id = %s AND status = 'published'",
                (h.page_id,),
            ).fetchone()
            if row is None:
                continue
            page = store.read_page(row["slug"])
            if page is None:
                continue
            pages.append({"id": row["id"], "slug": row["slug"], "title": page.title,
                          "body": page.body[:MAX_PAGE_CHARS], "frontmatter": page.frontmatter})
            if len(pages) >= MAX_RELATED_PAGES:
                break
    return pages


def _user_prompt(rev: dict, n_chunks: int, pages: list[dict]) -> str:
    lines = [
        f"A new revision of a document was ingested: {rev['doc_number'] or '(no number)'} "
        f"\"{rev['title']}\" revision {rev['revision']}, type {rev['doc_type']}, "
        f"disciplines {', '.join(rev['discipline'] or []) or 'unknown'}"
        + (f", project {rev['project']}" if rev["project"] else "") + ".",
        f"Sources 0-{n_chunks - 1} are passages from this document.",
    ]
    if pages:
        lines.append(
            f"Sources {n_chunks}-{n_chunks + len(pages) - 1} are existing published wiki pages that "
            "retrieval found related to it: " + "; ".join(f"{p['slug']} ({p['title']!r})" for p in pages)
            + ". Update these (kind=update, same slug) where the document adds to or corrects them; "
            "cite only document passages (indices below " + str(n_chunks) + ") as sources."
        )
    else:
        lines.append("No related wiki pages exist yet.")
    lines.append("Draft the wiki proposals this document warrants. Return an empty list if none.")
    return "\n".join(lines)


def _sources_for(indices: list[int], rev: dict, chunks: list[dict]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for i in indices:
        if not isinstance(i, int) or i < 0 or i >= len(chunks) or i in seen:
            continue
        seen.add(i)
        c = chunks[i]
        out.append({
            "index": i,
            "document_id": str(rev["document_id"]),
            "revision_id": str(rev["id"]),
            "chunk_id": str(c["id"]),
            "doc_number": rev["doc_number"],
            "revision": rev["revision"],
            "clause_id": c["clause_id"],
            "page": c["page_start"],
        })
    return out


def propose_for_revision(revision_id: UUID) -> list[dict[str, Any]]:
    loaded = _load_revision(revision_id)
    rev, all_chunks = loaded["revision"], loaded["chunks"]
    if rev["status"] not in ("active", "draft"):
        log.info("wiki.propose.skip_inactive", revision_id=str(revision_id), status=rev["status"])
        return []
    chunks = select_chunks(all_chunks)
    if not chunks:
        log.info("wiki.propose.no_chunks", revision_id=str(revision_id))
        return []
    principal = _agent_principal()
    pages = related_pages(rev, chunks, principal)

    documents = [DocumentBlock(text=f"{c['context_prefix']}\n{c['text']}".strip(),
                               title=_chunk_title(rev, c)) for c in chunks]
    documents += [DocumentBlock(text=f"Wiki page {p['slug']}\n\n{p['body']}",
                                title=f"Wiki: {p['title']} ({p['slug']})") for p in pages]
    s = get_settings()
    batch = get_llm().parse(
        schema=ProposalBatch, system=SYSTEM_PROMPT,
        user=_user_prompt(rev, len(chunks), pages), documents=documents,
        model=s.llm_model_answer, effort="high",
    )

    created: list[dict[str, Any]] = []
    for p in batch.proposals:
        try:
            slug = validate_slug(p.slug.strip().strip("/"))
        except SlugError as e:
            log.warning("wiki.propose.bad_slug", slug=p.slug, error=str(e))
            continue
        if not p.content.strip():
            continue
        sources = _sources_for(p.source_indices, rev, chunks)
        if not sources:  # every proposal must point back at the document that caused it
            sources = _sources_for(list(range(min(len(chunks), 3))), rev, chunks)
        row = service.create_proposal(
            slug=slug, kind=p.kind, title=p.title.strip() or slug.rsplit("/", 1)[-1],
            content=p.content, rationale=p.rationale, sources=sources, confidence=p.confidence,
            created_by="agent",
        )
        created.append(row)
    log.info("wiki.propose.done", revision_id=str(revision_id), proposals=len(created),
             chunks=len(chunks), related_pages=len(pages))
    return created


@job("wiki.propose")
def handle_propose(payload: dict) -> None:
    propose_for_revision(UUID(payload["revision_id"]))


@job("wiki.reindex")
def handle_reindex(payload: dict) -> None:
    """payload {page_id} re-indexes one page; {all: true} (or no page_id) syncs every file."""
    page_id = payload.get("page_id")
    force = bool(payload.get("force", False))
    if not page_id or page_id == "all":
        service.sync_from_disk()
        return
    with connection() as conn:
        row = conn.execute("SELECT id, slug, title FROM wiki_pages WHERE id = %s",
                           (UUID(page_id),)).fetchone()
    if row is None:
        raise RuntimeError(f"wiki page {page_id} not found")
    page = store.read_page(row["slug"])
    if page is None:
        raise RuntimeError(f"wiki page {row['slug']} has no file")
    index_page(row["id"], row["slug"], page.title, page.body, force=force)
