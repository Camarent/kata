-- 0020: goals of a planning track, their sources and the concepts they cover. Every row
-- is reached through its track, so the user scope follows track.user_id. track and
-- track_item are unchanged. Deleting a track cascades to its goals, sources and links.

-- A goal of a track. deadline is an optional time budget for the goal; NULL means none.
CREATE TABLE track_goal (
    id bigserial PRIMARY KEY,
    track_id bigint NOT NULL REFERENCES track (id) ON DELETE CASCADE,
    name text NOT NULL,
    deadline date,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Material a goal was built from: pasted text, a file or a page. A goal may have many.
CREATE TABLE track_goal_source (
    id bigserial PRIMARY KEY,
    goal_id bigint NOT NULL REFERENCES track_goal (id) ON DELETE CASCADE,
    kind text NOT NULL CHECK (kind IN ('text', 'file', 'page')),
    label text NOT NULL,
    body text NOT NULL,
    added_at timestamptz NOT NULL DEFAULT now()
);

-- A concept a goal covers. One row per (goal, concept): attaching twice keeps the first
-- row. source_id names the source it came from; it is nulled when that source is removed.
CREATE TABLE track_goal_concept (
    goal_id bigint NOT NULL REFERENCES track_goal (id) ON DELETE CASCADE,
    concept_id bigint NOT NULL REFERENCES concepts (id) ON DELETE CASCADE,
    source_id bigint REFERENCES track_goal_source (id) ON DELETE SET NULL,
    PRIMARY KEY (goal_id, concept_id)
);
