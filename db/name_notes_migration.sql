-- Name notes: optional freetext context for a species_name entry.
-- Used when a contributor wants to explain what a name means, where
-- it comes from, or in what context it's used (ceremonial, culinary,
-- regional slang, etc.). Idempotent.
--
-- Self-defensive: skips silently if species_name isn't in the current
-- schema, so a wrong-project run raises a clear notice instead of an
-- ERROR. Once on the right project, re-run to actually apply.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'species_name'
          AND table_schema = current_schema()
    ) THEN
        ALTER TABLE species_name
            ADD COLUMN IF NOT EXISTS notes TEXT;
        RAISE NOTICE 'species_name.notes column ensured.';
    ELSE
        RAISE NOTICE
            'species_name table not found in schema %. '
            'Check the Supabase project + schema before rerunning.',
            current_schema();
    END IF;
END $$;
