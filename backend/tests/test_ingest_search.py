import io

from eb.jobs import run_pending_once


def _upload(client, text: str, filename: str, **form):
    r = client.post("/documents", files={"file": (filename, io.BytesIO(text.encode()), "text/markdown")},
                    data=form)
    assert r.status_code == 201, r.text
    return r.json()


def test_upload_ingest_search_and_chat(client, sample_spec, sample_datasheet, fake_llm):
    up = _upload(client, sample_spec, "ps-100.md", doc_number="PS-100", revision="A",
                 doc_type="spec", discipline="mechanical,fluid")
    assert up["duplicate"] is False
    _upload(client, sample_datasheet, "cx-250.md", doc_number="DS-CX-250", doc_type="datasheet")

    assert run_pending_once() >= 2  # two ingest jobs (+ wiki.propose if registered)

    doc = client.get(f"/documents/{up['document_id']}").json()
    assert doc["parse_status"] == "done"
    assert doc["revision_status"] == "active"

    r = client.post("/search", json={"query": "design pressure of the casing", "k": 5})
    hits = r.json()["hits"]
    assert hits, "expected hits"
    assert any("16 bar" in h["text"] for h in hits)
    assert hits[0]["doc_number"] in ("PS-100", "DS-CX-250")

    r = client.post("/chat", json={"question": "What is the casing design pressure in PS-100?",
                                   "document_ids": [up["document_id"]]})
    body = r.json()
    assert r.status_code == 200, body
    assert body["answer"]
    assert body["citations"] and body["citations"][0]["doc_number"] == "PS-100"
    assert fake_llm.calls and fake_llm.calls[0]["documents"]

    # Conversation persisted with history
    conv = client.get(f"/chat/conversations/{body['conversation_id']}").json()
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]


def test_duplicate_and_new_revision(client, sample_spec, fake_llm):
    a = _upload(client, sample_spec, "ps-100.md", doc_number="PS-100", revision="A")
    dup = _upload(client, sample_spec, "ps-100.md", doc_number="PS-100", revision="A")
    assert dup["duplicate"] is True and dup["document_id"] == a["document_id"]

    b = _upload(client, sample_spec.replace("16 bar(g)", "25 bar(g)"), "ps-100-b.md",
                doc_number="PS-100", revision="B")
    assert b["document_id"] == a["document_id"]
    run_pending_once()

    doc = client.get(f"/documents/{a['document_id']}").json()
    assert doc["current_revision"] == "B"
    statuses = {r["revision"]: r["status"] for r in doc["revisions"]}
    assert statuses == {"A": "superseded", "B": "active"}

    # Default search sees only the active revision.
    hits = client.post("/search", json={"query": "design pressure casing", "k": 10}).json()["hits"]
    assert all(h["revision"] == "B" for h in hits if h["doc_number"] == "PS-100")
    assert any("25 bar" in h["text"] for h in hits)


def test_acl_hides_documents_from_other_groups(client, sample_spec, db, fake_llm):
    a = _upload(client, sample_spec, "ps-100.md", doc_number="PS-100")
    run_pending_once()
    with db() as conn:
        conn.execute("DELETE FROM document_acl WHERE document_id = %s", (a["document_id"],))
    assert client.get(f"/documents/{a['document_id']}").status_code == 404
    hits = client.post("/search", json={"query": "pump design pressure"}).json()["hits"]
    assert hits == []
