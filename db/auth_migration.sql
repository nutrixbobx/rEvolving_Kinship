-- Phase 1 auth migration: extend contributor with username, password_hash,
-- bio, avatar_url, last_login_at. Idempotent — safe to run any number of times
-- against the existing v2 schema.
--
-- Run this ONCE in the Supabase SQL editor before deploying the new auth code.

ALTER TABLE contributor
    ADD COLUMN IF NOT EXISTS username       TEXT,
    ADD COLUMN IF NOT EXISTS password_hash  TEXT,
    ADD COLUMN IF NOT EXISTS bio            TEXT,
    ADD COLUMN IF NOT EXISTS avatar_url     TEXT,
    ADD COLUMN IF NOT EXISTS last_login_at  TIMESTAMPTZ;

-- Case-insensitive unique constraint on username. NULLs allowed (guests).
CREATE UNIQUE INDEX IF NOT EXISTS contributor_username_uq
    ON contributor (lower(username))
    WHERE username IS NOT NULL;

-- Make sure the role constraint allows our three roles.
ALTER TABLE contributor DROP CONSTRAINT IF EXISTS contributor_role_check;
ALTER TABLE contributor
    ADD CONSTRAINT contributor_role_check
    CHECK (role IN ('visitor', 'editor', 'admin'));

-- Promote any existing Maya-named contributor row to admin + assign username.
UPDATE contributor
SET username = 'maya', role = 'admin'
WHERE lower(display_name) IN ('maya', 'maya nutria')
  AND (username IS NULL OR role <> 'admin');

-- If no Maya row exists at all, create one. Password is empty until first
-- login through the app, when the auth module hashes ADMIN_PASSWORD into it.
INSERT INTO contributor (display_name, username, role, email, bio)
SELECT 'Maya', 'maya', 'admin', 'maya@shared-rivers.org',
       'Founder of Shared Rivers. Built {r}Evolving Kinship.'
WHERE NOT EXISTS (
    SELECT 1 FROM contributor WHERE lower(username) = 'maya'
);
