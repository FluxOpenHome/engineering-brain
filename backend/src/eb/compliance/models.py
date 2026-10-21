"""Pydantic models shared by the compliance API, the LLM calls and the checker."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Verdict = Literal["compliant", "non_compliant", "partial", "insufficient_evidence", "not_applicable"]
ReviewVerdict = Literal["compliant", "non_compliant", "partial", "insufficient_evidence", "not_applicable"]
RequirementKind = Literal["functional", "performance", "interface", "constraint", "design", "other"]
Op = Literal[">=", "<=", "==", ">", "<", "between"]


class QuantitySpec(BaseModel):
    """Structured quantity for deterministic comparison: {param, op, value, unit, tol}.

    A clause that fixes several values (flow AND head) carries the extra ones in `and`;
    the checker requires every one of them to pass.
    """

    model_config = ConfigDict(populate_by_name=True)

    param: str | None = None
    op: Op = "=="
    value: float
    unit: str | None = None
    tol: float | str | None = None
    high: float | None = Field(default=None, description="upper bound for op 'between'")
    and_: list[QuantitySpec] = Field(default_factory=list, alias="and")

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "param": self.param,
            "op": self.op,
            "value": self.value,
            "unit": self.unit,
            "tol": self.tol,
        }
        if self.op == "between" and self.high is not None:
            d["high"] = self.high
        if self.and_:
            d["and"] = [x.to_json() for x in self.and_]
        return d


class Quote(BaseModel):
    source_index: int = Field(ge=0, description="index of the <source> block the quote is copied from")
    quote: str


class FoundValue(BaseModel):
    param: str
    value_text: str = Field(description="the value with its unit exactly as written in the source")
    source_index: int = Field(ge=0)


class LLMVerdict(BaseModel):
    """Structured output of the per-requirement verdict call."""

    verdict: Verdict
    confidence: float = Field(ge=0.0, le=1.0)
    quotes: list[Quote] = Field(default_factory=list)
    found_values: list[FoundValue] = Field(default_factory=list)
    rationale: str = ""


class RequirementIn(BaseModel):
    req_id: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1)
    kind: RequirementKind | None = None
    quantity: QuantitySpec | None = None


class ExtractedRequirement(BaseModel):
    """One atomic requirement extracted from a clause by the LLM."""

    req_id: str
    text: str
    kind: RequirementKind = "other"
    quantity: QuantitySpec | None = None
    ears_pattern: str | None = None
    source_index: int | None = Field(default=None, description="index of the clause block it came from")


class ExtractedRequirements(BaseModel):
    requirements: list[ExtractedRequirement] = Field(default_factory=list)


class RequirementSetIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    discipline: list[str] = Field(default_factory=list)


class RequirementsIn(BaseModel):
    requirements: list[RequirementIn]


class ExtractIn(BaseModel):
    document_id: str


class RunIn(BaseModel):
    set_id: str
    document_id: str
    revision_id: str | None = None


class ReviewIn(BaseModel):
    verdict: ReviewVerdict
    note: str | None = None
