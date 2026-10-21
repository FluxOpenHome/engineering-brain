# Existing open-source RAG / document-chat platforms (survey as of 2026-10-21)

Method note: GitHub API and raw github.com HTTP were blocked by the session proxy, so repo facts below come from WebFetch reads of GitHub repo pages, `/commits`, `/releases` and LICENSE files on 2026-10-21. Star counts are as rendered on those pages that day. Many third-party comparison sites (vdf.ai, awesomeosai.com, onyx.app, docs.onyx.app, andrew.ooo, zenml.io, frontiersin.org, substack) were unreachable from this environment; where I cite them the fact comes from a search-result excerpt, and I flag that. The web-search budget was exhausted partway through, so a few targeted follow-ups (Haystack/LlamaIndex community discussion, engineering-datasheet repos) could not be run.

## Key Question 1: Which 3-5 projects are the strongest candidates to build on for a multi-user, self-hosted, high-volume (tens of thousands of documents) engineering knowledge base, and why?

### Takeaway
RAGFlow (Apache-2.0, 92.5k stars, 1.0.0-rc2 on 16 Oct 2026, Go rewrite, DeepDoc table/OCR parsing, team sharing, built-in "Wiki" compilation) and Tencent WeKnora (MIT, 34.9k stars, v0.8.3 on 14 Oct 2026, hybrid+rerank+GraphRAG, 4-role RBAC, OIDC, ~360 REST endpoints, editable Wiki mode, "Wiki ingest scales to 40k-document KBs") are the two best fits for a self-hosted, multi-user, tens-of-thousands-of-documents engineering KB; Onyx (MIT core + Enterprise-licensed `ee/` dirs, OpenSearch hybrid index, 50+ connectors, SSO/RBAC only in EE) is the strongest if SaaS connectors and permission-inheritance matter more than parsing quality; Open WebUI (156k stars, BM25+vector+rerank, 9 vector DBs, RBAC/LDAP/SCIM) is the most popular but has documented knowledge-base scaling pain at 30k-60k files and a branding-clause license above 50 users; LightRAG (MIT, 40.2k, PostgreSQL backend, citations, REST API) is the best building-block if you want to own the app layer and only reuse the retrieval engine.

### Cited Findings

#### Candidate survey (primary-source data, 2026-10-21)

**Onyx (formerly Danswer)** — https://github.com/onyx-dot-app/onyx
- 32.6k stars, 4.6k forks; "Onyx Community Edition (CE) is available freely under the MIT license"; Enterprise Edition "includes extra features that are primarily useful for larger organizations" — [Onyx repo](https://github.com/onyx-dot-app/onyx)
- LICENSE: "All content that resides under 'ee' directories of this repository is licensed under the Onyx Enterprise License" (copies at `backend/ee/LICENSE`, `web/src/app/ee/LICENSE`, `web/src/ee/LICENSE`); everything else "is available under the 'MIT Expat' license" — [Onyx LICENSE](https://github.com/onyx-dot-app/onyx/blob/main/LICENSE)
- Enterprise License text: software "may only be used in production, if you (and any entity that you represent) have agreed to" the Enterprise Terms and hold "a valid Enterprise License" for the seat count; copying/modifying without subscription allowed only "for development and testing purposes" — [backend/ee/LICENSE](https://github.com/onyx-dot-app/onyx/blob/main/backend/ee/LICENSE)
- EE feature list on README: SSO "via Google OAuth, OIDC, or SAML", SCIM group sync, "RBAC for sensitive resources like access to agents, actions, etc.", analytics, query history, custom PII-removal code, whitelabeling — [Onyx README](https://github.com/onyx-dot-app/onyx/blob/main/README.md)
- Stack: Python backend + Next.js; "Vector + Keyword index for RAG"; Agentic RAG "based on hybrid index + a custom agent harness tuned for information retrieval"; connects to "50+ applications"; self-hosted LLMs via "Ollama, LiteLLM, vLLM, etc."; Docker/Kubernetes/Helm/Terraform; "air-gappable, self-hosted"; Lite mode "requires less resources (under 1GB memory)" — [Onyx repo](https://github.com/onyx-dot-app/onyx)
- docker-compose.yml services: api_server (FastAPI), background workers, web_server (Next.js), mcp_server, inference_model_server, indexing_model_server, PostgreSQL 15.2, **`opensearchproject/opensearch:3.6.0`** (no Vespa service defined), Redis 7.4, nginx, code-interpreter sandbox, optional SeaweedFS/MinIO; OpenSearch JVM heap `-Xms2g -Xmx2g` — [Onyx docker-compose](https://github.com/onyx-dot-app/onyx/blob/main/deployment/docker_compose/docker-compose.yml)
- Activity: commits on 21 Oct 2026; releases v4.9.2 (15 Oct, "Latest"), v5.0.0-beta.1 (17 Oct), v5.0.0-beta.2 (20 Oct, pre-release) — [commits](https://github.com/onyx-dot-app/onyx/commits/main); [releases](https://github.com/onyx-dot-app/onyx/releases)
- Scale claim (search excerpt, unverified in my README read): README reportedly says retrieval "remains performant and accurate for scales of up to tens of millions of documents"; a ZenML case study (~2024) says Danswer served customers with "millions of documents" and migrated to Vespa after accuracy degraded past several million — [onyx.app enterprise guide](https://onyx.app/insights/enterprise-rag-platforms-2026) (vendor); [ZenML case study](https://www.zenml.io/llmops-database/scaling-enterprise-rag-with-advanced-vector-search-migration) (unreachable, excerpt only). NOTE: the current compose file uses OpenSearch, not Vespa, so the ZenML description is historical.

**RAGFlow (InfiniFlow)** — https://github.com/infiniflow/ragflow
- 92.5k stars, 11.1k forks, Apache-2.0; "RAGFlow 1.0.0-rc1 released" 2026-09-29; quick-start checks out `v1.0.0-rc2` — [RAGFlow repo](https://github.com/infiniflow/ragflow)
- Releases: v1.0.0-rc2 (16 Oct, Latest), v1.0.0-rc1 (29 Sep), v0.27.2 (10 Sep); rc1 described as "a comprehensive rewrite in Go"; rc2 unifies "12 built-in document parsers" with Pipeline parsers, adds "Team/Me sharing", Agentic chat mode, arm64 images — [RAGFlow releases](https://github.com/infiniflow/ragflow/releases)
- Stack: Go (go.mod, Go 1.27), Python SDK, React web; document engines Elasticsearch or Infinity; compose also runs MySQL, MinIO, NATS, Kvrocks; DeepDoc does "layout analysis, OCR, and table recognition on CPU"; formats: Word, PowerPoint, Excel, TXT, images, PDFs, scanned copies, structured data, web pages; "Multiple recall paired with fused re-ranking"; traceable citations with view of chunking "for human intervention"; Knowledge Compilation produces "Wikis, Graphs, Trees, PageIndex, Mind Maps, Timelines, and Skills"; recommended "4 CPU cores, 16 GB RAM, and 50 GB of available disk space"; "macOS is not currently supported" — [RAGFlow repo](https://github.com/infiniflow/ragflow)
- Commits: 20 Oct 2026 (5 commits that day, incl. "isolate user agent and dataset listings in EE files") — [RAGFlow commits](https://github.com/infiniflow/ragflow/commits/main)
- Permissions: team docs define `invite` → `normal` roles; sharing scopes "Me" ("Only the owner can access the resource") and "Team"; "Team membership and resource permissions are separate concepts"; open-source edition resources "can usually be set to 'Only me' or 'Team'" — [team_and_resource_permissions.md](https://github.com/infiniflow/ragflow/blob/main/docs/guides/team/permission_system_overview/team_and_resource_permissions.md); [resource_sharing_scope.md](https://github.com/infiniflow/ragflow/blob/main/docs/guides/team/permission_system_overview/resource_sharing_scope.md)
- Note: the phrase "EE files" in an Oct 2026 commit implies RAGFlow is now also splitting enterprise code paths — [RAGFlow commits](https://github.com/infiniflow/ragflow/commits/main)

**Tencent WeKnora** — https://github.com/Tencent/WeKnora
- 34.9k stars, MIT; v0.8.3 dated 2026-10-14; Go backend (Go 1.26), Vue frontend, `docreader` service; vector stores: PostgreSQL (pgvector), Elasticsearch, OpenSearch, Milvus, Weaviate, Qdrant, Apache Doris, Tencent VectorDB; retrieval "Keyword + vector hybrid search, rerank, parent-child chunking and GraphRAG" (Neo4j); rerankers incl. TEI/Pinecone/Cohere/Volcengine; Quick Q&A "cites the sources it used" and v0.8.3 adds navigation from answer to cited passage in the original document; "Multi-workspace RBAC" with "four roles", per-resource ownership, per-workspace audit log, OIDC, scoped API keys, AES-256-GCM credential encryption; REST API "~360 API endpoints", Go SDK, CLI, MCP server; Ollama for LLM and embeddings; "offline and private-cloud installs"; formats PDF, Word, PPT, Excel, CSV, TXT, Markdown, HTML, EPUB, MHTML, JSON, XMind, images; v0.5.2 note "Wiki ingest scales to 40k-document KBs"; Helm charts; "Lite" single binary with SQLite — [WeKnora repo](https://github.com/Tencent/WeKnora)
- Commits 20 Oct 2026 — [WeKnora commits](https://github.com/Tencent/WeKnora/commits/main)

**Open WebUI** — https://github.com/open-webui/open-webui
- 156.3k stars; "contains code under multiple licenses", main code under the Open WebUI License requiring "Open WebUI" branding be kept; vector DBs: ChromaDB, PGVector, Qdrant, Milvus, Elasticsearch, OpenSearch, Pinecone, S3Vector, Oracle 23ai; loaders: Tika, Docling, Document Intelligence, Mistral OCR, PaddleOCR-vl, external; "Supports hybrid search (BM25 + vector) with reranking"; "Granular RBAC & User Groups", SSO via trusted headers/OAuth, LDAP/AD, SCIM 2.0; Ollama + OpenAI-compatible APIs — [Open WebUI repo](https://github.com/open-webui/open-webui)
- LICENSE: "licensees are strictly prohibited from altering, removing, obscuring, or replacing any 'Open WebUI' branding" except where end users do not exceed "fifty (50)" "within any rolling thirty (30) day period", with written permission, or with "a duly executed enterprise license" — [Open WebUI LICENSE](https://github.com/open-webui/open-webui/blob/main/LICENSE); docs state the clause took effect with v0.6.6 (April 2025) and earlier code stays BSD-3 — [docs.openwebui.com/license](https://docs.openwebui.com/license/) (search excerpt)
- Releases v0.12.3 (16 Oct), v0.12.2 and v0.12.1 (14 Oct); commits 16 Oct 2026 — [releases](https://github.com/open-webui/open-webui/releases); [commits](https://github.com/open-webui/open-webui/commits/main)

**AnythingLLM (Mintplex Labs)** — https://github.com/Mintplex-Labs/anything-llm
- 67.4k stars, MIT; React/Vite + Node.js Express + collector; vector DBs: LanceDB (default), PGVector, Astra DB, Pinecone, Chroma, Weaviate, Qdrant, Milvus, Zilliz; "Multi-user instance support and permissioning _Docker version only_"; developer API; "source citations"; agents + MCP; "Built-in optimizations for large document sets"; "Production-ready for any cloud deployment"; telemetry on by default — [AnythingLLM repo](https://github.com/Mintplex-Labs/anything-llm)
- Commits 20 Oct 2026 — [commits](https://github.com/Mintplex-Labs/anything-llm/commits/master)

**Dify** — https://github.com/langgenius/dify
- 159.1k stars; "Dify Open Source License" = "based on Apache 2.0 with additional conditions"; "Extensive RAG capabilities that cover everything from document ingestion to retrieval", built-in extraction for PDFs/PPTs; SSO/RBAC are Enterprise: "For organizations requiring self-hosting, SSO, RBAC Security and Enterprise Support SLAs"; "All of Dify's offerings come with corresponding APIs"; min 2 CPU / 4 GiB RAM — [Dify repo](https://github.com/langgenius/dify)
- LICENSE §1a: "Unless explicitly authorized by Dify in writing, you may not use the Dify source code to operate a multi-tenant environment"; "one tenant corresponds to one workspace"; §1b: "you may not remove or modify the LOGO or copyright information in the Dify console" — [Dify LICENSE](https://github.com/langgenius/dify/blob/main/LICENSE); OSI license-discuss thread (Oct 2025) argues it is not open source — [OSI list](https://lists.opensource.org/pipermail/license-discuss_lists.opensource.org/2025-October/022425.html)
- Commits 20 Oct 2026 — [commits](https://github.com/langgenius/dify/commits/main)

**LightRAG (HKU)** — https://github.com/HKUDS/LightRAG
- 40.2k stars, MIT; Python 3.10; default in-memory storage "suitable only for small-scale testing"; production: PostgreSQL for all four storage types, or MongoDB/OpenSearch; Milvus/Qdrant vectors, Neo4j/Memgraph graphs; modes local/global/hybrid/naive/mix; reranking default for mix since 2025.08 ("1–2 second delay"); citations since 2025.03; parsers MinerU, Docling, Native; "Merge RagAnything into LightRAG" 2026.05; web UI `/webui` + query-only `/workspace`; `AUTH_ACCOUNTS`; hiding admin UI "is a UX split, not a security boundary"; "LightRAG does not currently provide a re-embedding tool"; without auth "every endpoint is public" — [LightRAG repo](https://github.com/HKUDS/LightRAG)
- Commits 14 Oct 2026 — [commits](https://github.com/HKUDS/LightRAG/commits/main)

**Cognee** — https://github.com/topoteretes/cognee
- 32.6k stars, Apache-2.0; v1.6.5 released 16 Oct 2026; multi-tenant default ("every /api/v1 call requires an authenticated user" unless `ENABLE_BACKEND_ACCESS_CONTROL=false`); REST API, Python, TypeScript SDK, Rust impl; Postgres graph store "is currently released as a demo feature" and "The production-ready version is available as a licensed product"; BEAM eval 0.79 at 100K tokens, 0.67 at 10M tokens ("Exploratory") — [Cognee repo](https://github.com/topoteretes/cognee); [commits](https://github.com/topoteretes/cognee/commits/main)

**Kotaemon (Cinnamon)** — https://github.com/Cinnamon/kotaemon
- 25.8k stars, Apache-2.0; vector stores ChromaDB, LanceDB, InMemory, Milvus, Qdrant; "hybrid (full-text & vector) retriever", re-ranking, "detailed citations" with in-browser PDF highlights; "Support multi-user login"; GraphRAG via MS GraphRAG / NanoGraphRAG / LightRAG; parsers Azure DI, Adobe PDF Extract, Docling, PaddleOCR — [Kotaemon repo](https://github.com/Cinnamon/kotaemon)
- Only 4 commits in 2026; last 30 May 2026, before that 28 Mar, 4 Mar, 27 Feb 2026, then 2 Jul 2025 — [commits](https://github.com/Cinnamon/kotaemon/commits/main)

**Quivr** — https://github.com/QuivrHQ/quivr
- 39.6k stars, MIT; now "An open-source engine that turns continuous content streams into search and monitoring"; Go binary (`api`, `worker`, `migrate`), PostgreSQL, S3, Temporal, Weaviate; "**Status: evaluation stage.** The API is `v0` and may change without notice. Do not run it in production yet."; older `multimodal-rag/` is "earlier exploration (submodule), not the target architecture" — [Quivr repo](https://github.com/QuivrHQ/quivr); commits 15 Oct 2026, "2.0.0-alpha.7" on 14 Oct — [commits](https://github.com/QuivrHQ/quivr/commits/main)

**Khoj** — https://github.com/khoj-ai/khoj
- 37.8k stars, AGPL-3.0; formats image, pdf, markdown, org-mode, word, notion; local LLMs; "self-hostable. Always."; vector store and auth not described on page — [Khoj repo](https://github.com/khoj-ai/khoj); last commit 2 Aug 2026, prior 24 Jun 2026 — [commits](https://github.com/khoj-ai/khoj/commits/master)

**PrivateGPT (Zylon)** — https://github.com/zylon-ai/private-gpt
- 57.6k stars, Apache-2.0; 1.0 "rebuilt from the ground up as a proper API layer for private AI applications"; "connects to any OpenAI-compatible inference server" (Ollama, llama.cpp, vLLM); token-based auth supported, "OAuth / organizations" not supported; LDAP/AD + RBAC only in Zylon commercial product — [PrivateGPT repo](https://github.com/zylon-ai/private-gpt); commits 20 Oct 2026 ("citations fix") — [commits](https://github.com/zylon-ai/private-gpt/commits/main)

**Microsoft GraphRAG** — https://github.com/microsoft/graphrag
- 36.4k stars, MIT; "This project is largely in maintenance mode, and won't be accepting new PRs or implementing new features."; "GraphRAG indexing can be an expensive operation" — [GraphRAG repo](https://github.com/microsoft/graphrag); still commits (v3.3.0 on 8 Oct 2026, 20 Oct 2026 dep sweep) — [commits](https://github.com/microsoft/graphrag/commits/main)

**R2R (SciPhi)** — https://github.com/SciPhi-AI/R2R
- 8.0k stars, MIT; "Semantic + keyword search with reciprocal rank fusion", entity/relationship extraction, "Complete authentication & collection system", REST API with Python/JS clients, RAG "with citations" — [R2R repo](https://github.com/SciPhi-AI/R2R); **last commit 7 Nov 2025** (nothing in 2026) — [commits](https://github.com/SciPhi-AI/R2R/commits/main)

**Morphik** — https://github.com/morphik-org/morphik-core
- 3.7k stars; **Business Source License 1.1** ("source-available"), free below US$2,000/month revenue, each version converts to Apache 2.0 four years after release; ColPali visual retrieval; Python SDK + REST; "we cannot provide full support for self-hosted deployments" — [Morphik repo](https://github.com/morphik-org/morphik-core); active, commits 20 Oct 2026 — [commits](https://github.com/morphik-org/morphik-core/commits/main)

**Verba (Weaviate)** — https://github.com/weaviate/Verba
- 7.7k stars, BSD-3-Clause; "This repository was archived by the owner on Jun 8, 2026. It is now read-only."; "Verba is no longer in active development."; multi-user collaboration was explicitly out of scope — [Verba repo](https://github.com/weaviate/Verba)

**txtai (NeuML)** — https://github.com/neuml/txtai
- 13.0k stars, Apache-2.0; Python 3.11+; "union of vector indexes (sparse and dense), graph networks and relational databases"; Web + MCP APIs; txtai 9.0; no multi-user — [txtai repo](https://github.com/neuml/txtai); commits 20 Oct 2026 — [commits](https://github.com/neuml/txtai/commits/master)

**Haystack (deepset)** — https://github.com/deepset-ai/haystack
- 26.8k stars, Apache-2.0, Python; "AI orchestration framework"; serving via separate Hayhooks ("REST APIs" or "MCP servers"); "used by thousands of teams building production AI systems" — [Haystack repo](https://github.com/deepset-ai/haystack); commits 20 Oct 2026 — [commits](https://github.com/deepset-ai/haystack/commits/main)

**LlamaIndex** — https://github.com/run-llama/llama_index
- 52.6k stars, MIT; "over 300 LlamaIndex integration packages"; the company's "primary focus has shifted towards LlamaParse" (commercial) — [LlamaIndex repo](https://github.com/run-llama/llama_index); release 0.14.25 on 21 Sep 2026, commits 14 Oct 2026 — [commits](https://github.com/run-llama/llama_index/commits/main)

**MaxKB (1Panel)** — https://github.com/1Panel-dev/MaxKB
- 23.0k stars, GPL-3.0; Vue + Python/Django; "PostgreSQL + pgvector"; MCP tool use; local models DeepSeek/Llama/Qwen — [MaxKB repo](https://github.com/1Panel-dev/MaxKB); **last commit 19 Aug 2025** on `main` (possibly development moved to another branch; unverified) — [commits](https://github.com/1Panel-dev/MaxKB/commits/main)

**ApeRAG (ApeCloud)** — https://github.com/apecloud/ApeRAG
- 1.3k stars, Apache-2.0; FastAPI + React; Qdrant + Elasticsearch + PostgreSQL + Redis; "combining Graph RAG, vector search, full-text search, summary-based retrieval, and vision-based search"; "Deeply modified LightRAG implementation"; MCP; Helm/KubeBlocks — [ApeRAG repo](https://github.com/apecloud/ApeRAG); last commit 15 Apr 2026 — [commits](https://github.com/apecloud/ApeRAG/commits/main)

**Casibase** — https://github.com/casibase/casibase
- The repo page now renders as "OpenAgent": 5.7k stars, Apache-2.0, Go 1.25 + Node 20; "OIDC / OAuth2 / LDAP / SAML via the built-in auth layer"; "Multi-tenancy ... Isolated workspaces per user or organisation"; REST API + Swagger; Ollama; only "Semantic Search" (no hybrid mentioned) — [casibase repo (renders as OpenAgent)](https://github.com/casibase/casibase)

**Volcengine OpenViking (new, 2026)** — https://github.com/volcengine/OpenViking
- 40.5k stars; AGPLv3 (CLI crate Apache-2.0); "Self-evolving Context Database for AI Agents. Unify Agent Memory, Knowledge RAG and Skills."; "supports accounts and user isolation"; Python/Go/TS SDKs + HTTP API; local Ollama; LoCoMo "80–83% accuracy" — [OpenViking repo](https://github.com/volcengine/OpenViking)

**nashsu/llm_wiki (new, 2026)** — https://github.com/nashsu/llm_wiki
- 20.8k stars, GPL-3.0; Tauri v2 + Rust + React 19; LanceDB vectors; Milkdown WYSIWYG editor; two-step LLM ingest produces entity/concept pages, index.md, log.md; keyword + optional vector + graph expansion (own benchmark recall 58.2% → 71.4%); local MCP server; single-user desktop; v0.6.12 on 27 Sep 2026 — [llm_wiki repo](https://github.com/nashsu/llm_wiki); [commits](https://github.com/nashsu/llm_wiki/commits/main)

#### Third-party comparison claims (secondary, excerpt-only)
- A 2026 comparison lists Verba as "Archived" with last release 2.1.3 (14 Jul 2025), Kotaemon latest 0.12.0 (31 May 2026) with "slowed" activity, R2R last release June 2025 / last commit Nov 2025, LightRAG 1.5.7 (2 Sep 2026) "Active" — [vdf.ai](https://vdf.ai/blog/best-rag-frameworks/) (unreachable; search excerpt)
- Self-hosted guides rank Onyx first for "workforce-facing deployments that need many connectors and permission inheritance" and RAGFlow for document parsing, while noting RAGFlow is "heavier to deploy" — [olostep](https://www.olostep.com/blog/open-source-rag-frameworks); [firecrawl](https://www.firecrawl.dev/blog/best-open-source-rag-frameworks); [awesomeosai](https://awesomeosai.com/self-hosted/rag) (excerpts)
- Onyx's own guide: 40+ native connectors, hybrid search via OpenSearch; RAGFlow "ingestion is primarily file-based (local upload, S3, MinIO, web crawl)" with limited SaaS connectors — [onyx.app self-hosted RAG guide](https://onyx.app/insights/self-hosted-rag) (vendor, excerpt)

### Inferences
- For an *engineering document* corpus (PDF datasheets, standards with tables, scanned drawings), parsing quality dominates, which favours RAGFlow (DeepDoc layout/OCR/table recognition, "view chunking for human intervention") and WeKnora (docreader + navigation to cited passage) over Onyx, whose strength is SaaS connectors.
- WeKnora is the only candidate that already combines all of: permissive MIT license, hybrid+rerank, RBAC with roles, OIDC, a large REST API, an editable wiki, and an explicit tens-of-thousands-of-documents claim (40k). Risk: it is Tencent-driven, young (v0.8.x), and moving fast (v0.5.2 → v0.8.3 within months), so upgrade churn is likely.
- RAGFlow's 1.0 Go rewrite in Sep/Oct 2026 is both a maturity signal and an upgrade-risk signal: rc builds, "EE files" appearing in commits, and the earlier memory-leak history (see Q5) mean you should pin a release.
- Onyx is viable only if you accept that SSO/RBAC/SCIM live under the Enterprise License, which forbids production use without an agreement; the MIT core gives you basic auth and hybrid search but not RBAC.
- Open WebUI should be treated as a chat front-end over an external retrieval service, not as the KB engine, given the 30k–60k-file UI problems reported.
- Frameworks (Haystack, LlamaIndex, txtai, LightRAG as library) are appropriate if the team wants to own the application layer; LightRAG's PostgreSQL-everything backend is the smallest-footprint production path among them but lacks a real multi-user model.
- Avoid: Verba (archived), R2R (no commits since Nov 2025), Kotaemon (4 commits in 2026), Quivr (pivoted, "Do not run it in production"), GraphRAG (maintenance mode), MaxKB (`main` stale since Aug 2025), Morphik (BUSL).

### Gaps
- Could not obtain exact last-commit dates for Haystack/LlamaIndex community health beyond commit pages; could not fetch deepset/LlamaIndex vector-store lists.
- Onyx docs (docs.onyx.app) unreachable; could not confirm the current reranker model, citation behaviour, or the "tens of millions of documents" README phrase (not present in the README section I was served).
- RAGFlow hardware guidance for tens of thousands of documents beyond the 16 GB RAM baseline was not found.
- WeKnora hardware-requirements doc returned 404 at the guessed path.
- Casibase → OpenAgent rename could not be confirmed from a changelog; only the rendered page title.

## Key Question 2: Which projects already pair document chat with an editable wiki, and how well does that work?

### Takeaway
Three projects do this today: Tencent WeKnora (agent-generated interlinked wiki with "in-browser editing, revision diff and rollback", multi-user RBAC, claimed 40k-document ingest), RAGFlow (Knowledge Compilation emits Wiki/Graph/Tree/PageIndex/Mind-Map/Timeline artifacts, but editability of the generated wiki was not documented in what I could read), and nashsu/llm_wiki (Karpathy-style compiled wiki with a Milkdown WYSIWYG editor, but single-user desktop, GPL-3.0). Only WeKnora combines editable wiki + chat + multi-user in a server product; evidence of how well it works at scale is the project's own claim.

### Cited Findings
- WeKnora Wiki mode: "Agent-generated, interlinked pages with a knowledge graph" plus "in-browser editing, revision diff and rollback"; pages "can be edited directly and every change can be rolled back"; v0.5.2: "Wiki ingest scales to 40k-document KBs" — [WeKnora repo](https://github.com/Tencent/WeKnora)
- WeKnora Gitee mirror description: agents "distill raw documents into a self-maintaining, interlinked markdown knowledge base with an interactive knowledge graph, with manual editing, revision history, and rollback" — [Gitee mirror](https://gitee.com/markhoo/WeKnora) (search excerpt)
- RAGFlow Knowledge Compilation "Compiles document- and dataset-level content into artifacts such as Wikis, Graphs, Trees, PageIndex, Mind Maps, Timelines, and Skills"; docs folder `docs/guides/knowledge_compilation` exists; rc2 changelog includes "refactor of knowledge compilation templates" — [RAGFlow repo](https://github.com/infiniflow/ragflow); [docs/guides](https://github.com/infiniflow/ragflow/tree/main/docs/guides); [releases](https://github.com/infiniflow/ragflow/releases)
- llm_wiki: "turns your documents into an organized, interlinked knowledge base — automatically. Instead of traditional RAG ... the LLM incrementally builds and maintains a persistent wiki"; Milkdown WYSIWYG editor; wiki directory "works as an Obsidian vault"; MCP server with hybrid search, graph traversal, rescans; personal/single-user; 20.8k stars, GPL-3.0; recall 58.2% → 71.4% with vector search on (own benchmark) — [llm_wiki repo](https://github.com/nashsu/llm_wiki)
- Curated list of "AI-compiled knowledge base" projects (incl. SwarmVault, a "local-first RAG knowledge base compiler and MCP server that maps files into an interlinked Markdown wiki") — [awesome-llm-wiki](https://github.com/gavischneider/awesome-llm-wiki)
- The "LLM Wiki" pattern (Karpathy, 2026) compiles knowledge at ingestion into structured wiki pages with explicit cross-references rather than retrieving chunks at query time — [kunalganglani guide](https://www.kunalganglani.com/blog/llm-wiki-karpathy-local-knowledge-base) (secondary)
- Open WebUI v0.12.3 fixed "Knowledge sharing kept on rename" for shared knowledge bases, indicating knowledge bases are shareable/collaborative objects but not wikis — [Open WebUI releases](https://github.com/open-webui/open-webui/releases)

### Inferences
- The "compiled wiki" pattern is a 2026 trend (Karpathy post → llm_wiki 20.8k stars within months, WeKnora Wiki mode, RAGFlow Knowledge Compilation), so expect rapid feature change and immature editing/merge workflows.
- WeKnora is the only one with the full loop (ingest → generated wiki → human edit → versioned rollback → chat over both) in a multi-user server; RAGFlow's artifacts appear to be regenerable outputs rather than a human-maintained wiki (unconfirmed).
- llm_wiki is a good reference implementation to borrow ideas (two-step LLM ingest, SHA256 change cache, index/log/overview pages) but its GPL-3.0 licence and desktop architecture make it unsuitable as a server base.

### Gaps
- Could not verify whether RAGFlow's generated Wiki pages are human-editable and whether edits survive recompilation (docs page not fetched).
- No independent user reports on WeKnora Wiki quality/accuracy at scale were found; the 40k figure is self-reported.
- Did not find any project that ingests documents into an existing wiki engine (e.g., Wiki.js/Outline/BookStack) with bidirectional sync.

## Key Question 3: Which projects explicitly support hybrid (keyword + vector) search, reranking, and citation of sources in answers?

### Takeaway
Hybrid + rerank + citations are all three explicitly present in WeKnora, Kotaemon, LightRAG, RAGFlow ("multiple recall" + fused re-ranking + traceable citations), R2R (RRF hybrid + citations) and Open WebUI (BM25+vector+rerank; citations not stated on README). Onyx has a hybrid index but its README does not mention reranking or citations; AnythingLLM has citations but no hybrid/rerank statement; Dify's README mentions none of the three.

### Cited Findings
- WeKnora: "Keyword + vector hybrid search, rerank, parent-child chunking and GraphRAG"; Q&A "cites the sources it used"; v0.8.3 navigation from answer to cited passage — [WeKnora](https://github.com/Tencent/WeKnora)
- RAGFlow: "Multiple recall paired with fused re-ranking"; setup "requires adding a reranker model"; traceable citations and chunk view "for human intervention" — [RAGFlow](https://github.com/infiniflow/ragflow)
- Kotaemon: "hybrid (full-text & vector) retriever", "re-ranking to ensure best retrieval quality", "detailed citations" with relevance scores and in-browser PDF highlights — [Kotaemon](https://github.com/Cinnamon/kotaemon)
- LightRAG: mix mode merges local/global/naive; reranking default since 2025.08 ("typically introduces a 1–2 second delay"); citations since 2025.03 "enabling proper source attribution" — [LightRAG](https://github.com/HKUDS/LightRAG)
- R2R: "Semantic + keyword search with reciprocal rank fusion"; RAG "with citations" — [R2R](https://github.com/SciPhi-AI/R2R)
- Open WebUI: "Supports hybrid search (BM25 + vector) with reranking" and a full-context mode; citations not mentioned on README — [Open WebUI](https://github.com/open-webui/open-webui)
- Onyx: "Vector + Keyword index for RAG"; hybrid index + agent harness; reranking and citations not mentioned on README — [Onyx](https://github.com/onyx-dot-app/onyx)
- AnythingLLM: "source citations"; hybrid/rerank not mentioned — [AnythingLLM](https://github.com/Mintplex-Labs/anything-llm)
- Verba (archived): hybrid search yes; reranking was still "planned" at archival — [Verba](https://github.com/weaviate/Verba)
- txtai: "union of vector indexes (sparse and dense)" (hybrid by construction); RAG guide covers citations — [txtai](https://github.com/neuml/txtai)
- ApeRAG: "Graph RAG, vector search, full-text search, summary-based retrieval, and vision-based search"; reranking/citations not mentioned — [ApeRAG](https://github.com/apecloud/ApeRAG)
- PrivateGPT: a 20 Oct 2026 commit is titled "citations fix (#2414)", so citations exist — [PrivateGPT commits](https://github.com/zylon-ai/private-gpt/commits/main)
- Casibase/OpenAgent: only "Semantic Search" listed — [casibase](https://github.com/casibase/casibase)

### Inferences
- For engineering Q&A where the exact clause/table matters, Kotaemon's PDF-highlight citations and WeKnora's jump-to-passage are the most useful UX patterns; Kotaemon, however, is nearly dormant.
- Onyx almost certainly has reranking and citations in the product (its docs were unreachable), but the README's silence means I could not confirm it here.

### Gaps
- Dify's and Onyx's reranker/citation specifics not confirmed from primary sources due to unreachable docs sites.

## Key Question 4: Which projects have real production deployments at scale, and what performance numbers do they report?

### Takeaway
Scale evidence is thin and mostly vendor-reported: Onyx claims 1,000+ enterprise customers (Ramp ~115K queries/month, UC San Diego 37K+ users air-gapped) and a 220K-document internal benchmark; WeKnora claims 40k-document wiki ingest; Cognee publishes a BEAM score (0.79 @100K tokens, 0.67 @10M tokens, "Exploratory"); RAGFlow publishes no document-count figures but has issues showing single 1,600-page PDFs exhausting 62 GB RAM. No independent third-party benchmark at tens-of-thousands-of-documents scale was found for any platform.

### Cited Findings
- Onyx site lists production use at Ramp, Thales, Astranis, UC San Diego among "1,000+ enterprise customers"; Ramp "115K queries per month"; UC San Diego "37K+ users" air-gapped; EnterpriseRAG-Bench 72.4 on "99 real workplace questions across 220K internal documents" judged by two LLM judges — [onyx.app enterprise RAG 2026](https://onyx.app/insights/enterprise-rag-platforms-2026) (vendor; search excerpt)
- Third-party review repeats 64–76% win rate vs ChatGPT/Claude/Notion AI on same 220K corpus — [teamazing review](https://www.teamazing.com/blog/onyx-ai-enterprise-review-2026/) (secondary)
- Danswer (pre-rename) served "enterprise customers with millions of documents" and migrated to Vespa after accuracy degraded past "several million" — [ZenML LLMOps DB](https://www.zenml.io/llmops-database/scaling-enterprise-rag-with-advanced-vector-search-migration) (excerpt; ~2024). Current compose uses OpenSearch 3.6.0 — [Onyx compose](https://github.com/onyx-dot-app/onyx/blob/main/deployment/docker_compose/docker-compose.yml)
- WeKnora: "Wiki ingest scales to 40k-document KBs" (v0.5.2 note) — [WeKnora](https://github.com/Tencent/WeKnora)
- Cognee BEAM: 0.79 at 100K tokens, 0.67 at 10M tokens, labelled "Exploratory", with a "remaining reproduction gap for the distributed 10M ingestion" — [Cognee](https://github.com/topoteretes/cognee)
- OpenViking: LoCoMo "80–83% accuracy" vs 24–57% native memory; input tokens down 34.3–91.0% (self-reported) — [OpenViking](https://github.com/volcengine/OpenViking)
- llm_wiki own benchmark: recall 58.2% → 71.4% with vector search enabled — [llm_wiki](https://github.com/nashsu/llm_wiki)
- Haystack: "used by thousands of teams building production AI systems" (no numbers) — [Haystack](https://github.com/deepset-ai/haystack)
- AnythingLLM: "Production-ready for any cloud deployment", "battle-tested" (no numbers) — [AnythingLLM](https://github.com/Mintplex-Labs/anything-llm)
- RAGFlow baseline: "4 CPU cores, 16 GB RAM, and 50 GB" — [RAGFlow](https://github.com/infiniflow/ragflow); real-world: 1,600-page/5 MB PDF OOM at 62 GB RAM — [ragflow #11822](https://github.com/infiniflow/ragflow/issues/11822); 875-page PDF used 32 GB with Knowledge-Graph chunking — [ragflow #4668](https://github.com/infiniflow/ragflow/issues/4668)
- Open WebUI user with "60,000+ files" in a knowledge base: `/api/models` response 43–50 MB, browser freezes — [open-webui discussion #13891](https://github.com/open-webui/open-webui/discussions/13891); another at 30k+ documents: browser ~5 GB RAM — same thread

### Inferences
- Onyx is the only platform with named large customers, but all figures are vendor-published; treat 220K-document benchmark as the best available indicator of tens-of-thousands-scale viability.
- Open WebUI's architecture (file UUID lists in `/api/models`, browser-side directory sync) is a structural, not incidental, limit at the 30k–60k-file level.
- RAGFlow's limits are per-document (huge PDFs) rather than per-corpus; a corpus of many normal-size datasheets is a different regime from the OOM reports, but you should budget RAM well above 16 GB for parallel parsing.

### Gaps
- No independent latency/throughput benchmarks (QPS, p95) for any platform at 10k+ documents were found.
- Dify, AnythingLLM, LightRAG and RAGFlow publish no corpus-size guidance; could not reach ragflow.io docs.

## Key Question 5: What are the recurring complaints in issues/discussions (speed, accuracy, memory, upgrade pain)?

### Takeaway
RAGFlow's recurring complaints are memory (DeepDoc/GraphRAG OOM on large PDFs, idle memory growth after v0.19.0) and slow parsing (3 hours for a 68-page PDF with GraphRAG); Open WebUI's are knowledge-base ingestion speed (5,000 files "very slow", 1,000-file uploads memory-heavy with default Chroma), slow retrieval (minute-plus searches), silent stalls on >100 KB Markdown files, and UI collapse at 30k–60k files; cross-cutting license complaints target Dify (multi-tenant/logo clauses, OSI thread) and Open WebUI (branding clause from v0.6.6). LightRAG's own README flags no re-embedding tool and public endpoints without auth.

### Cited Findings
RAGFlow
- 1,600-page, 5 MB PDF drove task executor OOM even with 62 GB RAM; attributed to page images + OCR/layout intermediates held for the whole run — [#11822](https://github.com/infiniflow/ragflow/issues/11822)
- 875-page PDF consumed 32 GB (Knowledge Graph chunking, all pages OCR'd in one pass) — [#4668](https://github.com/infiniflow/ragflow/issues/4668)
- 68-page, 2 MB PDF with GraphRAG took ~3 hours; reporter says LightRAG did it in 1–2 hours — [#5088](https://github.com/infiniflow/ragflow/issues/5088)
- 44 MB PDF: CPU ~99%, memory climbing to all 25 GB — [#7602](https://github.com/infiniflow/ragflow/issues/7602); "Reduce Ram Usage of Ragflow while parsing file" — [#7622](https://github.com/infiniflow/ragflow/issues/7622)
- After v0.19.0, production user saw memory creep to 100% with no traffic, requiring Docker restarts ("Memory leak?") — [#7995](https://github.com/infiniflow/ragflow/issues/7995)
- CPU-only Docker + local model: HTTP 500 during parsing, minutes between log entries — [#10245](https://github.com/infiniflow/ragflow/issues/10245)
- Changelog lists lazy loading / chunked parsing for PDFs >50 pages and a v0.19.1 fix for "memory leak under high-concurrency requests" — [ragflow.io changelog](https://ragflow.io/changelog) (excerpt)
- Platform constraint: "macOS is not currently supported"; Elasticsearch needs `vm.max_map_count` ≥ 262144 — [RAGFlow](https://github.com/infiniflow/ragflow)

Open WebUI
- 60,000+ files → 43–50 MB `/api/models` payload, browser 100% core, freeze ~1 minute into rendering (v0.6.9, May 2025); 30k+ docs → browser ~5 GB RAM (June 2025); no maintainer response or fix in thread — [discussion #13891](https://github.com/open-webui/open-webui/discussions/13891)
- Uploading ~5,000 small Markdown files "very slow" (Jan 2026); maintainer: 1,000 files at once with local processing uses a lot of memory, especially with default Chroma — [discussion #20511](https://github.com/open-webui/open-webui/discussions/20511) (excerpt)
- RAG search taking a minute or more even on small sets, CPU heavily loaded (2025) — [discussion #12746](https://github.com/open-webui/open-webui/discussions/12746) (excerpt)
- Markdown files >~100 KB stall on upload to Knowledge with no error — [issue #15702](https://github.com/open-webui/open-webui/issues/15702) (excerpt)
- Official docs: in-app directory sync "runs in the browser and gets slow on large sets"; recommends external tool "oikb" — [docs: knowledge](https://docs.openwebui.com/features/workspace/knowledge/) (excerpt); RAG troubleshooting suggests `RAG_SYSTEM_CONTEXT` — [docs: troubleshoot RAG](https://docs.openwebui.com/troubleshooting/rag/) (excerpt)
- License: branding clause effective v0.6.6 (April 2025), 50-user/30-day exception — [LICENSE](https://github.com/open-webui/open-webui/blob/main/LICENSE); business commentary — [wz-it](https://wz-it.com/en/blog/open-webui-license-branding-business/)

Dify
- License issue thread and OSI license-discuss (Oct 2025) arguing the "Dify Open Source License" is not open source due to SaaS/multi-tenant and logo restrictions; Apache trademark team notified — [dify issue #17109](https://github.com/langgenius/dify/issues/17109); [OSI thread](https://lists.opensource.org/pipermail/license-discuss_lists.opensource.org/2025-October/022425.html); critical blog — [vonng "dify humiliated"](https://blog.vonng.com/en/ai/dify-humiliated/)

LightRAG (self-declared limitations)
- Default storage "suitable only for small-scale testing"; changing embedding model requires re-embedding and "LightRAG does not currently provide a re-embedding tool"; slow LLMs cause extraction timeouts; without auth "every endpoint is public"; admin/workspace split "is not a security boundary" — [LightRAG](https://github.com/HKUDS/LightRAG)

Others
- GraphRAG: "indexing can be an expensive operation", project in maintenance mode — [GraphRAG](https://github.com/microsoft/graphrag)
- Morphik: "we cannot provide full support for self-hosted deployments" — [Morphik](https://github.com/morphik-org/morphik-core)
- Kotaemon: 221 open issues, 41 open PRs with 4 commits in 2026; CVE-2026-82281 affects ≤0.12.0 — [Kotaemon](https://github.com/Cinnamon/kotaemon); [ionix CVE page](https://www.ionix.io/threat-center/cve-2026-82281/) (excerpt)
- AnythingLLM: telemetry on by default (`DISABLE_TELEMETRY`); multi-user only in Docker build — [AnythingLLM](https://github.com/Mintplex-Labs/anything-llm)
- Onyx: production use of any `ee/` code requires an Enterprise agreement — [backend/ee/LICENSE](https://github.com/onyx-dot-app/onyx/blob/main/backend/ee/LICENSE)

### Inferences
- The two most-starred document-chat apps (Dify, Open WebUI) are both now under non-OSI-approved licences; for a company-internal single-tenant deployment with original branding, neither clause bites, but they rule out white-labelling or a multi-workspace SaaS without a paid licence.
- Memory headroom (64 GB+ on the parsing worker) and per-document page limits should be planned if RAGFlow DeepDoc/GraphRAG is used on long standards documents.
- Open WebUI complaints cluster around the knowledge-base feature specifically, not the chat UI, reinforcing the "front-end only" role.

### Gaps
- Could not search GitHub issues for WeKnora, Onyx, AnythingLLM, Cognee or LightRAG (search budget exhausted), so complaint profiles for those are missing.
- No Reddit r/Rag or r/LocalLLaMA threads were returned by searches; community sentiment is under-represented here.

## Key Question 6 (supplementary): Engineering-document-specific repos, abandoned projects, and licence changes

### Takeaway
No mature open-source repo dedicated to engineering datasheets/standards knowledge bases was found; the closest are a 2025 Frontiers paper (n8n-based RAG over national codes and design standards, code released) and a construction-specs RAG skill, plus general tooling (RAGFlow DeepDoc tables, Docling/MinerU parsers). Abandoned or de-prioritised in 2025–2026: Verba (archived Jun 2026), R2R (no commits since Nov 2025), Kotaemon (near-dormant), GraphRAG (maintenance mode), MaxKB `main` (stale since Aug 2025), Quivr (pivoted away from document chat). Licence changes to note: Open WebUI (BSD-3 → branding clause, v0.6.6/Apr 2025), Dify (Apache-2.0 + conditions since 2023, challenged at OSI Oct 2025), Morphik (BUSL 1.1), Onyx (`ee/` dirs under Enterprise License), Cognee (Postgres graph store production version "licensed product").

### Cited Findings
- Frontiers in AI (2025) paper: RAG-LLMs on n8n for engineering, tested on national codes, technical standards and design standards, with a workflow for tabular structures and "exception logic"; parsing/embedding code released via Data Availability — [Frontiers article](https://www.frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2025.1697169/full) (unreachable; search excerpt)
- OpenFOAM end-to-end RAG paper addressing formulae corrupted during PDF extraction — [ACL Anthology, Himanshu Dhurve](https://aclanthology.org/people/himanshu-dhurve/) (unreachable; excerpt)
- DataDrivenConstruction skill for RAG over specs, drawings, RFIs — [getclawkit listing](https://getclawkit.com/skills/official-datadrivenconstruction-rag-construction) (secondary)
- Flocode article on LightRAG for engineering knowledge bases (paywalled) — [Flocode #078](https://flocode.substack.com/p/078-lightrag-from-document-retrieval)
- Verba archived 8 Jun 2026 — [Verba](https://github.com/weaviate/Verba); R2R last commit 7 Nov 2025 — [R2R commits](https://github.com/SciPhi-AI/R2R/commits/main); Kotaemon last commit 30 May 2026 — [Kotaemon commits](https://github.com/Cinnamon/kotaemon/commits/main); GraphRAG maintenance mode — [GraphRAG](https://github.com/microsoft/graphrag); MaxKB main last commit 19 Aug 2025 — [MaxKB commits](https://github.com/1Panel-dev/MaxKB/commits/main); Quivr "Do not run it in production yet" — [Quivr](https://github.com/QuivrHQ/quivr)
- Licence facts: Open WebUI — [LICENSE](https://github.com/open-webui/open-webui/blob/main/LICENSE); Dify — [LICENSE](https://github.com/langgenius/dify/blob/main/LICENSE); Morphik BUSL 1.1 — [Morphik](https://github.com/morphik-org/morphik-core); Onyx — [LICENSE](https://github.com/onyx-dot-app/onyx/blob/main/LICENSE); Cognee licensed graph store — [Cognee](https://github.com/topoteretes/cognee); FastGPT reportedly Apache-2.0 "with extra conditions" restricting SaaS and MaxKB GPL-3.0 — [jimmysong comparison](https://jimmysong.io/blog/open-source-ai-agent-workflow-comparison/) (excerpt)
- Trend: Volcengine OpenViking (40.5k, AGPLv3) and Tencent WeKnora (34.9k, MIT) are 2025–2026 entrants now larger by stars than Kotaemon, Cognee or Onyx — [OpenViking](https://github.com/volcengine/OpenViking); [WeKnora](https://github.com/Tencent/WeKnora)

### Inferences
- Engineering-specific value will come from the parsing layer (tables, formulae, scanned drawings) rather than from any existing vertical repo; RAGFlow DeepDoc, Docling, MinerU and PaddleOCR are the parsers the surveyed platforms converge on.
- Chinese-origin projects (RAGFlow, WeKnora, Dify, MaxKB, FastGPT, OpenViking) now dominate the top of the document-RAG category by stars; community/issue discussion is often bilingual.

### Gaps
- Could not run targeted GitHub searches for "datasheet"/"standards" RAG repos (search budget exhausted); none surfaced in the general searches performed.
- Could not confirm whether MaxKB development continues on a non-`main` branch.
