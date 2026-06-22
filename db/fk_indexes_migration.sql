-- Add missing FK indexes. Foreign-key columns without a backing index
-- cause sequential scans on every join, and the read_tree / list_*
-- queries are join-heavy. CREATE INDEX IF NOT EXISTS is idempotent.
--
-- Eleven indexes total. Each is small; the table-side cost is one extra
-- B-tree per FK. The benefit is constant-time lookups for "all rows
-- where contributed_by = X" (Profile activity tabs), "all rows where
-- deity_id = Y" (species_deity links), etc.

CREATE INDEX IF NOT EXISTS species_name_contributed_by_idx
    ON species_name (contributed_by);

CREATE INDEX IF NOT EXISTS tree_owner_idx
    ON tree (owner_id);

CREATE INDEX IF NOT EXISTS tree_species_added_by_idx
    ON tree_species (added_by);

CREATE INDEX IF NOT EXISTS story_contributed_by_idx
    ON story (contributed_by);

CREATE INDEX IF NOT EXISTS dish_contributed_by_idx
    ON dish (contributed_by);

CREATE INDEX IF NOT EXISTS dish_species_species_idx
    ON dish_species (species_id);

CREATE INDEX IF NOT EXISTS deity_pantheon_idx
    ON deity (pantheon_id);

CREATE INDEX IF NOT EXISTS species_deity_deity_idx
    ON species_deity (deity_id);

CREATE INDEX IF NOT EXISTS species_deity_contributed_by_idx
    ON species_deity (contributed_by);

CREATE INDEX IF NOT EXISTS cultural_connection_contributed_by_idx
    ON cultural_connection (contributed_by);

CREATE INDEX IF NOT EXISTS edit_log_contributor_idx
    ON edit_log (contributor_id);

CREATE INDEX IF NOT EXISTS edit_log_approved_by_idx
    ON edit_log (approved_by);
