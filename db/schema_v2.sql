-- {r}Evolving Kinship master schema, version 2 (4NF+, Postgres / Supabase)
--
-- This is the community-revisable kinship database. NCBI taxonomy stays read
-- only on the file system (taxa.sqlite from GitHub Releases). This schema
-- holds the *community* layer that joins to NCBI by ncbi_taxid and adds the
-- multilingual naming, the per-tree stories, the recipes that braid species
-- into dishes, the pantheons that braid species into mythologies, and the
-- audit trail that records who added what.
--
-- All identifiers are surrogate UUIDs (Supabase-friendly). Foreign keys
-- cascade on delete inside the community layer. NCBI references (ncbi_taxid)
-- are stored as plain integers, not foreign keys, because NCBI lives in a
-- separate read-only file system.
--
-- Normalization target: fourth normal form throughout, with a few 5NF-flavored
-- join tables where the conceptual seams are clean (species_clade,
-- tree_species, dish_species, species_deity).


-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- for gen_random_uuid()


-- ---------------------------------------------------------------------------
-- 1. Contributors (anyone who writes data)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS contributor (
    contributor_id   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name     TEXT         NOT NULL,
    pronouns         TEXT,
    home_watershed   TEXT,
    email            TEXT         UNIQUE,
    role             TEXT         NOT NULL DEFAULT 'visitor'
                                  CHECK (role IN ('visitor','editor','admin')),
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Seed an anonymous contributor so unsigned-in kiosk requests have a home.
INSERT INTO contributor (display_name, role)
    VALUES ('anonymous', 'visitor')
    ON CONFLICT DO NOTHING;


-- ---------------------------------------------------------------------------
-- 2. Species (one row per real species, deduped across trees)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS species (
    species_id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    ncbi_taxid                INTEGER      NOT NULL UNIQUE,
    canonical_scientific_name TEXT         NOT NULL,
    rank                      TEXT,        -- 'species', 'subspecies', ...
    created_at                TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS species_sci_lower_idx
    ON species (lower(canonical_scientific_name));


-- ---------------------------------------------------------------------------
-- 3. Clades (taxonomic ancestry, canonical not per-species)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS clade (
    clade_id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    ncbi_taxid        INTEGER      NOT NULL UNIQUE,
    name              TEXT         NOT NULL,
    rank              TEXT,        -- 'kingdom','phylum','class','order','family','genus',...
    parent_clade_id   UUID         REFERENCES clade(clade_id) ON DELETE SET NULL,
    divergence_mya    NUMERIC,     -- nullable, only for dated clades
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS clade_name_lower_idx ON clade (lower(name));
CREATE INDEX IF NOT EXISTS clade_parent_idx     ON clade (parent_clade_id);

CREATE TABLE IF NOT EXISTS species_clade (
    species_id  UUID NOT NULL REFERENCES species(species_id) ON DELETE CASCADE,
    clade_id    UUID NOT NULL REFERENCES clade(clade_id)     ON DELETE CASCADE,
    PRIMARY KEY (species_id, clade_id)
);
CREATE INDEX IF NOT EXISTS species_clade_clade_idx ON species_clade (clade_id);


-- ---------------------------------------------------------------------------
-- 4. Multi-lingual / multi-cultural names
--
-- One row per (species, name, language, category). A species can carry many
-- common names in many languages without duplicating the species row.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS species_name (
    name_id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    species_id       UUID         NOT NULL REFERENCES species(species_id)
                                  ON DELETE CASCADE,
    name_text        TEXT         NOT NULL,
    language_code    TEXT         NOT NULL DEFAULT 'en',  -- ISO 639-1
    name_category    TEXT         NOT NULL DEFAULT 'common'
                                  CHECK (name_category IN
                                  ('common','folk','ceremonial','scientific','synonym')),
    region_code      TEXT,        -- ISO 3166, optional ('US-GA', 'AM')
    source           TEXT         NOT NULL DEFAULT 'community',
                                  -- 'ncbi','inaturalist','wikipedia','community','contributor:xxx'
    is_preferred     BOOLEAN      NOT NULL DEFAULT false,
    contributed_by   UUID         REFERENCES contributor(contributor_id)
                                  ON DELETE SET NULL,
    contributed_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (species_id, name_text, language_code, name_category)
);
CREATE INDEX IF NOT EXISTS species_name_species_idx ON species_name (species_id);
CREATE INDEX IF NOT EXISTS species_name_lang_idx    ON species_name (language_code);


-- ---------------------------------------------------------------------------
-- 5. Trees (community-built selections of species)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tree (
    tree_id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    name             TEXT         NOT NULL,    -- editable, not the key
    slug             TEXT         NOT NULL UNIQUE,  -- filesystem-safe, generated
    owner_id         UUID         REFERENCES contributor(contributor_id)
                                  ON DELETE SET NULL,
    title_template   TEXT         NOT NULL DEFAULT '{owner}''s kinship looks like:',
    is_public        BOOLEAN      NOT NULL DEFAULT true,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS tree_name_lower_idx ON tree (lower(name));

CREATE TABLE IF NOT EXISTS tree_species (
    tree_id          UUID         NOT NULL REFERENCES tree(tree_id)
                                  ON DELETE CASCADE,
    species_id       UUID         NOT NULL REFERENCES species(species_id)
                                  ON DELETE RESTRICT,
    note             TEXT,        -- a per-this-tree note about this species
    added_by         UUID         REFERENCES contributor(contributor_id)
                                  ON DELETE SET NULL,
    added_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (tree_id, species_id)
);
CREATE INDEX IF NOT EXISTS tree_species_species_idx ON tree_species (species_id);


-- ---------------------------------------------------------------------------
-- 6. Stories (long-form community contributions per species or per tree)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS story (
    story_id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    species_id       UUID         REFERENCES species(species_id) ON DELETE CASCADE,
    tree_id          UUID         REFERENCES tree(tree_id) ON DELETE CASCADE,
    title            TEXT,
    body_text        TEXT         NOT NULL,
    language_code    TEXT         NOT NULL DEFAULT 'en',
    region_code      TEXT,
    is_published     BOOLEAN      NOT NULL DEFAULT true,
    contributed_by   UUID         REFERENCES contributor(contributor_id)
                                  ON DELETE SET NULL,
    contributed_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CHECK (species_id IS NOT NULL OR tree_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS story_species_idx ON story (species_id);
CREATE INDEX IF NOT EXISTS story_tree_idx    ON story (tree_id);


-- ---------------------------------------------------------------------------
-- 7. Dishes (recipes that braid species into food)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dish (
    dish_id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    name             TEXT         NOT NULL,
    origin_region    TEXT,        -- 'Armenia', 'Atlanta GA', 'Yucatán'
    cuisine          TEXT,        -- 'Armenian', 'Lowcountry', 'Mayan'
    description      TEXT,
    contributed_by   UUID         REFERENCES contributor(contributor_id)
                                  ON DELETE SET NULL,
    contributed_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS dish_name_lower_idx ON dish (lower(name));

CREATE TABLE IF NOT EXISTS dish_species (
    dish_id          UUID         NOT NULL REFERENCES dish(dish_id)
                                  ON DELETE CASCADE,
    species_id       UUID         NOT NULL REFERENCES species(species_id)
                                  ON DELETE RESTRICT,
    role             TEXT         NOT NULL DEFAULT 'ingredient',
                                  -- 'main','protein','wrapping','flavoring','herb','garnish'
    quantity_note    TEXT,        -- 'a cup', 'two leaves', 'pinch'
    PRIMARY KEY (dish_id, species_id, role)
);


-- ---------------------------------------------------------------------------
-- 8. Pantheons + deities (religious / mythological associations)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pantheon (
    pantheon_id      UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    name             TEXT         NOT NULL UNIQUE,
    region           TEXT,
    tradition_type   TEXT         NOT NULL DEFAULT 'mythological'
                                  CHECK (tradition_type IN
                                  ('religious','mythological','folk','animist'))
);

CREATE TABLE IF NOT EXISTS deity (
    deity_id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    pantheon_id      UUID         NOT NULL REFERENCES pantheon(pantheon_id)
                                  ON DELETE CASCADE,
    name             TEXT         NOT NULL,
    aliases          TEXT[],      -- alternate names
    domain           TEXT,        -- 'water', 'hunt', 'fertility', 'death'
    UNIQUE (pantheon_id, name)
);

CREATE TABLE IF NOT EXISTS species_deity (
    species_id       UUID         NOT NULL REFERENCES species(species_id)
                                  ON DELETE CASCADE,
    deity_id         UUID         NOT NULL REFERENCES deity(deity_id)
                                  ON DELETE CASCADE,
    relationship     TEXT         NOT NULL DEFAULT 'sacred_to',
                                  -- 'sacred_to','avatar_of','offering','companion','symbol_of'
    note             TEXT,
    contributed_by   UUID         REFERENCES contributor(contributor_id)
                                  ON DELETE SET NULL,
    PRIMARY KEY (species_id, deity_id, relationship)
);


-- ---------------------------------------------------------------------------
-- 9. Cultural connections (catch-all for non-deity associations)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cultural_connection (
    connection_id      UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    species_id         UUID         NOT NULL REFERENCES species(species_id)
                                    ON DELETE CASCADE,
    culture            TEXT         NOT NULL,   -- 'Cherokee', 'Armenian', 'Yoruba'
    significance_type  TEXT,                    -- 'totem','medicinal','ceremonial','foundational'
    description        TEXT,
    source             TEXT,                    -- citation or url
    contributed_by     UUID         REFERENCES contributor(contributor_id)
                                    ON DELETE SET NULL,
    contributed_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS cultural_species_idx ON cultural_connection (species_id);


-- ---------------------------------------------------------------------------
-- 10. Audit log (community edits leave a trail)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS edit_log (
    edit_id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    contributor_id   UUID         REFERENCES contributor(contributor_id)
                                  ON DELETE SET NULL,
    table_affected   TEXT         NOT NULL,
    row_id_affected  UUID,
    field_changed    TEXT,
    old_value        TEXT,
    new_value        TEXT,
    edit_timestamp   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    approved_by      UUID         REFERENCES contributor(contributor_id)
                                  ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS edit_log_table_idx     ON edit_log (table_affected);
CREATE INDEX IF NOT EXISTS edit_log_timestamp_idx ON edit_log (edit_timestamp DESC);


-- ---------------------------------------------------------------------------
-- VIEWS: the public surface that the app reads
-- ---------------------------------------------------------------------------

-- A flat species projection that BI tools and the website read instead of
-- joining a dozen tables themselves. Names rolled into a JSON array.
CREATE OR REPLACE VIEW v_species_full WITH (security_invoker = on) AS
SELECT
    s.species_id,
    s.ncbi_taxid,
    s.canonical_scientific_name AS scientific_name,
    s.rank,
    COALESCE(
        (SELECT jsonb_agg(jsonb_build_object(
            'name', sn.name_text,
            'language', sn.language_code,
            'category', sn.name_category,
            'preferred', sn.is_preferred))
         FROM species_name sn WHERE sn.species_id = s.species_id),
        '[]'::jsonb
    ) AS names,
    COALESCE(
        (SELECT jsonb_agg(jsonb_build_object(
            'rank', c.rank, 'name', c.name, 'mya', c.divergence_mya)
            ORDER BY c.divergence_mya DESC NULLS LAST)
         FROM species_clade sc JOIN clade c ON c.clade_id = sc.clade_id
         WHERE sc.species_id = s.species_id),
        '[]'::jsonb
    ) AS ancestors,
    (SELECT count(*) FROM story st WHERE st.species_id = s.species_id) AS stories_count,
    (SELECT count(DISTINCT ds.dish_id) FROM dish_species ds
        WHERE ds.species_id = s.species_id) AS dishes_count,
    (SELECT count(*) FROM species_deity sd WHERE sd.species_id = s.species_id) AS deities_count
FROM species s
ORDER BY s.canonical_scientific_name;

-- Tree summary (what the dashboard lists).
CREATE OR REPLACE VIEW v_tree_summary WITH (security_invoker = on) AS
SELECT
    t.tree_id,
    t.name,
    t.slug,
    t.is_public,
    co.display_name AS owner,
    (SELECT count(*) FROM tree_species ts WHERE ts.tree_id = t.tree_id) AS species_count,
    (SELECT count(DISTINCT sn.language_code)
        FROM tree_species ts
        JOIN species_name sn ON sn.species_id = ts.species_id
        WHERE ts.tree_id = t.tree_id) AS languages_count,
    t.created_at
FROM tree t
LEFT JOIN contributor co ON co.contributor_id = t.owner_id
ORDER BY t.created_at DESC;

-- Recipe index, for the dishes section of the future site.
CREATE OR REPLACE VIEW v_recipe_index WITH (security_invoker = on) AS
SELECT
    d.dish_id,
    d.name,
    d.origin_region,
    d.cuisine,
    COALESCE(
        (SELECT jsonb_agg(jsonb_build_object(
            'scientific_name', s.canonical_scientific_name,
            'role', ds.role,
            'quantity', ds.quantity_note))
         FROM dish_species ds JOIN species s ON s.species_id = ds.species_id
         WHERE ds.dish_id = d.dish_id),
        '[]'::jsonb
    ) AS ingredients
FROM dish d
ORDER BY d.name;

-- Pantheon index, for browsing mythological / religious connections.
CREATE OR REPLACE VIEW v_pantheon_index WITH (security_invoker = on) AS
SELECT
    p.pantheon_id,
    p.name AS pantheon_name,
    p.region,
    p.tradition_type,
    (SELECT count(*) FROM deity de WHERE de.pantheon_id = p.pantheon_id) AS deities_count,
    (SELECT count(DISTINCT sd.species_id)
        FROM deity de JOIN species_deity sd ON sd.deity_id = de.deity_id
        WHERE de.pantheon_id = p.pantheon_id) AS species_count
FROM pantheon p
ORDER BY p.name;

-- A back-compat view shaped like the OLD user_species_requests table, so the
-- existing dashboard table-listing code keeps working while we refactor
-- consumers tree-by-tree. Read only; writes go through the new API.
CREATE OR REPLACE VIEW v_legacy_species_rows WITH (security_invoker = on) AS
SELECT
    t.name AS tree_name,
    (SELECT sn.name_text FROM species_name sn
        WHERE sn.species_id = s.species_id
          AND sn.language_code = 'en'
          AND sn.name_category = 'common'
        ORDER BY sn.is_preferred DESC, sn.contributed_at LIMIT 1) AS common_name,
    s.canonical_scientific_name AS scientific_name,
    s.ncbi_taxid,
    (SELECT c.name FROM species_clade sc JOIN clade c ON c.clade_id = sc.clade_id
        WHERE sc.species_id = s.species_id AND c.rank = 'kingdom' LIMIT 1) AS kingdom,
    (SELECT c.name FROM species_clade sc JOIN clade c ON c.clade_id = sc.clade_id
        WHERE sc.species_id = s.species_id AND c.rank = 'phylum' LIMIT 1) AS phylum,
    (SELECT c.name FROM species_clade sc JOIN clade c ON c.clade_id = sc.clade_id
        WHERE sc.species_id = s.species_id AND c.rank = 'class' LIMIT 1) AS class_,
    (SELECT c.name FROM species_clade sc JOIN clade c ON c.clade_id = sc.clade_id
        WHERE sc.species_id = s.species_id AND c.rank = 'order' LIMIT 1) AS order_,
    (SELECT c.name FROM species_clade sc JOIN clade c ON c.clade_id = sc.clade_id
        WHERE sc.species_id = s.species_id AND c.rank = 'family' LIMIT 1) AS family,
    (SELECT c.name FROM species_clade sc JOIN clade c ON c.clade_id = sc.clade_id
        WHERE sc.species_id = s.species_id AND c.rank = 'genus' LIMIT 1) AS genus,
    ts.note AS notes,
    co.display_name AS submitted_by,
    ts.added_at AS created_at
FROM tree_species ts
JOIN tree t      ON t.tree_id = ts.tree_id
JOIN species s   ON s.species_id = ts.species_id
LEFT JOIN contributor co ON co.contributor_id = ts.added_by
ORDER BY t.name, s.canonical_scientific_name;

-- A clean public surface for embedding (already mirrors v_species_public from v1).
CREATE OR REPLACE VIEW v_species_public WITH (security_invoker = on) AS
SELECT
    tree_name, common_name, scientific_name, ncbi_taxid,
    kingdom, phylum, class_, order_, family, genus, notes
FROM v_legacy_species_rows;


-- ---------------------------------------------------------------------------
-- Row Level Security (Supabase note)
--
-- Once you wire Supabase auth into the dashboard, you'll want to flip these
-- on. For now everything stays open so the deployed app can read and write
-- with the service role connection string.
--
-- ALTER TABLE tree                ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE tree_species        ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE species_name        ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE story               ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE dish                ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE cultural_connection ENABLE ROW LEVEL SECURITY;
--
-- Then add policies like:
-- CREATE POLICY tree_public_read ON tree FOR SELECT USING (is_public = true);
-- CREATE POLICY tree_owner_write ON tree FOR UPDATE USING (owner_id = auth.uid());
-- CREATE POLICY name_editor_write ON species_name FOR INSERT WITH CHECK (
--     EXISTS (SELECT 1 FROM contributor WHERE contributor_id = auth.uid()
--                                         AND role IN ('editor','admin')));
-- ---------------------------------------------------------------------------
