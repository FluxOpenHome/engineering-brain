# ADR-0001: PostgreSQL is the single system of record (including vectors)

Status: accepted, 2026-10-21

## Context
The corpus target is 10k–100k documents, roughly 0.5–5 million chunks. The research report
(section 3) shows every mainstream engine, including pgvector, answers ANN queries in single-digit
milliseconds at 1M vectors on CPU, and that filtered recall collapses when ACL filtering is applied
after ranking in a separate vector store.

## Decision
Documents, revisions, chunks (text, tsvector, halfvec embeddings), ACLs, wiki metadata, requirements,
verdicts, conversations and the job queue live in one PostgreSQL 16 database with pgvector 0.8
(HNSW, iterative scans). Keyword search uses tsvector; fusion is reciprocal rank fusion in the API.
ACL and revision filters are WHERE clauses evaluated before ranking.

## Consequences
- One backup, one transaction boundary (chunk swap + revision activation is atomic).
- No second search cluster to operate.
- Revisit (ADR to follow) if vectors exceed ~5M (pgvectorscale) or heavy multi-vector/ColPali
  retrieval is needed (Qdrant).
