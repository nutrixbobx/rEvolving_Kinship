-- Theme skins: per-user palette selection.
-- Column stores the theme slug (e.g. "crimson_amber", "river_sea",
-- "warm_forest"). NULL means "use the default". Idempotent.

ALTER TABLE contributor
    ADD COLUMN IF NOT EXISTS theme TEXT;

-- Not indexed; only read per session on sign-in.
