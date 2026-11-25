-- 0019: named concept lists per user (M21). A list name is unique per user after
-- normalising: trimmed, inner whitespace collapsed, case-folded (as migration 0014 does for course titles).
-- Deleting a user removes their lists; deleting a list or a concept removes its list items.

CREATE TABLE concept_list (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX concept_list_user_id_name_norm_uidx
    ON concept_list (user_id, (lower(btrim(regexp_replace(name, '\s+', ' ', 'g')))));

CREATE TABLE concept_list_item (
    list_id bigint NOT NULL REFERENCES concept_list (id) ON DELETE CASCADE,
    concept_id bigint NOT NULL REFERENCES concepts (id) ON DELETE CASCADE,
    PRIMARY KEY (list_id, concept_id)
);
