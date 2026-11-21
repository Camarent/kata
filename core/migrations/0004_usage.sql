-- 0004: per-user daily usage: spend and call count per day.
-- Money is integer micro-USD (no floats). Every row carries user_id ON DELETE CASCADE.

CREATE TABLE usage_daily (
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    day date NOT NULL,
    micro_usd bigint NOT NULL CHECK (micro_usd >= 0),
    calls integer NOT NULL,
    PRIMARY KEY (user_id, day)
);
