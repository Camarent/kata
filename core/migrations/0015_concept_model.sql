-- 0015: concept model schema (D42, D53, D55). Schema only: migration 0016 copies data.
-- Concept identity stays on concepts (area = category, topic, name); nothing here moves it.

-- Alternative names for a concept (D53). topic_id is copied from the concept, so
-- uniqueness can run per area+topic+owner. A shared alias has owner_user_id NULL.
CREATE TABLE concept_aliases (
    id bigserial PRIMARY KEY,
    concept_id bigint NOT NULL REFERENCES concepts (id) ON DELETE CASCADE,
    topic_id bigint NOT NULL REFERENCES topics (id) ON DELETE CASCADE,
    alias text NOT NULL,
    owner_user_id bigint REFERENCES users (id) ON DELETE CASCADE
);

-- Aliases are unique per topic and owner, case-insensitively. Ids start at 1,
-- so coalesce(owner_user_id, 0) gives shared aliases one fixed key.
CREATE UNIQUE INDEX concept_aliases_topic_alias_owner
    ON concept_aliases (topic_id, lower(alias), coalesce(owner_user_id, 0));

-- Definition text (D55) and the date fields the sort order uses (D42).
-- Existing concepts get an empty definition, added_at = migration time, and no last view.
ALTER TABLE concepts
    ADD COLUMN definition text NOT NULL DEFAULT '',
    ADD COLUMN added_at timestamptz NOT NULL DEFAULT now(),
    ADD COLUMN last_viewed_at timestamptz NULL;

-- Concepts a user hides from their lists (D55). A hidden concept keeps its marks.
CREATE TABLE concept_ignored (
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    concept_id bigint NOT NULL REFERENCES concepts (id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, concept_id)
);
