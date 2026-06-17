-- Backfill: reassign every existing community row to Maya admin.
--
-- Idempotent. Run as many times as you want. Side effects:
--
--   * tree.owner_id        --> Maya
--   * tree_species.added_by --> Maya  (where currently null OR anonymous)
--   * story.contributed_by, dish.contributed_by, species_name.contributed_by,
--     species_deity.contributed_by, cultural_connection.contributed_by --> Maya
--   * Deletes orphan contributor rows nobody references anymore (so the
--     library Team list isn't full of one-off guest stubs).
--
-- Why: in the early life of the app, the contributor column was either
-- 'anonymous' or the typed-in display name (which often defaulted to "maya"
-- on Maya's own machine but landed on visitor stubs for other adds). This
-- consolidates the early data under one owner so Maya can curate cleanly.
--
-- Run in the Supabase SQL editor, after db/auth_migration.sql has been
-- applied so Maya's contributor row has username='maya' and role='admin'.

BEGIN;

-- Resolve Maya's contributor_id once.
DO $$
DECLARE
    maya_id UUID;
BEGIN
    SELECT contributor_id INTO maya_id
    FROM contributor
    WHERE lower(username) = 'maya' AND role = 'admin'
    LIMIT 1;

    IF maya_id IS NULL THEN
        RAISE EXCEPTION 'Maya admin row not found. Apply db/auth_migration.sql first.';
    END IF;

    -- 1. Tree ownership
    UPDATE tree SET owner_id = maya_id
    WHERE owner_id IS DISTINCT FROM maya_id;

    -- 2. Tree-species link attribution
    UPDATE tree_species SET added_by = maya_id
    WHERE added_by IS DISTINCT FROM maya_id;

    -- 3. Community datapoints
    UPDATE story                SET contributed_by = maya_id
        WHERE contributed_by IS DISTINCT FROM maya_id;
    UPDATE dish                 SET contributed_by = maya_id
        WHERE contributed_by IS DISTINCT FROM maya_id;
    UPDATE species_name         SET contributed_by = maya_id
        WHERE contributed_by IS DISTINCT FROM maya_id;
    UPDATE species_deity        SET contributed_by = maya_id
        WHERE contributed_by IS DISTINCT FROM maya_id;
    UPDATE cultural_connection  SET contributed_by = maya_id
        WHERE contributed_by IS DISTINCT FROM maya_id;

    RAISE NOTICE 'Reassigned all attribution to Maya (%).', maya_id;
END $$;

-- 4. Garbage-collect contributor rows nobody points at any more.
--    Keep Maya, any contributor with a username (signed-in user, even if
--    their first contribution got reassigned), and the seed 'anonymous' row.
DELETE FROM contributor c
WHERE c.username IS NULL
  AND lower(c.display_name) <> 'anonymous'
  AND lower(c.display_name) <> 'maya'
  AND NOT EXISTS (SELECT 1 FROM tree                t  WHERE t.owner_id        = c.contributor_id)
  AND NOT EXISTS (SELECT 1 FROM tree_species       ts WHERE ts.added_by        = c.contributor_id)
  AND NOT EXISTS (SELECT 1 FROM story              s  WHERE s.contributed_by   = c.contributor_id)
  AND NOT EXISTS (SELECT 1 FROM dish               d  WHERE d.contributed_by   = c.contributor_id)
  AND NOT EXISTS (SELECT 1 FROM species_name       sn WHERE sn.contributed_by  = c.contributor_id)
  AND NOT EXISTS (SELECT 1 FROM species_deity      sd WHERE sd.contributed_by  = c.contributor_id)
  AND NOT EXISTS (SELECT 1 FROM cultural_connection cc WHERE cc.contributed_by = c.contributor_id);

COMMIT;

-- Verify
SELECT
    (SELECT count(*) FROM tree                WHERE owner_id        IS NOT NULL) AS trees_with_owner,
    (SELECT count(*) FROM tree_species        WHERE added_by        IS NOT NULL) AS species_with_added_by,
    (SELECT count(*) FROM story               WHERE contributed_by  IS NOT NULL) AS stories_attributed,
    (SELECT count(*) FROM dish                WHERE contributed_by  IS NOT NULL) AS dishes_attributed,
    (SELECT count(*) FROM species_name        WHERE contributed_by  IS NOT NULL) AS names_attributed,
    (SELECT count(*) FROM cultural_connection WHERE contributed_by  IS NOT NULL) AS cultural_attributed,
    (SELECT count(*) FROM contributor) AS contributors_remaining;
