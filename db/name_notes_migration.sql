-- Name notes: optional freetext context for a species_name entry.
-- Used when a contributor wants to explain what a name means, where
-- it comes from, or in what context it's used (ceremonial, culinary,
-- regional slang, etc.). Idempotent.

ALTER TABLE species_name
    ADD COLUMN IF NOT EXISTS notes TEXT;
