-- 0012: syllabi (D10). A syllabus belongs to one user (user_id ON DELETE CASCADE).
-- Its modules and their concept links reference the syllabus ON DELETE CASCADE.

CREATE TABLE syllabus (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    title text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'ready',
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Syllabi of one user, newest first.
CREATE INDEX syllabus_user_id_id_idx ON syllabus (user_id, id);

-- Modules of a syllabus, in position order. words counts the words of body.
CREATE TABLE syllabus_module (
    id bigserial PRIMARY KEY,
    syllabus_id bigint NOT NULL REFERENCES syllabus (id) ON DELETE CASCADE,
    position int NOT NULL CHECK (position >= 0),
    title text NOT NULL,
    body text NOT NULL,
    words int NOT NULL CHECK (words >= 0),
    UNIQUE (syllabus_id, position)
);

-- Concepts a module covers. Replaced as a set; cascades with the module and the concept.
CREATE TABLE syllabus_module_concept (
    module_id bigint NOT NULL REFERENCES syllabus_module (id) ON DELETE CASCADE,
    concept_id bigint NOT NULL REFERENCES concepts (id) ON DELETE CASCADE,
    PRIMARY KEY (module_id, concept_id)
);
