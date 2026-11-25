-- 0021: course version and start rung. version counts the regenerations of a course (1 for
-- a new course). learning_rung is the dojo ladder stage a course starts at: 0, 1, 2 or 3
-- (the ladder is 0, 1, 5, 10, 30 days; stage 4 means learned, so it is never a start rung).
-- Existing rows take the defaults.

ALTER TABLE course
    ADD COLUMN version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    ADD COLUMN learning_rung integer NOT NULL DEFAULT 2 CHECK (learning_rung BETWEEN 0 AND 3);
