"""Structure-aware chunking (architecture 6.2).

- Headings build a section path; every chunk carries it.
- Numbered clauses ("4.2.3 The pump shall ...") become their own chunks with clause_id.
- Tables are atomic (never split, never merged with prose).
- Prose paragraphs are packed up to a target token size and split at sentence boundaries
  when a single paragraph exceeds the maximum.
- Every chunk gets a context_prefix: document number, title, revision, section path.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from eb.embeddings import approx_tokens
from eb.ingest.parse import Block, ParsedDocument

_CLAUSE_RE = re.compile(r"^\s*((?:[A-Z]\.)?\d+(?:\.\d+){1,4})\s+(.+)$", re.DOTALL)
_REQ_WORDS = re.compile(r"\b(shall|must|is required to|shall not|must not)\b", re.IGNORECASE)
_SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(])")


@dataclass
class Chunk:
    ordinal: int
    kind: str  # text | table | figure | clause | requirement | heading
    text: str
    section_path: list[str] = field(default_factory=list)
    clause_id: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    bbox: list[float] | None = None
    context_prefix: str = ""
    token_count: int = 0
    content_hash: str = ""


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _prefix(doc_meta: dict, section_path: list[str]) -> str:
    bits = []
    if doc_meta.get("doc_number"):
        bits.append(doc_meta["doc_number"])
    if doc_meta.get("title"):
        bits.append(doc_meta["title"])
    if doc_meta.get("revision") is not None:
        bits.append(f"Rev {doc_meta['revision']}")
    head = " | ".join(bits)
    if section_path:
        head += " > " + " > ".join(section_path)
    return head


def _split_long(text: str, max_tokens: int) -> list[str]:
    if approx_tokens(text) <= max_tokens:
        return [text]
    out: list[str] = []
    buf: list[str] = []
    for sent in _SENT_RE.split(text):
        if buf and approx_tokens(" ".join(buf + [sent])) > max_tokens:
            out.append(" ".join(buf))
            buf = []
        buf.append(sent)
    if buf:
        out.append(" ".join(buf))
    return out


def chunk_document(
    parsed: ParsedDocument,
    doc_meta: dict,
    *,
    target_tokens: int = 400,
    max_tokens: int = 800,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    section_path: list[str] = []
    pack: list[Block] = []

    def finish(c: Chunk) -> Chunk:
        c.context_prefix = _prefix(doc_meta, c.section_path)
        c.token_count = approx_tokens(c.context_prefix + " " + c.text)
        c.content_hash = _hash(c.context_prefix + "\n" + c.text)
        c.ordinal = len(chunks)
        chunks.append(c)
        return c

    def flush_pack() -> None:
        nonlocal pack
        if not pack:
            return
        text = "\n\n".join(b.text for b in pack)
        pages = [b.page for b in pack if b.page is not None]
        for piece in _split_long(text, max_tokens):
            finish(
                Chunk(
                    ordinal=0,
                    kind="requirement" if _REQ_WORDS.search(piece) else "text",
                    text=piece,
                    section_path=list(section_path),
                    page_start=min(pages) if pages else None,
                    page_end=max(pages) if pages else None,
                )
            )
        pack = []

    for b in parsed.blocks:
        if b.kind == "heading":
            flush_pack()
            level = max(1, b.level)
            section_path = section_path[: level - 1] + [b.text.strip()]
            continue
        if b.kind in ("table", "figure"):
            flush_pack()
            finish(
                Chunk(0, b.kind, b.text, list(section_path), page_start=b.page, page_end=b.page,
                      bbox=b.bbox)
            )
            continue
        m = _CLAUSE_RE.match(b.text)
        if m and len(m.group(1)) <= 12:
            flush_pack()
            clause_id, body = m.group(1), m.group(2).strip()
            kind = "requirement" if _REQ_WORDS.search(body) else "clause"
            for i, piece in enumerate(_split_long(b.text, max_tokens)):
                finish(
                    Chunk(0, kind, piece, list(section_path),
                          clause_id=clause_id if i == 0 else f"{clause_id} (cont.)",
                          page_start=b.page, page_end=b.page, bbox=b.bbox)
                )
            continue
        # Prose: pack paragraphs up to the target size.
        candidate = "\n\n".join(x.text for x in pack + [b])
        if pack and approx_tokens(candidate) > target_tokens:
            flush_pack()
        pack.append(b)
    flush_pack()
    return chunks
