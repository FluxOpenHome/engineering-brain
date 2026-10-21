"""Wiki module: human edits publish immediately; agent drafts are proposals until a reviewer
accepts them; only published pages are ever searchable or citable."""

from __future__ import annotations

import io
import subprocess
import uuid
from pathlib import Path

import frontmatter
import pytest

from eb.config import get_settings
from eb.jobs import run_pending_once
from eb.wiki import service, store
from eb.wiki.jobs import Proposal, ProposalBatch
from eb.wiki.store import SlugError, validate_slug


def _upload(client, text: str, filename: str, **form):
    r = client.post("/documents", files={"file": (filename, io.BytesIO(text.encode()), "text/markdown")},
                    data=form)
    assert r.status_code == 201, r.text
    return r.json()


def _wiki_search(client, query: str, needle: str | None = None) -> list[dict]:
    """Wiki-only hits; with `needle`, only hits whose text or title mention it.

    Dense retrieval always returns nearest neighbours, so "not found" is "no hit mentions it",
    never "no hits at all" (the wiki dir keeps pages from earlier tests).
    """
    r = client.post("/search", json={"query": query, "k": 10, "include_documents": False})
    assert r.status_code == 200, r.text
    hits = r.json()["hits"]
    if needle is None:
        return hits
    return [h for h in hits if needle.lower() in (h["text"] + " " + h["title"]).lower()]


def _git_log(path: str) -> list[str]:
    root = Path(get_settings().wiki_dir)
    out = subprocess.run(["git", "-C", str(root), "log", "--format=%H %ae", "--", path],
                         check=True, capture_output=True, text=True).stdout
    return out.splitlines()


def _uniq(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


PUMP_BODY = """Centrifugal pumps move liquid by converting rotational kinetic energy to hydrodynamic \
energy. The casing design pressure for cooling water duty is 16 bar(g) per PS-100.[^0]

## Performance testing

Performance tests follow ISO 9906 Grade 2B and are witnessed by the purchaser.[^1]

[^0]: PS-100 clause 4.2
[^1]: PS-100 clause 5.1
"""


# ------------------------------------------------------------------------------ human edits


def test_human_save_publishes_commits_and_indexes(client, db, fake_llm):
    slug = f"mechanical/{_uniq('zorbic-impeller')}"
    body = ("# Zorbic impellers\n\nA zorbic impeller is a fictional closed impeller rated for "
            "glorp duty at 37 bar(g).\n\n## Materials\n\nCasing material ASTM A216 WCB.\n")
    r = client.put(f"/wiki/pages/{slug}", json={"title": "Zorbic impellers", "content": body,
                                              "discipline": ["mechanical"], "tags": ["pumps"],
                                              "message": "Add zorbic impeller page"})
    assert r.status_code == 200, r.text
    page = r.json()
    assert page["slug"] == slug and page["status"] == "published" and page["human_edited"] is True
    assert page["frontmatter"]["generated_by"] == "human"
    assert page["frontmatter"]["reviewed_by"] == "dev@example.com"
    assert page["content"].strip() == body.strip()
    assert len(page["history"]) == 1 and page["history"][0]["message"] == "Add zorbic impeller page"

    # File on disk with frontmatter, one commit attributed to the editor.
    path = Path(get_settings().wiki_dir) / f"{slug}.md"
    assert path.is_file()
    post = frontmatter.load(path)
    assert post["title"] == "Zorbic impellers" and post["status"] == "published"
    assert post["human_edited"] is True and post["discipline"] == ["mechanical"]
    assert len(_git_log(f"{slug}.md")) == 1 and _git_log(f"{slug}.md")[0].endswith("dev@example.com")

    with db() as conn:
        row = conn.execute("SELECT * FROM wiki_pages WHERE slug=%s", (slug,)).fetchone()
        assert row["status"] == "published" and row["human_edited"] is True
        assert row["last_published_sha"] == page["history"][0]["sha"]
        assert row["content_hash"] == store.content_hash(body)
        n = conn.execute("SELECT count(*) AS n FROM wiki_chunks WHERE page_id=%s", (row["id"],)).fetchone()
        assert n["n"] >= 1

    hits = _wiki_search(client, "zorbic impeller glorp duty")
    assert hits and hits[0]["source"] == "wiki" and hits[0]["page_id"] == page["id"]
    assert hits[0]["context_prefix"].startswith("Wiki: Zorbic impellers")

    listed = client.get("/wiki/pages", params={"q": "zorbic"}).json()
    assert [p["slug"] for p in listed] == [slug]
    assert set(listed[0]) >= {"id", "slug", "title", "status", "discipline", "tags", "updated_at",
                              "human_edited"}
    assert client.get("/wiki/pages", params={"discipline": "mechanical", "q": "zorbic"}).json()
    assert client.get("/wiki/pages", params={"status": "published", "q": "zorbic"}).json()

    tree = client.get("/wiki/tree").json()
    mech = next(n for n in tree if n["name"] == "mechanical")
    assert any(c.get("slug") == slug for c in mech["children"])

    # Second save with unchanged content: no new commit, index untouched.
    r2 = client.put(f"/wiki/pages/{slug}", json={"title": "Zorbic impellers", "content": body})
    assert r2.status_code == 200 and len(_git_log(f"{slug}.md")) == 1
    # Changed content: a second commit, re-indexed.
    r3 = client.put(f"/wiki/pages/{slug}", json={"title": "Zorbic impellers",
                                               "content": body + "\nAlso suitable for frobnication.\n"})
    assert len(r3.json()["history"]) == 2
    assert _wiki_search(client, "frobnication", "frobnication")


# ------------------------------------------------------------------------------ proposals


def test_proposal_round_trip(client, db, fake_llm, sample_spec):
    slug = f"mechanical/{_uniq('centrifugal-pumps')}"
    up = _upload(client, sample_spec, "ps-100.md", doc_number="PS-100", revision="A", doc_type="spec",
                 discipline="mechanical,fluid")
    fake_llm.parsed.append(ProposalBatch(proposals=[Proposal(
        slug=slug, kind="create", title="Centrifugal pumps", content=PUMP_BODY,
        rationale="PS-100 defines the cooling water pump class.", confidence=0.8, source_indices=[0, 1],
    )]))
    assert run_pending_once() >= 2  # ingest.parse then wiki.propose

    # The job built a structured call with the document's chunks as sources and the right prompt.
    call = fake_llm.calls[-1]
    assert call["schema"] is ProposalBatch
    assert any("16 bar" in d.text for d in call["documents"])
    assert all(d.title.startswith("PS-100") for d in call["documents"])
    for phrase in ("Do not invent", "exactly", "near-duplicate", "traceable", "engineers"):
        assert phrase in call["system"], phrase

    open_props = client.get("/wiki/proposals", params={"status": "open"}).json()
    assert len(open_props) == 1
    prop = open_props[0]
    assert prop["slug"] == slug and prop["kind"] == "create" and prop["status"] == "open"
    assert prop["created_by"] == "agent" and prop["confidence"] == pytest.approx(0.8)
    assert set(prop) >= {"id", "slug", "kind", "title", "rationale", "confidence", "sources", "created_at",
                         "created_by", "status"}
    assert prop["sources"][0]["document_id"] == up["document_id"]
    assert prop["sources"][0]["revision_id"] == up["revision_id"]
    assert prop["sources"][0]["doc_number"] == "PS-100" and prop["sources"][0]["chunk_id"]

    # Until accepted the draft is invisible to retrieval and to chat.
    assert _wiki_search(client, "centrifugal pumps hydrodynamic energy", "hydrodynamic") == []
    chat = client.post("/chat", json={"question": "What is a centrifugal pump casing design pressure?",
                                      "include_documents": False}).json()
    assert not any("hydrodynamic" in c["cited_text"] for c in chat["citations"])
    assert not any("hydrodynamic" in h["text"] for h in chat["sources"])
    assert not (Path(get_settings().wiki_dir) / f"{slug}.md").exists()

    detail = client.get(f"/wiki/proposals/{prop['id']}").json()
    assert detail["content"] == PUMP_BODY and detail["current_content"] is None
    assert detail["stale_base"] is False
    assert detail["diff"].startswith("--- /dev/null") and "+Centrifugal pumps move liquid" in detail["diff"]

    r = client.post(f"/wiki/proposals/{prop['id']}/accept", json={"note": "Looks right"})
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["stale_base"] is False
    page = result["page"]
    assert page["slug"] == slug and page["status"] == "published" and page["human_edited"] is False
    assert page["frontmatter"]["generated_by"] == "agent"
    assert page["frontmatter"]["reviewed_by"] == "dev@example.com"
    assert page["frontmatter"]["discipline"] == ["mechanical"]
    assert page["frontmatter"]["sources"][0]["chunk_id"] == prop["sources"][0]["chunk_id"]
    assert len(page["sources"]) == 2 and page["sources"][0]["document_id"] == up["document_id"]
    assert len(page["history"]) == 1 and "accepted by dev@example.com" in page["history"][0]["message"]

    with db() as conn:
        p = conn.execute("SELECT * FROM wiki_proposals WHERE id=%s", (prop["id"],)).fetchone()
        assert p["status"] == "accepted" and p["review_note"] == "Looks right" and p["decided_at"]
        assert str(p["page_id"]) == page["id"]
        srcs = conn.execute("SELECT * FROM wiki_page_sources WHERE page_id=%s", (page["id"],)).fetchall()
        assert len(srcs) == 2
        assert {str(s["document_id"]) for s in srcs} == {up["document_id"]}
        assert all(s["chunk_id"] is not None and s["doc_number"] == "PS-100" for s in srcs)

    hits = _wiki_search(client, "centrifugal pumps hydrodynamic energy")
    assert hits and hits[0]["page_id"] == page["id"]
    chat = client.post("/chat", json={"question": "casing design pressure for cooling water pumps",
                                      "include_documents": False}).json()
    assert chat["citations"] and chat["citations"][0]["source"] == "wiki"
    assert chat["citations"][0]["page_id"] == page["id"]

    # A second accept is a conflict; the proposal list no longer shows it as open.
    assert client.post(f"/wiki/proposals/{prop['id']}/accept", json={}).status_code == 409
    assert client.get("/wiki/proposals").json() == []
    accepted = client.get("/wiki/proposals", params={"status": "accepted"}).json()
    assert [p["id"] for p in accepted] == [prop["id"]]


def test_reject_proposal(client, db, fake_llm):
    slug = f"electrical/{_uniq('lv-motors')}"
    prop = service.create_proposal(slug=slug, kind="create", title="LV motors",
                                   content="# LV motors\n\nQuuxable motors run at 400 V, 50 Hz.\n",
                                   rationale="r", confidence=0.4)
    assert prop["status"] == "open" and prop["base_hash"] is None
    r = client.post(f"/wiki/proposals/{prop['id']}/reject", json={"note": "duplicate of existing page"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    with db() as conn:
        row = conn.execute("SELECT status, review_note, reviewed_by FROM wiki_proposals WHERE id=%s",
                           (prop["id"],)).fetchone()
    assert row["status"] == "rejected" and row["review_note"] == "duplicate of existing page"
    assert row["reviewed_by"] is not None
    assert not (Path(get_settings().wiki_dir) / f"{slug}.md").exists()
    assert client.get(f"/wiki/pages/{slug}").status_code == 404
    assert _wiki_search(client, "quuxable motors", "quuxable") == []
    assert client.post(f"/wiki/proposals/{prop['id']}/accept", json={}).status_code == 409
    assert client.post(f"/wiki/proposals/{prop['id']}/reject", json={}).status_code == 409
    assert client.get(f"/wiki/proposals/{uuid.uuid4()}").status_code == 404


def test_accept_with_edit_marks_human_edited_and_flags_stale_base(client, db, fake_llm, user):
    slug = f"fluid/{_uniq('strainers')}"
    client.put(f"/wiki/pages/{slug}", json={"title": "Strainers", "content": "# Strainers\n\nOriginal.\n"})
    prop = service.create_proposal(slug=slug, kind="create", title="Strainers",
                                   content="# Strainers\n\nOriginal.\n\nAgent adds mesh sizes.\n")
    assert prop["kind"] == "update" and prop["base_hash"] == store.content_hash("# Strainers\n\nOriginal.\n")
    # Another agent proposal for the same slug supersedes the first open one.
    prop2 = service.create_proposal(slug=slug, kind="update", title="Strainers",
                                    content="# Strainers\n\nOriginal.\n\nAgent adds mesh sizes (v2).\n")
    with db() as conn:
        st = conn.execute("SELECT status FROM wiki_proposals WHERE id=%s", (prop["id"],)).fetchone()
    assert st["status"] == "superseded"

    detail = client.get(f"/wiki/proposals/{prop2['id']}").json()
    assert detail["stale_base"] is False and detail["current_content"].strip() == "# Strainers\n\nOriginal."
    assert "+Agent adds mesh sizes (v2)." in detail["diff"]

    # A human edits the page under the proposal: the base is now stale but accept still works.
    client.put(f"/wiki/pages/{slug}", json={"title": "Strainers", "content": "# Strainers\n\nHuman edit.\n"})
    assert client.get(f"/wiki/proposals/{prop2['id']}").json()["stale_base"] is True
    edited = "# Strainers\n\nHuman edit.\n\nAgent adds mesh sizes (v2), reviewed: 40 mesh.\n"
    r = client.post(f"/wiki/proposals/{prop2['id']}/accept", json={"content": edited, "note": "merged"})
    assert r.status_code == 200, r.text
    assert r.json()["stale_base"] is True
    page = r.json()["page"]
    assert page["content"].strip() == edited.strip() and page["human_edited"] is True
    assert page["frontmatter"]["human_edited"] is True
    assert len(page["history"]) == 3
    assert _wiki_search(client, "40 mesh strainers", "40 mesh")


# ------------------------------------------------------------------------------ publish-only indexing


def test_archived_page_disappears_from_search(client, db, fake_llm):
    slug = f"civil/{_uniq('culverts')}"
    body = "# Culverts\n\nA wumpus culvert carries flibber water under a road.\n"
    page = client.put(f"/wiki/pages/{slug}", json={"title": "Culverts", "content": body}).json()
    assert _wiki_search(client, "wumpus culvert flibber", "wumpus")

    assert client.delete(f"/wiki/pages/{slug}").status_code == 204
    assert _wiki_search(client, "wumpus culvert flibber", "wumpus") == []
    with db() as conn:
        row = conn.execute("SELECT status FROM wiki_pages WHERE id=%s", (page["id"],)).fetchone()
        n = conn.execute("SELECT count(*) AS n FROM wiki_chunks WHERE page_id=%s", (page["id"],)).fetchone()
    assert row["status"] == "archived" and n["n"] == 0
    # The file stays (history preserved) with status archived; hidden from the default list.
    got = client.get(f"/wiki/pages/{slug}").json()
    assert got["status"] == "archived" and got["frontmatter"]["status"] == "archived"
    assert client.get("/wiki/pages", params={"q": "culverts"}).json() == []
    assert [p["slug"] for p in client.get("/wiki/pages", params={"q": "culverts",
                                                                "status": "archived"}).json()] == [slug]
    assert client.delete(f"/wiki/pages/{_uniq('nope')}").status_code == 404


def test_proposed_page_is_never_searchable_or_cited(client, db, fake_llm):
    # A page file that exists on disk with status=proposed (e.g. pulled from another branch).
    slug = f"chemical/{_uniq('scrubbers')}"
    fm = store.default_frontmatter("Scrubbers", status="proposed", generated_by="agent")
    store.write_page(slug, fm, "# Scrubbers\n\nA snorkel scrubber removes glorp from gas.\n",
                     message="draft", author=store.AGENT_AUTHOR)
    service.sync_from_disk()
    with db() as conn:
        row = conn.execute("SELECT id, status FROM wiki_pages WHERE slug=%s", (slug,)).fetchone()
        n = conn.execute("SELECT count(*) AS n FROM wiki_chunks WHERE page_id=%s", (row["id"],)).fetchone()
    assert row["status"] == "proposed" and n["n"] == 0
    assert client.get(f"/wiki/pages/{slug}").json()["status"] == "proposed"
    assert _wiki_search(client, "snorkel scrubber glorp", "snorkel") == []

    # An open proposal with unique content is equally invisible.
    service.create_proposal(slug=f"chemical/{_uniq('absorbers')}", kind="create", title="Absorbers",
                            content="# Absorbers\n\nA blartwick absorber captures glorp.\n")
    assert _wiki_search(client, "blartwick absorber", "blartwick") == []
    chat = client.post("/chat", json={"question": "What does a blartwick absorber or snorkel scrubber do?",
                                      "include_documents": False}).json()
    assert all(c.get("page_id") != str(row["id"]) for c in chat["citations"])
    assert not any(w in c["cited_text"] for c in chat["citations"] for w in ("blartwick", "snorkel"))
    assert not any(w in h["text"] for h in chat["sources"] for w in ("blartwick", "snorkel"))

    # Publishing it through the human path makes it visible.
    client.put(f"/wiki/pages/{slug}", json={"title": "Scrubbers",
                                          "content": "# Scrubbers\n\nA snorkel scrubber removes glorp.\n"})
    assert _wiki_search(client, "snorkel scrubber glorp", "snorkel")


# ------------------------------------------------------------------------------ slugs, lint, sync


def test_slug_validation(client, db):
    for bad in ("../x", "a/../b", "Upper", "has space", "under_score", "x..y", "/lead", "trail/", ""):
        with pytest.raises(SlugError):
            validate_slug(bad)
    for good in ("a", "mechanical/centrifugal-pumps", "standards/iso-9906", "a1/b2-c3/d"):
        assert validate_slug(good) == good
    with pytest.raises(SlugError):
        validate_slug("a" * 201)

    assert client.put("/wiki/pages/Bad_Slug", json={"title": "t", "content": "c"}).status_code == 422
    assert client.put("/wiki/pages/%2e%2e/x", json={"title": "t", "content": "c"}).status_code == 422
    assert client.get("/wiki/pages/a/%2e%2e/x").status_code == 422
    assert client.get("/wiki/pages/UPPER").status_code == 422
    assert client.delete("/wiki/pages/..%2fx").status_code == 422
    assert not (Path(get_settings().wiki_dir).parent / "x.md").exists()


def test_lint_marks_pages_citing_superseded_revisions_stale(client, db, fake_llm, sample_spec):
    slug = f"mechanical/{_uniq('pump-casings')}"
    a = _upload(client, sample_spec, "ps-100.md", doc_number="PS-100", revision="A")
    fake_llm.parsed.append(ProposalBatch(proposals=[Proposal(
        slug=slug, kind="create", title="Pump casings", content=PUMP_BODY, source_indices=[1])]))
    run_pending_once()
    prop = client.get("/wiki/proposals").json()[0]
    page = client.post(f"/wiki/proposals/{prop['id']}/accept", json={}).json()["page"]
    assert _wiki_search(client, "casing design pressure cooling water", "hydrodynamic")

    report = client.get("/wiki/lint").json()
    assert report["stale"] == [] and report["orphan_citations"] == []

    # Revision B supersedes A; the agent proposes nothing for it.
    fake_llm.parsed.append(ProposalBatch(proposals=[]))
    b = _upload(client, sample_spec.replace("16 bar(g)", "25 bar(g)"), "ps-100-b.md", doc_number="PS-100",
                revision="B")
    assert b["document_id"] == a["document_id"]
    run_pending_once()

    report = client.get("/wiki/lint").json()
    assert [s["slug"] for s in report["stale"]] == [slug]
    assert report["stale"][0]["revision"] == "A" and report["stale"][0]["revision_status"] == "superseded"
    assert client.get(f"/wiki/pages/{slug}").json()["status"] == "stale"
    assert _wiki_search(client, "casing design pressure cooling water", "hydrodynamic") == []

    # Deleting the cited chunks (re-index of revision A) must not fail and shows up as orphans.
    with db() as conn:
        conn.execute("DELETE FROM chunks WHERE revision_id = %s", (a["revision_id"],))
    report = client.get("/wiki/lint").json()
    assert any(o["slug"] == slug and o["reason"] == "chunk deleted" for o in report["orphan_citations"])
    assert any(o["slug"] == slug and o["reason"] == "chunk id not found" for o in report["orphan_citations"])
    assert page["id"]


def test_sync_from_disk_and_reindex_job(client, db, fake_llm):
    slug = f"structural/{_uniq('beams')}"
    fm = store.default_frontmatter("Beams", discipline=["structural"], tags=["steel"], human_edited=True)
    sha = store.write_page(slug, fm, "# Beams\n\nA plonk beam spans 12 m.\n", message="import",
                           author=("Importer", "importer@example.com"))
    assert sha and store.head_sha() == sha
    assert store.history(slug)[0]["author"] == "Importer"
    assert _wiki_search(client, "plonk beam", "plonk") == []  # not synced yet

    result = service.sync_from_disk()
    assert result["indexed"] >= 1
    hits = _wiki_search(client, "plonk beam spans", "plonk")
    assert hits and hits[0]["title"] == "Beams"
    listed = {p["slug"]: p for p in client.get("/wiki/pages").json()}
    assert listed[slug]["discipline"] == ["structural"] and listed[slug]["human_edited"] is True

    # Hash gate: an unchanged page is not re-embedded; a changed file is picked up on read.
    with db() as conn:
        row = conn.execute("SELECT id, content_hash FROM wiki_pages WHERE slug=%s", (slug,)).fetchone()
    assert row["content_hash"] == store.content_hash("# Beams\n\nA plonk beam spans 12 m.\n")
    store.write_page(slug, fm, "# Beams\n\nA plonk beam spans 14 m and carries 20 kN/m.\n",
                     message="edit on disk", author=("Importer", "importer@example.com"))
    got = client.get(f"/wiki/pages/{slug}").json()
    assert "14 m" in got["content"] and len(got["history"]) == 2
    assert _wiki_search(client, "plonk beam 20 kN/m", "20 kN/m")

    # The reindex job for one page and for all pages both run.
    r = client.post("/wiki/reindex")
    assert r.status_code == 200 and r.json()["job_id"]
    from eb.jobs import enqueue
    enqueue("wiki.reindex", {"page_id": str(row["id"]), "force": True})
    assert run_pending_once() == 2
    with db() as conn:
        statuses = conn.execute("SELECT status FROM jobs WHERE kind='wiki.reindex'").fetchall()
    assert [s["status"] for s in statuses] == ["done", "done"]

    # Hard delete removes the file with a commit; sync archives the row and drops its chunks.
    assert store.delete_page(slug, message="purge", author=("Importer", "importer@example.com"))
    assert store.read_page(slug) is None
    service.sync_from_disk()
    with db() as conn:
        row = conn.execute("SELECT status FROM wiki_pages WHERE slug=%s", (slug,)).fetchone()
    assert row["status"] == "archived"
    assert _wiki_search(client, "plonk beam", "plonk") == []

    # POST /wiki/propose enqueues the job.
    r = client.post("/wiki/propose", json={"revision_id": str(uuid.uuid4())})
    assert r.status_code == 200 and r.json()["job_id"]
    with db() as conn:
        kinds = conn.execute("SELECT kind FROM jobs WHERE status='queued'").fetchall()
    assert any(k["kind"] == "wiki.propose" for k in kinds)
