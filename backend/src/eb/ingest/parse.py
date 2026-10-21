"""Document parsing into a simple structured model.

Pass 1 (text layer): pypdf for PDFs, plain decode for text/markdown, python-docx-free DOCX
reader via zipfile. Pass 2 (layout/VLM) is provided by Docling or docling-serve when
configured; both produce the same `ParsedDocument` so chunking does not care which ran.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from eb.config import get_settings


@dataclass
class Block:
    """A parsed unit: paragraph, heading, table (as markdown) or figure caption."""

    kind: str  # paragraph | heading | table | figure
    text: str
    page: int | None = None
    level: int = 0  # heading level when kind == heading
    bbox: list[float] | None = None


@dataclass
class ParsedDocument:
    blocks: list[Block] = field(default_factory=list)
    page_count: int | None = None
    parse_pass: str = "text_layer"  # text_layer | layout | vlm
    title: str | None = None

    @property
    def text(self) -> str:
        return "\n\n".join(b.text for b in self.blocks)


_HEADING_RE = re.compile(
    r"^\s*(?:(?:section|clause|chapter)\s+)?(\d+(?:\.\d+){0,4})\.?\s+([A-Z][^\n]{2,120})$",
    re.IGNORECASE,
)
_ALLCAPS_RE = re.compile(r"^[A-Z0-9][A-Z0-9 ,\-/&()]{4,80}$")


_SENTENCE_END_RE = re.compile(r"[.;:]\s*$")
_REQ_WORD_RE = re.compile(r"\b(shall|must|should|will|is|are)\b", re.IGNORECASE)


def _looks_like_heading(s: str) -> bool:
    """Numbered headings are short, have no sentence punctuation and no verb of obligation."""
    return len(s) <= 90 and not _SENTENCE_END_RE.search(s) and not _REQ_WORD_RE.search(s)


def _classify_line(line: str) -> Block | None:
    s = line.strip()
    if not s:
        return None
    m = _HEADING_RE.match(s)
    if m and _looks_like_heading(s):
        level = m.group(1).count(".") + 1
        return Block("heading", s, level=level)
    if _ALLCAPS_RE.match(s) and len(s.split()) <= 12:
        return Block("heading", s.title(), level=1)
    return Block("paragraph", s)


def _blocks_from_page_text(text: str, page: int | None) -> list[Block]:
    """Join wrapped lines into paragraphs; detect numbered headings."""
    blocks: list[Block] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            blocks.append(Block("paragraph", " ".join(buf), page=page))
            buf.clear()

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            flush()
            continue
        b = _classify_line(line)
        if b is None:
            continue
        if b.kind == "heading":
            flush()
            b.page = page
            blocks.append(b)
        else:
            # New clause number at line start also starts a new paragraph.
            if buf and re.match(r"^\s*\d+(\.\d+)+\s", line):
                flush()
            buf.append(line.strip())
    flush()
    return blocks


def parse_pdf_text_layer(data: bytes) -> ParsedDocument:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    doc = ParsedDocument(page_count=len(reader.pages), parse_pass="text_layer")
    meta_title = None
    try:
        meta_title = (reader.metadata or {}).get("/Title")  # type: ignore[union-attr]
    except Exception:  # pragma: no cover - metadata is best effort
        pass
    doc.title = str(meta_title) if meta_title else None
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        doc.blocks.extend(_blocks_from_page_text(text, i))
    return doc


def parse_markdown_or_text(data: bytes) -> ParsedDocument:
    text = data.decode("utf-8", errors="replace")
    doc = ParsedDocument(page_count=1, parse_pass="text_layer")
    buf: list[str] = []
    in_table: list[str] = []

    def flush() -> None:
        if buf:
            doc.blocks.append(Block("paragraph", " ".join(buf), page=1))
            buf.clear()

    def flush_table() -> None:
        if in_table:
            doc.blocks.append(Block("table", "\n".join(in_table), page=1))
            in_table.clear()

    for line in text.splitlines():
        s = line.rstrip()
        if s.lstrip().startswith("|"):
            flush()
            in_table.append(s.strip())
            continue
        flush_table()
        if not s.strip():
            flush()
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            flush()
            doc.blocks.append(Block("heading", m.group(2).strip(), page=1, level=len(m.group(1))))
            continue
        b = _classify_line(s)
        if b and b.kind == "heading":
            flush()
            b.page = 1
            doc.blocks.append(b)
        else:
            buf.append(s.strip())
    flush()
    flush_table()
    return doc


def parse_docx_text_layer(data: bytes) -> ParsedDocument:
    """Minimal DOCX reader: paragraphs with heading styles and tables as markdown."""
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    doc = ParsedDocument(page_count=None, parse_pass="text_layer")
    body = root.find("w:body", ns)
    if body is None:
        return doc

    def para_text(p) -> str:
        return "".join(t.text or "" for t in p.iter(f"{{{ns['w']}}}t")).strip()

    for el in body:
        tag = el.tag.split("}")[1]
        if tag == "p":
            txt = para_text(el)
            if not txt:
                continue
            style = el.find("w:pPr/w:pStyle", ns)
            sv = style.get(f"{{{ns['w']}}}val", "") if style is not None else ""
            m = re.match(r"Heading(\d)", sv or "")
            if m:
                doc.blocks.append(Block("heading", txt, level=int(m.group(1))))
            else:
                b = _classify_line(txt)
                doc.blocks.append(b or Block("paragraph", txt))
        elif tag == "tbl":
            rows = []
            for tr in el.iter(f"{{{ns['w']}}}tr"):
                cells = [para_text(tc) for tc in tr.iter(f"{{{ns['w']}}}tc")]
                rows.append("| " + " | ".join(c.replace("|", "/") for c in cells) + " |")
            if rows:
                if len(rows) > 1:
                    ncol = rows[0].count("|") - 1
                    rows.insert(1, "|" + " --- |" * max(ncol, 1))
                doc.blocks.append(Block("table", "\n".join(rows)))
    return doc


def parse_with_docling(data: bytes, filename: str) -> ParsedDocument:
    """Layout-aware pass via the Docling library (optional dependency)."""
    from docling.document_converter import DocumentConverter  # type: ignore
    from docling_core.types.io import DocumentStream  # type: ignore

    conv = DocumentConverter()
    result = conv.convert(DocumentStream(name=filename, stream=io.BytesIO(data)))
    dl = result.document
    doc = ParsedDocument(parse_pass="layout", page_count=len(dl.pages) if dl.pages else None)
    for item, _level in dl.iterate_items():
        label = getattr(item, "label", "")
        page = None
        bbox = None
        prov = getattr(item, "prov", None)
        if prov:
            page = prov[0].page_no
            bb = prov[0].bbox
            bbox = [bb.l, bb.t, bb.r, bb.b]
        if label in ("section_header", "title"):
            doc.blocks.append(Block("heading", item.text, page=page, level=1, bbox=bbox))
        elif label == "table":
            try:
                md = item.export_to_markdown(dl)
            except TypeError:
                md = item.export_to_markdown()
            doc.blocks.append(Block("table", md, page=page, bbox=bbox))
        elif label in ("picture", "figure"):
            cap = getattr(item, "caption_text", None)
            cap = cap(dl) if callable(cap) else cap
            if cap:
                doc.blocks.append(Block("figure", cap, page=page, bbox=bbox))
        elif getattr(item, "text", None):
            doc.blocks.append(Block("paragraph", item.text, page=page, bbox=bbox))
    return doc


def parse_bytes(data: bytes, filename: str, mime: str) -> ParsedDocument:
    s = get_settings()
    lower = filename.lower()
    if s.parser == "docling":
        try:
            return parse_with_docling(data, filename)
        except ImportError:
            pass  # fall through to text-layer pass
    if mime == "application/pdf" or lower.endswith(".pdf"):
        return parse_pdf_text_layer(data)
    if lower.endswith(".docx"):
        return parse_docx_text_layer(data)
    return parse_markdown_or_text(data)
