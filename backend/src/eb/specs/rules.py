"""Deterministic requirement-writing checker: INCOSE GtWR v4 style rules and EARS patterns.

No LLM. Every rule has a stable name (R<n>-<Name>), a severity and a message so the UI can
show per-rule guidance and the reviewer can waive a rule knowingly.
"""

from __future__ import annotations

import re
from typing import Any

from eb.compliance.units import parse_quantity

VAGUE_TERMS = [
    "adequate",
    "appropriate",
    "sufficient",
    "as required",
    "as necessary",
    "etc",
    "etc.",
    "user-friendly",
    "user friendly",
    "approximately",
    "approx.",
    "about",
    "several",
    "some",
    "best",
    "optimal",
    "optimum",
    "state-of-the-art",
    "state of the art",
    "as far as possible",
    "reasonable",
    "reasonably",
    "generally",
    "normally",
    "typically",
    "usually",
    "nearly",
    "almost",
    "significant",
    "substantial",
    "relevant",
    "suitable",
    "satisfactory",
    "acceptable",
    "proper",
    "properly",
    "timely",
    "in a timely manner",
    "quickly",
    "rapidly",
    "easily",
    "easy",
    "efficiently",
    "effectively",
    "flexible",
    "robust",
    "reliable",
    "seamless",
    "intuitive",
    "and/or",
    "including but not limited to",
    "but not limited to",
    "support",
    "supports",
]
UNBOUNDED_VERBS = ["maximize", "maximise", "minimize", "minimise", "optimize", "optimise"]
ESCAPE_CLAUSES = [
    "if possible",
    "where possible",
    "where practicable",
    "as practicable",
    "if practicable",
    "as appropriate",
    "where appropriate",
    "if appropriate",
    "where feasible",
    "if feasible",
    "as applicable",
    "where applicable",
    "to the extent possible",
    "as far as practicable",
    "unless otherwise",
    "where necessary",
    "if necessary",
    "as agreed",
    "to be agreed",
]
NON_MEASURABLE_ADJ = [
    "fast",
    "slow",
    "quick",
    "high-quality",
    "high quality",
    "lightweight",
    "heavy-duty",
    "heavy duty",
    "modern",
    "simple",
    "safe",
    "secure",
    "stable",
    "durable",
    "strong",
    "powerful",
    "quiet",
    "silent",
    "compact",
    "small",
    "large",
    "big",
    "long-lasting",
    "maintenance-free",
    "maintenance free",
    "cost-effective",
    "cost effective",
    "cheap",
    "inexpensive",
    "ergonomic",
    "accurate",
    "precise",
    "clean",
    "smooth",
    "good",
    "better",
    "excellent",
    "superior",
    "minimal",
    "maximal",
    "low-noise",
]
UNIVERSALS = ["all", "always", "never", "every", "any", "none", "each and every", "at all times"]
PRONOUNS = [
    "it",
    "they",
    "them",
    "its",
    "their",
    "theirs",
    "he",
    "she",
    "him",
    "her",
    "this",
    "these",
    "those",
]
TBD = ["tbd", "tbc", "tba", "to be determined", "to be confirmed", "to be defined", "to be advised", "???"]
_PASSIVE_RE = re.compile(
    r"\b(?:shall|must)\s+(?:not\s+)?be\s+(?:\w+ly\s+)?(?P<part>[a-z]+(?:ed|en|t|wn|ne))\b(?!\s+by\b)",
    re.IGNORECASE,
)
_PASSIVE_EXCLUDE = {
    "not",
    "least",
    "set",
    "fit",
    "cast",
    "cut",
    "flat",
    "lit",
    "wet",
    "hot",
    "left",
    "right",
    "present",
    "resistant",
    "compliant",
    "independent",
    "sent",
    "ten",
    "open",
    "sudden",
    "wooden",
    "golden",
    "often",
    "then",
    "even",
    "seven",
    "between",
    "subject",
    "constant",
    "built-in",
}
_MODAL_RE = re.compile(r"\b(shall|must|should|may|will|can|could|would|might)\b", re.IGNORECASE)
_SHALL_RE = re.compile(r"\b(shall|must)\b", re.IGNORECASE)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(\[])|\n+")
_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9.\-/])[-+]?\d+(?:[.,]\d+)?(?![A-Za-z0-9\-/]|[.,]\d)")
_STANDARD_PREFIX = re.compile(
    r"\b(?:ISO|IEC|EN|ASTM|API|ASME|ANSI|DIN|BS|IEEE|NFPA|NEMA|UL|RAL|Grade|Class|Type|Model|Table|"
    r"Section|Clause|Figure|Fig\.?|Rev\.?|Revision|No\.?|Item|Part|Page|Annex|Schedule|Sch\.?|DN|PN|NPS|"
    r"SIL|IP|IK|Zone|Category|Cat\.?|phase|pole|stage|pass)\s*$",
    re.IGNORECASE,
)


def _has_phrase(text: str, phrase: str) -> bool:
    pat = r"(?<![A-Za-z-])" + re.escape(phrase) + r"(?![A-Za-z-])"
    return re.search(pat, text, re.IGNORECASE) is not None


def classify_ears(text: str) -> str | None:
    """EARS pattern of one requirement sentence, or None when it has no modal of obligation."""
    s = text.strip()
    if not _MODAL_RE.search(s):
        return None
    head = s[: max(0, s.lower().find(" shall")) or len(s)].lower() if " shall" in s.lower() else s.lower()
    event = re.match(r"^\s*(when|upon|after|once|on\s+(?:receipt|detection|loss)|in\s+the\s+event)\b", head)
    state = re.match(r"^\s*(while|whilst|during|as\s+long\s+as|whenever\s+in)\b", head)
    option = re.match(r"^\s*where\b", head)
    unwanted = re.match(r"^\s*if\b", head) and re.search(r"\bthen\b", s, re.IGNORECASE)
    n = sum(1 for x in (event, state, option, unwanted) if x)
    # A second trigger inside the precondition makes it complex ("While ..., when ..., the ...").
    inner = re.search(r",\s*(when|while|where|if)\b", head)
    if n > 1 or (n == 1 and inner):
        return "complex"
    if unwanted:
        return "unwanted"
    if event:
        return "event-driven"
    if state:
        return "state-driven"
    if option:
        return "optional"
    if re.match(r"^\s*if\b", head):
        return "unwanted"
    return "ubiquitous"


def _issue(rule: str, severity: str, message: str) -> dict[str, str]:
    return {"rule": rule, "severity": severity, "message": message}


def check_requirement(text: str) -> dict[str, Any]:
    """Check one requirement sentence. Returns {"issues": [...], "ears_pattern": ...}."""
    s = " ".join(text.split())
    low = s.lower()
    issues: list[dict[str, str]] = []

    # R1 vague terms and unbounded verbs
    found = [t for t in VAGUE_TERMS if _has_phrase(s, t)]
    for v in UNBOUNDED_VERBS:
        if _has_phrase(s, v) and not parse_quantity(s):
            found.append(v)
    if found:
        issues.append(
            _issue(
                "R1-NoVagueTerms",
                "error",
                "Vague or unbounded term(s): "
                + ", ".join(f"'{t}'" for t in sorted(set(found)))
                + ". State a measurable value or condition.",
            )
        )

    # R2 escape clauses
    esc = [t for t in ESCAPE_CLAUSES if _has_phrase(s, t)]
    if esc:
        issues.append(
            _issue(
                "R2-NoEscapeClauses",
                "error",
                "Escape clause(s): "
                + ", ".join(f"'{t}'" for t in esc)
                + ". A requirement is binding; remove the loophole or make the condition explicit.",
            )
        )

    # R3 modal verb
    shall_count = len(_SHALL_RE.findall(s))
    if shall_count == 0:
        weak = re.findall(r"\b(should|may|will|can|could|would|might)\b", s, re.IGNORECASE)
        if weak:
            issues.append(
                _issue(
                    "R3-UseShall",
                    "error",
                    f"Uses '{weak[0].lower()}' instead of 'shall'. "
                    "'shall' is the only binding modal; 'should' is a goal, 'will' a fact, "
                    "'may' a permission.",
                )
            )
        else:
            issues.append(
                _issue(
                    "R3-UseShall", "error", "No 'shall': the sentence does not read as a binding requirement."
                )
            )
    elif re.search(r"\b(should|may|will)\b", s, re.IGNORECASE):
        issues.append(
            _issue(
                "R3-UseShall",
                "warning",
                "Mixes 'shall' with 'should'/'may'/'will'; keep one binding modal per requirement.",
            )
        )

    # R4 one requirement per sentence
    multi: list[str] = []
    if shall_count >= 2:
        multi.append(f"{shall_count} occurrences of shall/must")
    if _has_phrase(s, "and/or"):
        multi.append("'and/or'")
    if re.search(
        r"\b(shall|must)\b[^.;]*\b(?:,\s*and|;\s*and|and\s+(?:shall|must|also))\b", s, re.IGNORECASE
    ):
        multi.append("conjoined clauses")
    if multi:
        issues.append(
            _issue(
                "R4-SingleThought",
                "error",
                "More than one requirement in a sentence ("
                + "; ".join(multi)
                + "). Split so each can be verified and traced on its own.",
            )
        )

    # R5 active voice with an explicit actor
    pm = _PASSIVE_RE.search(s)
    if pm and pm.group("part").lower() not in _PASSIVE_EXCLUDE:
        issues.append(
            _issue(
                "R5-ActiveVoice",
                "warning",
                f"Passive construction 'be {pm.group('part')}' without an actor; "
                "name who or what performs the action (e.g. 'The supplier shall ...').",
            )
        )

    # R6 negative requirements
    if re.search(r"\b(shall|must)\s+not\b", s, re.IGNORECASE):
        issues.append(
            _issue(
                "R6-AvoidNegatives",
                "info",
                "Negative requirement ('shall not'). Prefer stating the required behaviour; "
                "keep negatives only for genuine prohibitions.",
            )
        )

    # R7 bare numbers without a unit; R8 numeric value without tolerance or bound
    quantities = parse_quantity(s)
    # A bare integer is not a quantity for R7; decimals (ratios, factors) and percentages are.
    covered = [(q.start, q.end) for q in quantities if q.unit is not None or "." in q.text]
    for nm in _NUMBER_RE.finditer(s):
        if any(a <= nm.start() < b for a, b in covered):
            continue
        before = s[: nm.start()]
        if _STANDARD_PREFIX.search(before):
            continue  # ISO 9906, Grade 2, Table 3, RAL 5015 are identifiers
        if re.match(r"^\s*(?:-\s*)?(?:phase|pole|stage|pass|x\b|off\b|%)", s[nm.end() :], re.IGNORECASE):
            continue
        issues.append(
            _issue(
                "R7-UnitsOnNumbers",
                "warning",
                f"Number '{nm.group(0)}' has no unit. State the unit, or the quantity it counts.",
            )
        )
        break
    for q in quantities:
        if q.unit == "percent" and q.value in (0.0, 100.0):
            continue
        bounded = q.op is not None or q.tol is not None or q.tol_rel is not None or q.high is not None
        if not bounded and not re.search(
            r"\b(min|max|minimum|maximum|at least|not (?:less|more) than|"
            r"within|between|up to|exceed|rated|nominal|±|\+/-)\b",
            low,
        ):
            issues.append(
                _issue(
                    "R8-Tolerance",
                    "warning",
                    f"Value '{q.text}' has no tolerance or bound. Use 'not less than', "
                    "'not more than', a range or ± tolerance so compliance is decidable.",
                )
            )
            break

    # R9 pronouns
    prons = [p for p in PRONOUNS if re.search(rf"\b{p}\b", s, re.IGNORECASE)]
    if prons:
        issues.append(
            _issue(
                "R9-NoPronouns",
                "warning",
                "Pronoun(s) "
                + ", ".join(f"'{p}'" for p in prons)
                + ": repeat the noun so the sentence stands on its own.",
            )
        )

    # R10 non-measurable adjectives
    adj = [a for a in NON_MEASURABLE_ADJ if _has_phrase(s, a)]
    if adj and not quantities:
        issues.append(
            _issue(
                "R10-Measurable",
                "warning",
                "Non-measurable adjective(s): "
                + ", ".join(f"'{a}'" for a in adj)
                + ". Replace with a quantified characteristic.",
            )
        )

    # R11 placeholders
    tbd = [t for t in TBD if _has_phrase(s, t)]
    if tbd:
        issues.append(
            _issue(
                "R11-NoTBD",
                "error",
                "Placeholder "
                + ", ".join(f"'{t.upper()}'" for t in tbd)
                + ": the requirement is incomplete and cannot be verified.",
            )
        )

    # R12 universal quantifiers
    uni = [u for u in UNIVERSALS if _has_phrase(s, u)]
    if uni:
        issues.append(
            _issue(
                "R12-UniversalQuantifiers",
                "warning",
                "Universal quantifier(s) "
                + ", ".join(f"'{u}'" for u in uni)
                + ": confirm the set is really unbounded, or name it.",
            )
        )

    # R13 length
    words = len(s.split())
    if words > 50:
        issues.append(
            _issue(
                "R13-Length", "warning", f"{words} words; keep a requirement under 50 words by splitting it."
            )
        )

    return {"issues": issues, "ears_pattern": classify_ears(s)}


def split_requirements(text: str) -> list[str]:
    """Sentences or lines that carry a modal of obligation (shall/must/should/will/may)."""
    out: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^(?:[-*•]|\d+(?:\.\d+)*\.?|[A-Z]\)|\(\w\))\s+", "", line)  # list markers / clause ids
        line = re.sub(r"^\|?\s*[^|]*\|\s*", "", line) if line.startswith("|") else line  # table cells
        for sent in _SENTENCE_SPLIT.split(line):
            sent = sent.strip()
            if sent and re.search(r"\b(shall|must|should|will|may)\b", sent, re.IGNORECASE):
                out.append(sent)
    return out


def check_text(text: str) -> list[dict[str, Any]]:
    """Check every requirement sentence in a block of text."""
    results = []
    for sent in split_requirements(text):
        r = check_requirement(sent)
        results.append({"text": sent, "issues": r["issues"], "ears_pattern": r["ears_pattern"]})
    return results


def summarise(results: list[dict[str, Any]]) -> dict[str, int]:
    errors = sum(1 for r in results for i in r["issues"] if i["severity"] == "error")
    warnings = sum(1 for r in results for i in r["issues"] if i["severity"] == "warning")
    infos = sum(1 for r in results for i in r["issues"] if i["severity"] == "info")
    return {"requirements": len(results), "errors": errors, "warnings": warnings, "info": infos}
