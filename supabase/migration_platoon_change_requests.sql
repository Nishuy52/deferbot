-- Migration: platoon change requests
-- Apply this to an existing Supabase DB that already holds data (init.sql drops
-- everything, so it cannot be re-run in production). Safe to run once.

CREATE TABLE IF NOT EXISTS platoon_change_requests (
    id            SERIAL PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users(id),
    from_platoon  TEXT,
    to_platoon    TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected
    decided_by    TEXT REFERENCES users(id),
    decision_note TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS platoon_change_requests_status_to_platoon_idx
    ON platoon_change_requests(status, to_platoon);

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS viewing_change_id INTEGER REFERENCES platoon_change_requests(id);

CREATE OR REPLACE VIEW platoon_change_requests_full AS
SELECT
    p.*,
    u.name AS requester_name
FROM platoon_change_requests p
JOIN users u ON p.user_id = u.id;
