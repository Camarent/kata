-- 0025: exam mode data. Additive only: three new tables, no existing table is altered or dropped.
-- exam_mode_session: one row per exam-mode run; at most one open (ended_at NULL) per user.
-- exam_mode_signal: one row per captured question; position is unique within a session.
-- exam_mode_proposal_decision: the owner's answer per proposed concept, idempotent per key.
-- No column holds question text: names are capped and sanitised by the caller.
--
-- Rollback (reverse SQL, FK order; no other table changes):
--   DROP TABLE exam_mode_proposal_decision;
--   DROP TABLE exam_mode_signal;
--   DROP TABLE exam_mode_session;

CREATE TABLE exam_mode_session (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    started_at timestamptz NOT NULL DEFAULT now(),
    last_activity_at timestamptz NOT NULL DEFAULT now(),
    ended_at timestamptz NULL,
    end_reason text NULL CHECK (end_reason IN ('button', 'idle')),
    site_host text NOT NULL,
    result_date date NULL,
    passed boolean NULL,
    score text NULL,
    picked_topic_ids bigint[] NOT NULL DEFAULT '{}'
);

CREATE UNIQUE INDEX exam_mode_one_open_session_per_user
    ON exam_mode_session (user_id) WHERE ended_at IS NULL;

CREATE TABLE exam_mode_signal (
    id bigserial PRIMARY KEY,
    session_id bigint NOT NULL REFERENCES exam_mode_session (id) ON DELETE CASCADE,
    position integer NOT NULL,
    status text NOT NULL CHECK (status IN ('pending', 'analysed', 'failed', 'skipped')),
    topic_id bigint NULL,
    proposed_topic text NULL,
    concept_ids bigint[] NOT NULL DEFAULT '{}',
    proposed_names text[] NOT NULL DEFAULT '{}',
    outcome text NOT NULL DEFAULT 'unknown'
        CHECK (outcome IN ('likely_right', 'likely_wrong', 'unsure', 'unknown')),
    created_at timestamptz NOT NULL DEFAULT now(),
    analysed_at timestamptz NULL,
    UNIQUE (session_id, position)
);

CREATE TABLE exam_mode_proposal_decision (
    session_id bigint NOT NULL REFERENCES exam_mode_session (id) ON DELETE CASCADE,
    proposal_key text NOT NULL,
    decision text NOT NULL CHECK (decision IN ('confirmed', 'dismissed')),
    concept_id bigint NULL,
    decided_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (session_id, proposal_key)
);
