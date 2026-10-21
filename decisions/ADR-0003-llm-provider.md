# ADR-0003: Hosted Claude by default; local vLLM only under residency mandates

Status: accepted, 2026-10-21

## Context
For 50–200 engineers the research cost model puts hosted generation (Haiku-class for chat,
Sonnet-class 1M context for whole-document checks) well below the cost of one rented GPU, while
embedding and reranking every chunk and query makes those two stages worth self-hosting.

## Decision
Generation uses the official Anthropic SDK through one thin module (`eb.llm`); model per route is
configuration. Embeddings and rerankers run on self-hosted TEI (Qwen3-Embedding / Qwen3-Reranker).
A vLLM/SGLang backend will be added behind the same module when a residency mandate requires it.
Zero-data-retention terms are requested per organisation; note that Fable-class models are
excluded from ZDR.

## Consequences
- No orchestration framework; prompts are visible in the calling module.
- Every call is traced (tokens, model, retrieved chunk ids) via OpenTelemetry (Phase 5).
