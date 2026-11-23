-- 0014: course titles unique per user after normalisation (lower case, trimmed, runs of
-- whitespace collapsed to one space). Step 1 renames the later duplicates; step 2 adds
-- the unique index. The index expression must match NORMAL_TITLE_SQL in
-- kata_core/trainer/store.py verbatim: a test checks it.

-- Step 1: the oldest course of each normalised title keeps its title. Each later
-- duplicate gets the lowest ' (k)' suffix (k >= 2) that no course of the user already
-- uses. Rows are visited in id order, so a rerun finds no duplicates and changes nothing.
DO $$
DECLARE
    r record;
    k integer;
    candidate text;
BEGIN
    FOR r IN SELECT id, user_id, title FROM course ORDER BY user_id, id LOOP
        IF EXISTS (
            SELECT 1 FROM course c
            WHERE c.user_id = r.user_id AND c.id < r.id
              AND lower(btrim(regexp_replace(c.title, '\s+', ' ', 'g')))
                = lower(btrim(regexp_replace(r.title, '\s+', ' ', 'g')))
        ) THEN
            k := 2;
            LOOP
                candidate := r.title || ' (' || k || ')';
                EXIT WHEN NOT EXISTS (
                    SELECT 1 FROM course c
                    WHERE c.user_id = r.user_id
                      AND lower(btrim(regexp_replace(c.title, '\s+', ' ', 'g')))
                        = lower(btrim(regexp_replace(candidate, '\s+', ' ', 'g')))
                );
                k := k + 1;
            END LOOP;
            UPDATE course SET title = candidate WHERE id = r.id;
        END IF;
    END LOOP;
END
$$;

-- Step 2: one normalised title per user. No WHERE clause: every row takes part.
CREATE UNIQUE INDEX course_user_id_title_norm_uidx
    ON course (user_id, lower(btrim(regexp_replace(title, '\s+', ' ', 'g'))));
