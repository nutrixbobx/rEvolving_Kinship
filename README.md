# {r}Evolving Kinship

*a living kinship pipeline*

A participatory piece by Maya, of Shared Rivers, presented at SITE in The Goat
Farm, Atlanta, on the evening of October 3rd 2026.

Visitors name a species they feel kin to. The pipeline places that species in
the tree of life, redraws the tree with the visitor's kin inside it, sounds the
deep-time distances back as a microtonal chord, and gathers everyone's voices
into one tree the whole room belongs to. Each finished tree carries a photo, a
short profile, and the species' actual recorded voice, so the kinship is felt
across every sense the gallery has.

---

## About Shared Rivers and Maya's practice

Shared Rivers is the global confluence lab Maya works through, gathering
artists and ecologists and educators around the idea that waterways are not
borders or resources but living connectors. The lab convenes immersive events
that braid art, ecology, music, gastronomy, and education into one room. Past
work has run along the Yaanga in Los Angeles and now along Proctor Creek in
Atlanta. The next gatherings extend into Armenian foodways, Caribbean reef
listening, and other waters Maya is in conversation with. Everything Shared
Rivers makes is open, attributable, and free to remix. The site lives at
[shared-rivers.org](https://shared-rivers.org).

Maya's practice asks how a person can be reintroduced to kin they grew up
beside without ever being told they were kin. {r}Evolving Kinship is one
answer to that question, built as a tool other collectives can take and run
with.

---

## The {r} in {r}Evolving Kinship

The bracketed lowercase r is a quiet thing that does a lot of work.

Read it as written and the name is *Revolving Evolving Kinship*. Revolving
because evolution is not the linear ascent it gets drawn as. Lineages turn
back on themselves. Mothers become grandmothers. The same set of body plans
gets reassembled across deep time. Evolving because change is the only
constant the lineage has. The two words together propose evolution as a
returning, a re-encounter with the kin you have always had.

Drop the curly brackets and the name is *Evolving Kinship*. Plain, declarative,
the piece behaving as if it never needed the modifier. The brackets are an
invitation to read carefully or not. They mark the {r} as optional grammar,
the way you'd mark an optional capture group in a regex. A small computational
gesture peeking through the name, the code aware of itself.

Reread it with the lowercase emphasis and you get *rEvolving*, a near-pun on
revolt. The piece quietly resists the way ecology gets taught as a memorisation
of names and the way evolution gets taught as a tidy march toward us. The
revolt is not loud. It is the kind that lets you sit with a coyote and feel
your shared grandmother.

Read it once more and it becomes *Re-Evolving*, the prefix meaning again, anew,
not finished. The pipeline is itself re-evolving each time someone names a new
species, the tree absorbing the addition and reshaping accordingly. Nothing
about this work is meant to settle.

So the {r} is four reads on one syllable. Revolving, rEvolving, Re-Evolving,
or simply gone. Maya wrote it that way on purpose. The bracket is a door
visitors can open or walk past.

---

## Four sciences this piece sits on top of

The piece works because four overlapping ways of thinking about life have each
done part of the labour.

**Taxonomy** is the naming. It tells us a coyote is *Canis latrans*, a white
oak is *Quercus alba*, a honey bee is *Apis mellifera*. It places each living
thing inside a hierarchy of categories with one name per box. Without
taxonomy nobody could ask for the coyote by name and get the right animal back.
The pipeline reads the National Center for Biotechnology Information's
taxonomy database for this, the same one biologists rely on every day.

**Systematics** is the broader question of how those boxes should be drawn at
all. It studies which traits matter for grouping, which lineages share
common ancestry, where the categories should bend or break. Systematics is
the field that decides whether the American bullfrog stays under *Lithobates*
or moves into *Aquarana*. The pipeline inherits those decisions through NCBI's
classifications, which is why the bullfrog now sits with its newer genus on
the rendered tree even though many visitors will still type the older name.

**Phylogenetics** is the work of reconstructing actual evolutionary history.
It takes shared traits, shared genes, fossil dates, and builds branching trees
that show which lineages descend from which. The branching topology in the
rendered kinship trees is a phylogenetic structure. The deep-time labels on
the orange clade nodes come from a curated chronology that phylogeneticists
have spent careers calibrating.

**Cladistics** is one method inside phylogenetics that asks branches to be
defined strictly by shared derived traits. It produces clades, where every
named group contains an ancestor and every descendant of that ancestor. The
six labeled clades you see in any given tree (Eukaryota, Eumetazoa, Amniota,
Sauria, Boreoeutheria, Carnivora) are clades in the cladistic sense.

This piece sits on top of all four and then does something the four together
do not usually do. It returns the data to the body. Names become voices.
Branch points become sustained tones. Divergence ages become frequencies you
can feel in the chest. The four sciences supply the architecture. The piece
asks what that architecture sounds like when you stand under it for a minute.

---

## Re-envisioning ecological education

The default frame teaches species as facts to memorise. Lists of names, lists
of attributes, lists of habitats. The pipeline treats species as kin you
share rooms with.

When a visitor names a coyote they grew up hearing at dusk, the dashboard
does not respond with a Wikipedia tab and a quiz. It draws the coyote into the
tree next to the visitor's own human lineage, finds the branch point where
the two lineages last shared an ancestor (Boreoeutheria, 96 million years ago),
plays a tone at 477 Hz that represents that depth, and lets the visitor sit
inside the sound for as long as they want. The lesson is structural and
sensory at once. You do not learn the coyote's biology. You learn that you
and the coyote share a 96 million year old grandmother, and what 96 million
years sounds like.

Education by sensory immersion does not replace the textbook. It changes who
the textbook is for. Children, elders, neighbours, gallery walkers, people who
were always going to skip the binomial Latin can still arrive at the same
kinship the binomial Latin is pointing at. The piece is meant as a model
other educators, organisers, and ecologists can pick up and replicate for
their own waterways, foodways, and gatherings.

---

## What the pipeline actually does, briefly

For one tree:

1. A CSV or the kiosk supplies a list of species names.
2. The local NCBI taxonomy database resolves each to a real TaxID, fills the
   group and the rank ancestors (kingdom, phylum, class, order, family, genus),
   and saves a row per species.
3. ete3 asks NCBI for the topology that connects those species through the
   tree of life and names every node along the way.
4. toytree renders the tree three ways (rectangular, circular, unrooted),
   collapsing the long rank chains for clarity, marking dated clades, and
   placing each species' common and italic scientific name at the tip.
5. The sonification module maps each dated clade's age to a frequency in Hz
   via a log curve and additive sine synthesis. No scale snapping. The chord
   is true to the actual deep-time distances.
6. The species audio module fetches a CC-licensed recording per species from
   Xeno-canto (when an API key is set) or Wikipedia / Wikimedia Commons.
7. The chorus module mixes those recordings into a stereo blend per tree.
8. The spectrogram tree composes the cladogram and the per-species
   spectrograms side by side. The photo tree does the same with iNaturalist
   photos.
9. The meditation track module folds the chord and a sparse scatter of
   species voices into a one, two, or five minute soundscape.
10. The website bundle writes a JSON the live site can embed so the work
    keeps living after the event.

Every step is open source, attributable, and runs offline.

---

## Running it

### Offline (the gallery default)

```bash
pip install -r requirements.txt     # or: make install
make init                           # create the warehouse table
make load                           # load the Goat Farm sample species
make run                            # build tree, iTOL files, render, chord
make app                            # open the request station and dashboard
```

The first `make run` downloads the NCBI taxonomy once (a few hundred MB) so it
can place species in the tree of life. After that it works with no internet
for the core pipeline. Audio features fetch from Xeno-canto and Wikipedia on
demand and cache results so subsequent runs are local.

Some audio formats need ffmpeg on the system path. On a Mac, install once with
`brew install ffmpeg`. Without it, the chorus and spectrogram tree will skip
species whose recordings come back in codecs librosa can't decode on its own,
but nothing will crash.

### Online (Supabase, public site)

Copy `.env.example` to `.env`, then set:

```bash
DATABASE_URL=postgresql+psycopg2://postgres:YOUR-PASSWORD@db.YOUR-PROJECT.supabase.co:5432/postgres
XENO_CANTO_API_KEY=your-key-here     # optional, falls back to Wikipedia
ADMIN_PASSWORD=your-admin-password   # optional, gates the override editors
```

Run `db/schema.sql` once in the Supabase SQL editor. After that the same
`make load` and `make run` commands write to Supabase. Embed the per-tree
JSON in `outputs/web/` from any page, or query `v_species_public` through the
Supabase client. The public surface is always a named view, never the raw
table.

### Deploying the dashboard publicly

The dashboard is a Streamlit app and the simplest path to a public URL is
[Streamlit Community Cloud](https://streamlit.io/cloud). Push the repo to
GitHub, add `DATABASE_URL`, `XENO_CANTO_API_KEY`, and `ADMIN_PASSWORD` as
secrets in the Streamlit Cloud dashboard, deploy. Hugging Face Spaces is the
identical workflow if you prefer. WordPress can't host Python directly, but
you can embed the deployed Streamlit URL in any WordPress page with an
`<iframe>`.

---

## What gets generated for each tree

Under `outputs/`:

- `<stem>_named_tree.nwk` — the canonical Newick file with every internal
  clade named. Opens cleanly in FigTree, Dendroscope, iTOL, Bio.Phylo, or
  anything that reads Newick.
- `<stem>_nodes.json` — per-node metadata: scientific name, rank, common
  name, divergence age in MYA.
- `<stem>_tree.svg` and `.png` — the rectangular kinship-report render on a warm
  paper background. Italic parenthesised scientific names, dated clades in
  orange, header reading "{r}Evolving Kinship · a living kinship pipeline"
  plus the per-tree personalised title.
- `<stem>_sound_tree.png` — the rectangular tree plus a column of
  spectrograms (one per species with audio).
- `<stem>_photo_tree.png` — same composition with iNaturalist photos
  replacing the spectrograms. Both carry attribution per image.
- `<stem>_chord.mid` and `.wav` — the microtonal ecosystem chord. The `.mid`
  carries per-voice pitch bend so any DAW plays the exact cents.
- `<stem>_chorus.wav` — the stereo animal-voice blend.
- `<stem>_meditation_60s.wav` / `_120s.wav` / `_300s.wav` — meditation
  tracks at one, two, and five minutes. Quiet microtonal drone with the
  chorus sparsely scattered on top.
- `web/<stem>.json` — the embedding bundle for the website.
- `itol_common_names.txt`, `itol_internal_node_mya.txt`, `itol_options.txt`
  — drag-and-drop iTOL dataset files for the most recently built tree.

The dashboard exposes everything through Build / refresh buttons plus a
"Listen to each species" view with synced spectrogram playheads and a "Photo
tree" view. The Newick file has its own download button.

---

## Personalising the press graphics

Each tree carries an *owner* and a *title template*. The owner is the
human the tree belongs to; the title renders into every generated graphic.
Defaults to "Goat Farm - Proctor Creek looks like:" until you set one. With
`owner=Maya` and the default template it becomes "Maya's kinship looks like:".

Personalisation lives in `outputs/tree_owners.json` and is editable through
the admin panel in the dashboard (sign in with the `ADMIN_PASSWORD` you set
in `.env`).

The same admin panel exposes per-species profile overrides: pin a custom
image URL or a custom summary for any species without touching code. These
go into `outputs/species_overrides.json` and are merged on top of whatever
iNaturalist or Wikipedia returned.

---

## The community layer

The piece has grown a community side that lives alongside the kiosk.
Visitors make a free account (or just type a first name as a guest);
signed-in people can:

- **Add names** in any language and any script, with a click-to-compose
  keyboard for Devanagari, Gurmukhi, Bengali, Tamil, Armenian, Arabic,
  Hebrew, Cyrillic, Greek, Hiragana, Katakana
- **Add stories, dishes, cultural connections, deities** through the
  Library tab; editors and admins also get a Manage tab with bulk
  delete and a "Recent community additions" review feed
- **Follow** other contributors; **favorite** trees they want to revisit
- **Own their trees** — only the tree's owner (or an admin / editor)
  can rename, edit, or delete it
- See their **profile page** with avatar, bio, six count tiles, activity
  feed, change-password card; visit other contributors' public profiles
  by clicking any byline in Library

All fetched images are filtered to Creative Commons licenses only
(iNat's all-rights-reserved photos are skipped; the next CC photo on
the same taxon is used instead). Audio is CC by source policy.

Three core tree outputs ship from the Dashboard — Unrooted SVG,
unrooted with circular tip photos, and a rectangular photo + audio
combined tree — plus a four-page **Personalized kinship report (PDF)**.

See `CHANGELOG.md` for the complete feature inventory and `MIGRATIONS.md`
for the schema setup.

---

## Credits and licence

This pipeline is released under CC-BY-SA so any collective can take it,
remix it, and stand up their own waterway, foodway, or ecology piece.

Per-tree, the credits roll up automatically:

- Tree topology: NCBI Taxonomy, public domain.
- Deep-time chronology: hand-curated from TimeTree of Life when a dated
  tree is downloaded for the species, otherwise from the curated values in
  `config.py`.
- Species recordings: each cached file ships with a `.json` sibling that
  records the source, recordist, and licence. Xeno-canto recordings are
  attributed XC<id> with the contributor and the Creative Commons variant.
  Wikipedia / Wikimedia Commons recordings carry their original author and
  licence string.
- Species photos: iNaturalist (medium photo per taxon) with attribution
  preserved on every image in the photo tree. Falls back to Wikipedia
  thumbnails when iNaturalist has none. Custom overrides credit whoever
  the operator pins.
- Code: Maya (Shared Rivers) plus contributions from the open source
  Python scientific stack.

---

## If the first setup trips up

The first run can hit one of these depending on your Mac and Python version.

**`ModuleNotFoundError: No module named 'cgi'`**
Python 3.13 removed the old `cgi` module that ete3 still imports. A fresh
`pip install -r requirements.txt` installs a backport (`legacy-cgi`) on
Python 3.13 and 3.14 and clears it.

**`SSL: CERTIFICATE_VERIFY_FAILED` while downloading the taxonomy**
Python from python.org does not trust certificates until you run its
installer: `/Applications/Python\ 3.14/Install\ Certificates.command`, then
run the pipeline again. If your network inspects secure traffic and the
error returns, download the taxonomy file in your browser from
https://ftp.ncbi.nih.gov/pub/taxonomy/taxdump.tar.gz and build from it with
`python -m src.build_taxonomy ~/Downloads/taxdump.tar.gz`. ete3 never touches
the network when you hand it the file.

**`disk I/O error` from SQLite**
SQLite can struggle inside a cloud-synced folder while it is syncing. If you
see this in offline mode, point the database somewhere local, for example
`export DATABASE_URL="sqlite:////Users/you/revolving_kinship.db"`.

**ete3 keeps surfacing new errors on Python 3.14**
ete3 is an older library and Python 3.14 is brand new. If one fix just
reveals another, make a fresh environment on Python 3.12, where ete3 runs
cleanly: `rm -rf .venv && python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`.

**Audio features need ffmpeg**
The chorus and sound kinship tree call out to ffmpeg for codecs that pip
packages alone do not handle (Opus, some MP3 variants). Install once on
macOS with `brew install ffmpeg`. Without it the modules will skip those
species cleanly rather than crash, but you'll have a smaller chorus.
