-- 0001: initial schema. Every personal row carries user_id ON DELETE CASCADE.
-- A topic or alias with owner_user_id NULL is shared (visible to all users).

CREATE TABLE users (
    id bigserial PRIMARY KEY,
    name text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE enrolment_codes (
    id bigserial PRIMARY KEY,
    code_hash text NOT NULL UNIQUE,
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    expires_at timestamptz NOT NULL,
    used_at timestamptz
);

CREATE TABLE devices (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    label text NOT NULL,
    token_hash text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz
);

CREATE TABLE categories (
    id bigserial PRIMARY KEY,
    name text NOT NULL UNIQUE
);

CREATE TABLE topics (
    id bigserial PRIMARY KEY,
    category_id bigint NOT NULL REFERENCES categories (id),
    label text NOT NULL,
    owner_user_id bigint REFERENCES users (id) ON DELETE CASCADE
);

-- Labels are unique per category and owner, case-insensitively. Ids start at 1,
-- so coalesce(owner_user_id, 0) gives shared topics one fixed key.
CREATE UNIQUE INDEX topics_category_label_owner
    ON topics (category_id, lower(label), coalesce(owner_user_id, 0));

CREATE TABLE topic_aliases (
    id bigserial PRIMARY KEY,
    topic_id bigint NOT NULL REFERENCES topics (id) ON DELETE CASCADE,
    alias text NOT NULL,
    owner_user_id bigint REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE marks (
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    topic_id bigint NOT NULL REFERENCES topics (id) ON DELETE CASCADE,
    status text NOT NULL CHECK (status IN ('known')),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, topic_id)
);

CREATE TABLE jobs (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    payload text NOT NULL,
    status text NOT NULL CHECK (status IN ('queued', 'leased', 'done', 'failed')),
    lease_expires_at timestamptz,
    attempts int NOT NULL DEFAULT 0,
    result_topic_id bigint REFERENCES topics (id),
    created_at timestamptz NOT NULL DEFAULT now()
);
