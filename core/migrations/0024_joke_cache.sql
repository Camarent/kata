-- 0024: joke cache. Additive only: no existing table is altered or dropped.
-- joke_cache: one row per (source_id, text); a joke already cached is not stored twice.
-- served_at stays NULL until the joke is handed out; only served rows may be pruned.

CREATE TABLE joke_cache (
    id bigserial PRIMARY KEY,
    source_id text NOT NULL,
    text text NOT NULL,
    created_at timestamptz DEFAULT now(),
    served_at timestamptz NULL,
    UNIQUE (source_id, text)
);
