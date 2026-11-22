-- 0013: planning tracks, weekly budget, decision points (D11, D12). Every row is
-- user-scoped; children cascade with their track or user.

-- A learning track with a deadline. Only active tracks are allocated.
CREATE TABLE track (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name text NOT NULL,
    deadline date NOT NULL,
    priority integer NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'dropped')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Ordered items of a track. module_id is kept without a foreign key: the syllabus
-- tables (0012) own it, and a track item may outlive a removed module.
CREATE TABLE track_item (
    track_id bigint NOT NULL REFERENCES track (id) ON DELETE CASCADE,
    position integer NOT NULL CHECK (position >= 0),
    module_id bigint,
    label text NOT NULL,
    action text NOT NULL,
    minutes integer NOT NULL CHECK (minutes >= 0),
    PRIMARY KEY (track_id, position)
);

-- One weekly study budget per user.
CREATE TABLE planning_budget (
    user_id bigint PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
    minutes_per_week integer NOT NULL CHECK (minutes_per_week >= 0),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- A checkpoint after item `after_position` of a track. While open, later items are
-- not allocated. choice is set exactly when the point is decided. target_track_id
-- is nulled when the target track is deleted, so a decided switch may lack it;
-- set_decided requires a target when it records a switch.
CREATE TABLE decision_point (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    track_id bigint NOT NULL REFERENCES track (id) ON DELETE CASCADE,
    after_position integer NOT NULL CHECK (after_position >= 0),
    due_on date NOT NULL,
    status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'decided')),
    choice text CHECK (choice IN ('continue', 'switch', 'drop')),
    target_track_id bigint REFERENCES track (id) ON DELETE SET NULL,
    decided_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT decision_point_choice_matches_status
        CHECK ((status = 'open') = (choice IS NULL)),
    CONSTRAINT decision_point_decided_at_matches_status
        CHECK ((status = 'open') = (decided_at IS NULL))
);
