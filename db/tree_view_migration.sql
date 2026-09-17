-- Saved arrangements for the interactive tree.
--
-- Two tiers, distinguished by contributor_id:
--   contributor_id IS NULL  -> the shared view for this tree. One per tree.
--                              Only admins and editors write it; everyone
--                              sees it when they have no view of their own.
--   contributor_id NOT NULL -> that person's own view of this tree. One per
--                              (tree, person). It wins over the shared one.
--
-- Guests and signed-out visitors keep using browser localStorage, so they can
-- still arrange and keep a tree without an account and without touching
-- anyone else's view.
--
-- view_json holds the canvas state (layout, which clade names are ticked,
-- sizes, toggles, focused clade, chosen photo and name per species, and node
-- positions when they fit). Stored as text so the shape can evolve without a
-- migration; the reader tolerates unknown keys.
--
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS tree_view (
    view_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tree_id        uuid NOT NULL REFERENCES tree(tree_id) ON DELETE CASCADE,
    contributor_id uuid NULL REFERENCES contributor(contributor_id) ON DELETE CASCADE,
    view_json      text NOT NULL,
    updated_at     timestamptz NOT NULL DEFAULT now(),
    updated_by     uuid NULL REFERENCES contributor(contributor_id) ON DELETE SET NULL
);

-- One shared view per tree (contributor_id IS NULL).
CREATE UNIQUE INDEX IF NOT EXISTS tree_view_shared_uniq
    ON tree_view (tree_id)
    WHERE contributor_id IS NULL;

-- One personal view per person per tree.
CREATE UNIQUE INDEX IF NOT EXISTS tree_view_personal_uniq
    ON tree_view (tree_id, contributor_id)
    WHERE contributor_id IS NOT NULL;

-- Lookup path used on every dashboard load.
CREATE INDEX IF NOT EXISTS tree_view_tree_idx ON tree_view (tree_id);
