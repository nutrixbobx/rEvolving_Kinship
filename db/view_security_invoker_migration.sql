-- Flip every public view from SECURITY DEFINER (the Postgres default for
-- older versions, which Supabase's linter flags) to SECURITY INVOKER, so
-- the views run with the caller's permissions and respect any RLS
-- policies on the underlying tables.
--
-- Idempotent — re-runs are no-ops.
--
-- Fixes Supabase database linter rule 0010_security_definer_view for:
--   v_legacy_species_rows, v_species_full, v_tree_summary,
--   v_recipe_index, v_pantheon_index, v_species_public

ALTER VIEW IF EXISTS public.v_legacy_species_rows SET (security_invoker = on);
ALTER VIEW IF EXISTS public.v_species_full        SET (security_invoker = on);
ALTER VIEW IF EXISTS public.v_tree_summary        SET (security_invoker = on);
ALTER VIEW IF EXISTS public.v_recipe_index        SET (security_invoker = on);
ALTER VIEW IF EXISTS public.v_pantheon_index      SET (security_invoker = on);
ALTER VIEW IF EXISTS public.v_species_public      SET (security_invoker = on);

-- Verify
SELECT
    schemaname,
    viewname,
    -- security_invoker is in the reloptions array; if missing or =off,
    -- the view is still DEFINER. Should show "{security_invoker=on}".
    (SELECT reloptions FROM pg_class
       WHERE relname = viewname AND relnamespace =
             (SELECT oid FROM pg_namespace WHERE nspname = schemaname)
    ) AS reloptions
FROM pg_views
WHERE schemaname = 'public'
  AND viewname IN ('v_legacy_species_rows', 'v_species_full',
                    'v_tree_summary', 'v_recipe_index',
                    'v_pantheon_index', 'v_species_public');
