-- 0022: quiz sources and questions, exam results. Additive only: no existing table is
-- altered or dropped.
-- quiz_source: one fetched text per (url, sha256). tier 1 is a curated source, tier 2 a
-- user-added domain. licence is recorded with every source and is never empty by intent.
-- quiz_question: questions generated from a source; answer_index points into choices.
-- exam_result: one exam taken on the dojo or on a page; status gates the Known step.
-- exam_result_concept: per-concept outcome of one exam; confirmed is set by the user.

CREATE TABLE quiz_source (
    id bigserial PRIMARY KEY,
    url text NOT NULL,
    tier integer NOT NULL CHECK (tier IN (1, 2)),
    licence text NOT NULL,
    revision text,
    text_sha256 text,
    fetched_at timestamptz,
    UNIQUE (url, text_sha256)
);

CREATE TABLE quiz_question (
    id bigserial PRIMARY KEY,
    source_id bigint NOT NULL REFERENCES quiz_source (id) ON DELETE CASCADE,
    question text NOT NULL,
    choices jsonb NOT NULL CHECK (jsonb_typeof(choices) = 'array'),
    answer_index integer NOT NULL,
    quote text,
    UNIQUE (source_id, question),
    CHECK (
        CASE
            WHEN jsonb_typeof(choices) = 'array'
                THEN answer_index >= 0 AND answer_index < jsonb_array_length(choices)
            ELSE false
        END
    )
);

CREATE TABLE exam_result (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    origin text NOT NULL CHECK (origin IN ('dojo', 'page')),
    taken_at timestamptz NOT NULL DEFAULT now(),
    passed boolean,
    score numeric,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'confirmed', 'dismissed'))
);

CREATE TABLE exam_result_concept (
    result_id bigint NOT NULL REFERENCES exam_result (id) ON DELETE CASCADE,
    concept_id bigint NOT NULL REFERENCES concepts (id) ON DELETE CASCADE,
    correct boolean NOT NULL,
    confirmed boolean NOT NULL DEFAULT false,
    PRIMARY KEY (result_id, concept_id)
);
