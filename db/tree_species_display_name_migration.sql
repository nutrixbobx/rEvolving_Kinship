-- Per-tree display-name override for tree_species.
-- Lets a tree's owner (or editor/admin) choose which of the species' names
-- shows up as that species' label in THIS tree, without flipping the global
-- preferred flag (which would change the label for every tree).
--
-- Idempotent. Run once in the Supabase SQL editor.

ALTER TABLE tree_species
    ADD COLUMN IF NOT EXISTS display_name_id UUID
    REFERENCES species_name(name_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS tree_species_display_name_idx
    ON tree_species (display_name_id)
    WHERE display_name_id IS NOT NULL;
