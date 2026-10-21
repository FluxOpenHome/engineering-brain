"""One thin LLM layer. Every model call in the system goes through here.

Providers:
  anthropic - official Anthropic SDK (default). Credentials resolve from the environment.
  fake      - scripted responses for tests and credential-free development.

No orchestration framework (architecture principle P11). Prompts live with their callers.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel

from eb.config import get_settings

T = TypeVar("T", bound=BaseModel)


@dataclass
class Citation:
    document_index: int
    cited_text: str
    start: int | None = None
    end: int | None = None


@dataclass
class TextPart:
    text: str
    citations: list[Citation] = field(default_factory=list)


@dataclass
class Completion:
    parts: list[TextPart]
    usage: dict[str, int]
    stop_reason: str | None
    model: str

    @property
    def text(self) -> str:
        return "".join(p.text for p in self.parts)


@dataclass
class DocumentBlock:
    """A cited source: one chunk, one wiki section, one requirement."""

    text: str
    title: str


class LLM:
    def complete(
        self,
        *,
        system: str,
        user: str,
        documents: list[DocumentBlock] | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        effort: str = "medium",
        cache_system: bool = True,
    ) -> Completion:
        raise NotImplementedError

    def stream(
        self,
        *,
        system: str,
        user: str,
        documents: list[DocumentBlock] | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        effort: str = "medium",
    ) -> Iterator[TextPart | Completion]:
        """Yield TextParts as they arrive, then a final Completion."""
        raise NotImplementedError

    def parse(
        self,
        *,
        schema: type[T],
        system: str,
        user: str,
        documents: list[DocumentBlock] | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        effort: str = "medium",
    ) -> T:
        raise NotImplementedError


def _user_content(user: str, documents: list[DocumentBlock] | None) -> Any:
    if not documents:
        return user
    blocks: list[dict[str, Any]] = []
    for d in documents:
        blocks.append(
            {
                "type": "document",
                "source": {"type": "text", "media_type": "text/plain", "data": d.text},
                "title": d.title,
                "citations": {"enabled": True},
            }
        )
    blocks.append({"type": "text", "text": user})
    return blocks


class AnthropicLLM(LLM):
    def __init__(self) -> None:
        import anthropic

        self._client = anthropic.Anthropic()
        self._anthropic = anthropic

    def _kwargs(self, *, system, user, documents, model, max_tokens, effort, cache_system=True):
        s = get_settings()
        sys_block: Any = (
            [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
            if cache_system
            else system
        )
        model = model or s.llm_model_answer
        kw: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens or s.llm_max_tokens,
            "system": sys_block,
            "messages": [{"role": "user", "content": _user_content(user, documents)}],
            "output_config": {"effort": effort},
        }
        # Server-side refusal fallback ("default" routing) for Opus/Sonnet/Fable-class models.
        # Haiku has no server-side fallback and rejects the parameter.
        if not model.startswith("claude-haiku"):
            kw["betas"] = ["server-side-fallback-2026-07-01"]
            kw["fallbacks"] = "default"
        return kw

    @staticmethod
    def _parts(message) -> list[TextPart]:
        parts: list[TextPart] = []
        for block in message.content:
            if block.type != "text":
                continue
            cites = []
            for c in getattr(block, "citations", None) or []:
                cites.append(
                    Citation(
                        document_index=getattr(c, "document_index", 0),
                        cited_text=getattr(c, "cited_text", ""),
                        start=getattr(c, "start_char_index", None),
                        end=getattr(c, "end_char_index", None),
                    )
                )
            parts.append(TextPart(text=block.text, citations=cites))
        return parts

    @staticmethod
    def _usage(message) -> dict[str, int]:
        u = message.usage
        return {
            "input_tokens": getattr(u, "input_tokens", 0) or 0,
            "output_tokens": getattr(u, "output_tokens", 0) or 0,
            "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
            "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
        }

    def complete(self, *, system, user, documents=None, model=None, max_tokens=None,
                 effort="medium", cache_system=True) -> Completion:
        kw = self._kwargs(system=system, user=user, documents=documents, model=model,
                          max_tokens=max_tokens, effort=effort, cache_system=cache_system)
        with self._client.beta.messages.stream(**kw) as stream:
            msg = stream.get_final_message()
        return Completion(parts=self._parts(msg), usage=self._usage(msg),
                          stop_reason=msg.stop_reason, model=msg.model)

    def stream(self, *, system, user, documents=None, model=None, max_tokens=None,
               effort="medium") -> Iterator[TextPart | Completion]:
        kw = self._kwargs(system=system, user=user, documents=documents, model=model,
                          max_tokens=max_tokens, effort=effort)
        with self._client.beta.messages.stream(**kw) as stream:
            for event in stream:
                if event.type == "content_block_delta" and event.delta.type == "text_delta":
                    yield TextPart(text=event.delta.text)
            msg = stream.get_final_message()
        yield Completion(parts=self._parts(msg), usage=self._usage(msg),
                         stop_reason=msg.stop_reason, model=msg.model)

    def parse(self, *, schema, system, user, documents=None, model=None, max_tokens=None,
              effort="medium"):
        # Citations and output_config.format are mutually exclusive: documents are inlined
        # as plain text for structured calls; callers quote evidence and we verify in code.
        s = get_settings()
        if documents:
            user = "\n\n".join(f"<source index=\"{i}\" title=\"{d.title}\">\n{d.text}\n</source>"
                               for i, d in enumerate(documents)) + "\n\n" + user
        resp = self._client.messages.parse(
            model=model or s.llm_model_answer,
            max_tokens=max_tokens or s.llm_max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_format=schema,
            output_config={"effort": effort},
        )
        return resp.parsed_output


class FakeLLM(LLM):
    """Scripted LLM. `responses` is consumed in order; `parse` builds from `parsed`."""

    def __init__(self, responses: list[str] | None = None, parsed: list[Any] | None = None):
        self.responses = list(responses or [])
        self.parsed = list(parsed or [])
        self.calls: list[dict[str, Any]] = []

    def _next_text(self, user: str, documents) -> str:
        if self.responses:
            return self.responses.pop(0)
        # Default: echo the first sentence of each document so citation plumbing can be tested.
        if documents:
            return " ".join(re.split(r"(?<=[.!?])\s", d.text.strip())[0] for d in documents[:2])
        return f"(fake answer to: {user[:60]})"

    def complete(self, *, system, user, documents=None, model=None, max_tokens=None,
                 effort="medium", cache_system=True) -> Completion:
        self.calls.append({"system": system, "user": user, "documents": documents, "model": model})
        text = self._next_text(user, documents)
        cites = [Citation(document_index=0, cited_text=documents[0].text[:40])] if documents else []
        return Completion(parts=[TextPart(text=text, citations=cites)],
                          usage={"input_tokens": 0, "output_tokens": 0}, stop_reason="end_turn",
                          model="fake")

    def stream(self, *, system, user, documents=None, model=None, max_tokens=None,
               effort="medium"):
        c = self.complete(system=system, user=user, documents=documents, model=model)
        for word in c.text.split(" "):
            yield TextPart(text=word + " ")
        yield c

    def parse(self, *, schema, system, user, documents=None, model=None, max_tokens=None,
              effort="medium"):
        self.calls.append({"system": system, "user": user, "documents": documents, "schema": schema})
        if self.parsed:
            item = self.parsed.pop(0)
            return item if isinstance(item, schema) else schema.model_validate(item)
        # Build a minimal valid instance from JSON if the fake was given raw text responses.
        if self.responses:
            return schema.model_validate(json.loads(self.responses.pop(0)))
        raise RuntimeError("FakeLLM.parse called with no scripted output")


_llm: LLM | None = None


def get_llm() -> LLM:
    global _llm
    if _llm is None:
        s = get_settings()
        _llm = FakeLLM() if s.llm_provider == "fake" else AnthropicLLM()
    return _llm


def set_llm(llm: LLM | None) -> None:
    """Override the process-wide LLM (tests)."""
    global _llm
    _llm = llm
