"""Draft an equipment specification from a template, the wiki and project documents (6.6)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from pydantic import BaseModel, Field

from eb.auth import Principal
from eb.llm import DocumentBlock, get_llm
from eb.retrieval.search import Hit, Scope, search
from eb.specs import rules
from eb.specs.templates import Template, get_template

log = structlog.get_logger(__name__)

MAX_EVIDENCE = 40
HITS_PER_PARAM = 3


class DraftParameter(BaseModel):
    name: str
    value: str | None = None
    unit: str | None = None
    source_index: int | None = Field(default=None, description="index of the <source> the value comes from")
    note: str = ""


class DraftResponse(BaseModel):
    parameters: list[DraftParameter] = Field(default_factory=list)
    requirements_markdown: str = ""


DRAFT_SYSTEM = """You help an engineer draft an equipment requirement specification.

You receive an equipment template (parameters with units) and numbered <source> blocks from the \
organisation's wiki and project documents. Fill the parameters only from the sources:
- value: the value as written in the source (with the number exactly as written). Leave null when \
no source gives it; never invent, estimate or use typical values.
- unit: the unit as written; convert nothing.
- source_index: the source the value comes from, or null.
- note: one short remark (e.g. "from P&ID line list", "conflicting values in sources 2 and 5").
requirements_markdown: one requirement per line, each a single sentence using "shall", with the \
value and unit, and tolerance or bound (not less than / not more than / ±). Write requirements only \
for parameters you could fill or that are marked required; mark unknown values as TBD. Do not \
include the parameter table, headings or commentary."""


def _citation(h: Hit) -> str:
    if h.source == "wiki":
        return f"wiki: {h.title}"
    bits = [h.doc_number or h.title or "document"]
    if h.revision:
        bits.append(f"Rev {h.revision}")
    if h.clause_id:
        bits.append(f"clause {h.clause_id}")
    if h.page_start:
        bits.append(f"p.{h.page_start}")
    return " ".join(bits)


def gather_evidence(
    tmpl: Template,
    user: Principal,
    *,
    project: str | None,
    context: str | None,
    document_ids: list[UUID] | None,
) -> list[Hit]:
    scope = Scope(
        project=project, document_ids=document_ids or None, include_wiki=True, include_documents=True
    )
    seen: set[UUID] = set()
    hits: list[Hit] = []
    for p in tmpl.parameters:
        q = f"{tmpl.name} {p.name}" + (f" {context}" if context else "")
        try:
            found = search(q, user=user, scope=scope, k=HITS_PER_PARAM)
        except Exception as e:  # pragma: no cover - retrieval errors should not block drafting
            log.warning("specs.draft.search_failed", parameter=p.name, error=str(e))
            found = []
        for h in found:
            if h.id not in seen:
                seen.add(h.id)
                hits.append(h)
        if len(hits) >= MAX_EVIDENCE:
            break
    return hits[:MAX_EVIDENCE]


def _llm_fill(tmpl: Template, hits: list[Hit], context: str | None) -> DraftResponse | None:
    docs = [DocumentBlock(text=f"{h.context_prefix}\n{h.text}".strip(), title=_citation(h)) for h in hits]
    lines = [f"Equipment: {tmpl.name} ({tmpl.discipline}). Standards: {', '.join(tmpl.standards_refs)}."]
    if context:
        lines.append(f"Project context: {context}")
    lines.append("Template parameters (name | unit | required | description):")
    for p in tmpl.parameters:
        lines.append(
            f"- {p.name} | {p.unit or '-'} | {'required' if p.required else 'optional'} | {p.description}"
        )
    lines.append("Fill the parameters from the sources and write the requirement sentences.")
    try:
        return get_llm().parse(
            schema=DraftResponse, system=DRAFT_SYSTEM, user="\n".join(lines), documents=docs
        )
    except Exception as e:
        log.warning("specs.draft.llm_failed", error=str(e))
        return None


def _interface_requirements(tmpl: Template) -> list[str]:
    out = []
    for p in tmpl.parameters:
        if p.interface:
            out.append(
                f"The supplier shall state the {p.name.lower()}"
                + (f" in {p.unit}" if p.unit else "")
                + f" for the {p.interface} design interface."
            )
    for item in tmpl.interface_checklist:
        out.append(
            f"The {item.from_discipline} and {item.to_discipline} disciplines shall confirm the "
            f"{item.topic.lower()} interface: {item.check}"
        )
    return out


def draft_spec(
    template_key: str,
    user: Principal,
    project: str | None = None,
    context: str | None = None,
    document_ids: list[UUID] | None = None,
) -> dict[str, Any]:
    tmpl = get_template(template_key)
    if tmpl is None:
        raise KeyError(f"unknown template {template_key!r}")
    hits = gather_evidence(tmpl, user, project=project, context=context, document_ids=document_ids)
    llm = _llm_fill(tmpl, hits, context) if hits else None
    filled = {p.name: p for p in (llm.parameters if llm else [])}

    parameters: list[dict[str, Any]] = []
    for p in tmpl.parameters:
        f = filled.get(p.name)
        src = (
            hits[f.source_index]
            if f and f.source_index is not None and 0 <= f.source_index < len(hits)
            else None
        )
        parameters.append(
            {
                "name": p.name,
                "unit": (f.unit if f and f.unit else p.unit),
                "value": f.value if f else None,
                "required": p.required,
                "interface": p.interface,
                "description": p.description,
                "source": _citation(src) if src else None,
                "chunk_id": str(src.id) if src else None,
                "note": (f.note if f else ("no evidence retrieved" if not hits else "not found in sources")),
            }
        )

    req_lines = [ln.strip() for ln in (llm.requirements_markdown if llm else "").splitlines() if ln.strip()]
    interface_lines = _interface_requirements(tmpl)

    md: list[str] = [f"# {tmpl.name} requirement specification", ""]
    if context:
        md += [f"_Context: {context}_", ""]
    if project:
        md += [f"_Project: {project}_", ""]
    md += [
        "## 1 Scope",
        "",
        f"This specification covers the {tmpl.name.lower()} ({tmpl.discipline}). "
        "Values below were drafted from the sources cited; every value must be reviewed by the "
        "responsible engineer before issue.",
        "",
    ]
    md += ["## 2 Reference standards", ""] + [f"- {s}" for s in tmpl.standards_refs] + [""]
    md += [
        "## 3 Parameters",
        "",
        "| Parameter | Value | Unit | Source | Note |",
        "| --- | --- | --- | --- | --- |",
    ]
    for p in parameters:
        md.append(
            f"| {p['name']} | {p['value'] if p['value'] is not None else 'TBD'} | {p['unit'] or '-'} | "
            f"{p['source'] or '-'} | {p['note'] or ''} |"
        )
    md += ["", "## 4 Requirements", ""]
    md += [f"4.{i} {line}" for i, line in enumerate(req_lines, start=1)] or [
        "(no requirements drafted: no evidence)"
    ]
    md += ["", "## 5 Interface requirements", ""]
    md += [f"5.{i} {line}" for i, line in enumerate(interface_lines, start=1)]
    md += ["", "## 6 Interface checklist", ""]
    md += [
        f"- **{i.topic}** ({i.from_discipline} -> {i.to_discipline}): {i.check}"
        for i in tmpl.interface_checklist
    ]
    markdown = "\n".join(md) + "\n"

    issues = rules.check_text("\n".join(req_lines + interface_lines))
    return {
        "template": tmpl.key,
        "markdown": markdown,
        "parameters": parameters,
        "issues": issues,
        "issue_summary": rules.summarise(issues),
        "sources": [h.to_dict() for h in hits],
        "llm_used": llm is not None,
    }
