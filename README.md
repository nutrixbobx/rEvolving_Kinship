# {r}Evolving Kinship: open data pipeline

This is the rebuilt pipeline for {r}Evolving Kinship, the kinship-tree piece
heading to The Goat Farm. It does the same thing the old version did, building a
phylogenetic tree from the species people feel kin to and turning deep-time
distances into a chord, but it runs on open and free tools instead of Google.

Someone names a species. The pipeline finds its place in the tree of life,
draws the tree, and plays the evolutionary distances back as sound. Common
names and the stories people carry ride alongside the scientific data the whole
way through.

## What changed from the old version

The science stayed. The plumbing moved off Google and off anything paid.

| Old (Google) | Now (open and free) | Why |
| --- | --- | --- |
| Google Sheets intake | a plain CSV, or the kiosk app | edit in any spreadsheet, no account |
| BigQuery warehouse | Postgres / Supabase, or SQLite offline | real SQL, runs offline, embeds in the site |
| Colab notebook | plain Python scripts | runs on the gallery mini-PC, no notebook |
| ete3 trees | ete3 trees (kept) | already open |
| iTOL files | iTOL files (kept) plus an offline render | a gallery copy that needs no internet |
| MIDIUtil chord | MIDIUtil chord (kept, now microtonal) | already open |

The database is picked by one setting, so the same code runs two ways. Offline
at the gallery it writes to a local SQLite file with nothing to install. Online
it points at Supabase (Postgres) and the results can be embedded back into
shared-rivers.org so the work keeps living after October 3rd.

## Quick start (offline, the gallery default)

```bash
pip install -r requirements.txt     # or: make install
make init                           # create the warehouse table
make load                           # load the Goat Farm sample species
make run                            # build tree, iTOL files, render, chord
make app                            # open the request station + dashboard
```

The first `make run` downloads the NCBI taxonomy once (a few hundred MB) so it
can place species in the tree of life. After that it works with no internet.

Everything lands in `outputs/`:

- `goat_farm_-_proctor_creek_named_tree.nwk`, the tree
- `itol_common_names.txt`, `itol_internal_node_mya.txt`, `itol_options.txt`, the iTOL files
- `goat_farm_-_proctor_creek_tree.svg` (and `.png`), the offline render
- `goat_farm_-_proctor_creek_chord.mid`, the chord for a DAW
- `goat_farm_-_proctor_creek_chord.wav`, the same chord as audio, played in the dashboard
- `web/goat_farm_-_proctor_creek.json`, the bundle for the website

## Online version (Supabase / Postgres)

Copy `.env.example` to `.env`, then set your connection string:

```bash
DATABASE_URL=postgresql+psycopg2://postgres:YOUR-PASSWORD@db.YOUR-PROJECT.supabase.co:5432/postgres
```

Run `db/schema.sql` once in the Supabase SQL editor. It creates the table, a
unique constraint so a tree never collects the same species twice, and two
governance views (`v_tree_summary` and `v_species_public`) that the website and
any BI tool read from instead of touching the raw table. After that, the same
`make load` and `make run` commands write to Supabase. Uploading this schema does
not rebuild the NCBI taxonomy in Supabase. That database stays local to whatever
machine runs the pipeline, and Supabase only holds the species rows and, if you
push it, the finished tree JSON.

To embed results in the site you have two simple paths. Read the JSON in
`outputs/web/` from a page on shared-rivers.org, or query `v_species_public`
through the Supabase client. Either way the public surface is a named view, not
the raw table.

## The request station

`make app` opens a small two-tab app, reading and writing the same warehouse as
the command-line tools.

The request station tab is the kiosk, and it is deliberately one box. A visitor
searches by common or scientific name and picks a real match. The species joins
the tree with its NCBI TaxID filled, so the warehouse never stores a null, and
its group and clade ranks (kingdom down to genus) are read from the NCBI lineage
automatically. Those columns show up in the dashboard table and in the public
view, which makes them easy to group and filter in a BI tool.

The dashboard tab shows the data, the chord, and the tree. You can switch the
tree between circular, rectangular, and unrooted, the three iTOL layouts, and
hover any node to read its metadata. A leaf shows its common and scientific name.
An internal node shows the clade, its rank, and the divergence time in millions
of years when that is known. A checkbox shows or hides the scientific names on
the tips, and an expander lets you remove species from a tree or delete a whole
tree. After removing anything, rebuild so the tree and chord match the data.

## Divergence dates from TimeTree

NCBI gives the branching structure but not the dates, so divergence times come
from TimeTree of Life. It has no clean API, but it takes a species list and
returns a dated tree, which is a dependable way to get real numbers.

It is two steps. Export the species list for a tree:

```bash
python -m src.timetree export "Goat Farm - Proctor Creek"
```

Upload that file at timetree.org under "Load a List of Species", then save the
dated tree it returns as `data/<stem>_timetree.nwk` (the export prints the exact
name to use). The dashboard has an "Export species list for TimeTree" button for
the same thing. From then on, every run reads that dated tree and puts a real age
on each internal node, matched by finding the same group of species in the
TimeTree result. Without a dated tree, the pipeline falls back to the curated
chronology in `config.py`, so nothing breaks.

## How a run flows

1. `src/etl.py` loads a CSV into the warehouse, skipping species already in that tree.
2. `src/enrich.py` fills in NCBI TaxIDs from the scientific names, and reports anything it cannot match.
3. `src/tree.py` asks ete3 for the topology that connects those species, names every node, and writes the Newick.
4. `src/itol_export.py` writes the three iTOL files.
5. `src/render.py` draws the tree to SVG with toytree, no web service needed.
6. `src/sonify.py` maps each clade's age to a frequency in Hz (log of mya, mapped to cents) and sums pure sines into one sustained chord. The .wav holds the exact microtonal pitches; the .mid uses per-voice pitch bend so any DAW plays them.
7. `src/export_web.py` writes the JSON bundle for the site.

`src/pipeline.py` runs steps 2 through 7 for one tree.

## The data

`data/goat_farm_proctor_creek.csv` is the site-specific starter set for the
Goat Farm, drawn from the Proctor Creek watershed, with Homo sapiens placed
beside the local kin. `data/yaanga_los_angeles.csv` is the original LA pilot,
ported over so the two trees stay comparable. `data/intake_template.csv` is the
blank you hand to a collaborator.

TaxIDs are left blank on purpose. You only need a scientific name, and the
pipeline fills the rest from the authoritative NCBI database rather than from
numbers typed by hand.

## Notes

The deep-time chronology lives at the top of `config.py`. Add a clade to
`LCA_CHRONOLOGY_MYA` and it shows up in both the iTOL labels and the chord.

The pipeline also writes a `.wav` of the chord, and the dashboard plays it in the
browser, so you need no extra software to hear it. The `.mid` is there for a DAW.

The `.mid` plays in any DAW or media player. iTOL display mode (normal,
circular, unrooted) is a one-click toggle in its Controls panel, and the
offline render comes out as a clean rectangular cladogram by default.

## If the first setup trips up

The first run can hit one of these, depending on your Mac and Python version.

**`ModuleNotFoundError: No module named 'cgi'`**
Python 3.13 removed the old `cgi` module that ete3 still imports. A fresh
`pip install -r requirements.txt` installs a backport (`legacy-cgi`) on Python
3.13 and 3.14 and clears it. If you still see it, run `pip install legacy-cgi`.

**`SSL: CERTIFICATE_VERIFY_FAILED` while downloading the taxonomy**
Python from python.org does not trust certificates until you run its installer:
`/Applications/Python\ 3.14/Install\ Certificates.command`, then run the
pipeline again. If your network inspects secure traffic and the error returns,
download the taxonomy file in your browser from
https://ftp.ncbi.nih.gov/pub/taxonomy/taxdump.tar.gz and build from it with
`python -m src.build_taxonomy ~/Downloads/taxdump.tar.gz`. ete3 never touches the
network when you hand it the file, so this gets past any certificate trouble.

**`disk I/O error` from SQLite**
SQLite can struggle inside a cloud-synced folder (Dropbox, iCloud) while it is
syncing. If you see this in offline mode, point the database somewhere local,
for example `export DATABASE_URL="sqlite:////Users/you/revolving_kinship.db"`.

**ete3 keeps surfacing new errors on Python 3.14**
ete3 is an older library and Python 3.14 is brand new. If one fix just reveals
another, make a fresh environment on Python 3.12, where ete3 runs cleanly:
`rm -rf .venv && python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`.


**Audio features need ffmpeg**
The chorus and sound kinship tree call out to ffmpeg for codecs that pip
packages alone do not handle (Opus, some MP3 variants). Install once on macOS
with `brew install ffmpeg`. Without it the modules will skip those species
cleanly rather than crash, but you'll have a smaller chorus.
