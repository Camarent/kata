-- 0005: per-user journal of policy and activity events, newest first on read.
-- Every row carries user_id ON DELETE CASCADE. detail is free-form jsonb.

CREATE TABLE journal_entry (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    kind text NOT NULL,
    detail jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL
);

CREATE INDEX journal_entry_user_id_id_idx ON journal_entry (user_id, id DESC);
