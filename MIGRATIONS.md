# Supabase migrations — run order and status

The schema in `db/schema_v2.sql` is the baseline. Every file below extends it
with new columns, tables, or data. They are all **idempotent** (use
`IF NOT EXISTS` and `IF EXISTS`) so re-running any of them is a safe no-op
when the change is already applied.

When deploying to a fresh Supabase project, paste each file's contents
into the **Supabase SQL Editor** and run, in this order:

| # | File                                          | What it does                                                                                                  |
|---|-----------------------------------------------|---------------------------------------------------------------------------------------------------------------|
| 0 | `db/wipe_and_init.sql` (fresh setups only)    | Drops v1 + reinstalls v2 schema. Skip if you already have v2 data.                                            |
| 0a| `db/schema_v2.sql`                            | Baseline 4NF+ schema. Re-run is safe.                                                                         |
| 1 | `db/auth_migration.sql`                       | Adds username, password_hash, bio, avatar_url, last_login_at to `contributor`; ensures Maya admin row.        |
| 2 | `db/forgot_password_migration.sql`            | Adds must_change_password, last_reset_at columns + `pending_reset` table.                                     |
| 3 | `db/tree_species_display_name_migration.sql`  | Adds display_name_id column to `tree_species` for per-tree common name overrides.                             |
| 4 | `db/follow_favorite_migration.sql`            | Creates `user_follow` and `tree_favorite` join tables for follow/favorite features.                           |
| 5 | `db/iso639_3_migration.sql`                   | Upgrades existing 2-letter language codes (en, hy, ...) to uppercase 3-letter ISO 639-3 (ENG, HYE, ...).      |
| 6 | `db/species_name_script_migration.sql`        | Adds optional `script` column to `species_name` for non-Latin entries.                                        |
| 7 | `db/auth_session_migration.sql`               | Creates `auth_session` table backing the URL-token remember-me (was cookies before — see git history). Required for refresh-stays-signed-in.      |
| 8 | `db/fk_indexes_migration.sql`                | Adds 11 indexes on foreign-key columns that were missing them (joins on contributor_id, deity_id, etc.). Speeds up Profile + Library queries.   |
| 9 | `db/view_security_invoker_migration.sql`     | Flips public views from SECURITY DEFINER to INVOKER. Silences the Supabase linter and is the right posture before turning RLS on.                                   |
| 10| `db/backfill_attribution_to_maya.sql`         | Data-only: reassigns every existing row (trees, stories, dishes, names, cultural ties) to Maya admin.         |

## Verification after each run

The Supabase SQL editor prints the affected row count. Spot-check by running:

```sql
-- Should list all the expected tables
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' ORDER BY table_name;

-- Maya admin row exists and is admin
SELECT username, role FROM contributor WHERE lower(username) = 'maya';

-- Auth session table is empty until first sign-in after migration #7
SELECT count(*) FROM auth_session;
```

## Streamlit secrets

In **Streamlit Cloud → Manage app → Settings → Secrets**, the following keys
make the app run:

```toml
DATABASE_URL = "postgresql://postgres.<project>:<password>@aws-1-us-east-1.pooler.supabase.com:5432/postgres"
ADMIN_PASSWORD = "<your-admin-password>"
COOKIE_KEY = "<32-character random string>"   # optional but recommended; used to derive the auth cookie signing key
NCBI_TAXA_URL = "https://github.com/<you>/<repo>/releases/download/<tag>/taxa.sqlite.gz"
XENO_CANTO_API_KEY = "<optional, for bird audio>"
GROQ_API_KEY = "<optional, for LLM blurbs>"
HF_TOKEN = "<optional, alternative LLM provider>"
```

`ADMIN_PASSWORD` is what Maya types as her admin password on first run; on
that first run the auth module hashes it into the `maya` contributor row,
so this env var is never read as a plaintext password after that.

## Deployment cadence

When you push a code change that includes a new `db/*_migration.sql` file:

1. Push the code (`git push`)
2. Paste + run the new migration in Supabase SQL editor
3. **Manage app → ⋮ → Reboot** in Streamlit Cloud (forces fresh container,
   re-downloads taxa.sqlite if needed, reads updated requirements.txt)

If you forget the migration, the app may surface a column-missing error.
Most of those are gracefully caught (the user just sees "feature
temporarily unavailable" instead of a crash), but the affected feature
won't work until the migration runs.
