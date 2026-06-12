-- {r}Evolving Kinship: nuke v1 + initialize v2
--
-- Run this in the Supabase SQL editor ONCE, after backing up anything you
-- want to keep (you said it's all test data, so nothing).
--
-- After this finishes, the kiosk + dashboard read/write the new 4NF+ schema.

-- 1. Drop the v1 table, indexes, and views.
DROP VIEW  IF EXISTS v_species_public CASCADE;
DROP VIEW  IF EXISTS v_tree_summary   CASCADE;
DROP TABLE IF EXISTS user_species_requests CASCADE;

-- 2. Drop any v2 tables and views (so re-runs are idempotent).
DROP VIEW  IF EXISTS v_species_full        CASCADE;
DROP VIEW  IF EXISTS v_tree_summary        CASCADE;
DROP VIEW  IF EXISTS v_recipe_index        CASCADE;
DROP VIEW  IF EXISTS v_pantheon_index      CASCADE;
DROP VIEW  IF EXISTS v_legacy_species_rows CASCADE;
DROP VIEW  IF EXISTS v_species_public      CASCADE;

DROP TABLE IF EXISTS edit_log            CASCADE;
DROP TABLE IF EXISTS cultural_connection CASCADE;
DROP TABLE IF EXISTS species_deity       CASCADE;
DROP TABLE IF EXISTS deity               CASCADE;
DROP TABLE IF EXISTS pantheon            CASCADE;
DROP TABLE IF EXISTS dish_species        CASCADE;
DROP TABLE IF EXISTS dish                CASCADE;
DROP TABLE IF EXISTS story               CASCADE;
DROP TABLE IF EXISTS tree_species        CASCADE;
DROP TABLE IF EXISTS tree                CASCADE;
DROP TABLE IF EXISTS species_name        CASCADE;
DROP TABLE IF EXISTS species_clade       CASCADE;
DROP TABLE IF EXISTS clade               CASCADE;
DROP TABLE IF EXISTS species             CASCADE;
DROP TABLE IF EXISTS contributor         CASCADE;

-- 3. Now run the v2 schema. (Paste the contents of db/schema_v2.sql below,
--    or run it as a separate script right after this one.)
