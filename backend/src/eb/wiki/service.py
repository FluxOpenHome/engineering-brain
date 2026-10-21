"""Wiki pages and proposals: files in git are canonical, Postgres is the index (architecture 6.4).

Two write paths:
  * human edit  -> `save_page`: commit, publish, index. No proposal.
  * agent draft -> `create_proposal` (never touches files) -> reviewer `accept_proposal` /
    `reject_proposal`. Accept commits, publishes, records provenance, indexes.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any
from uuid import UUID

import structlog

from eb.auth import Principal
from eb.db import connection
from eb.wiki import store
from eb.wiki.index import index_page, unindex_page
from eb.wiki.store import AGENT_AUTHOR, Page, content_hash, validate_slug

log = structlog.get_logger(__name__)


class NotFound(LookupError):
    pass


class Conflict(RuntimeError):
    pass


def _author(user: Principal) -> tuple[str, str]:
    return (user.display_name or user.email, user.email)


def _json(v: Any) -> Any:
    return json.loads(json.dumps(v, default=str))


def _row(r: dict | None) -> dict | None:
    return None if r is None else _json(dict(r))


def _uuid(v: Any) -> UUID | None:
    try:
        return UUID(str(v)) if v else None
    except ValueError:
        return None


# ------------------------------------------------------------------------------ wiki_pages rows


def _upsert_page(conn, page: Page, *, status: str | None = None, reviewed_by: UUID | None = None,
                 human_edited: bool | None = None, last_published_sha: str | None = None) -> dict:
    fm = page.frontmatter
    status = status or page.status
    if status not in store.STATUSES:
        status = "published"
    row = conn.execute(
        """
        INSERT INTO wiki_pages (slug, title, status, discipline, tags, reviewed_by, human_edited,
                                last_published_sha)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (slug) DO UPDATE SET
            title = EXCLUDED.title,
            status = EXCLUDED.status,
            discipline = EXCLUDED.discipline,
            tags = EXCLUDED.tags,
            reviewed_by = COALESCE(EXCLUDED.reviewed_by, wiki_pages.reviewed_by),
            human_edited = EXCLUDED.human_edited,
            last_published_sha = COALESCE(EXCLUDED.last_published_sha, wiki_pages.last_published_sha),
            updated_at = now()
        RETURNING *, status::text AS status
        """,
        (
            page.slug, page.title, status, list(fm.get("discipline") or []), list(fm.get("tags") or []),
            reviewed_by,
            bool(fm.get("human_edited")) if human_edited is None else human_edited,
            last_published_sha,
        ),
    ).fetchone()
    return row


def _replace_sources(conn, page_id: UUID, sources: list[dict]) -> int:
    """Rewrite wiki_page_sources from a list of {document_id, revision_id, chunk_id, page}."""
    conn.execute("DELETE FROM wiki_page_sources WHERE page_id = %s", (page_id,))
    seen: set[tuple[str, str | None]] = set()
    n = 0
    for s in sources or []:
        if not isinstance(s, dict):
            continue
        doc_id, chunk_id = _uuid(s.get("document_id")), _uuid(s.get("chunk_id"))
        rev_id = _uuid(s.get("revision_id"))
        if doc_id is None or (doc_id, chunk_id) in seen:
            continue
        seen.add((doc_id, chunk_id))
        # Documents and chunks may have been deleted since the proposal was drafted; only
        # existing rows can be referenced (FKs), the rest surfaces in lint via the frontmatter.
        r = conn.execute(
            """
            INSERT INTO wiki_page_sources (page_id, document_id, revision_id, chunk_id, page, doc_number)
            SELECT %s, d.id,
                   (SELECT r.id FROM document_revisions r WHERE r.id = %s),
                   (SELECT c.id FROM chunks c WHERE c.id = %s),
                   %s, %s
            FROM documents d WHERE d.id = %s
            """,
            (page_id, rev_id, chunk_id, s.get("page"), s.get("doc_number"), doc_id),
        )
        n += r.rowcount
    return n


def _page_row(conn, slug: str) -> dict | None:
    return conn.execute(
        "SELECT *, status::text AS status FROM wiki_pages WHERE slug = %s", (slug,)
    ).fetchone()


# ------------------------------------------------------------------------------ reads


def list_pages(*, q: str | None = None, status: str | None = None, discipline: str | None = None
               ) -> list[dict[str, Any]]:
    """Pages from the index. Archived pages are hidden unless asked for explicitly."""
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT id, slug, title, status::text AS status, discipline, tags, updated_at, human_edited
            FROM wiki_pages
            WHERE (%s::text IS NULL OR title ILIKE '%%' || %s || '%%' OR slug ILIKE '%%' || %s || '%%')
              AND (CASE WHEN %s::text IS NULL THEN status <> 'archived' ELSE status::text = %s END)
              AND (%s::text IS NULL OR %s = ANY(discipline))
            ORDER BY slug
            """,
            (q, q, q, status, status, discipline, discipline),
        ).fetchall()
    return [_row(r) for r in rows]


def tree(pages: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Nested {name, slug?, title?, status?, children[]} built from slugs."""
    pages = list_pages() if pages is None else pages
    root: dict[str, Any] = {"children": {}}
    for p in pages:
        node = root
        parts = p["slug"].split("/")
        for part in parts:
            node = node["children"].setdefault(part, {"name": part, "children": {}})
        node.update({"slug": p["slug"], "title": p["title"], "status": p["status"]})

    def finish(node: dict[str, Any]) -> dict[str, Any]:
        kids = [finish(c) for _, c in sorted(node["children"].items())]
        out = {k: v for k, v in node.items() if k != "children"}
        out["children"] = kids
        return out

    return [finish(c) for _, c in sorted(root["children"].items())]


def get_page(slug: str) -> dict[str, Any] | None:
    validate_slug(slug)
    page = store.read_page(slug)
    if page is None:
        return None
    with connection() as conn:
        row = _page_row(conn, slug)
        if row is None or row["content_hash"] != content_hash(page.body):
            # The file was edited outside the API (git push, `vi`): refresh the index lazily.
            row = _upsert_page(conn, page)
    if row["status"] == "published":
        index_page(row["id"], slug, page.title, page.body)
    elif row["content_hash"] != content_hash(page.body):
        unindex_page(row["id"])
    with connection() as conn:
        sources = conn.execute(
            """
            SELECT s.document_id, s.revision_id, s.chunk_id, s.page, s.doc_number,
                   d.title AS document_title, r.revision
            FROM wiki_page_sources s
            JOIN documents d ON d.id = s.document_id
            LEFT JOIN document_revisions r ON r.id = s.revision_id
            WHERE s.page_id = %s ORDER BY s.doc_number, s.page
            """,
            (row["id"],),
        ).fetchall()
    return {
        "id": str(row["id"]),
        "slug": slug,
        "title": page.title,
        "status": row["status"],
        "discipline": list(row["discipline"] or []),
        "tags": list(row["tags"] or []),
        "human_edited": bool(row["human_edited"]),
        "updated_at": _json(row["updated_at"]),
        "last_published_sha": row["last_published_sha"],
        "frontmatter": page.frontmatter,
        "content": page.body,
        "sources": [_row(s) for s in sources] or list(page.frontmatter.get("sources") or []),
        "history": store.history(slug),
    }


# ------------------------------------------------------------------------------ human edits


def save_page(slug: str, title: str, body: str, user: Principal, *, discipline: list[str] | None = None,
              tags: list[str] | None = None, message: str | None = None) -> dict[str, Any]:
    """Web-editor save: commit directly, publish immediately, re-index (gated by content hash)."""
    validate_slug(slug)
    existing = store.read_page(slug)
    prev = existing.frontmatter if existing else {}
    fm = store.default_frontmatter(
        title,
        status="published",
        discipline=discipline if discipline is not None else list(prev.get("discipline") or []),
        tags=tags if tags is not None else list(prev.get("tags") or []),
        sources=list(prev.get("sources") or []),
        generated_by="human" if not existing else prev.get("generated_by", "human"),
        reviewed_by=user.email,
        human_edited=True,
        updated=dt.date.today().isoformat(),
    )
    msg = message or (f"Update {slug}" if existing else f"Create {slug}")
    sha = store.write_page(slug, fm, body, message=msg, author=_author(user))
    page = Page(slug=slug, frontmatter=fm, body=body)
    with connection() as conn:
        row = _upsert_page(conn, page, status="published", reviewed_by=user.id, human_edited=True,
                           last_published_sha=sha)
    index_page(row["id"], slug, title, body)
    log.info("wiki.save", slug=slug, user=user.email, sha=sha)
    return get_page(slug)


def archive_page(slug: str, user: Principal, *, message: str | None = None) -> bool:
    """Soft delete: frontmatter status=archived (committed), row archived, chunks removed now."""
    validate_slug(slug)
    page = store.read_page(slug)
    with connection() as conn:
        row = _page_row(conn, slug)
    if page is None and row is None:
        return False
    if page is not None:
        fm = dict(page.frontmatter)
        fm.update({"status": "archived", "updated": dt.date.today().isoformat()})
        sha = store.write_page(slug, fm, page.body, message=message or f"Archive {slug}",
                               author=_author(user))
    else:
        sha = None
    with connection() as conn:
        row = conn.execute(
            """
            UPDATE wiki_pages SET status = 'archived', updated_at = now(),
                   last_published_sha = COALESCE(%s, last_published_sha)
            WHERE slug = %s RETURNING id
            """,
            (sha, slug),
        ).fetchone()
        if row:
            unindex_page(row["id"], conn=conn)
            conn.execute(
                "UPDATE wiki_proposals SET status = 'superseded', decided_at = now() "
                "WHERE slug = %s AND status = 'open'",
                (slug,),
            )
    log.info("wiki.archive", slug=slug, user=user.email)
    return True


# ------------------------------------------------------------------------------ sync


def sync_from_disk() -> dict[str, int]:
    """Make wiki_pages mirror the files: upsert every page, index published ones, archive rows
    whose file is gone. Used by `eb wiki sync` and the all-pages reindex job."""
    pages = store.list_pages()
    seen = set()
    indexed = 0
    with connection() as conn:
        rows = {p.slug: _upsert_page(conn, p) for p in pages}
    for p in pages:
        seen.add(p.slug)
        row = rows[p.slug]
        if row["status"] == "published":
            index_page(row["id"], p.slug, p.title, p.body)
            indexed += 1
        else:
            unindex_page(row["id"])
    with connection() as conn:
        gone = conn.execute(
            "SELECT id, slug FROM wiki_pages WHERE status <> 'archived' AND NOT (slug = ANY(%s))",
            (list(seen),),
        ).fetchall()
        for g in gone:
            conn.execute("UPDATE wiki_pages SET status='archived', updated_at=now() WHERE id=%s",
                         (g["id"],))
            unindex_page(g["id"], conn=conn)
    log.info("wiki.sync", pages=len(pages), indexed=indexed, archived=len(gone))
    return {"pages": len(pages), "indexed": indexed, "archived": len(gone)}


# ------------------------------------------------------------------------------ proposals


def _split_content(content: str | None) -> tuple[dict[str, Any], str]:
    """Proposals normally hold a markdown body; tolerate a full page with frontmatter."""
    text = content or ""
    if text.lstrip().startswith("---"):
        try:
            return store.parse(text)
        except Exception:
            pass
    return {}, text


def create_proposal(*, slug: str, kind: str, title: str, content: str, rationale: str = "",
                    sources: list[dict] | None = None, confidence: float | None = None,
                    created_by: str = "agent", supersede_open: bool = True) -> dict[str, Any]:
    """Record a draft for review. Never writes files (architecture P3/P4)."""
    validate_slug(slug)
    existing = store.read_page(slug)
    if kind != "delete":  # the agent's guess is overridden by what is actually on disk
        kind = "update" if existing else "create"
    base_hash = content_hash(existing.body) if existing else None
    with connection() as conn:
        page_row = _page_row(conn, slug)
        if supersede_open:
            conn.execute(
                "UPDATE wiki_proposals SET status='superseded', decided_at=now() "
                "WHERE slug = %s AND status = 'open' AND created_by = %s",
                (slug, created_by),
            )
        row = conn.execute(
            """
            INSERT INTO wiki_proposals (page_id, slug, kind, base_hash, title, content, rationale,
                                        sources, confidence, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
            RETURNING *, kind::text AS kind, status::text AS status
            """,
            (page_row["id"] if page_row else None, slug, kind, base_hash, title, content, rationale,
             json.dumps(_json(sources or [])), confidence, created_by),
        ).fetchone()
    log.info("wiki.proposal.create", slug=slug, kind=kind, id=str(row["id"]), created_by=created_by)
    return _row(row)


_PROPOSAL_COLS = """
    id, page_id, slug, kind::text AS kind, base_hash, title, content, rationale, sources, confidence,
    status::text AS status, created_by, reviewed_by, review_note, created_at, decided_at
"""


def list_proposals(status: str | None = "open") -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            f"SELECT {_PROPOSAL_COLS} FROM wiki_proposals "
            "WHERE (%s::text IS NULL OR status::text = %s) ORDER BY created_at DESC",
            (status, status),
        ).fetchall()
    out = []
    for r in rows:
        d = _row(r)
        d.pop("content", None)
        out.append(d)
    return out


def _load_proposal(conn, proposal_id: UUID) -> dict:
    row = conn.execute(f"SELECT {_PROPOSAL_COLS} FROM wiki_proposals WHERE id = %s",
                       (proposal_id,)).fetchone()
    if row is None:
        raise NotFound(f"proposal {proposal_id} not found")
    return row


def get_proposal(proposal_id: UUID) -> dict[str, Any]:
    with connection() as conn:
        row = _load_proposal(conn, proposal_id)
    existing = store.read_page(row["slug"])
    current = existing.body if existing else None
    _, proposed_body = _split_content(row["content"])
    d = _row(row)
    d["current_content"] = current
    d["diff"] = store.diff(row["slug"], current, proposed_body if row["kind"] != "delete" else None)
    d["stale_base"] = (content_hash(current) if current is not None else None) != row["base_hash"]
    return d


def accept_proposal(proposal_id: UUID, user: Principal, *, content_override: str | None = None,
                    note: str | None = None) -> dict[str, Any]:
    """Publish a proposal: commit the page, record provenance, index, close the proposal.

    The reviewer may edit the draft first (`content_override`), which marks the page
    human_edited. If the page changed since the proposal was drafted the accept still goes
    through (the reviewer saw the live diff) but the result carries `stale_base: true`.
    """
    with connection() as conn:
        prop = _load_proposal(conn, proposal_id)
    if prop["status"] != "open":
        raise Conflict(f"proposal is {prop['status']}, not open")
    slug = prop["slug"]
    existing = store.read_page(slug)
    current_hash = content_hash(existing.body) if existing else None
    stale_base = current_hash != prop["base_hash"]

    if prop["kind"] == "delete":
        archive_page(slug, user, message=f"Archive {slug} (proposal {proposal_id})")
        _decide(proposal_id, "accepted", user, note)
        return {"page": get_page(slug), "stale_base": stale_base}

    _, proposed_body = _split_content(prop["content"])
    body = proposed_body
    human_edited = False
    if content_override is not None:
        _, body = _split_content(content_override)
        human_edited = body.strip() != proposed_body.strip()
    prev = existing.frontmatter if existing else {}
    title = prop["title"] or prev.get("title") or slug.rsplit("/", 1)[-1]
    sources = list(prop["sources"] or [])
    discipline = list(prev.get("discipline") or []) or _discipline_from_slug(slug)
    fm = store.default_frontmatter(
        title,
        status="published",
        discipline=discipline,
        tags=list(prev.get("tags") or []),
        sources=sources,
        generated_by="agent" if prop["created_by"] == "agent" else "human",
        reviewed_by=user.email,
        human_edited=bool(prev.get("human_edited")) or human_edited,
        updated=dt.date.today().isoformat(),
    )
    msg = f"{'Update' if existing else 'Create'} {slug} (proposal {proposal_id} accepted by {user.email})"
    author = _author(user) if human_edited or prop["created_by"] != "agent" else AGENT_AUTHOR
    sha = store.write_page(slug, fm, body, message=msg, author=author)

    page = Page(slug=slug, frontmatter=fm, body=body)
    with connection() as conn:
        row = _upsert_page(conn, page, status="published", reviewed_by=user.id,
                           human_edited=fm["human_edited"], last_published_sha=sha)
        _replace_sources(conn, row["id"], sources)
        conn.execute(
            """
            UPDATE wiki_proposals SET status='accepted', page_id=%s, reviewed_by=%s, review_note=%s,
                   decided_at=now() WHERE id=%s
            """,
            (row["id"], user.id, note, proposal_id),
        )
        conn.execute(
            "UPDATE wiki_proposals SET status='superseded', decided_at=now() "
            "WHERE slug = %s AND status = 'open' AND id <> %s",
            (slug, proposal_id),
        )
    index_page(row["id"], slug, title, body)
    log.info("wiki.proposal.accept", id=str(proposal_id), slug=slug, user=user.email,
             stale_base=stale_base, human_edited=human_edited)
    return {"page": get_page(slug), "stale_base": stale_base}


def _decide(proposal_id: UUID, status: str, user: Principal, note: str | None) -> None:
    with connection() as conn:
        conn.execute(
            "UPDATE wiki_proposals SET status=%s, reviewed_by=%s, review_note=%s, decided_at=now() "
            "WHERE id=%s",
            (status, user.id, note, proposal_id),
        )


def reject_proposal(proposal_id: UUID, user: Principal, note: str | None = None) -> None:
    with connection() as conn:
        prop = _load_proposal(conn, proposal_id)
    if prop["status"] != "open":
        raise Conflict(f"proposal is {prop['status']}, not open")
    _decide(proposal_id, "rejected", user, note)
    log.info("wiki.proposal.reject", id=str(proposal_id), slug=prop["slug"], user=user.email)


_DISCIPLINES = {"fluid", "electrical", "civil", "structural", "mechanical", "chemical", "materials",
                "ic", "general"}


def _discipline_from_slug(slug: str) -> list[str]:
    head = slug.split("/", 1)[0]
    return [head] if "/" in slug and head in _DISCIPLINES else []


# ------------------------------------------------------------------------------ lint


def lint() -> dict[str, Any]:
    """Pages whose evidence has moved under them.

    * `stale`: published pages citing a revision that is now superseded/archived -> status stale.
    * `orphan_citations`: sources (frontmatter or wiki_page_sources) whose chunk no longer exists.
    """
    stale: list[dict[str, Any]] = []
    orphans: list[dict[str, Any]] = []
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT p.id, p.slug, p.title, s.document_id, s.revision_id, r.revision,
                   r.status::text AS revision_status, d.doc_number, d.current_revision_id
            FROM wiki_page_sources s
            JOIN wiki_pages p ON p.id = s.page_id
            JOIN document_revisions r ON r.id = s.revision_id
            JOIN documents d ON d.id = s.document_id
            WHERE p.status = 'published' AND r.status IN ('superseded', 'archived')
            ORDER BY p.slug
            """
        ).fetchall()
        for r in rows:
            conn.execute("UPDATE wiki_pages SET status='stale', updated_at=now() WHERE id=%s", (r["id"],))
            stale.append(_row(r))
        db_orphans = conn.execute(
            """
            SELECT p.id, p.slug, s.document_id, s.doc_number, s.page
            FROM wiki_page_sources s JOIN wiki_pages p ON p.id = s.page_id
            WHERE s.chunk_id IS NULL AND p.status <> 'archived'
            """
        ).fetchall()
        orphans += [dict(_row(o), reason="chunk deleted") for o in db_orphans]
        live = {
            r["slug"] for r in conn.execute(
                "SELECT slug FROM wiki_pages WHERE status <> 'archived'"
            ).fetchall()
        }
        cited = set()
        for page in store.list_pages():
            if page.status == "archived" or page.slug not in live:
                continue
            for s in page.frontmatter.get("sources") or []:
                cid = s.get("chunk_id") if isinstance(s, dict) else None
                if cid:
                    cited.add((page.slug, str(cid), s.get("doc_number"), s.get("page")))
        ids = [u for u in {_uuid(c[1]) for c in cited} if u is not None]
        existing = set()
        if ids:
            existing = {
                str(x["id"]) for x in conn.execute(
                    "SELECT id FROM chunks WHERE id = ANY(%s)", (ids,)
                ).fetchall()
            }
        for slug, cid, doc_number, pg in sorted(cited):
            if cid not in existing:
                orphans.append({"slug": slug, "chunk_id": cid, "doc_number": doc_number, "page": pg,
                                "reason": "chunk id not found"})
    report = {"stale": stale, "orphan_citations": orphans, "checked_at": dt.datetime.now(dt.UTC).isoformat()}
    log.info("wiki.lint", stale=len(stale), orphans=len(orphans))
    return report
