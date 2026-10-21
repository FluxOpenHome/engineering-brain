-- Wiki provenance fixes.
--
-- 0001 declared wiki_page_sources with PRIMARY KEY (page_id, document_id, chunk_id) while the
-- chunk_id foreign key is ON DELETE SET NULL. A primary-key column is NOT NULL, so deleting any
-- cited chunk (re-indexing a revision) failed with a not-null violation. Use a surrogate key and
-- allow chunk_id to become NULL (an orphaned citation, surfaced by `eb wiki lint`).
-- A source also records the cited page number and the document number for display.
ALTER TABLE wiki_page_sources DROP CONSTRAINT wiki_page_sources_pkey;
ALTER TABLE wiki_page_sources ALTER COLUMN chunk_id DROP NOT NULL;
ALTER TABLE wiki_page_sources ADD COLUMN id uuid PRIMARY KEY DEFAULT gen_random_uuid();
ALTER TABLE wiki_page_sources ADD COLUMN page int;
ALTER TABLE wiki_page_sources ADD COLUMN doc_number text;
CREATE UNIQUE INDEX wiki_page_sources_uniq_idx ON wiki_page_sources
    (page_id, document_id, COALESCE(chunk_id, '00000000-0000-0000-0000-000000000000'::uuid));
CREATE INDEX wiki_page_sources_revision_idx ON wiki_page_sources (revision_id);
CREATE INDEX wiki_page_sources_chunk_idx ON wiki_page_sources (chunk_id);
