-- Forgot-password support. Idempotent.
ALTER TABLE contributor
    ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS last_reset_at        TIMESTAMPTZ;

-- Tracking pending resets so Maya can see who requested + when in the admin panel.
CREATE TABLE IF NOT EXISTS pending_reset (
    reset_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contributor_id  UUID NOT NULL REFERENCES contributor(contributor_id) ON DELETE CASCADE,
    requested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS pending_reset_contributor_idx
    ON pending_reset (contributor_id);
