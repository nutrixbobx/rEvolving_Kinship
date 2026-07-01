-- Clade notes: any signed-in user can attach a short note to a named
-- clade (e.g., "This is where our grandmother's stories start"). Notes
-- are surfaced in the Library and next to the clade in the tree's
-- Clade Browser. Idempotent.

CREATE TABLE IF NOT EXISTS clade_note (
    clade_note_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clade_name     TEXT NOT NULL,
    body           TEXT NOT NULL CHECK (length(body) > 0),
    contributor_id UUID REFERENCES contributor(contributor_id)
                       ON DELETE SET NULL,
    tree_name      TEXT,                -- optional: pin the note to a
                                        -- specific tree; NULL means
                                        -- global to the clade.
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_clade_note_clade
    ON clade_note (clade_name);
CREATE INDEX IF NOT EXISTS idx_clade_note_contributor
    ON clade_note (contributor_id);
