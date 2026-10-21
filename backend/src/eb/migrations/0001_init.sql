-- Engineering Brain: initial schema. See docs/ARCHITECTURE.md section 5.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------- identities
CREATE TABLE users (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email         text UNIQUE NOT NULL,
    display_name  text NOT NULL DEFAULT '',
    external_id   text UNIQUE,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE groups (
    id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name  text UNIQUE NOT NULL
);

CREATE TABLE user_groups (
    user_id  uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    group_id uuid NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, group_id)
);

-- Everyone belongs to "everyone"; documents default to readable by it.
INSERT INTO groups (name) VALUES ('everyone'), ('admins');

-- ---------------------------------------------------------------- documents
CREATE TYPE revision_status AS ENUM ('draft', 'active', 'superseded', 'archived');
CREATE TYPE parse_status AS ENUM ('queued', 'running', 'done', 'failed');
CREATE TYPE parse_pass AS ENUM ('none', 'text_layer', 'layout', 'vlm');

CREATE TABLE documents (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_number          text,                      -- organisation's document number, if any
    title               text NOT NULL,
    doc_type            text NOT NULL DEFAULT 'unknown',  -- spec|datasheet|standard|drawing|report|procedure|other
    discipline          text[] NOT NULL DEFAULT '{}',     -- fluid|electrical|civil|structural|mechanical|chemical|materials|ic|general
    project             text,
    owner_group_id      uuid REFERENCES groups(id),
    current_revision_id uuid,                      -- FK added below
    created_by          uuid REFERENCES users(id),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX documents_doc_number_idx ON documents (doc_number);
CREATE INDEX documents_project_idx ON documents (project);
CREATE INDEX documents_title_trgm_idx ON documents USING gin (title gin_trgm_ops);

CREATE TABLE document_revisions (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id      uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    revision         text NOT NULL DEFAULT '0',
    status           revision_status NOT NULL DEFAULT 'draft',
    effective_date   date,
    source_sha256    text NOT NULL,
    storage_key      text NOT NULL,
    filename         text NOT NULL,
    mime             text NOT NULL,
    size_bytes       bigint NOT NULL,
    page_count       int,
    parse_status     parse_status NOT NULL DEFAULT 'queued',
    parse_pass       parse_pass NOT NULL DEFAULT 'none',
    parse_error      text,
    parsed_at        timestamptz,
    superseded_by_id uuid REFERENCES document_revisions(id),
    created_by       uuid REFERENCES users(id),
    created_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, revision)
);
CREATE INDEX document_revisions_sha_idx ON document_revisions (source_sha256);
CREATE INDEX document_revisions_doc_idx ON document_revisions (document_id);

ALTER TABLE documents
    ADD CONSTRAINT documents_current_revision_fk
    FOREIGN KEY (current_revision_id) REFERENCES document_revisions(id) DEFERRABLE INITIALLY DEFERRED;

CREATE TYPE acl_perm AS ENUM ('read', 'write', 'admin');
CREATE TABLE document_acl (
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    group_id    uuid NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    perm        acl_perm NOT NULL DEFAULT 'read',
    PRIMARY KEY (document_id, group_id)
);

-- ---------------------------------------------------------------- chunks
CREATE TYPE chunk_kind AS ENUM ('text', 'table', 'figure', 'clause', 'requirement', 'heading');

CREATE TABLE chunks (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    revision_id     uuid NOT NULL REFERENCES document_revisions(id) ON DELETE CASCADE,
    ordinal         int NOT NULL,
    kind            chunk_kind NOT NULL DEFAULT 'text',
    section_path    text[] NOT NULL DEFAULT '{}',
    clause_id       text,
    page_start      int,
    page_end        int,
    bbox            jsonb,
    text            text NOT NULL,
    context_prefix  text NOT NULL DEFAULT '',
    token_count     int NOT NULL DEFAULT 0,
    content_hash    text NOT NULL,
    embedding       halfvec(1024),
    embedding_model text,
    tsv             tsvector GENERATED ALWAYS AS (
                        setweight(to_tsvector('english', coalesce(context_prefix, '')), 'A') ||
                        setweight(to_tsvector('english', coalesce(clause_id, '')), 'A') ||
                        setweight(to_tsvector('english', text), 'B')
                    ) STORED,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (revision_id, ordinal)
);
CREATE INDEX chunks_doc_idx ON chunks (document_id, revision_id);
CREATE INDEX chunks_tsv_idx ON chunks USING gin (tsv);
CREATE INDEX chunks_embedding_idx ON chunks USING hnsw (embedding halfvec_cosine_ops)
    WITH (m = 16, ef_construction = 128);

-- ---------------------------------------------------------------- jobs
CREATE TYPE job_status AS ENUM ('queued', 'running', 'done', 'failed', 'dead');

CREATE TABLE jobs (
    id          bigserial PRIMARY KEY,
    kind        text NOT NULL,
    payload     jsonb NOT NULL DEFAULT '{}',
    status      job_status NOT NULL DEFAULT 'queued',
    priority    int NOT NULL DEFAULT 100,        -- lower runs first
    attempts    int NOT NULL DEFAULT 0,
    max_attempts int NOT NULL DEFAULT 3,
    run_after   timestamptz NOT NULL DEFAULT now(),
    locked_by   text,
    locked_at   timestamptz,
    error       text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    started_at  timestamptz,
    finished_at timestamptz
);
CREATE INDEX jobs_claim_idx ON jobs (status, priority, run_after) WHERE status = 'queued';

-- ---------------------------------------------------------------- wiki
CREATE TYPE wiki_status AS ENUM ('proposed', 'published', 'stale', 'archived');

CREATE TABLE wiki_pages (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug               text UNIQUE NOT NULL,       -- path relative to wiki root, no extension
    title              text NOT NULL,
    status             wiki_status NOT NULL DEFAULT 'published',
    discipline         text[] NOT NULL DEFAULT '{}',
    tags               text[] NOT NULL DEFAULT '{}',
    content_hash       text NOT NULL DEFAULT '',
    last_published_sha text,                      -- git commit of last publish
    reviewed_by        uuid REFERENCES users(id),
    human_edited       boolean NOT NULL DEFAULT false,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX wiki_pages_title_trgm_idx ON wiki_pages USING gin (title gin_trgm_ops);

CREATE TABLE wiki_page_sources (
    page_id     uuid NOT NULL REFERENCES wiki_pages(id) ON DELETE CASCADE,
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    revision_id uuid REFERENCES document_revisions(id) ON DELETE SET NULL,
    chunk_id    uuid REFERENCES chunks(id) ON DELETE SET NULL,
    PRIMARY KEY (page_id, document_id, chunk_id)
);

CREATE TYPE proposal_kind AS ENUM ('create', 'update', 'delete');
CREATE TYPE proposal_status AS ENUM ('open', 'accepted', 'rejected', 'superseded');

CREATE TABLE wiki_proposals (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    page_id     uuid REFERENCES wiki_pages(id) ON DELETE CASCADE,
    slug        text NOT NULL,
    kind        proposal_kind NOT NULL,
    base_hash   text,                             -- content_hash the proposal was computed against
    title       text,
    content     text,                             -- full proposed markdown (frontmatter + body)
    rationale   text NOT NULL DEFAULT '',
    sources     jsonb NOT NULL DEFAULT '[]',      -- [{document_id, revision_id, chunk_id, page}]
    confidence  real,
    status      proposal_status NOT NULL DEFAULT 'open',
    created_by  text NOT NULL DEFAULT 'agent',    -- 'agent' or a user id
    reviewed_by uuid REFERENCES users(id),
    review_note text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    decided_at  timestamptz
);
CREATE INDEX wiki_proposals_open_idx ON wiki_proposals (status, created_at) WHERE status = 'open';

CREATE TABLE wiki_chunks (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    page_id         uuid NOT NULL REFERENCES wiki_pages(id) ON DELETE CASCADE,
    ordinal         int NOT NULL,
    section_path    text[] NOT NULL DEFAULT '{}',
    text            text NOT NULL,
    context_prefix  text NOT NULL DEFAULT '',
    token_count     int NOT NULL DEFAULT 0,
    content_hash    text NOT NULL,
    embedding       halfvec(1024),
    embedding_model text,
    tsv             tsvector GENERATED ALWAYS AS (
                        setweight(to_tsvector('english', coalesce(context_prefix, '')), 'A') ||
                        setweight(to_tsvector('english', text), 'B')
                    ) STORED,
    UNIQUE (page_id, ordinal)
);
CREATE INDEX wiki_chunks_tsv_idx ON wiki_chunks USING gin (tsv);
CREATE INDEX wiki_chunks_embedding_idx ON wiki_chunks USING hnsw (embedding halfvec_cosine_ops)
    WITH (m = 16, ef_construction = 128);

-- ---------------------------------------------------------------- requirements & compliance
CREATE TYPE requirement_source AS ENUM ('manual', 'reqif', 'excel', 'extracted');
CREATE TYPE requirement_kind AS ENUM ('functional', 'performance', 'interface', 'constraint', 'design', 'other');

CREATE TABLE requirement_sets (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL,
    description text NOT NULL DEFAULT '',
    source      requirement_source NOT NULL DEFAULT 'manual',
    document_id uuid REFERENCES documents(id) ON DELETE SET NULL,
    revision_id uuid REFERENCES document_revisions(id) ON DELETE SET NULL,
    discipline  text[] NOT NULL DEFAULT '{}',
    created_by  uuid REFERENCES users(id),
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE requirements (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    set_id          uuid NOT NULL REFERENCES requirement_sets(id) ON DELETE CASCADE,
    req_id          text NOT NULL,                -- e.g. "REQ-PMP-012" or clause "4.2.3"
    text            text NOT NULL,
    kind            requirement_kind NOT NULL DEFAULT 'other',
    -- Structured quantity for deterministic comparison:
    -- {"param":"design pressure","op":">=","value":16,"unit":"bar","tol":null}
    quantity        jsonb,
    parent_id       uuid REFERENCES requirements(id) ON DELETE SET NULL,
    source_chunk_id uuid REFERENCES chunks(id) ON DELETE SET NULL,
    ears_pattern    text,                         -- ubiquitous|event|state|option|unwanted|complex
    ordinal         int NOT NULL DEFAULT 0,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (set_id, req_id)
);
CREATE INDEX requirements_set_idx ON requirements (set_id, ordinal);

CREATE TYPE run_status AS ENUM ('queued', 'running', 'done', 'failed');
CREATE TYPE verdict AS ENUM ('compliant', 'non_compliant', 'partial', 'insufficient_evidence', 'not_applicable', 'unverified');

CREATE TABLE compliance_runs (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    set_id               uuid NOT NULL REFERENCES requirement_sets(id) ON DELETE CASCADE,
    subject_document_id  uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    subject_revision_id  uuid NOT NULL REFERENCES document_revisions(id) ON DELETE CASCADE,
    status               run_status NOT NULL DEFAULT 'queued',
    model                text,
    summary              jsonb NOT NULL DEFAULT '{}',
    error                text,
    started_by           uuid REFERENCES users(id),
    created_at           timestamptz NOT NULL DEFAULT now(),
    finished_at          timestamptz
);

CREATE TABLE compliance_findings (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id           uuid NOT NULL REFERENCES compliance_runs(id) ON DELETE CASCADE,
    requirement_id   uuid NOT NULL REFERENCES requirements(id) ON DELETE CASCADE,
    verdict          verdict NOT NULL,
    llm_verdict      verdict,
    confidence       real,
    -- [{"chunk_id":..., "quote":..., "page":..., "verified":true}]
    evidence         jsonb NOT NULL DEFAULT '[]',
    numeric_check    jsonb,                       -- {"required":..., "found":..., "result":"pass|fail|unknown", "detail":...}
    rationale        text NOT NULL DEFAULT '',
    needs_review     boolean NOT NULL DEFAULT false,
    reviewer_verdict verdict,
    reviewer_note    text,
    reviewed_by      uuid REFERENCES users(id),
    reviewed_at      timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, requirement_id)
);
CREATE INDEX compliance_findings_review_idx ON compliance_findings (run_id) WHERE needs_review;

-- ---------------------------------------------------------------- chat
CREATE TABLE conversations (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid REFERENCES users(id) ON DELETE CASCADE,
    title      text NOT NULL DEFAULT '',
    scope      jsonb NOT NULL DEFAULT '{}',       -- {"document_ids":[...], "project":..., "wiki":true}
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE messages (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            text NOT NULL,                -- user|assistant
    content         text NOT NULL,
    citations       jsonb NOT NULL DEFAULT '[]',
    usage           jsonb,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX messages_conv_idx ON messages (conversation_id, created_at);
