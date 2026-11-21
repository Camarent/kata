-- 0002: concepts under a topic, and per-user marks on concepts.
-- A concept with owner_user_id NULL is shared. Concept marks are private: every row
-- carries user_id ON DELETE CASCADE. The marks table (0001) is untouched.

CREATE TABLE concepts (
    id bigserial PRIMARY KEY,
    topic_id bigint NOT NULL REFERENCES topics (id) ON DELETE CASCADE,
    label text NOT NULL,
    owner_user_id bigint REFERENCES users (id) ON DELETE CASCADE
);

-- Labels are unique per topic and owner, case-insensitively. Ids start at 1,
-- so coalesce(owner_user_id, 0) gives shared concepts one fixed key.
CREATE UNIQUE INDEX concepts_topic_label_owner
    ON concepts (topic_id, lower(label), coalesce(owner_user_id, 0));

CREATE TABLE concept_marks (
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    concept_id bigint NOT NULL REFERENCES concepts (id) ON DELETE CASCADE,
    state text NOT NULL CHECK (state IN ('known', 'learning', 'new')),
    evidence text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, concept_id)
);
