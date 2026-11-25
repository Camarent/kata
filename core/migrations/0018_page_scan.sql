-- 0018: page classification cache (D55d) and remembered concept choices (D38).
-- A classification is per user and page; a remembered choice is per user, topic and word.
-- Deleting a user, topic or concept removes the rows that depend on it.

CREATE TABLE page_classifications (
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    page_key text NOT NULL,
    topic_id bigint NOT NULL REFERENCES topics (id) ON DELETE CASCADE,
    candidates jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, page_key)
);

CREATE TABLE concept_choices (
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    topic_id bigint NOT NULL REFERENCES topics (id) ON DELETE CASCADE,
    word_key text NOT NULL,
    concept_id bigint NOT NULL REFERENCES concepts (id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, topic_id, word_key)
);
