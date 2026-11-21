-- 0008: job kind and output. Existing rows get kind 'tag' from the default, so every job queued before this migration stays a tagging job.
-- output holds the per-kind result document; NULL until a job completes with one.

ALTER TABLE jobs
    ADD COLUMN kind text NOT NULL DEFAULT 'tag',
    ADD COLUMN output jsonb;

CREATE INDEX jobs_kind_status ON jobs (kind, status);
