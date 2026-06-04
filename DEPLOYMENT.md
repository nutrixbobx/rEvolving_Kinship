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

3. Open `db/schema.sql` from this repo, copy everything, paste it into the
   SQL editor, and click **Run**. This creates the warehouse table, the
   unique constraint, and the two governance views
   (`v_tree_summary`, `v_species_public`).

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

       DATABASE_URL = "postgresql+psycopg2://postgres:YOUR-PASSWORD@db.YOUR-PROJECT.supabase.co:5432/postgres"
       ADMIN_PASSWORD = "otterhood6"
       XENO_CANTO_API_KEY = "f9a979326bc115d27f3020a85800a172304ca2e6"
       # Optional, only if you sign up:
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
- `README.md`, `DEPLOYMENT.md` — your press kit and this guide.
- `.streamlit/secrets.example.toml` — yes, this template is fine to commit.

Never commit:

- `.env` (gitignored)
- `.streamlit/secrets.toml` (gitignored)
- `outputs/` (gitignored except `.gitkeep`)
- `revolving_kinship.db` (local SQLite, gitignored)
- `taxdump.tar.gz` (large, gitignored)

The `.gitignore` is already set up for all of these.
