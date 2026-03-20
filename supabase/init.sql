-- NS Deferment Bot — initial schema
-- Run this in the Supabase SQL editor to initialise the database.
-- Safe to re-run: drops all existing tables first.

-- 1. Drop view and tables in dependency-safe order
DROP VIEW  IF EXISTS applications_full CASCADE;
DROP TABLE IF EXISTS documents         CASCADE;
DROP TABLE IF EXISTS audit_log         CASCADE;
DROP TABLE IF EXISTS applications      CASCADE;
DROP TABLE IF EXISTS users             CASCADE;

-- 2. Create tables

CREATE TABLE users (
    id                  TEXT PRIMARY KEY,          -- Telegram chat_id (string)
    name                TEXT NOT NULL,
    platoon             TEXT,
    role                TEXT NOT NULL DEFAULT 'user',  -- user | pc | oc | admin
    pc_can_submit_to_oc BOOLEAN NOT NULL DEFAULT FALSE,
    reg_step            TEXT,                      -- NULL = registered | 'name' | 'platoon'
    viewing_app_id      INTEGER,                   -- FK added after applications table exists
    review_step         TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE applications (
    id                  SERIAL PRIMARY KEY,
    applicant_id        TEXT NOT NULL REFERENCES users(id),
    type                TEXT,                      -- exchange | internship_credit | internship_non_credit | off_cycle | overseas_vacation | other
    type_detail         TEXT,                      -- free text for 'other'
    ippt_done           BOOLEAN,
    status              TEXT NOT NULL DEFAULT 'draft',
    current_step        TEXT NOT NULL DEFAULT 'type_select',
    revision_note       TEXT,
    reviewed_by         TEXT REFERENCES users(id),
    co_rejection_reason TEXT,
    submitted_at        TIMESTAMPTZ,
    resolved_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ON applications(applicant_id, status);
CREATE INDEX ON applications(status);

-- Deferred FK: users.viewing_app_id → applications.id
ALTER TABLE users
    ADD CONSTRAINT users_viewing_app_id_fkey
    FOREIGN KEY (viewing_app_id) REFERENCES applications(id);

CREATE TABLE documents (
    id              SERIAL PRIMARY KEY,
    application_id  INTEGER NOT NULL REFERENCES applications(id),
    doc_type        TEXT NOT NULL,                 -- matches keys in deferment_docs.yaml
    storage_path    TEXT NOT NULL,
    file_id         TEXT,                          -- Telegram file_id for resending
    mimetype        TEXT,
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE audit_log (
    id              SERIAL PRIMARY KEY,
    application_id  INTEGER REFERENCES applications(id),
    actor_id        TEXT NOT NULL,
    action          TEXT NOT NULL,
    note            TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. View: joins applications with applicant and reviewer user info
CREATE VIEW applications_full AS
SELECT
    a.*,
    u.name    AS applicant_name,
    u.platoon AS applicant_platoon,
    r.name    AS reviewer_name,
    r.platoon AS reviewer_platoon,
    r.role    AS reviewer_role
FROM applications a
JOIN users u ON a.applicant_id = u.id
LEFT JOIN users r ON a.reviewed_by = r.id;
