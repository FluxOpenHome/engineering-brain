# Engineering Brain: Architecture

Status: v0.1, 2026-10-21. Derived from `reports/Engineering knowledge platform research.md`.
Owner: Brandon Halterman. Decisions that change this document get an ADR in `decisions/`.

## 1. What this system is

Engineering Brain is a self-hosted, multi-user **document-control and review system in which
retrieval is one component**. It serves a multi-disciplinary engineering organisation
(fluid systems, electrical, civil, structural, mechanical, chemical, materials) and must:

1. Ingest tens of thousands of engineering documents (specs, data sheets, standards,
   reports, drawings) and make them searchable within minutes of upload.
2. Maintain a Wikipedia-style wiki that engineers can edit with zero friction, and that
   the system drafts and updates from ingested documents **subject to human review**.
3. Answer detailed questions over documents and wiki with verbatim, page-level citations.
4. Check a supplier document against a set of requirement specifications, clause by clause,
   with evidence, and never silently pass a non-compliant item.
5. Check an engineer's own document against the wiki's engineering knowledge.
6. Help engineers author requirement specifications for equipment, with systems-integration
   (interface) awareness across disciplines.

Non-goals for v1: replacing a formal requirements-management tool (DOORS, Polarion),
CAD integration, and redistributing the text of licensed standards.

## 2. Principles (each is backed by the research report)

| # | Principle | Why |
|---|-----------|-----|
| P1 | **Compose, don't fork.** Thin custom code over ~8 mature components. | No open platform has a reviewed wiki or compliance engine; forking RAGFlow/Onyx/WeKnora inherits heavy topologies. |
| P2 | **PostgreSQL is the single system of record** for documents, chunks, vectors, keyword index, wiki metadata, ACLs, requirements, verdicts, and the job queue. | 0.5–5M chunks fit in RAM; ANN is single-digit ms on CPU; ACL as a `WHERE` clause avoids the filtered-recall cliff; one backup, one transaction boundary. |
| P3 | **Markdown + YAML frontmatter in git is the canonical wiki store.** Agents write files; humans use a web editor; a review queue sits in front of every machine-written change. | Every working LLM-wiki implementation uses this model; Wikipedia's 2026 ban on LLM drafts shows auto-publish destroys trust. |
| P4 | **Only published content is indexed for chat.** Drafts and proposals are never cited. | Prevents the assistant from citing unreviewed text. |
| P5 | **Parsing and chunking decide answer quality.** Structure-aware, clause-level, table-atomic chunks with contextual prefixes; hybrid BM25+dense; cross-encoder rerank. | Recall@5 0.59 (dense) → 0.82 (hybrid+rerank) on table-heavy corpora; contextual retrieval cuts failures 67%. |
| P6 | **Revisions are first-class.** Every chunk carries `document_id`, `revision`, `status`; default retrieval filters to the active revision. | Similarity cannot tell authoritative from stale. |
| P7 | **Deterministic judge around the LLM** for compliance. LLM extracts and matches; code verifies quotes and compares numbers with units; unknown → human. | Single-pass LLM verdicts: ~60–75% precision, missed non-compliance dominant. |
| P8 | **GPU for ingest, CPU for serving search.** GPU pays off on PDF parsing (7–14x), bulk embedding (10–100x), reranking (~30x), and local LLM generation; not on ANN search. | Measured in the report, section 3. |
| P9 | **Generation is a cost/residency decision.** Default to a hosted Claude model with caching; local vLLM/SGLang only under residency mandates. Embeddings and rerankers are always self-hosted. | Per-token API cost is far below one rented GPU at 50–200 users. |
| P10 | **Reference standards, don't redistribute them.** Store clause IDs, titles, and the organisation's own derived parameters; process licensed standard text ephemerally. | ISO, IEEE, ASHRAE licences now prohibit AI processing of their text. |
| P11 | **No orchestration framework.** Direct Anthropic SDK calls behind one thin `llm` module; typed schemas via Pydantic. | Anthropic's and practitioners' guidance; frameworks hide prompts and add p99 latency. |
| P12 | **Evals from day one.** A golden question set and a golden compliance set run in CI. | Teams that skip evals cannot tell whether a chunking change helped. |

## 3. System context

```
                 ┌──────────────────────────────────────────────────────────────┐
                 │                        Engineers (browser)                   │
                 │   upload · search · chat · edit wiki · review · run checks   │
                 └───────────────┬──────────────────────────────┬───────────────┘
                                 │ HTTPS (SSO via Authentik)     │ WebSocket (Yjs)
                 ┌───────────────▼───────────────┐   ┌──────────▼──────────────┐
                 │   web  (Next.js, Tiptap)      │   │ hocuspocus (collab)     │
                 └───────────────┬───────────────┘   └──────────┬──────────────┘
                                 │ REST/SSE                      │ persists to
                 ┌───────────────▼───────────────────────────────▼──────────────┐
                 │                  api  (Python · FastAPI)                     │
                 │  documents · search · chat · wiki · review · compliance ·    │
                 │  specs · jobs                                                │
                 └───┬───────────────┬────────────────┬───────────────┬─────────┘
                     │               │                │               │
          ┌──────────▼───┐  ┌────────▼────────┐  ┌────▼─────┐  ┌──────▼───────────┐
          │ PostgreSQL   │  │ worker(s)       │  │ object   │  │ LLM provider     │
          │ pgvector     │  │ parse·chunk·    │  │ store    │  │ Anthropic API    │
          │ tsvector     │  │ embed·wiki·     │  │ (S3 or   │  │ (or vLLM/SGLang) │
          │ jobs · ACL   │◄─┤ compliance      │  │ local FS)│  └──────────────────┘
          └──────────────┘  └───┬────────┬────┘  └──────────┘
                                │        │
                     ┌──────────▼──┐  ┌──▼─────────────────────┐
                     │ TEI embed + │  │ parser service          │
                     │ TEI rerank  │  │ docling-serve (CPU) /   │
                     │ (GPU)       │  │ MinerU2.5 (GPU)         │
                     └─────────────┘  └─────────────────────────┘
                                          ┌──────────────────┐
                 wiki repo (git, markdown) │ Langfuse (OTel)  │  evals in CI
                                          └──────────────────┘
```

## 4. Components and choices

| Component | Choice | License | Role | Fallback / dev mode |
|---|---|---|---|---|
| Database | PostgreSQL 16 + pgvector 0.8 (`halfvec`, HNSW, iterative scans) + `tsvector` | PostgreSQL | System of record, ANN, BM25-class keyword search, job queue | pgvectorscale when > ~5M vectors; ParadeDB `pg_search` if AGPL is acceptable and BM25 scoring matters |
| API | Python 3.13, FastAPI, Pydantic v2, psycopg 3 | MIT | HTTP/SSE API, auth, ACL enforcement, orchestration of LLM calls | — |
| Worker | Same codebase, `eb worker` process; Postgres `jobs` table with `SKIP LOCKED` | — | Parse, chunk, embed, wiki proposals, compliance runs | Hatchet when DAG workflows or > ~100 jobs/s are needed |
| Parser | Docling (MIT) for Office/born-digital PDF; MinerU2.5 or PaddleOCR-VL on GPU for tables/formulas/scans | MIT / Apache+cond. | Two-pass ingest (text layer first, VLM second) | `pypdf` text-layer pass in dev |
| Embeddings | Qwen3-Embedding-0.6B (dev) / 4B (prod) via Hugging Face TEI | Apache-2.0 | Dense vectors for chunks and queries | Deterministic hash embedder for unit tests |
| Reranker | Qwen3-Reranker-0.6B/4B via TEI | Apache-2.0 | Rerank top-150 to top-20 | Disabled (hybrid only) |
| Generation | Anthropic Claude via official SDK; model configurable (`claude-opus-5-5` default, Haiku-class for high-volume chat, Sonnet-class 1M context for whole-standard checks) | — | Answers, wiki drafts, requirement extraction, verdict drafting | vLLM/SGLang with Qwen3/gpt-oss on 80–96 GB GPU for on-prem residency |
| Wiki store | git repo of markdown + frontmatter (`wiki/`) | — | Canonical pages; history; agent-writable | — |
| Wiki editor | Tiptap (MIT core) + Hocuspocus (MIT, Yjs) | MIT | Real-time co-editing, comments | Outline (BSL 1.1) if the editor is not built |
| Web | Next.js (React, TypeScript) | MIT | Upload, search, chat, wiki, review, compliance UI | — |
| Object store | S3-compatible (cloud S3, Ceph RGW, Garage, SeaweedFS) behind one adapter | — | Original files, parsed artifacts, page images | Local filesystem in dev |
| Auth | Authentik (or Keycloak) via OIDC; groups → ACL | MIT | SSO, groups | Static dev user |
| Observability | Langfuse via OpenTelemetry | MIT | Traces, token cost, prompt versions | Log to stdout |
| Evals | promptfoo + DeepEval/Ragas on golden sets | — | CI gate on retrieval and verdict quality | — |

Not chosen and why: LangChain/LlamaIndex (P11); Elasticsearch/OpenSearch (second search cluster for no gain under 5M chunks); MinIO (community repo archived April 2026); Ollama for multi-user serving (serialises requests); Wiki.js (five-year beta); Obsidian as server (no headless API).

## 5. Data model (PostgreSQL)

Core identities and the revision model:

```
users(id, email, display_name, external_id)                 groups(id, name)
user_groups(user_id, group_id)

documents(id, doc_number, title, doc_type, discipline[], project, owner_group_id,
          current_revision_id, created_at)
document_revisions(id, document_id, revision, status{draft,active,superseded,archived},
          effective_date, source_sha256, storage_key, mime, page_count, parse_status,
          parse_pass{text_layer,layout,vlm}, parsed_at, superseded_by_id)
document_acl(document_id, group_id, perm{read,write,admin})

chunks(id, revision_id, document_id, ordinal, section_path, clause_id, page_start, page_end,
       bbox jsonb, kind{text,table,figure,clause,requirement}, text, context_prefix,
       token_count, content_hash,
       tsv tsvector GENERATED, embedding halfvec(1024), embedding_model, created_at)
   INDEX hnsw (embedding halfvec_cosine_ops), GIN (tsv), btree (document_id, revision_id)

jobs(id, kind, payload jsonb, status{queued,running,done,failed,dead}, priority,
     attempts, run_after, locked_by, locked_at, error, created_at, finished_at)
```

Wiki:

```
wiki_pages(id, slug, title, path, status{proposed,published,stale,archived}, discipline[],
           content_hash, last_published_sha, reviewed_by, human_edited, updated_at)
wiki_page_sources(page_id, document_id, revision_id, chunk_id)       -- provenance
wiki_proposals(id, page_id|null, kind{create,update,delete}, base_sha, diff, rationale,
           sources jsonb, confidence, status{open,accepted,rejected,superseded},
           created_by{agent,user}, reviewed_by, decided_at)
wiki_chunks  -- same shape as chunks, keyed by page_id; only status=published is indexed
```

Requirements and compliance:

```
requirement_sets(id, name, source{manual,reqif,excel,extracted}, document_id|null, discipline[])
requirements(id, set_id, req_id, text, kind{functional,performance,interface,constraint},
             quantity jsonb{param,op,value,unit,tol}, parent_id, source_chunk_id, ears_pattern)
compliance_runs(id, set_id, subject_revision_id, status, model, started_by, summary jsonb)
compliance_findings(run_id, requirement_id, verdict{compliant,non_compliant,partial,
             insufficient_evidence,not_applicable}, confidence, evidence jsonb[{chunk_id,
             quote, page, verified bool}], numeric_check jsonb, rationale, reviewer_verdict,
             reviewed_by, reviewed_at)
```

Rules: a row in `chunks` is immutable; a new revision creates new chunks and flips
`status` on the old ones. `documents.current_revision_id` is switched atomically after
indexing completes. Retrieval filters `status='active'` unless the user asks for history.

## 6. Pipelines

### 6.1 Ingest (two passes)

1. `POST /documents` stores the file in the object store, creates `documents` +
   `document_revisions(status=draft, parse_status=queued)`, enqueues `parse_text_layer`.
2. **Pass 1, text layer (seconds, CPU):** extract text per page with Docling fast mode or
   `pypdf`; classify document type and disciplines (rules + small LLM call); chunk; embed;
   index. The document is searchable now. Revision is activated.
3. **Pass 2, layout/VLM (minutes, GPU, prioritised by document class):** Docling layout
   model or MinerU2.5 produces a structured document (headings, clauses, tables with
   cells, figures with bboxes). Chunks are regenerated; the revision's chunks are swapped
   in one transaction; `parse_pass='layout'`.
4. Drawings route: a CLIP-class classifier (later) sends P&IDs and drawings to a separate
   track (DXF/DEXPI extraction, page-image index). Text parsing is not applied to them.
5. Duplicate detection by `source_sha256`; a re-upload of the same bytes is a no-op; a new
   revision of a known `doc_number` creates `document_revisions` and supersedes the old.

### 6.2 Chunking

Structure-aware: one chunk per numbered clause or paragraph under its heading path; tables
are atomic with caption and heading path; figures carry captions. Each chunk gets a
50–100-token `context_prefix` (document number, title, revision, section path, and an LLM-
written one-line summary when enabled) that is embedded and keyword-indexed with the text.
Parent-child: chunks keep `section_path` so the answerer can expand to the parent section.

### 6.3 Retrieval and chat

```
query → [ACL filter + revision filter] →
   BM25-class (tsvector, websearch_to_tsquery)  top-150 ─┐
   dense (halfvec cosine, HNSW, ef_search=200)  top-150 ─┴→ RRF fuse → top-150
→ rerank (TEI cross-encoder) → top-20 → answer with citations (one LLM call)
```

The answer prompt receives chunks as `document` blocks with `citations` enabled so the
API returns page-level citations we map back to `chunk_id`. Scope selectors: whole corpus,
a project, a document set, the wiki only, or "this document against the wiki". Streaming
via SSE. Every call is traced with prompt version, token counts, and retrieved chunk ids.

### 6.4 Wiki loop

```
document activated → wiki_propose job →
  retrieve related published pages → LLM drafts create/update proposals with
  per-paragraph source chunk ids → wiki_proposals(open)
→ reviewer sees diff beside cited passages → accept (commit to git, page published,
  re-chunk + re-embed if content_hash changed) | reject | edit-then-accept (human_edited=true)
→ nightly lint: contradictions, orphan citations, pages citing superseded revisions → stale
```

Human edits in the web editor commit directly to git (no proposal) and are published
immediately; the index is updated on commit, gated by content hash. Agents never overwrite a
`human_edited` page without a proposal.

### 6.5 Compliance check

```
subject document (supplier) + requirement set →
 for each requirement (parallel):
   hybrid retrieval over subject chunks (tables row-wise) → candidate evidence (≤ 8 chunks)
   LLM verdict (schema-constrained): verdict, verbatim quotes, rationale
   code: verify each quote is a substring of the cited chunk (else verdict → unverified)
   code: if requirement.quantity present → parse numbers+units from quotes with pint,
         compare in code; code result overrides LLM verdict on numeric clauses
   route: insufficient_evidence | unverified | low confidence → human queue
 reverse pass: every requirement must have a finding; every "shall" in the subject that
   matches no requirement is listed as "unrequested claim"
→ compliance matrix (web + Excel export + ReqIF write-back later)
```

Primary quality metric: false "compliant" verdicts on the golden set (target 0).

### 6.6 Specification authoring

Template per equipment class (pump, valve, transformer, switchgear, vessel, piping, steel,
HVAC) defined as a property schema (IEC CDD / ECLASS-style parameter list with units).
The assistant fills parameters from the wiki and project documents with citations, writes
prose and rationale, and runs an INCOSE GtWR v4 / EARS rule checker over every requirement
sentence (named rules, per-rule severity, human-review flag for necessity/correctness).
Interface requirements are generated from a cross-discipline checklist (electrical load vs
cooling, structural load vs equipment mass, utilities, I&C signals).

## 7. Security and access control

- OIDC via Authentik; the API validates the JWT and maps groups to `groups`.
- Every retrieval query joins `document_acl` for the caller's groups in the `WHERE` clause
  before similarity ranking. There is no post-filtering.
- Wiki pages inherit ACL from their space; proposals inherit from their target page.
- Uploaded files are scanned for type; original bytes are immutable in the object store.
- LLM provider: zero-data-retention terms where available; model choice per route is
  configuration, not code. Standards text is never stored in chunks beyond clause IDs and
  titles unless the organisation's licence permits (P10, enforced by `doc_type='standard'`
  ingest policy).

## 8. Deployment

Docker Compose, one host. Services: `postgres`, `api`, `worker`, `web`, `hocuspocus`,
`tei-embed`, `tei-rerank`, `parser`, `langfuse` (optional), `authentik` (optional).

| Tier | Hardware | Capacity | Notes |
|---|---|---|---|
| Dev | Laptop/VM, CPU only | 1–3 users, hundreds of docs | pypdf/Docling fast, small embedder on CPU, hosted LLM |
| 1 | One workstation, RTX 4090/5090, 64–128 GB RAM | ~10 users, 10k docs | Parsing + embedding + rerank on one GPU; hosted LLM |
| 2 | Server with one 80–96 GB GPU (H100/H200/RTX 6000 Pro) | 50–200 users, 100k docs | Optional local 30–70B LLM via vLLM; hosted LLM otherwise |

Ingest throughput planning: 10k documents ≈ 300k pages ≈ 9–42 h on one GPU for the
layout pass; the text-layer pass finishes in hours on CPU.

## 9. Observability and evaluation

- OpenTelemetry traces from API and worker to Langfuse: retrieval candidates, rerank scores,
  prompt version, tokens, latency, cost.
- Golden sets in `evals/`: 100+ question/answer/citation triples; 50+ requirement/evidence/
  verdict triples; a labelled 50–100-page parsing sample. CI fails on regression.
- Dashboards: ingest backlog, parse pass coverage, proposal acceptance rate, reviewer
  throughput, false-compliant count.

## 10. Repository layout

```
engineering-brain/
  docs/ARCHITECTURE.md          this document
  decisions/                    ADRs
  reports/, research_notes/     research behind the decisions
  backend/                      Python: api + worker (package `eb`)
    src/eb/{config,db,llm,storage}.py
    src/eb/migrations/*.sql
    src/eb/{documents,ingest,retrieval,chat,wiki,compliance,specs,jobs}/
    tests/
  web/                          Next.js app
  (EB_WIKI_DIR)                 canonical markdown wiki: its own git repo, default backend/data/wiki
  evals/                        golden sets and eval runners
  deploy/docker-compose.yml, deploy/.env.example
  Makefile
```

## 11. Build phases

| Phase | Deliverable | Done when |
|---|---|---|
| 0 | Schema, migrations, job queue, storage adapter, config, CI | `make test` green; `eb migrate` idempotent |
| 1 | Upload → text-layer parse → chunk → embed → hybrid search → cited chat (SSE) | Golden QA set ≥ baseline; p95 search < 300 ms at 100k chunks |
| 2 | Wiki: markdown repo, pages API, Tiptap editor, proposals + review queue, publish-only indexing | Proposal round-trip works; drafts never appear in chat citations |
| 3 | Compliance: requirement sets (manual/Excel/ReqIF), check run, verified verdicts, unit comparison, human queue, matrix export | Zero false-compliant on golden set; coverage dashboard |
| 4 | Spec authoring: equipment templates, INCOSE/EARS checker, interface checklist | Generates a reviewed pump spec end to end |
| 5 | GPU layout pass (MinerU/Docling layout), rerank, contextual prefixes, drawings route, SSO, Langfuse | Layout pass coverage > 90% of active revisions |
| 6 | Only if measured need: pgvectorscale/Qdrant, relationship retrieval, SysML v2 interfaces | — |

## 12. Open decisions (tracked as ADRs)

- ADR-0001 Postgres as the single store (accepted, this doc).
- ADR-0002 Markdown-in-git canonical wiki with web editor (accepted, this doc).
- ADR-0003 Hosted Claude vs local LLM default: hosted with ZDR, revisit on residency mandate.
- ADR-0004 Standards ingest policy: reference-only by default (P10); per-licence override.
- ADR-0005 Editor: build on Tiptap/Hocuspocus vs adopt Outline. Decide at end of Phase 1.
- ADR-0006 Job queue: Postgres table vs Hatchet. Decide when DAG workflows are needed.
