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

Session AG (photos arrive with the build; per-clade names; pick photos and
names in the canvas, 2026-09-17):
  - Kin cards warm automatically. `pipeline.warm_kin_cards(df)` fetches
    every species' profile (photo, summary, credits) and recording in
    parallel, and runs as step 1b of `pipeline.run` AND inside
    `_ensure_tree_built`. So a tree arrives with its images instead of
    needing a manual "Load kin cards" then a go-back-and-refresh.
    Per-species failures are non-fatal.
  - Per-clade name checkboxes. The "Clades…" button opens a panel listing
    every clade (sorted oldest first, with its age) with a checkbox each,
    plus Dated / All / None presets. Replaces the old three-way cycle, so
    you can name exactly the handful you want, the way the range map does
    species. Ticked set persists in the saved view.
  - The whole node is a drag handle. `pointer-events:none` came off the
    labels and photos, so dragging a name or a picture moves its node.
  - Photo choice. `species_profile` now stores up to three CC-licensed
    candidates per species (commercial-CC first), read back without
    network by `cached_image_candidates()`. The canvas draws ‹ 1/3 › under
    a photo when there is a choice; the arrows stop propagation so they
    never start a drag. The pick persists in the saved view and is
    stripped from exports (it is UI, not artwork).
  - Name picker. Every Library name for a species (via
    `db.list_tree_species_with_names`, cached 120s) is passed in; clicking
    a species opens a popup listing the default plus each name with its
    language and category, and choosing one relabels it in the tree.
    Clade click still focuses, so click means "pick a name" on species and
    "focus" on clades. The choice persists in the saved view.
  - Note: the name pick is a view-level choice (per device, in the saved
    view), not a write to `tree_species.display_name_id`. Wiring it to the
    DB needs an iframe-to-Streamlit round-trip; worth doing next now that
    Save view makes a rerun survivable.
  - Verified headless (jsdom): 16-row clade panel with presets, label is
    hit-testable, arrows cycle 1/3 -> 2/3 and stay hidden for single-photo
    species, name popup lists default + 3 names and relabels, and a full
    save -> reload -> restore -> reset cycle carries clades, photoIdx, and
    nameIdx. Plus a unit test of warm_kin_cards.


Session AF (the tree is the interactive tree; exports everywhere; clean
composites; sweep, 2026-09-16):
  - Dashboard: the side "Interactive" checkbox is gone. The live D3 canvas
    IS the tree. Its menu now also has a Size group (Photos and Text
    sliders), "Scientific names" (renamed from Latin; the name renders as
    an italic <tspan class="sci">, on canvas and in exports), and Save
    view / Reset in the View group. Save writes the whole state (layout,
    toggles, sizes, focus, every node position, zoom) to localStorage
    keyed by tree title and it restores on the next load, so a rerun or a
    reload no longer loses an arrangement; Reset clears it. The toyplot
    controls (layout radio, deep-time branch lengths, every clade to the
    root, Build SVG / PNG) live in one collapsed "Fixed drawings for
    print" expander under the canvas, horizontal and compact.
  - Range map: Export group inside the map. "PNG of this view" composes
    every loaded tile (basemap <img> tiles now load with crossOrigin so
    the canvas stays clean, plus our density canvases) at its screen
    position, respects the dark/light basemap and softer/bolder dot
    opacity, and draws a legend of the species currently shown with the
    scientific name in italics, plus attribution. "Species CSV" exports
    the list with GBIF keys, colors, and shown state.
  - Composites inherit the interactive view: T1 photo tree and the
    photo-spectral tree now prune the deep ancestral spine above the LCA
    (`render._prune_ancestral_spine`), so the poster shows the same tree
    the canvas does. In the photo-spectral tree the content band is now
    derived from the photo height (tips pulled in by half a photo on each
    end), which guarantees every photo and spectrogram stays between the
    header band and the legend + credit footer. Verified by render: the
    top photo used to climb into the title.
  - Sweep: no dangling drag_mode / drag_photos / zoom_pct references, no
    duplicate widget keys across station / library / profile, all
    modules compile, tree v4 and map JS verified headless (jsdom): italic
    tspans, sliders, save -> reload -> restore -> reset cycle, To LCA,
    exports.


Session AE (range map, same play-space feel as the tree, 2026-09-15):
  - `gbif_map.build_map_html` rewritten on a token template (no f-string
    brace doubling) with one grouped menu inside the map, top-left, so
    nothing needs a Streamlit rerun:
      Species: checkbox + color swatch + quick-look link + "solo" per
        species; All / None; hover a row to spotlight that species and
        dim the rest.
      Map: Dark / Light basemap (light_all, for reading and annotating),
        Softer / Bolder dots (GridLayer opacity), Reset view, and Tour.
      Tour walks through the species one at a time, each shown alone with
        its name on a banner (3.6s), then restores all. Solo, All, or None
        stops it.
  - CARTO key rides on both basemaps via a single JS var. Species links
    still carry the remember-me token.
  - The Streamlit-side species checkboxes stay but are reframed as "Limit
    which species load", for trimming very large trees; the in-map menu
    is the play surface. Range map tab copy updated to match.


Session AD (interactive tree v3: one menu, no overlap, real unrooted, 2026-09-15):
  - One grouped menu inside the canvas now carries every control (Layout:
    Unrooted / Radial / Rectangular; Show: Clades, Labels, Latin names,
    Photos; View: To LCA, Whole tree, Fit; Export: PNG, SVG). When the
    interactive view is on (now the default), the Dashboard side panel
    steps back to just the toggle, so nothing needs a Streamlit rerun and
    an arrangement is never wiped by a checkbox. The fixed toyplot
    controls (layout radio, deep-time scaling, show every clade, zoom)
    appear only when interactive is off.
  - Nothing overlaps and zoom never balloons or shrinks things: dots,
    labels, and photos are counter-scaled (transform scale(1/k)) so zoom
    changes spacing, not element size; edges use non-scaling stroke.
    Labels are decluttered greedily in screen space (focused root, then
    species top-to-bottom, then clades by age) and re-run on zoom, so
    zooming in reveals more names; hover always works. Labels point
    outward from the parent in the round layouts, so a fan never
    crosses itself. Fit zoom is clamped to [0.45, 2.4].
  - A true equal-angle Unrooted layout (default), distinct from Radial.
    It uses short steps along unary ladders and long steps at branch
    points, so a deep spine stays compact while the species fan gets
    room. Verified on a marigold tree with a 15-clade spine: all 20
    labels visible, zero collisions.
  - Photos come from the on-disk profile cache only via the new
    `species_profile.cached_image_url()`, so the dashboard never blocks
    on network; the in-canvas Photos toggle shows them instantly for any
    species already looked up. Latin names are a client toggle too.
  - Export fix: an explicit xmlns on the cloned SVG duplicated the
    serializer's own and produced an invalid file. Now the namespace is
    injected only if missing. Photos are still embedded as data URLs.


Session AC (prune the deep spine + interactive polish, 2026-09-11):
  - The default toyplot views now prune the ancestral ladder above the
    tree's last common ancestor. `render._prune_ancestral_spine` returns
    the subtree at the first branching node, so a marigold tree shows
    Asteraceae plus its species instead of fifteen deep-time ancestors
    stacked toward the middle. "Show every clade" turns the full spine to
    root back on. This is what finally opens up the circular view (which
    also now collapses its unary chain and uses more padding, less shrink)
    and spreads the unrooted tips instead of clustering them.
  - Interactive tree:
      - Hiding/showing clades, toggling labels, and focusing a clade no
        longer reset a tree you have arranged. A `manuallyMoved` flag: once
        you drag anything, focus keeps your positions and zoom instead of
        reflowing and refitting. Density and label toggles were already
        draw-only; the focus path is the one that used to yank the camera.
      - "To LCA" button jumps straight to the last common ancestor, hiding
        the whole deep ladder in one press. "Whole tree" restores it.
      - Species photos are 20% larger (34px).
      - PNG export now embeds each photo as a data URL first (fetch ->
        blob -> dataURL), so exported images no longer break; external
        hrefs were tainting the canvas. SVG export embeds them too.


Session AB (layout harmony + interactive tree fixes, 2026-09-11):
  - Deep-time scaling now defaults OFF. With it on, a marigold tree (root
    at 4290 mya, genus splits near 50 mya) crushed all five tips into one
    overlapping cluster in the unrooted view and a thin spine in the
    rectangular one. Topology spacing reads far more harmonious, so the
    "Scale branches to deep time" checkbox starts unchecked; turn it on
    for the time-faithful view.
  - Interactive tree, four fixes:
      - The Dashboard "Show scientific names" checkbox now feeds the drag
        tree. On, a leaf reads "Common (Scientific)"; off, just the common
        name. `build_interactive_html` takes show_scientific.
      - Labels on/off now hides clade labels too, not only species.
      - Clicking a clade FOCUSES on it and hides the deeper ancestors (the
        long dated ladder), instead of collapsing its species. Click the
        focused top clade again to step back out; "Whole tree" restores
        everything. Implemented as a re-rootable displayRoot with a y
        offset so the subtree lays out from the display origin.
      - Optional species photos: a "Photos on the drag tree" checkbox on
        the Dashboard passes {sci: image_url} into the canvas, and a
        thumbnail rides beside each species, travelling with it on drag.
        (External images can block PNG export for browser-security
        reasons; the export falls back to SVG with a note.)


Session AA (drop apt, restore ffmpeg + fonts via pip/bundle, 2026-09-02):
  - Deploys stopped depending on apt. Streamlit Cloud was failing the
    build on an expired Debian mirror Release file, and that step only
    ran because packages.txt existed. packages.txt is removed from the
    repo, so no more apt, no more mirror-breakage deploy failures.
  - The two things apt used to give us are back without it, in the new
    `src/env_setup.py` (both helpers idempotent):
      - ffmpeg for mp3 decoding, via the imageio-ffmpeg pip wheel (a
        static binary). `ensure_ffmpeg()` puts it on PATH as "ffmpeg" so
        librosa and audioread find it. Called at app startup and before
        every librosa.load (audio_blend, spectrogram_blend, meditation,
        photo_audio_tree).
      - fonts for non-Latin names in generated images and the PDF. Noto
        Sans and Noto Sans Armenian are bundled under assets/fonts and
        registered with matplotlib, which falls back per glyph. DejaVu
        still covers Latin, Greek, and Cyrillic; Noto Sans Armenian fills
        the collective's actual gap. `register_matplotlib_fonts()` runs
        at startup and in image_tree / photo_audio_tree; range_map_static
        falls back to the bundled font if the system DejaVu is missing.
        Verified Armenian, Cyrillic, and Greek all render, no boxes.
  - Note: full CJK glyphs in generated images would still need the large
    Noto CJK font, which is not bundled (the collective's data is Latin
    plus Armenian). Easy to add if CJK names show up.


Session Z (declutter default trees + full-width layout, 2026-09-02):
  - Trees start calm. `render._layout_settings` takes `show_all_clades`
    (default False). Off, the unrooted and rectangular toyplot views draw
    only the species and the DATED clades; undated internal nodes become
    invisible pass-through dots with no label, so a six-species tree shows
    two named clades, not five. `render._draw`, `render_html`, and
    `render_files` thread the flag; a "Show every clade" checkbox on the
    Dashboard turns the busy view back on. This walks back the everything-
    at-once look Maya flagged (twenty circles on a four-species tree). The
    interactive D3 tree now also opens in "Clades: dated".
  - Full-width layout. `theme.py` capped `.block-container` at 1200px,
    which boxed the app into roughly two thirds of a wide Chrome window
    and squeezed the right-hand config column (which was crowding the
    loading card). Cap is now min(1680px, 95vw) with wider side padding,
    so the app uses the window and the config column has room.


Session Y (drag-tree declutter + export, loader polish, 2026-09-02):
  - Interactive tree can hide clades now. Click a clade dot to collapse
    its branch (the dot grows, ringed in the label color, and reads
    "clade (+N)"); click again to open it. A "Clades" button cycles the
    dots between all, dated only, and none. "Open all clades" restores
    everything. Shift-click a clade still flips its children; the old
    double-click flip was replaced by click-to-collapse with a drag-vs-
    click threshold so dragging never collapses by accident.
  - Interactive tree exports. "Export PNG" and "Export SVG" buttons save
    exactly what is on the canvas, with the arrangement, the dark
    background, and the styles baked in. All client-side. Verified the
    SVG serialization carries the current clade filter (jsdom).
  - Loader no longer clips. Both fun-fact cards in `src/loading.py` now
    auto-size their component iframe to content via window.frameElement
    plus a ResizeObserver, with a responsive style block for narrow
    screens and a smaller header on the first-visit gate. The fixed
    heights stay as a floor. This is the real fix for the clipping that
    the taller-iframe patch in Session X only softened.


Session X (drag tree, CARTO key, loader clip, 2026-09-02):
  - New draggable tree: `src/interactive_tree.py` builds a self-contained
    D3 canvas from the collapsed newick + node metadata. Drag any node to
    move it (dragging a clade carries its whole subtree), double-click a
    clade to flip its children, switch radial or rectangular, pan and
    zoom. Wired into the Dashboard tree view behind a "Drag to arrange
    (interactive)" checkbox; the fixed toyplot layouts and their SVG/PNG
    exports stay as they were. D3 loads from the cdnjs CDN. Nothing is
    saved: it is an exploration space. Verified headless (jsdom + d3):
    correct node/edge counts, finite coordinates, working layout switch.
  - CARTO API key. CARTO now watermarks keyless raster tiles.
    `config.CARTO_API_KEY` reads the key from the environment and
    `config.carto_key_suffix()` appends ?key=... to every CARTO URL: the
    two range_map_static templates and the interactive Leaflet tile URL.
    The key lives in .env locally (gitignored) and must be added to
    Streamlit secrets as CARTO_API_KEY for the deployed app. It is not in
    tracked source.
  - Printable outline map is now light blue-white (was warm cream) so it
    reads as water and prints clean for hand annotation.
  - Loader clipping fixed. The rotating fun-fact cards in `src/loading.py`
    were clipped in narrow columns because the component iframe was too
    short for a wrapped fact. Raised both iframe heights and their text
    stages, added word-break so long words wrap.


Session W (broken-items + optimization pass, 2026-09-02):
  - Branches now scale to deep time. `render._draw` takes `use_scaled`,
    loads the MYA-scaled sibling newick, and turns on
    `use_edge_lengths` for the rectangular and unrooted layouts, so a
    deep split reads as a long branch and a recent one reads as short.
    A "Scale branches to deep time (MYA)" checkbox in the Dashboard
    side panel drives it (default on). Circular stays topology-only on
    purpose. The scaled file was already built by `scale_tree`; nothing
    was drawing it until now.
  - Third layout added: Circular. `LAYOUTS` now carries Unrooted,
    Rectangular, and Circular, in that order, so Unrooted stays the
    default view. The "c" path already existed in `_layout_settings`.
  - The mya-to-Hz formula is on screen. The "How the chord is tuned"
    panel under Listen prints the exact log transform, pulled live from
    the sonify + config constants so the printed math can never drift
    from the audio. Verified equal to the engine across the age window.
  - T1 photo-spectral tree label cleanup. `image_tree._draw_tree`
    stacks a wrapped common name and drops the scientific name below
    its last line, so a two-line name can't sit on the sci line.
    `_draw_clade_legend` flows into extra columns when a tree has more
    clades than one column holds at a readable size. The photo-audio
    tree gutter between the spectrogram strip and the clade legend was
    widened so they never touch.
  - Range map colors are deterministic. `gbif_map.resolve_species`
    assigns each species a color by the alphabetical rank of its
    scientific name, so the live map and the static composite agree
    with their own legends and stay put across rebuilds. That was the
    "colors don't match the legend" confusion between the two maps.
  - Printable outline range map. `range_map_static.build_range_map`
    takes `outline=True`: light coastlines on warm paper, faint
    observed ranges, and an open ruled notes band, made to print and
    draw on. A build button sits next to the dark composite in Outputs.
  - Map show / hide. The Range map tab has clean per-species checkboxes
    with Show all and Hide all, so people can pare the map down to the
    kin they care about before it renders. Fewer species also means
    fewer tile fetches.


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

Session H (cleanup pass, 2026-07-01):
  - Deleted 700MB of stale weight: `taxdump/` (515MB), `taxdump.tar.gz`
    (72MB), all `__pycache__/` dirs, all `.DS_Store` files.
  - Dead modules removed: `src/spectrogram_tree.py` (superseded by
    `spectrogram_blend.py` + `photo_audio_tree.py`),
    `src/cache_keys.py` (never imported).
  - Legacy `db/schema.sql` removed. `db/schema_v2.sql` is the baseline
    per `MIGRATIONS.md`.
  - Stale outputs cleaned: `outputs/*_sound_tree.png`, `outputs/web/`,
    `outputs/*_species_for_timetree.txt`, `outputs/itol_*.txt`.
    Regenerated by CLI (`python -m src.pipeline`, iTOL export) on
    demand.
  - README updated to point at schema_v2 and drop the sound_tree
    bullet.
  - `.gitignore` deduplicated (had `.DS_Store` listed six times).
  - `src/build_taxonomy.py` kept as the offline SSL fallback CLI. The
    README paragraph explaining it stays.

Session G (launch prep, 2026-07-01):
  - Sub-nav gates fixed (were bleeding through in Session E).
  - Static range map switched to blank-outline visual family
    (light coastlines + GBIF density + species legend).
  - `species_profile._is_useful_summary` heals cached "..." summaries
    on next visit by re-pulling Wikipedia. Fixes Tagetes patula and
    any other iNat-degenerate case.
  - Rank field no longer surfaces anywhere in views. DB still stores it.
  - `species_name.notes` column via `db/name_notes_migration.sql`.
    Add-name forms in Library + Dashboard carry a Notes textarea.
  - Region field is now `i18n.render_region_multi_picker` +
    `region_codes_to_str`/`region_str_to_codes` helpers. Stored as
    comma-separated string in the existing `region_code` TEXT column,
    so no schema change.
  - Dynamic photo sizing: T1 (`src/photo_audio_tree.py`) and T2
    (`src/photo_tip_tree.py`) both scale photo size inversely with
    tip count.
  - `src/composite_credits.py` provides `draw_pil_credit_strip` +
    `draw_matplotlib_credit_strip` for the bottom-right footer on
    T1, spec blend, and static range map.
  - Range map species link: layer control labels wrap the species
    name in `<a href="?species=...">`. Station.py's Range map tab
    reads that param and renders a species quick-look card.
  - Clade hover images: `render._build_image_map` accepts
    `newick_path=`, walks descendants for each internal node, and
    registers the clade name → first leaf's photo. Overlay JS is
    unchanged and picks these up automatically.

Session F (optimization + UX masterization, 2026-07-01):
  - MYA-scaled branch lengths: `src/scale_tree.py` writes a sibling
    `<stem>_scaled_tree.nwk` with log10(1+mya) branch lengths derived
    from `<stem>_nodes.json`. `src/render.py:_resolve_newick_path()`
    prefers the scaled file when it exists, controlled by `use_scaled`
    kwarg on `_prepare()`. Default: True.
  - Numbered clade callouts on T1: `src/image_tree.py:_draw_tree()`
    returns clade_entries. `_draw_clade_legend()` renders them in a
    right-margin column. Solves the T1 clade-overlap issue Maya has
    called out many times.
  - Inline MYA editor: form inside the Clade Browser expander lets
    admins + editors write to `clade.divergence_mya` without SQL.
    Uses new `db.get_clade_id_by_name()`.
  - Range map palette fix: reverted `.point` solid styles (they
    silently fall back to yellow on GBIF v2) to the working heat
    styles. Swatch hex sampled from real tile pixels.
  - Mobile + tablet polish: horizontal-scroll tabs bar, adaptive tree
    iframe, tablet 3-col-to-2 fallback.
  - Speed: `_clade_browser_lookup()` on station.py is
    `@st.cache_data(ttl=600)`, so switching between clades is instant
    on the second visit.

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

- 2026-09-02: Session W added time-scaled branches, the Circular
  layout, the on-screen mya-to-Hz formula, T1 label + legend cleanup,
  deterministic map colors, the printable outline map, and map
  show/hide checkboxes.
- 2026-09-02: Session X added the draggable D3 tree, the CARTO API key
  wiring, the light-blue annotation outline map, and the fun-fact
  loader clip fix.
- 2026-09-02: Session Y added clade collapse/hide and PNG/SVG export to
  the drag tree, and made the fun-fact loader auto-size so it stops
  clipping on desktop and mobile.
- 2026-09-02: Session Z made the default trees show only species and
  dated clades (with a Show every clade toggle) and widened the app out
  of its 1200px box to use the window.
- 2026-09-02: Session AA dropped packages.txt so deploys skip apt, and
  restored ffmpeg (imageio-ffmpeg pip wheel) and non-Latin fonts (bundled
  Noto, registered with matplotlib) that apt used to provide.
- 2026-09-11: Session AB defaulted deep-time scaling off for calmer
  layouts, wired the scientific-names + labels toggles into the drag
  tree, reversed clade-click to focus/hide-ancestors, and added optional
  draggable species photos.
- 2026-09-11: Session AC pruned the deep ancestral spine from the default
  tree views (Show every clade restores it), opened the circular layout,
  and polished the drag tree (preserve arrangement on toggle/focus, To
  LCA button, bigger photos, embedded-image PNG export).
- 2026-09-15: Session AD shipped interactive tree v3: one in-canvas menu
  (side panel steps back), counter-scaled non-overlapping labels that
  reveal on zoom, a true equal-angle Unrooted layout, disk-cache photos,
  and the export xmlns fix.
- 2026-09-15: Session AE gave the range map one in-map menu (species
  toggle/solo/spotlight, dark/light basemap, dot weight, Tour, reset)
  to match the interactive tree.
- 2026-09-16: Session AF made the interactive canvas the only live tree
  (side toggle removed, fixed builds in an expander), added size sliders,
  italic scientific names, Save/Reset view, range map PNG + CSV export,
  LCA-pruned composites with a guaranteed header/footer band, and a
  dead-code / duplicate-key sweep.
- 2026-09-17: Session AG warmed kin cards into the build, added per-clade
  name checkboxes, made labels/photos drag handles, and added in-canvas
  photo cycling and a Library name picker.
- 2026-07-01: created after Session E for the Fable cleanup pass.
  Whoever picks this up next: keep this section current so future
  sessions know what changed.
