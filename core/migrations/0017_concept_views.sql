-- 0017: last-viewed time per user (audit A1/S2). Each user has their own row, so one
-- user viewing a shared concept does not change what another user sees.
-- concepts.last_viewed_at stays from 0015 but nothing writes or reads it any more.

CREATE TABLE concept_views (
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    concept_id bigint NOT NULL REFERENCES concepts (id) ON DELETE CASCADE,
    last_viewed_at timestamptz NOT NULL,
    PRIMARY KEY (user_id, concept_id)
);
