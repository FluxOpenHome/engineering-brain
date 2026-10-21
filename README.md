# Engineering Brain

A self-hosted knowledge platform for multi-disciplinary engineering teams: upload thousands of
documents, keep a reviewed Wikipedia-style wiki that the system drafts from those documents,
chat with everything with page-level citations, check supplier documents against requirement
specifications clause by clause, and author equipment specifications with built-in rule checks.

Disciplines in scope: fluid systems, electrical, civil, structural, mechanical, chemical,
materials, with systems-integration (interface) awareness across them.

## Design in one paragraph

Compose, don't fork. PostgreSQL (pgvector + tsvector) is the single store; markdown with
frontmatter in git is the canonical wiki with a web editor and a review queue in front of every
machine-written change; parsing and clause-level chunking decide answer quality; hybrid retrieval
with reranking; the LLM extracts and matches, code verifies quotes and compares numbers with
units, and anything uncertain goes to a human. Full reasoning and evidence:
[`reports/Engineering knowledge platform research.md`](reports/Engineering%20knowledge%20platform%20research.md).
Architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). Decisions: [`decisions/`](decisions/).

## Layout

```
backend/   Python 3.13 · FastAPI · psycopg · pgvector · Anthropic SDK   (API + worker, package `eb`)
web/       Next.js · Tiptap                                            (documents, search, chat, wiki, review, compliance, specs)
evals/     golden sets and eval runners
deploy/    docker-compose.yml, .env.example
docs/      architecture; decisions/ ADRs; reports/ + research_notes/ research
```

The wiki itself is a separate git repository of markdown files at `EB_WIKI_DIR` (default
`backend/data/wiki`, created on first use); point it at a clone with a remote to share it.

## Quick start (development)

Prerequisites: Python 3.13 with [uv](https://docs.astral.sh/uv/), Node 22, PostgreSQL 16 with the
pgvector extension (or `docker compose -f deploy/docker-compose.yml up postgres`).

```sh
# database role/db used by the defaults: eb/eb @ localhost:5432/engineering_brain
make setup            # backend deps (uv) + web deps (npm)
cp backend/.env.example backend/.env
make migrate
make api              # http://localhost:8000  (OpenAPI docs at /docs)
make worker           # in a second terminal: parses, embeds, proposes, checks
make web              # http://localhost:3000
```

Without an `ANTHROPIC_API_KEY`, set `EB_LLM_PROVIDER=fake` to exercise the pipeline; without a
GPU, `EB_EMBEDDING_PROVIDER=hash` gives a lexical stand-in embedder. Production uses TEI with
Qwen3-Embedding and Qwen3-Reranker (see `deploy/docker-compose.yml`, `gpu` profile).

## Tests

```sh
make test             # ruff + pytest against a dedicated test database
python evals/run_qa.py --api http://localhost:8000   # golden QA set against a running stack
```

## Status

Phases 0–4 are implemented and tested with a fake LLM and a lexical stand-in embedder:
schema and job queue; ingest (text-layer parsing, clause/table chunking); hybrid search; cited
chat; git-backed wiki with proposals, review queue and publish-only indexing; compliance engine
with code-verified quotes, unit-aware numeric checks and a human review queue; INCOSE/EARS spec
checker and template-driven spec drafting; the Next.js UI for all of it.

Not yet exercised against real services: the Anthropic API path (needs `ANTHROPIC_API_KEY`),
TEI embeddings/reranking, and the Docling layout pass. Phase 5 (GPU layout pass, reranking,
contextual prefixes, drawings route, SSO, Langfuse) is next. See `docs/ARCHITECTURE.md` section 11.
