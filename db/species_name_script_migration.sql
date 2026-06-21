-- Add an optional `script` column to species_name so non-Romanic entries
-- can be tagged with their writing system (Devanagari, Arabic, Han, etc.).
-- Idempotent.

ALTER TABLE species_name
    ADD COLUMN IF NOT EXISTS script TEXT;

-- Optional check that the value is reasonably short. No fixed enum because
-- we want to allow new scripts without another migration.
