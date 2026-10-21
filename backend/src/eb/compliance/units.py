"""Quantities with units in engineering free text, and deterministic comparison with pint.

`parse_quantity` finds numeric values with their units in text such as
"not less than 16 bar(g)", "250 m³/h", "10–16 bar", "45 m ±5%", "+/- 2 mm", "38 °C".
Gauge/absolute suffixes on pressure units are kept as a flag, not a unit.

`compare` converts a found quantity into the required unit and applies the operator and
tolerance. Unknown units or a dimension mismatch yield "unknown", never "pass".
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from typing import Any

import pint

ureg = pint.UnitRegistry()
ureg.define("revolutions_per_minute_alias = revolutions_per_minute = rev_per_min")
ureg.define("kilovar = kilovolt_ampere = kvar = kVAr")
ureg.define("decibel_A = decibel = dBA")

# How a unit is written in documents -> a pint expression. Longest spellings are matched first.
_UNIT_TABLE: dict[str, str] = {
    # volumetric flow
    "m3/h": "m**3/hour",
    "m³/h": "m**3/hour",
    "m^3/h": "m**3/hour",
    "m3/hr": "m**3/hour",
    "m³/hr": "m**3/hour",
    "m3/min": "m**3/minute",
    "m³/min": "m**3/minute",
    "m3/s": "m**3/second",
    "m³/s": "m**3/second",
    "L/s": "liter/second",
    "l/s": "liter/second",
    "L/min": "liter/minute",
    "l/min": "liter/minute",
    "L/h": "liter/hour",
    "l/h": "liter/hour",
    "lpm": "liter/minute",
    "gpm": "gallon/minute",
    "Nm3/h": "m**3/hour",
    "Nm³/h": "m**3/hour",
    "Sm3/h": "m**3/hour",
    # mass flow / density / viscosity
    "kg/h": "kg/hour",
    "kg/s": "kg/second",
    "t/h": "metric_ton/hour",
    "kg/m3": "kg/m**3",
    "kg/m³": "kg/m**3",
    "cSt": "centistokes",
    "mPa.s": "mPa*s",
    "mPa·s": "mPa*s",
    "cP": "centipoise",
    # pressure (gauge/absolute variants carry a flag)
    "bar(g)": "bar|g",
    "bar(a)": "bar|a",
    "barg": "bar|g",
    "bara": "bar|a",
    "bar": "bar",
    "mbar": "mbar",
    "kPa(g)": "kPa|g",
    "kPa(a)": "kPa|a",
    "kPag": "kPa|g",
    "kPaa": "kPa|a",
    "kPa": "kPa",
    "MPa(g)": "MPa|g",
    "MPa(a)": "MPa|a",
    "MPag": "MPa|g",
    "MPa": "MPa",
    "Pa": "Pa",
    "psi(g)": "psi|g",
    "psi(a)": "psi|a",
    "psig": "psi|g",
    "psia": "psi|a",
    "psi": "psi",
    "atm": "atm",
    "mmH2O": "mmH2O",
    "mm H2O": "mmH2O",
    "mmWC": "mmH2O",
    "inH2O": "inH2O",
    # temperature
    "degC": "degC",
    "°C": "degC",
    "ºC": "degC",
    "deg C": "degC",
    "deg. C": "degC",
    "degF": "degF",
    "°F": "degF",
    "ºF": "degF",
    "deg F": "degF",
    "K": "kelvin",
    # electrical
    "kVA": "kVA",
    "MVA": "MVA",
    "kVAr": "kVAr",
    "kvar": "kvar",
    "kW": "kW",
    "MW": "MW",
    "W": "W",
    "kV": "kV",
    "V": "V",
    "mV": "mV",
    "kA": "kA",
    "A": "A",
    "mA": "mA",
    "Hz": "Hz",
    "kHz": "kHz",
    "kWh": "kWh",
    "MWh": "MWh",
    "Ah": "A*hour",
    # rotation / frequency
    "rpm": "revolutions_per_minute",
    "r/min": "revolutions_per_minute",
    "min-1": "1/minute",
    "min⁻¹": "1/minute",
    "1/min": "1/minute",
    "RPM": "revolutions_per_minute",
    # length / area / volume
    "mm": "mm",
    "cm": "cm",
    "km": "km",
    "m": "m",
    "µm": "micrometer",
    "um": "micrometer",
    "micron": "micrometer",
    "microns": "micrometer",
    "inch": "inch",
    "inches": "inch",
    "in.": "inch",
    '"': "inch",
    "ft": "foot",
    "mm2": "mm**2",
    "mm²": "mm**2",
    "m2": "m**2",
    "m²": "m**2",
    "cm2": "cm**2",
    "cm²": "cm**2",
    "m3": "m**3",
    "m³": "m**3",
    "L": "liter",
    "l": "liter",
    "litre": "liter",
    "litres": "liter",
    "liter": "liter",
    "liters": "liter",
    "ml": "milliliter",
    "mL": "milliliter",
    "gal": "gallon",
    # mass / force / torque / energy
    "kg": "kg",
    "g": "gram",
    "t": "metric_ton",
    "tonne": "metric_ton",
    "tonnes": "metric_ton",
    "ton": "metric_ton",
    "tons": "metric_ton",
    "lb": "pound",
    "lbs": "pound",
    "N": "N",
    "kN": "kN",
    "MN": "MN",
    "Nm": "N*m",
    "N·m": "N*m",
    "N.m": "N*m",
    "kNm": "kN*m",
    "kN·m": "kN*m",
    "kN.m": "kN*m",
    "kJ": "kJ",
    "MJ": "MJ",
    "J": "J",
    "kJ/kg": "kJ/kg",
    "kN/m2": "kN/m**2",
    "kN/m²": "kN/m**2",
    "N/mm2": "N/mm**2",
    "N/mm²": "N/mm**2",
    "MPa.s": "MPa*s",
    # time / speed / misc
    "ms": "millisecond",
    "s": "second",
    "sec": "second",
    "seconds": "second",
    "min": "minute",
    "minutes": "minute",
    "h": "hour",
    "hr": "hour",
    "hrs": "hour",
    "hours": "hour",
    "days": "day",
    "day": "day",
    "years": "year",
    "yr": "year",
    "m/s": "m/s",
    "mm/s": "mm/s",
    "km/h": "km/hour",
    "m/s2": "m/s**2",
    "m/s²": "m/s**2",
    "dB(A)": "dBA",
    "dBA": "dBA",
    "dB": "dB",
    "ppm": "ppm",
    "%": "percent",
    "percent": "percent",
    "per cent": "percent",
    "W/m2": "W/m**2",
    "W/m²": "W/m**2",
    "W/mK": "W/(m*K)",
    "W/m.K": "W/(m*K)",
    "W/(m·K)": "W/(m*K)",
}

_NUM = r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
_UNIT_ALT = "|".join(re.escape(k) for k in sorted(_UNIT_TABLE, key=len, reverse=True))
_GA = r"(?:\s?\((?P<{name}>[gaGA])\))?"

_PREFIX_OPS: list[tuple[str, str]] = [
    (r"not\s+less\s+than", ">="),
    (r"no\s+less\s+than", ">="),
    (r"at\s+least", ">="),
    (r"minimum\s+of", ">="),
    (r"minimum", ">="),
    (r"min\.", ">="),
    (r"min\b", ">="),
    (r"greater\s+than\s+or\s+equal\s+to", ">="),
    (r"≥", ">="),
    (r">=", ">="),
    (r"⩾", ">="),
    (r"not\s+more\s+than", "<="),
    (r"no\s+more\s+than", "<="),
    (r"not\s+exceed(?:ing)?", "<="),
    (r"not\s+greater\s+than", "<="),
    (r"at\s+most", "<="),
    (r"maximum\s+of", "<="),
    (r"maximum", "<="),
    (r"max\.", "<="),
    (r"max\b", "<="),
    (r"up\s+to", "<="),
    (r"less\s+than\s+or\s+equal\s+to", "<="),
    (r"≤", "<="),
    (r"<=", "<="),
    (r"⩽", "<="),
    (r"greater\s+than", ">"),
    (r"more\s+than", ">"),
    (r"exceed(?:s|ing)?", ">"),
    (r">", ">"),
    (r"less\s+than", "<"),
    (r"below", "<"),
    (r"<", "<"),
]
_PREFIX_RE = "|".join(f"(?:{p})" for p, _ in _PREFIX_OPS)

_QTY_RE = re.compile(
    rf"(?P<prefix>(?:{_PREFIX_RE})\s*)?"
    rf"(?P<n1>{_NUM})"
    rf"(?:\s*(?:[-–—]|to)\s*(?P<n2>{_NUM}))?"
    rf"(?:\s?(?P<unit>{_UNIT_ALT})(?![A-Za-z0-9²³]))?"
    + _GA.format(name="ga")
    + rf"(?:\s*(?:±|\+/-|\+/−|\+-)\s*(?P<tol>{_NUM})\s?(?P<tolunit>%|{_UNIT_ALT})?(?![A-Za-z0-9]))?",
    re.IGNORECASE,
)
_GENERIC_UNIT_RE = re.compile(
    r"\s([A-Za-zµ°]{1,8}(?:\*\*?\d|[²³])?(?:/[A-Za-z]{1,6}(?:\*\*?\d|[²³])?)?)(?![A-Za-z0-9])"
)
_ENGLISH_STOP = {
    "a",
    "an",
    "as",
    "at",
    "and",
    "or",
    "of",
    "for",
    "to",
    "in",
    "on",
    "by",
    "the",
    "is",
    "be",
    "per",
    "with",
    "from",
    "no",
    "not",
    "if",
    "each",
    "all",
    "any",
    "are",
    "was",
    "were",
    "it",
    "its",
    "that",
    "this",
    "than",
    "then",
    "when",
    "where",
    "while",
    "shall",
    "must",
    "should",
    "may",
    "will",
    "can",
    "off",
    "out",
    "up",
    "down",
    "over",
    "under",
    "about",
    "into",
    "onto",
    "has",
    "have",
    "had",
    "do",
    "does",
    "nos",
    "pcs",
    "set",
    "sets",
    "units",
    "unit",
    "items",
    "item",
    "phase",
    "pole",
    "poles",
    "stage",
    "stages",
    "pass",
    "passes",
    "x",
    "X",
}
_STANDARD_TOKENS = {
    "iso",
    "iec",
    "en",
    "astm",
    "api",
    "asme",
    "ansi",
    "din",
    "bs",
    "ieee",
    "nfpa",
    "nema",
    "ul",
    "csa",
    "aisc",
    "aws",
    "sae",
    "jis",
    "gb",
    "gost",
    "ped",
    "atex",
    "ip",
    "ik",
    "nace",
    "mss",
    "awwa",
    "ral",
    "grade",
    "class",
    "type",
    "model",
    "table",
    "section",
    "clause",
    "figure",
    "fig",
    "fig.",
    "rev",
    "revision",
    "no",
    "no.",
    "item",
    "part",
    "page",
    "chapter",
    "annex",
    "schedule",
    "sch",
    "sch.",
    "appendix",
    "dn",
    "nps",
    "pn",
    "ref",
    "ref.",
    "issue",
    "edition",
    "ed.",
    "tag",
    "drawing",
    "dwg",
    "doc",
    "document",
    "req",
    "req.",
    "requirement",
    "size",
    "step",
    "note",
    "notes",
    "sheet",
    "para",
    "paragraph",
    "vol",
    "volume",
    "series",
    "zone",
    "level",
    "sil",
    "pl",
    "cat",
    "cat.",
    "category",
}
_BARE_KEYWORDS = {
    "factor",
    "ratio",
    "coefficient",
    "efficiency",
    "quantity",
    "count",
    "number",
    "least",
    "exceed",
    "than",
    "minimum",
    "maximum",
    "min",
    "max",
    "value",
    "of",
    "be",
    "is",
    "to",
    "equal",
}

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z.\-]*")


@dataclass
class Quantity:
    """A numeric value found in text, with its unit as written and as a pint expression."""

    value: float
    unit: str | None = None  # pint expression ("bar", "m**3/hour") or None for a bare number
    unit_text: str | None = None  # as written in the source
    gauge: str | None = None  # "g" | "a" | None (pressure only)
    op: str | None = None  # operator hinted by words before the number (">=", "<=", ...)
    high: float | None = None  # upper bound for a range "10–16 bar" (value holds the lower)
    tol: float | None = None  # absolute tolerance in `unit`
    tol_rel: float | None = None  # relative tolerance (0.05 for ±5%)
    percent: bool = False
    text: str = ""  # matched span
    context: str = ""  # a few words preceding the match
    start: int = 0
    end: int = 0

    @property
    def is_range(self) -> bool:
        return self.high is not None

    def to_pint(self) -> pint.Quantity | None:
        try:
            return ureg.Quantity(self.value, self.unit or "dimensionless")
        except Exception:
            return None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __str__(self) -> str:
        s = f"{_fmt(self.value)}"
        if self.high is not None:
            s += f"–{_fmt(self.high)}"
        if self.unit_text:
            s += f" {self.unit_text}"
        return s


def _fmt(v: float) -> str:
    if v is None:
        return "?"
    if float(v).is_integer():
        return str(int(v))
    return f"{v:.6g}"


def _to_float(s: str) -> float:
    return float(s.replace(",", ""))


def _split_unit(token: str) -> tuple[str | None, str | None]:
    """Map a written unit to (pint expression, gauge flag) using the table."""
    expr = _UNIT_TABLE.get(token)
    if expr is None:
        # case-insensitive fallback for a few spellings (barg, psig, rpm, kpa...)
        lower = {k.lower(): v for k, v in _UNIT_TABLE.items()}
        expr = lower.get(token.lower())
    if expr is None:
        return None, None
    if "|" in expr:
        base, flag = expr.split("|", 1)
        return base, flag
    return expr, None


def is_unit_token(word: str) -> bool:
    """True when `word` is a unit spelling from the table (used to keep units out of parameter names)."""
    return word in _UNIT_TABLE or word.lower() in {k.lower() for k in _UNIT_TABLE}


def _generic_unit(text: str, pos: int) -> tuple[str, str] | None:
    """Try pint on a unit-like word directly after the number (fallback for unlisted units)."""
    m = _GENERIC_UNIT_RE.match(text, pos)
    if not m:
        return None
    word = m.group(1)
    if word.lower() in _ENGLISH_STOP or word.lower() in _STANDARD_TOKENS:
        return None
    if word.islower() and len(word) > 4:
        return None  # plain English word, not a unit symbol
    try:
        ureg.parse_units(word.replace("²", "**2").replace("³", "**3"))
    except Exception:
        return None
    return word, m.group(0)


def _preceding_words(text: str, start: int, n: int = 6) -> list[str]:
    return _WORD_RE.findall(text[max(0, start - 80) : start])[-n:]


def _is_identifier(text: str, start: int, end: int) -> bool:
    """Numbers glued to letters (A216, CX-250, 2B, 3-phase) or after standard tokens are not values."""
    before = text[start - 1] if start > 0 else " "
    if before.isalpha() or before in "-_/#":
        return True
    after = text[end] if end < len(text) else " "
    if after.isalpha() or after in "-_":
        return True
    return False


def parse_quantity(text: str) -> list[Quantity]:
    """Find every numeric value with (or without) a unit in `text`, left to right."""
    out: list[Quantity] = []
    pos = 0
    while True:
        m = _QTY_RE.search(text, pos)
        if not m:
            break
        pos = m.end() if m.end() > m.start() else m.start() + 1
        n1, n2, unit_tok = m.group("n1"), m.group("n2"), m.group("unit")
        num_start = m.start("n1")
        num_end = m.end("n2") if n2 else m.end("n1")
        if _is_identifier(text, num_start, num_end if not unit_tok else num_end):
            # "3-phase", "A216", "CX-250", "2B": not a quantity (unless a unit follows directly, e.g. 400V)
            glued_unit = unit_tok and m.start("unit") == num_end
            if not glued_unit:
                continue
        words = _preceding_words(text, m.start())
        prev = words[-1].lower() if words else ""
        if prev in _STANDARD_TOKENS and not unit_tok:
            continue  # "ISO 9906", "Grade 2", "Table 3", "RAL 5015"

        unit_expr: str | None = None
        unit_text: str | None = None
        gauge: str | None = None
        end = m.end()
        if unit_tok:
            unit_expr, gauge = _split_unit(unit_tok)
            unit_text = unit_tok
            if m.group("ga"):
                gauge = m.group("ga").lower()
                unit_text = f"{unit_tok}({gauge})"
        elif m.group("tol") and m.group("tolunit") and m.group("tolunit") != "%":
            # "1200 +/- 2 mm": the unit is written once, after the tolerance
            unit_expr, gauge = _split_unit(m.group("tolunit"))
            unit_text = m.group("tolunit")
        else:
            g = _generic_unit(text, num_end)
            if g:
                unit_text, span = g
                unit_expr = unit_text.replace("²", "**2").replace("³", "**3")
                end = num_end + len(span)
            else:
                # bare number: only accept decimals, or integers next to a value keyword
                has_decimal = "." in n1
                keyworded = any(w.lower() in _BARE_KEYWORDS for w in words[-3:]) or bool(m.group("prefix"))
                if not (has_decimal or keyworded):
                    continue

        value = _to_float(n1)
        high = _to_float(n2) if n2 else None
        op: str | None = None
        if m.group("prefix"):
            p = m.group("prefix").strip().lower()
            for pat, sym in _PREFIX_OPS:
                if re.fullmatch(pat, p, re.IGNORECASE):
                    op = sym
                    break
        if high is not None:
            op = "between"
            if high < value:
                value, high = high, value
        tol = tol_rel = None
        if m.group("tol"):
            t = _to_float(m.group("tol"))
            tu = m.group("tolunit")
            if tu == "%" or (tu and tu.lower() in ("percent", "per cent")):
                tol_rel = t / 100.0
            elif tu and unit_expr:
                te, _ = _split_unit(tu)
                try:
                    tol = ureg.Quantity(t, te).to(unit_expr).magnitude if te else t
                except Exception:
                    tol = t
            else:
                tol = t
        percent = unit_expr == "percent"
        out.append(
            Quantity(
                value=value,
                unit=unit_expr,
                unit_text=unit_text,
                gauge=gauge,
                op=op,
                high=high,
                tol=tol,
                tol_rel=tol_rel,
                percent=percent,
                text=text[m.start() : end].strip(),
                context=" ".join(words),
                start=m.start(),
                end=end,
            )
        )
    return out


# ------------------------------------------------------------------------- comparison

_ATM_KPA = 101.325
_PRESSURE_DIM = ureg.Quantity(1, "Pa").dimensionality


def _unknown(detail: str, required: dict[str, Any], found: Quantity | None) -> dict[str, Any]:
    return {
        "result": "unknown",
        "detail": detail,
        "required": required,
        "found": str(found) if found else None,
        "found_converted": None,
    }


def _tolerance(required: dict[str, Any], value: float) -> float:
    tol = required.get("tol")
    if tol is None:
        return 0.0
    if isinstance(tol, dict):
        if "rel" in tol:
            return abs(float(tol["rel"]) * value)
        if "abs" in tol:
            return abs(float(tol["abs"]))
        return 0.0
    if isinstance(tol, str):
        t = tol.strip().replace("±", "").replace("+/-", "").strip()
        if t.endswith("%"):
            return abs(float(t[:-1]) / 100.0 * value)
        try:
            return abs(float(t))
        except ValueError:
            return 0.0
    return abs(float(tol))


def normalise_unit(unit: str | None) -> str | None:
    """Written unit -> pint expression (gauge flag dropped). None when unknown."""
    if unit is None or str(unit).strip() in ("", "-", "none", "dimensionless"):
        return "dimensionless"
    tok = str(unit).strip()
    expr, _ = _split_unit(tok)
    if expr is None:
        m = re.fullmatch(r"(.+?)\s?\(([gaGA])\)", tok)
        if m:
            expr, _ = _split_unit(m.group(1))
    if expr is None:
        try:
            ureg.parse_units(tok.replace("²", "**2").replace("³", "**3"))
            expr = tok.replace("²", "**2").replace("³", "**3")
        except Exception:
            return None
    return expr


def _gauge_of_unit_text(unit: str | None) -> str | None:
    if not unit:
        return None
    tok = str(unit).strip()
    _, flag = _split_unit(tok)
    if flag:
        return flag
    m = re.fullmatch(r".+?\s?\(([gaGA])\)", tok)
    return m.group(1).lower() if m else None


def compare(required: dict[str, Any], found: Quantity) -> dict[str, Any]:
    """Compare a found quantity against a required one, converting units with pint.

    required: {"param", "op", "value", "unit", "tol"} (+ "high" for op "between").
    Returns {"result": pass|fail|unknown, "detail", "required", "found", "found_converted"}.
    """
    op = (required.get("op") or "==").strip()
    if op not in (">=", "<=", "==", ">", "<", "between"):
        return _unknown(f"unsupported operator {op!r}", required, found)
    try:
        req_value = float(required["value"])
    except (KeyError, TypeError, ValueError):
        return _unknown("required value missing or not numeric", required, found)
    req_unit = normalise_unit(required.get("unit"))
    if req_unit is None:
        return _unknown(f"unknown required unit {required.get('unit')!r}", required, found)

    found_unit = found.unit or "dimensionless"
    try:
        fq = ureg.Quantity(found.value, found_unit)
        rq_unit = ureg.parse_units(req_unit)
    except Exception as e:  # undefined unit in either side
        return _unknown(f"unknown unit: {e}", required, found)
    if fq.dimensionality != ureg.Quantity(1, rq_unit).dimensionality:
        return _unknown(
            f"dimension mismatch: found {found} ({fq.dimensionality}) vs required unit {req_unit}",
            required,
            found,
        )
    if found.unit is None and req_unit != "dimensionless":
        return _unknown("found value has no unit", required, found)
    try:
        conv = fq.to(rq_unit).magnitude
        conv_high = (
            ureg.Quantity(found.high, found_unit).to(rq_unit).magnitude if found.high is not None else None
        )
    except Exception as e:
        return _unknown(f"conversion failed: {e}", required, found)

    notes: list[str] = []
    # Gauge vs absolute pressure: adjust by one standard atmosphere when both are stated and differ.
    req_gauge = _gauge_of_unit_text(required.get("unit")) or required.get("gauge")
    if fq.dimensionality == _PRESSURE_DIM and found.gauge and req_gauge and found.gauge != req_gauge:
        atm = ureg.Quantity(_ATM_KPA, "kPa").to(rq_unit).magnitude
        delta = -atm if (found.gauge == "a" and req_gauge == "g") else atm
        conv += delta
        if conv_high is not None:
            conv_high += delta
        notes.append(f"converted {found.gauge} to {req_gauge} pressure (±1 atm)")

    tol = _tolerance(required, req_value)
    eps = 1e-9 * max(1.0, abs(req_value))
    lo = conv
    hi = conv_high if conv_high is not None else conv
    if op == ">=":
        ok = lo >= req_value - tol - eps
    elif op == ">":
        ok = lo > req_value - tol + eps
    elif op == "<=":
        ok = hi <= req_value + tol + eps
    elif op == "<":
        ok = hi < req_value + tol - eps
    elif op == "between":
        try:
            req_high = float(required.get("high", required.get("value_high")))
        except (TypeError, ValueError):
            return _unknown("'between' needs 'high'", required, found)
        ok = lo >= req_value - tol - eps and hi <= req_high + tol + eps
    else:  # ==
        ok = abs(lo - req_value) <= tol + eps and abs(hi - req_value) <= tol + eps
        if tol == 0.0:
            ok = ok or (
                math.isclose(lo, req_value, rel_tol=1e-9) and math.isclose(hi, req_value, rel_tol=1e-9)
            )

    unit_label = "" if req_unit == "dimensionless" else f" {required.get('unit')}"
    conv_label = _fmt(conv) + (f"–{_fmt(conv_high)}" if conv_high is not None else "")
    req_label = _fmt(req_value) + (f"–{_fmt(float(required['high']))}" if op == "between" else "")
    tol_label = f" ±{_fmt(tol)}" if tol else ""
    detail = (
        f"found {found} (= {conv_label}{unit_label}) {op} required {req_label}{unit_label}{tol_label}: "
        f"{'pass' if ok else 'fail'}"
    )
    if notes:
        detail += " (" + "; ".join(notes) + ")"
    return {
        "result": "pass" if ok else "fail",
        "detail": detail,
        "required": required,
        "found": str(found),
        "found_converted": {"value": conv, "high": conv_high, "unit": required.get("unit")},
    }


def compatible(required: dict[str, Any], found: Quantity) -> bool:
    """True when `found` has the same dimensionality as the required unit."""
    req_unit = normalise_unit(required.get("unit"))
    if req_unit is None:
        return False
    try:
        a = ureg.Quantity(1, found.unit or "dimensionless").dimensionality
        b = ureg.Quantity(1, req_unit).dimensionality
    except Exception:
        return False
    if a != b:
        return False
    return not (found.unit is None and req_unit != "dimensionless")
