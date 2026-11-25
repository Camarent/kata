-- 0023: page summary cache and reader document jobs. Additive only: no existing table is
-- altered or dropped.
-- page_summary: one cached summary per (url, text_sha256); the text hash keys the cache so a
-- changed page is summarised again.
-- reader_document: one uploaded document per reader job; content may be nulled once the job
-- is done, and status gates whether text is ready to read.

CREATE TABLE page_summary (
    id bigserial PRIMARY KEY,
    url text NOT NULL,
    text_sha256 text NOT NULL,
    summary text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (url, text_sha256)
);

CREATE TABLE reader_document (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    media_type text NOT NULL CHECK (media_type IN ('application/pdf', 'image/png', 'image/jpeg', 'image/webp')),
    size_bytes integer NOT NULL,
    sha256 text NOT NULL,
    content bytea,
    status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'done', 'failed')),
    text text,
    page_count integer,
    error text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX reader_document_user_id_idx ON reader_document (user_id);
