from eb.ingest.chunk import chunk_document
from eb.ingest.parse import parse_markdown_or_text


def test_chunking_keeps_clauses_and_tables(sample_spec):
    parsed = parse_markdown_or_text(sample_spec.encode())
    chunks = chunk_document(parsed, {"doc_number": "PS-100", "title": "Pump Spec", "revision": "A"})
    clauses = {c.clause_id: c for c in chunks if c.clause_id}
    assert "4.2" in clauses
    assert clauses["4.2"].kind == "requirement"
    assert "16 bar" in clauses["4.2"].text
    assert clauses["4.2"].section_path[-1].startswith("4 Design")
    assert clauses["4.2"].context_prefix.startswith("PS-100 | Pump Spec | Rev A")
    tables = [c for c in chunks if c.kind == "table"]
    assert len(tables) == 1 and "Design pressure" in tables[0].text
    assert all(c.content_hash for c in chunks)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_long_paragraph_is_split_at_sentences():
    text = " ".join(f"Sentence number {i} describes a requirement." for i in range(400))
    parsed = parse_markdown_or_text(text.encode())
    chunks = chunk_document(parsed, {"title": "t"}, target_tokens=100, max_tokens=150)
    assert len(chunks) > 3
    assert all(c.token_count <= 200 for c in chunks)
