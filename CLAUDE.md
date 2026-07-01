# Working notes for future Claude sessions (Fable, Sonnet, whoever picks this up)

This file is context for anyone tasked with a cleanup or refactor pass
on `{r}Evolving Kinship`, the participatory phylogenetic-tree app Maya
Nutria (Shared Rivers) is building on Streamlit Cloud + Supabase.

Read this FIRST before opening files. It captures voice rules, what
was recently touched, what's fragile, and where the load-bearing
architecture lives, so you don't repeat past mistakes or re-open
questions Maya has already answered.

## The user

- Maya Nutria (they / them), Founder of Shared Rivers.
- Non-developer background; can absolutely read + reason about code
  but shouldn't be asked to debug internals.
- Voice preferences, applied everywhere: in-app strings, PDF copy,
  markdown, git commit messages, all of it.
  - No em-dashes (`—`). Use commas, colons, periods, or parens.
  - No "writing in threes" (the classic AI cadence: "clear, concise,
    and correct"). Break the pattern.
  - No AI-buzzwordy language ("comprehensive," "seamless,"
    "leverage," "delve," "unlock," "ensure," "robust," "streamline").
  - Warm, conversational, occasionally poetic. Museum-placard voice
    over startup-landing-page voice.
- Maya has repeatedly (10+ times) pushed back on: chatty summaries at
  the end of every message, over-formatting with headers and bullets
  where prose would do, and re-explaining what the diff already shows.
  Keep responses short. Trust that Maya can read the code.

## What the app is

Streamlit Cloud app at a URL like `shared-rivers.streamlit.app`.
Users request species, the app builds a personalized phylogenetic
tree via NCBI taxonomy, sonifies it, layers community knowledge
(multilingual names, stories, dishes, cultural connections), and
outputs a Personalized Kinship Report PDF.

Five tabs: Request station, Dashboard, Range map, Library, Profile.
Auth model: admin / editor / visitor / guest.

## What just landed (Sessions A through E, 2026-07-01)

Roughly in order:

Session A (UX / structure):
  - Dashboard sub-nav radio: Outputs / Customize / Listen / Footprint.
  - "About the technology" expander on Request Station.
  - Press-kit + README + PDF About-page copy revamp: Shared Rivers
    foregrounded, Goat Farm decentered.

Session B (missing / broken fixes):
  - Undated clade labels back on in T1 rectangular.
  - Range map tile fetch failures log the URL.
  - Water consumption added to tree blurb.

Session C (new features):
  - Theme skins picker (crimson_amber default, river_sea,
    warm_forest), persisted on `contributor.theme`.
  - Clade browser under Customize: representative species photo,
    divergence age, species list, per-clade notes.
  - `clade_note` table for per-clade notes (per-tree or global scope).
  - Blank outline range map builder (light coastlines, printable
    with a notes gutter).

Session D (access control):
  - Public sign-up gated by ACCESS_CODE = "666" in `src/auth.py`.
  - Guest sessions can view + build composites, cannot add / edit /
    delete anything.
  - Guest -> full account upgrade form in Profile using the same
    access code.

Session E (guest lockdown + map polish + NCBI auto-load):
  - Range map switched to GBIF `.point` solid-color styles (red,
    green, blue, purple, orange, yellow). Legend swatch is now
    literally the on-map dot color.
  - Legend merged into the layer-toggle panel (top-right). No
    separate bottom-left legend.
  - NCBI auto-load: `src/loading.py` blocks the app on first visit
    until `taxa.sqlite` lands, rotating fun facts every ~5 seconds.
    Manual "Build NCBI" expander removed. Admin re-download panel
    stays on the Dashboard as a corruption escape hatch.

Two migrations shipped this cycle:
  - `db/theme_migration.sql`
  - `db/clade_note_migration.sql`

Both are idempotent, tolerant of not-yet-applied state.

## Architecture, briefly

- `app/station.py` (~1600 lines) is the single Streamlit entrypoint
  and the biggest file in the repo. Everything else is a module it
  imports from `src/`.
- `src/db.py` (~1700 lines) is the DB layer, thin SQLAlchemy calls.
- `src/render.py` renders the interactive tree + still SVG / PNG via
  toyplot + toytree + matplotlib. This is fragile territory (see
  below).
- `src/species_profile.py` fetches iNat + Wikipedia data for species,
  caches on disk, enforces Creative Commons licenses on photos.
- `src/species_audio.py` fetches Xeno-canto recordings.
- `src/press_pdf.py` builds the Personalized Kinship Report PDF via
  ReportLab.
- `src/gbif_map.py` builds the interactive Leaflet range map.
- `src/range_map_static.py` builds the static composite range map
  image for the PDF, plus the blank outline map for printing.
- `src/auth.py` custom auth (bcrypt hashes, URL query-param session
  tokens, no cookies).
- `src/profile.py` Profile tab.
- `src/library.py` Library tab.
- `src/theme.py` unified palette + CSS + theme skins.
- `src/loading.py` first-visit NCBI loading gate.

## Things that will bite you

- **Toyplot ignores newlines in labels.** Every attempt to fit
  overlapping clade labels via `\n` or arrows failed. The current
  solution in `_chain_combined_label` is "show only the innermost
  dated clade in a chain, hide the rest." Do not re-introduce
  newline hacks.
- **CSS injection cannot be guarded by session_state.** Streamlit
  re-renders the page from scratch on every rerun. `inject_css()`
  must re-emit its `<style>` block every time. If you see the app
  lose its palette mid-session, this is why.
- **`st.tabs()` resets to the first tab on `st.rerun()`.** The
  top-level tab bar in station.py uses session-state-backed
  `st.radio()` instead. Do not swap it back to `st.tabs()`.
- **GBIF `@1x` tiles are 512px; CARTO tiles are 256px.** Mixing them
  displaces the heatmap. `range_map_static.py` uses `@0.5x.png` for
  GBIF so tiles align 1:1 with CARTO. Do not swap back to `@1x`.
- **`profile` module name shadowing.** In station.py, a local
  variable named `profile` shadowed `from src import profile`. The
  local was renamed to `_sp_profile`. Watch for this pattern.
- **`packages.txt` cannot contain comments.** Streamlit reads each
  line literally as a package name. Strip all `#` lines.
- **`_verified_db_init` uses `@st.cache_resource`.** Do not remove.
  It runs the v2 schema check once per session, not every rerun.
- **NCBI loading gate must not be cached.** `setup_ncbi.is_ready()`
  reads the file every call by design. Do not add `@st.cache_data`
  around it or the loading screen will freeze forever.

## Voice rules for any generated content

Read the "The user" section above and internalize the tone. Concrete
patterns Maya likes:

- Sentences that don't all follow the same rhythm.
- Concrete nouns: "coyote" beats "canid," "riverbank" beats "riparian
  edge habitat."
- Occasional but sparing wordplay. Not puns for their own sake.
- Section headings that sound like a person named them, not a
  content-strategy team.

Bad (do not produce):

> Comprehensive support for multilingual names, seamlessly integrated
> with a robust cultural knowledge layer that enables users to
> unlock deeper engagement with biodiversity.

Better:

> Every species in the tree has room for the names it goes by.
> Community members can add another language, a folk name, a
> ceremonial name. The library holds all of them.

## What a cleanup pass could productively focus on

None of this is urgent, but it's the shape of a good refactor batch:

1. `app/station.py` is monolithic. Splitting the Request Station,
   Dashboard, Range map, Library, and Profile blocks into their own
   modules under `app/tabs/` would make the file readable again.
   Be very careful with widget-key namespacing when moving code
   (existing keys include the tree name to avoid collisions).
2. Inline heredocs in `src/gbif_map.py` mix JS + CSS + Python. It
   works but is hard to review. Extract the HTML template to a
   `templates/` file.
3. Widget-key collisions: run a grep pass for duplicate `key=`
   arguments. As of Session E there are zero, keep it that way.
4. `src/db.py` has grown to ~1700 lines. Splitting by table
   (`db/contributor.py`, `db/tree.py`, etc.) would help.
5. Dead code from earlier iterations that got replaced: streamlit-
   authenticator remnants (all in git history now, none in code),
   old cookie-based auth (removed but grep for `CookieManager` to
   confirm), old range-map builder that hung on 4000 tile fetches
   (replaced by ThreadPoolExecutor version).
6. Style: some functions in `app/station.py` and `src/render.py`
   are ~200 lines. Extraction opportunities exist.

## What NOT to touch in a cleanup pass

- Do not rename `_chain_combined_label` or change its innermost-only
  logic. Maya spent ~10 rounds getting it to look right.
- Do not re-add `@st.cache_data` on `species_profile.find_profile`
  or on `setup_ncbi.is_ready`. Both need to read live disk state.
- Do not change the URL-token remember-me back to cookies. Cookies
  do not work reliably inside the Streamlit Cloud iframe.
- Do not add loading spinners around the tree render itself. It's
  fast enough (~1s), and Maya finds constant spinners noisy.
- Do not rewrite copy without running through the voice rules first.

## Where the shared secrets live

Streamlit Cloud secrets, not this repo:
  - `SUPABASE_DB_URL`
  - `NCBI_TAXA_URL` (points at the taxa.sqlite.gz release asset)
  - `ADMIN_PASSWORD` (used once, on first admin bootstrap)
  - `XENO_CANTO_API_KEY`

`.streamlit/secrets.toml` is gitignored. Env vars in
`.env` (also gitignored) mirror the same values for local dev.

## Contact + escalation

If something is unclear, stop and ask Maya rather than guessing.
This project has landed 130+ tasks worth of iteration; assumptions
are expensive.

## Change log for this file

- 2026-07-01: created after Session E for the Fable cleanup pass.
  Whoever picks this up next: keep this section current so future
  sessions know what changed.
