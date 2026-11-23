-- 0003: retrieval entries: text bodies with full-text and optional embedding.
-- An entry with owner_user_id NULL is shared. Embeddings are plain real[]: no pgvector.

CREATE TABLE retrieval_entries (
    id bigserial PRIMARY KEY,
    owner_user_id bigint REFERENCES users (id) ON DELETE CASCADE,
    source_ref text NOT NULL,
    body text NOT NULL,
    tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', body)) STORED,
    embedding real[],
    embedding_model text
);

CREATE INDEX retrieval_entries_tsv ON retrieval_entries USING gin (tsv);
CREATE INDEX retrieval_entries_owner ON retrieval_entries (owner_user_id);
