-- 0011: revisioned progress document per course (D8). The document is the client's progress
-- state; revision is the compare-and-swap counter. Removed with the course.
CREATE TABLE trainer_progress_doc (
    course_id bigint PRIMARY KEY REFERENCES course (id) ON DELETE CASCADE,
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    revision integer NOT NULL CHECK (revision >= 1),
    doc jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
