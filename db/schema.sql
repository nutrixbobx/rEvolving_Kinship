-- {r}Evolving Kinship master schema (Postgres / Supabase dialect)
--
-- You can paste this straight into the Supabase SQL editor for the online
-- version. The offline SQLite version builds the same table from db.py, so you
-- do not strictly need this file to run, but it is the canonical record of the
-- schema and it adds the data-governance views and constraints.

-- ---------------------------------------------------------------------------
-- Master table: every species request, across every tree, kept as history.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_species_requests (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tree_name       TEXT        NOT NULL,
    common_name     TEXT,
    scientific_name TEXT        NOT NULL,
    ncbi_taxid      INTEGER,            -- filled from scientific_name if blank
    domain          TEXT,               -- simple group: Animal/Plant/Fungi/...
    kingdom         TEXT,               -- the clade ranks below are filled
    phylum          TEXT,               -- automatically from the NCBI lineage
    class_          TEXT,               -- class and order are reserved words,
    order_          TEXT,               -- hence the trailing underscore
    family          TEXT,
    genus           TEXT,
    story           TEXT,               -- the story a person carries, honored
    submitted_by    TEXT,
    notes           TEXT,                -- free-form metadata kept with the row
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per species per tree. Case-insensitive on the scientific name so
-- "Canis latrans" and "canis latrans" are treated as the same kin.
CREATE UNIQUE INDEX IF NOT EXISTS uq_tree_species
    ON user_species_requests (tree_name, lower(scientific_name));

-- ---------------------------------------------------------------------------
-- Governance views: stable, named surfaces the website and BI tools read from,
-- so nobody queries the raw table directly.
-- ---------------------------------------------------------------------------

-- Count and reach of each tree.
CREATE OR REPLACE VIEW v_tree_summary AS
SELECT
    tree_name,
    count(*)                              AS species_count,
    count(*) FILTER (WHERE ncbi_taxid IS NOT NULL) AS resolved_count,
    min(created_at)                       AS first_request,
    max(created_at)                       AS latest_request
FROM user_species_requests
GROUP BY tree_name;

-- The public surface: only the columns that should leave the building.
CREATE OR REPLACE VIEW v_species_public AS
SELECT
    tree_name,
    common_name,
    scientific_name,
    ncbi_taxid,
    domain,
    kingdom,
    phylum,
    class_,
    order_,
    family,
    genus,
    notes
FROM user_species_requests
WHERE ncbi_taxid IS NOT NULL
ORDER BY tree_name, scientific_name;

-- ---------------------------------------------------------------------------
-- Supabase note: turn on row level security and add a read policy on the views
-- if you embed this in the website. Example, run after the table exists:
--
--   ALTER TABLE user_species_requests ENABLE ROW LEVEL SECURITY;
--   CREATE POLICY public_read ON user_species_requests
--       FOR SELECT USING (true);
-- ---------------------------------------------------------------------------
