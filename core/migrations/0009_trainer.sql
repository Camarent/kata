-- 0009: trainer courses. A course belongs to one user (user_id ON DELETE CASCADE). Its
-- source files, artifacts and item map reference the course ON DELETE CASCADE.

CREATE TABLE course (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    title text NOT NULL DEFAULT '',
    status text NOT NULL CHECK (status IN ('queued', 'generating', 'building', 'ready', 'failed')),
    concept_ids bigint[] NOT NULL DEFAULT '{}',
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Courses of one user, newest first.
CREATE INDEX course_user_id_id_idx ON course (user_id, id);

-- Generated source files of a course.
CREATE TABLE course_file (
    course_id bigint NOT NULL REFERENCES course (id) ON DELETE CASCADE,
    path text NOT NULL,
    content text NOT NULL,
    PRIMARY KEY (course_id, path)
);

-- Built artifacts of a course.
CREATE TABLE course_artifact (
    course_id bigint NOT NULL REFERENCES course (id) ON DELETE CASCADE,
    path text NOT NULL,
    media_type text NOT NULL,
    content bytea NOT NULL,
    PRIMARY KEY (course_id, path)
);

-- Which concept each item of a course teaches. Append-only.
CREATE TABLE course_item_map (
    course_id bigint NOT NULL REFERENCES course (id) ON DELETE CASCADE,
    item_id text NOT NULL,
    concept_id bigint NOT NULL REFERENCES concepts (id) ON DELETE CASCADE,
    PRIMARY KEY (course_id, item_id)
);
