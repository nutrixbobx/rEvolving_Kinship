-- Server-side session table for the bulletproof remember-me.
-- The cookie holds only an opaque random session_id; the actual user is
-- looked up here. 30-day default expiry, deletable on sign-out.
-- Idempotent.

CREATE TABLE IF NOT EXISTS auth_session (
    session_id     UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    contributor_id UUID         NOT NULL
                                REFERENCES contributor(contributor_id)
                                ON DELETE CASCADE,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_seen_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    expires_at     TIMESTAMPTZ  NOT NULL DEFAULT now() + INTERVAL '30 days',
    user_agent     TEXT
);

CREATE INDEX IF NOT EXISTS auth_session_contributor_idx
    ON auth_session (contributor_id);
CREATE INDEX IF NOT EXISTS auth_session_expires_idx
    ON auth_session (expires_at);
