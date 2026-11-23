-- 0010: trainer mastery (D9). The trainer scores concepts from course evidence; a
-- user mark can hold against it. concept_marks.source tells who wrote a mark.

-- Which party wrote a concept mark. Existing marks were all written by the user.
ALTER TABLE concept_marks
    ADD COLUMN source text NOT NULL DEFAULT 'user' CHECK (source IN ('user', 'trainer'));

-- Cumulative ok/bad counts per course item, per user. Removed with the course.
CREATE TABLE trainer_progress (
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    course_id bigint NOT NULL REFERENCES course (id) ON DELETE CASCADE,
    item_id text NOT NULL,
    ok integer NOT NULL DEFAULT 0 CHECK (ok >= 0),
    bad integer NOT NULL DEFAULT 0 CHECK (bad >= 0),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, course_id, item_id)
);

-- Evidence deltas per course item. Evidence outlives its course: course_id becomes NULL.
CREATE TABLE trainer_evidence (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    course_id bigint REFERENCES course (id) ON DELETE SET NULL,
    item_id text NOT NULL,
    ok integer NOT NULL CHECK (ok >= 0),
    bad integer NOT NULL CHECK (bad >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT trainer_evidence_delta_unique UNIQUE (user_id, course_id, item_id, ok, bad)
);

-- Mastery score of a concept per user, in [0, 1]. contrary_rows counts trainer
-- updates that disagree with the user's mark, since the last agreement or override.
CREATE TABLE concept_mastery (
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    concept_id bigint NOT NULL REFERENCES concepts (id) ON DELETE CASCADE,
    score double precision NOT NULL CHECK (score >= 0 AND score <= 1),
    contrary_rows integer NOT NULL DEFAULT 0 CHECK (contrary_rows >= 0),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, concept_id)
);
