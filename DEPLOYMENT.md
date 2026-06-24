# Deploying {r}Evolving Kinship to Streamlit Cloud + Supabase

This is the path from your laptop to a public URL.

The local pipeline works offline against a SQLite file. The public app needs
two things wired in: a Postgres database that lives somewhere everyone can
reach (Supabase), and the NCBI taxonomy file (built once on the server).

The slogan, hover, AI blurb, chord, photo tree, and admin gating all work
identically once these two pieces are connected.

---

## Step 1. Set up Supabase (database)

1. Create a free project at [supabase.com](https://supabase.com). Name it
   anything; remember the password you set, you will need it.

2. In your Supabase project, open the **SQL Editor** in the left sidebar.

3. Apply the schema and migrations in order, all from the **SQL Editor**.
   See `MIGRATIONS.md` in this repo for the complete numbered list and the
   verification queries. In short:
   - `db/schema_v2.sql` (baseline)
   - then every `db/*_migration.sql` file in the order listed in `MIGRATIONS.md`
   - then `db/backfill_attribution_to_maya.sql` (optional, data-only)

   Every migration is idempotent (uses `IF NOT EXISTS` / `IF EXISTS`), so
   re-running any of them is a safe no-op.

4. Get your connection string from
   **Project Settings → Database → Connection string → URI**.
   It looks like:

       postgresql://postgres:YOUR-PASSWORD@db.YOUR-PROJECT.supabase.co:5432/postgres

   You need to **prefix** that with the SQLAlchemy driver:

       postgresql+psycopg2://postgres:YOUR-PASSWORD@db.YOUR-PROJECT.supabase.co:5432/postgres

   Keep this string private. It is your database password.

---

## Step 2. Tell Streamlit Cloud about your secrets

1. Go to your app at
   [revolving-kinship.streamlit.app](https://revolving-kinship.streamlit.app/)
   → **Manage app** (bottom-right) → **Settings** → **Secrets**.

2. Paste this block (replacing each placeholder), then **Save**:

       DATABASE_URL = "postgresql+psycopg2://postgres:YOUR-PASSWORD@aws-1-us-east-1.pooler.supabase.com:5432/postgres"
       ADMIN_PASSWORD = "<your admin password>"
       COOKIE_KEY = "<any 32+ char random string — used to sign remember-me tokens>"
       NCBI_TAXA_URL = "https://github.com/<you>/<repo>/releases/download/taxa/taxa.sqlite.gz"
       XENO_CANTO_API_KEY = "<your-xc-key>"
       # Optional:
       # GROQ_API_KEY = "your-groq-key"
       # HF_TOKEN = "your-hf-token"

3. The app will restart automatically. The Streamlit Cloud → Streamlit code
   bridge I added copies each of those secrets into `os.environ` so the rest
   of the pipeline (which reads from environment variables) picks them up
   identically to your local `.env`.

`.streamlit/secrets.example.toml` in the repo shows the same shape and is
safe to commit. The real `.streamlit/secrets.toml` is gitignored.

---

## Step 3. Build the NCBI taxonomy on the server

The NCBI taxonomy is a 600 MB SQLite file. It's too big to commit, so the
app builds it the first time you ask.

1. Open your Streamlit app and go to the **Request station** tab.

2. You'll see a warning that the NCBI database isn't built yet. Open the
   **Build NCBI taxonomy on this server** expander and click **Start NCBI
   build**.

3. Wait about five minutes. Don't close the tab. When it finishes you'll
   see "NCBI taxonomy built. Reload the page to activate kiosk autocomplete."

4. Reload. Live species search and validation now work in the kiosk, and
   `make run` (server-side) can rebuild trees from the warehouse.

A note about persistence on Streamlit Cloud: the built taxonomy stays in
your app container until Streamlit restarts the container (idle timeout,
deploy, or platform maintenance). Each cold start currently asks for a
fresh build. That's a one-click reset for now. If you want it to persist
across restarts, the cleanest path is to:

- Build the taxonomy once locally
- Upload `~/.etetoolkit/taxa.sqlite` to a Supabase Storage bucket
- Set `NCBI_TAXA_DB` in your Streamlit secrets to point at the local path
  the app downloads it to on startup

I'd add that bucket-download path the next time you want to remove the
five-minute first-load cost.

---

## Step 4. Verify the loop

1. In the Request station, add a species (e.g. type "coyote" and pick
   *Canis latrans*). It should save with a real NCBI TaxID.

2. Switch to the **Dashboard** tab. You should see your tree in the list,
   with the row count from Supabase.

3. Click **Build / rebuild "Your Tree"**. The pipeline runs against
   Supabase, draws the tree, sounds the chord, and saves everything under
   `outputs/` inside the container.

4. The dashboard shows the new tree, the AI blurb, the species cards with
   photos and audio, the energy footprint with the LED-bulb benchmark, and
   the CC footer.

5. Sign in as admin with `otterhood6` to enable the species-profile
   overrides, the tree-owner personalization, the edit-species and
   delete-tree controls.

---

## Embedding back into shared-rivers.org

Once your app runs, you can embed the dashboard in any page of
`shared-rivers.org` with a simple iframe:

    <iframe src="https://revolving-kinship.streamlit.app"
            width="100%" height="900"
            style="border:none;border-radius:10px"></iframe>

Or pull the per-tree JSON bundles directly from `outputs/web/` in the
deployed container and render them with your own front-end. The
`v_species_public` view in Supabase is also a clean public surface for
any other client (Hugo, WordPress, etc.) that wants to read the data
without touching the raw table.

---

## What to push to GitHub before redeploying

When you change anything locally that you want live, commit and push:

- `src/`, `app/`, `db/`, `data/` — the pipeline code and seed CSVs.
- `requirements.txt` — needed for Streamlit Cloud to install dependencies.
- `README.md`, `DEPLOYMENT.md` — your project documentation and this deploy guide.
- `.streamlit/secrets.example.toml` — yes, this template is fine to commit.

Never commit:

- `.env` (gitignored)
- `.streamlit/secrets.toml` (gitignored)
- `outputs/` (gitignored except `.gitkeep`)
- `revolving_kinship.db` (local SQLite, gitignored)
- `taxdump.tar.gz` (large, gitignored)

The `.gitignore` is already set up for all of these.


## Where is YOUR-PASSWORD in Supabase?

Two different things sit behind the word "password" in Supabase. Make sure
you grab the right one.

**The database password** is what goes into the connection string. You set
it when you created the project. To find it again:

1. In your Supabase dashboard, click your project.
2. Left sidebar → **Project Settings** (gear icon at bottom).
3. **Database** in the settings menu.
4. Scroll to **Database Password**. There is a **Reset database password**
   button. Click it once and you'll see the new password in a banner; copy
   it immediately. Then update your Streamlit Cloud `DATABASE_URL` secret
   with the new password.

When Supabase shows you the connection string under **Connection string →
URI**, the password is the part between `postgres:` and `@db.`. If you've
never noted it down, just reset it — that's the fastest way.

The other "password" in Supabase is your account login. That is for the
dashboard, not for the database. Don't put your login password into
`DATABASE_URL`.


## Hosting the NCBI taxonomy in Supabase Storage

This eliminates the five-minute rebuild on every container cold start.
Once your taxonomy file lives in a Supabase bucket, the app downloads it
in about thirty seconds.

### Step A. Build the taxonomy once on your Mac

```bash
cd revolving_kinship
source .venv/bin/activate
python -c "from ete3 import NCBITaxa; NCBITaxa()"
```

After a few minutes you'll have `~/.etetoolkit/taxa.sqlite` (~600 MB).

### Step B. Compress it (cuts size in half, saves bandwidth)

```bash
gzip -k ~/.etetoolkit/taxa.sqlite
# produces ~/.etetoolkit/taxa.sqlite.gz, around 250-300 MB
```

### Step C. Create a Supabase Storage bucket

1. In Supabase dashboard → **Storage** (left sidebar) → **New bucket**.
2. Name it `ncbi-taxonomy`. Toggle **Public bucket: ON** (so the app can
   fetch without auth).
3. Click **Create bucket**.

### Step D. Upload the file

The Supabase dashboard's drag-and-drop has a 50 MB limit per file, which
is too small. Use the CLI instead:

1. Install the Supabase CLI once: `brew install supabase/tap/supabase`
2. Log in: `supabase login` (browser flow)
3. **Link your project once** (the `storage cp` command needs this; it
   doesn't accept `--project-ref` directly):

```bash
cd revolving_kinship
supabase link --project-ref YOUR-PROJECT-REF
```

It will prompt for your database password (same one in `DATABASE_URL`).

4. Upload, using **three slashes** after `ss:` and the `--linked` flag:

```bash
supabase storage cp \
  ~/.etetoolkit/taxa.sqlite.gz \
  ss:///ncbi-taxonomy/taxa.sqlite.gz \
  --linked
```

Your project ref is the subdomain from your Supabase URL
(`https://YOUR-PROJECT-REF.supabase.co`). You can also find it in
**Project Settings → General**.

If the upload says the bucket does not exist, create `ncbi-taxonomy` in
the dashboard first (Storage → New bucket → Public ON → Create).

### Step E. Get the public URL

In **Storage → ncbi-taxonomy → taxa.sqlite.gz**, click the row to open
the file. Copy the **Public URL** at the top. It looks like:

    https://YOUR-PROJECT-REF.supabase.co/storage/v1/object/public/ncbi-taxonomy/taxa.sqlite.gz

### Step F. Add it to your Streamlit Cloud secrets

Open **Manage app → Settings → Secrets** and add this line:

    NCBI_TAXA_URL = "https://YOUR-PROJECT-REF.supabase.co/storage/v1/object/public/ncbi-taxonomy/taxa.sqlite.gz"

Save. The app restarts.

### Step G. Trigger the download on the deployed app

Open the **Request station** tab. If the warning about the missing NCBI
database is still showing, expand **Build NCBI taxonomy on this server**
and click **Start NCBI build**. The new code path tries `NCBI_TAXA_URL`
first; you'll see a thirty-second download spinner instead of a
five-minute build, and the app picks up the taxonomy from your bucket.

After this, every cold start of your Streamlit container takes thirty
seconds of NCBI bootstrapping instead of five minutes, and the bandwidth
stays comfortably inside Supabase's free tier (~250 MB per restart).
