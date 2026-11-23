-- 0006: device event ingest and per-user message queue.
-- Every row carries user_id ON DELETE CASCADE. event_id is unique per user only,
-- so two users may send the same event_id.

CREATE TABLE event (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    device_id bigint,
    event_id text NOT NULL,
    type text NOT NULL,
    occurred_at timestamptz NOT NULL,
    received_at timestamptz NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}',
    UNIQUE (user_id, event_id)
);

CREATE TABLE message (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    kind text NOT NULL,
    body jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL,
    delivered_at timestamptz
);

-- Pending messages of one user, oldest first.
CREATE INDEX message_user_id_id_pending_idx ON message (user_id, id) WHERE delivered_at IS NULL;
