"""Compliance run: retrieve evidence, ask the LLM for a verdict, verify in code (architecture 6.5).

For every requirement in the set:
  1. hybrid search inside the subject revision (<= 8 chunks, tables included);
  2. schema-constrained LLM verdict with verbatim quotes;
  3. code verification: each quote must be a normalised substring of the cited chunk, else it is
     dropped; a compliant/non_compliant verdict with no surviving quote becomes `unverified`;
  4. numeric clauses: values are parsed from the verified quotes with pint and compared in code;
     the code result overrides the LLM verdict (the LLM verdict is kept separately);
  5. routing: low confidence, insufficient evidence, partial, unverified -> needs_review.
Reverse pass: subject "shall" chunks nobody cited are listed as unrequested claims.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID, uuid4

import structlog

from eb.auth import Principal
from eb.compliance import units
from eb.compliance.models import LLMVerdict
from eb.config import get_settings
from eb.db import connection
from eb.llm import DocumentBlock, get_llm
from eb.retrieval.search import Hit, Scope, search

log = structlog.get_logger(__name__)

EVIDENCE_K = 8
LOW_CONFIDENCE = 0.6
REVIEW_VERDICTS = {"insufficient_evidence", "partial", "unverified"}

VERDICT_SYSTEM = """You assess whether a supplier document complies with ONE requirement.

You are given numbered <source> blocks copied from the supplier document. Decide strictly from them.

Rules:
- verdict: compliant (the sources state the requirement is met), non_compliant (the sources state a \
value or property that violates it), partial (met in part or with deviations), insufficient_evidence \
(the sources do not address it), not_applicable.
- quotes: copy the exact text, verbatim, character for character, from the source that supports the \
verdict, with its source_index. Never paraphrase, never merge text from two sources, never quote \
anything that is not in a source. A compliant or non_compliant verdict without a verbatim quote is \
not acceptable: use insufficient_evidence instead.
- found_values: every number with its unit that the sources give for the requirement's parameter(s), \
exactly as written (e.g. "20 bar(g)"), with its source_index.
- Do not compute or convert units yourself; report the values as written. Code compares them.
- Do not guess, infer from silence, or assume industry practice. Absence of evidence is \
insufficient_evidence, not compliance.
- confidence: 0 to 1, how sure you are that the sources support the verdict.
- rationale: one or two sentences naming the evidence."""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().casefold()


def quote_in_text(quote: str, text: str) -> bool:
    q = _norm(quote)
    return bool(q) and q in _norm(text)


def _principal_for_run(conn, started_by: UUID | None, document_id: UUID) -> Principal:
    """The run searches as the user who started it; otherwise as the groups that can read the subject."""
    if started_by:
        u = conn.execute("SELECT id, email, display_name FROM users WHERE id = %s", (started_by,)).fetchone()
        if u:
            groups = conn.execute(
                "SELECT group_id FROM user_groups WHERE user_id = %s", (started_by,)
            ).fetchall()
            return Principal(
                id=u["id"],
                email=u["email"],
                display_name=u["display_name"],
                group_ids=[g["group_id"] for g in groups],
            )
    groups = conn.execute(
        "SELECT group_id FROM document_acl WHERE document_id = %s", (document_id,)
    ).fetchall()
    return Principal(
        id=uuid4(),
        email="system@compliance",
        display_name="compliance worker",
        group_ids=[g["group_id"] for g in groups],
    )


def _hit_title(h: Hit) -> str:
    bits = [h.doc_number or "", h.title or ""]
    if h.clause_id:
        bits.append(f"clause {h.clause_id}")
    if h.page_start:
        bits.append(f"p.{h.page_start}")
    if h.kind == "table":
        bits.append("[table]")
    return " ".join(b for b in bits if b).strip()


def _quantities_of(requirement: dict[str, Any]) -> list[dict[str, Any]]:
    q = requirement.get("quantity")
    if not q:
        return []
    if isinstance(q, list):
        return [x for x in q if isinstance(x, dict)]
    out = [{k: v for k, v in q.items() if k != "and"}]
    for extra in q.get("and") or []:
        if isinstance(extra, dict):
            out.append({k: v for k, v in extra.items() if k != "and"})
    return out


def _param_overlap(param: str | None, q: units.Quantity) -> int:
    if not param:
        return 0
    words = {w for w in re.findall(r"[a-z]+", param.lower()) if len(w) > 2}
    ctx = set(re.findall(r"[a-z]+", q.context.lower()))
    return len(words & ctx)


def numeric_check(requirement: dict[str, Any], texts: list[str]) -> dict[str, Any] | None:
    """Compare every required quantity against the values found in `texts`. None when no quantity."""
    required = _quantities_of(requirement)
    if not required:
        return None
    found: list[units.Quantity] = []
    for t in texts:
        found.extend(units.parse_quantity(t))
    checks: list[dict[str, Any]] = []
    for req in required:
        cands = [q for q in found if units.compatible(req, q)]
        if not cands:
            checks.append(
                {
                    "required": req,
                    "result": "unknown",
                    "found": None,
                    "detail": "no value with unit compatible with "
                    f"{req.get('unit') or 'a dimensionless number'}"
                    f" found in the verified evidence",
                }
            )
            continue
        best = max(_param_overlap(req.get("param"), q) for q in cands)
        chosen = [q for q in cands if _param_overlap(req.get("param"), q) == best] if best > 0 else cands
        results = [units.compare(req, q) for q in chosen]
        outcomes = {r["result"] for r in results}
        if len(results) == 1 or len(outcomes) == 1:
            r = results[0] if len(results) == 1 else next(x for x in results if x["result"] in outcomes)
            if len(results) > 1:
                r = dict(r, detail=r["detail"] + f" ({len(results)} candidate values agree)")
            checks.append(r)
        else:
            checks.append(
                {
                    "required": req,
                    "result": "unknown",
                    "found": [str(q) for q in chosen],
                    "detail": "conflicting candidate values: " + "; ".join(x["detail"] for x in results),
                }
            )
    outcomes = [c["result"] for c in checks]
    result = "fail" if "fail" in outcomes else "unknown" if "unknown" in outcomes else "pass"
    return {
        "result": result,
        "detail": "; ".join(c["detail"] for c in checks),
        "required": required,
        "found": [str(q) for q in found],
        "checks": checks,
    }


def _verdict_from_numeric(result: str) -> str:
    return {"pass": "compliant", "fail": "non_compliant"}.get(result, "insufficient_evidence")


def assess(
    requirement: dict[str, Any], hits: list[Hit], llm_out: LLMVerdict | None, llm_error: str | None = None
) -> dict[str, Any]:
    """Pure decision step: verify quotes, run the numeric check, route to review. No I/O."""
    evidence: list[dict[str, Any]] = []
    dropped = 0
    cited: set[UUID] = set()
    verified_texts: list[str] = []
    if llm_out is None:
        rationale = (
            "No evidence retrieved from the subject document."
            if not hits
            else f"LLM verdict unavailable: {llm_error or 'no output'}"
        )
        return {
            "verdict": "insufficient_evidence",
            "llm_verdict": None,
            "confidence": None,
            "evidence": [],
            "numeric_check": numeric_check(requirement, []) if requirement.get("quantity") else None,
            "rationale": rationale,
            "needs_review": True,
            "cited_chunk_ids": set(),
        }

    for q in llm_out.quotes:
        if 0 <= q.source_index < len(hits) and quote_in_text(q.quote, hits[q.source_index].text):
            h = hits[q.source_index]
            evidence.append(
                {
                    "chunk_id": str(h.id),
                    "quote": q.quote.strip(),
                    "page": h.page_start,
                    "verified": True,
                    "clause_id": h.clause_id,
                }
            )
            cited.add(h.id)
            verified_texts.append(q.quote)
        else:
            dropped += 1
    for fv in llm_out.found_values:
        if 0 <= fv.source_index < len(hits) and quote_in_text(fv.value_text, hits[fv.source_index].text):
            verified_texts.append(fv.value_text)
            cited.add(hits[fv.source_index].id)

    llm_verdict = llm_out.verdict
    verdict = llm_verdict
    rationale = llm_out.rationale or ""
    if dropped:
        rationale += f" [{dropped} quote(s) dropped: not found verbatim in the cited source]"
    if not evidence and verdict in ("compliant", "non_compliant"):
        verdict = "unverified"

    nc = numeric_check(requirement, verified_texts)
    if nc is not None:
        code_verdict = _verdict_from_numeric(nc["result"])
        nc["overrode_llm"] = code_verdict != llm_verdict
        verdict = code_verdict
        if nc["overrode_llm"]:
            rationale += f" [code numeric check: {nc['result']} -> {code_verdict}; LLM said {llm_verdict}]"

    needs_review = (
        verdict in REVIEW_VERDICTS
        or llm_out.confidence < LOW_CONFIDENCE
        or bool(nc and nc.get("overrode_llm"))
    )
    return {
        "verdict": verdict,
        "llm_verdict": llm_verdict,
        "confidence": llm_out.confidence,
        "evidence": evidence,
        "numeric_check": nc,
        "rationale": rationale.strip(),
        "needs_review": needs_review,
        "cited_chunk_ids": cited,
    }


def _search_query(requirement: dict[str, Any]) -> str:
    text = requirement["text"]
    params = [q.get("param") for q in _quantities_of(requirement) if q.get("param")]
    return " ".join([text, *params])[:1500]


def _llm_verdict(requirement: dict[str, Any], hits: list[Hit]) -> tuple[LLMVerdict | None, str | None]:
    docs = [DocumentBlock(text=h.text, title=_hit_title(h)) for h in hits]
    user = (
        f"Requirement {requirement['req_id']}: {requirement['text']}\n"
        + (f"Structured quantity: {requirement['quantity']}\n" if requirement.get("quantity") else "")
        + "Assess compliance of the supplier document against this requirement using only the sources."
    )
    try:
        return get_llm().parse(schema=LLMVerdict, system=VERDICT_SYSTEM, user=user, documents=docs), None
    except Exception as e:
        log.warning("compliance.verdict.llm_failed", req_id=requirement["req_id"], error=str(e))
        return None, str(e)[:500]


def _store_finding(conn, run_id: UUID, requirement_id: UUID, a: dict[str, Any]) -> None:
    import json

    conn.execute(
        """
        INSERT INTO compliance_findings (run_id, requirement_id, verdict, llm_verdict, confidence, evidence,
                                         numeric_check, rationale, needs_review)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
        ON CONFLICT (run_id, requirement_id) DO UPDATE SET
            verdict = EXCLUDED.verdict, llm_verdict = EXCLUDED.llm_verdict, confidence = EXCLUDED.confidence,
            evidence = EXCLUDED.evidence, numeric_check = EXCLUDED.numeric_check,
            rationale = EXCLUDED.rationale, needs_review = EXCLUDED.needs_review
        """,
        (
            run_id,
            requirement_id,
            a["verdict"],
            a["llm_verdict"],
            a["confidence"],
            json.dumps(a["evidence"]),
            json.dumps(a["numeric_check"]) if a["numeric_check"] is not None else None,
            a["rationale"],
            a["needs_review"],
        ),
    )


def _unrequested_claims(conn, revision_id: UUID, cited: set[UUID]) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, clause_id, page_start, text FROM chunks
        WHERE revision_id = %s AND kind = 'requirement' ORDER BY ordinal
        """,
        (revision_id,),
    ).fetchall()
    out = []
    for r in rows:
        if r["id"] in cited:
            continue
        out.append(
            {
                "chunk_id": str(r["id"]),
                "clause_id": r["clause_id"],
                "page": r["page_start"],
                "text": r["text"][:300],
            }
        )
        if len(out) >= 50:
            break
    return out


def run_check(run_id: UUID) -> dict[str, Any]:
    """Execute a compliance run end to end and return its summary."""
    import json

    s = get_settings()
    with connection() as conn:
        run = conn.execute("SELECT * FROM compliance_runs WHERE id = %s", (run_id,)).fetchone()
        if run is None:
            raise KeyError(f"compliance run {run_id} not found")
        conn.execute(
            "UPDATE compliance_runs SET status = 'running', model = coalesce(model, %s), error = NULL "
            "WHERE id = %s",
            (s.llm_model_answer, run_id),
        )
        principal = _principal_for_run(conn, run["started_by"], run["subject_document_id"])
        requirements = conn.execute(
            "SELECT * FROM requirements WHERE set_id = %s ORDER BY ordinal, created_at, req_id",
            (run["set_id"],),
        ).fetchall()

    scope = Scope(revision_ids=[run["subject_revision_id"]], include_wiki=False, active_only=False)
    counts: dict[str, int] = {}
    needs_review = 0
    llm_errors = 0
    cited_all: set[UUID] = set()
    false_compliant = 0
    try:
        for req in requirements:
            hits = search(_search_query(req), user=principal, scope=scope, k=EVIDENCE_K)
            llm_out, err = _llm_verdict(req, hits) if hits else (None, None)
            if hits and llm_out is None:
                llm_errors += 1
            a = assess(req, hits, llm_out, err)
            counts[a["verdict"]] = counts.get(a["verdict"], 0) + 1
            needs_review += int(a["needs_review"])
            cited_all |= a["cited_chunk_ids"]
            if a["verdict"] == "compliant" and not any(e["verified"] for e in a["evidence"]):
                false_compliant += 1
            with connection() as conn:
                _store_finding(conn, run_id, req["id"], a)
        with connection() as conn:
            unrequested = _unrequested_claims(conn, run["subject_revision_id"], cited_all)
            summary = {
                "total": len(requirements),
                "verdicts": counts,
                "needs_review": needs_review,
                "false_compliant_guard": false_compliant,
                "llm_errors": llm_errors,
                "evidence_chunks_cited": len(cited_all),
                "unrequested_claims": unrequested,
                "unrequested_claims_count": len(unrequested),
            }
            conn.execute(
                "UPDATE compliance_runs SET status = 'done', summary = %s::jsonb, finished_at = now() "
                "WHERE id = %s",
                (json.dumps(summary), run_id),
            )
    except Exception as e:
        with connection() as conn:
            conn.execute(
                "UPDATE compliance_runs SET status = 'failed', error = %s, finished_at = now() WHERE id = %s",
                (str(e)[:2000], run_id),
            )
        raise
    log.info(
        "compliance.run.done",
        run_id=str(run_id),
        **{k: v for k, v in summary.items() if k != "unrequested_claims"},
    )
    return summary
