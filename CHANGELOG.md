# What's in this state of the app

A single-page summary of what the codebase does today. For the longer
story and tone, read `README.md`. For deploying, read `DEPLOYMENT.md`
and `MIGRATIONS.md`.

## Five tabs

**Request station** — kiosk. Search by common or scientific name, pick a
match, add to a tree (new or existing). Search hits the local NCBI
taxonomy (built once per server).

**Dashboard** — pick a tree, see it rendered live (unrooted or
rectangular layout), with a zoom slider and a tip-photo hover overlay.
Three downloadable outputs:

  1. **Unrooted SVG / PNG** — the canonical tree
  2. **Inline photo-tip tree** — unrooted SVG with a circular photo
     embedded at every species tip
  3. **Photo + audio tree** — rectangular layout, one row per species,
     with the photo and a spectrogram of its recorded voice side by side
     plus per-row attributions

Plus the **Personalized kinship report (PDF)** — four pages: hero
photo-tip tree, project info + license + footprint, photo+audio tree,
one kin card per species with photo, summary, image + audio credits, and
a per-species spectrogram.

**Range map** — GBIF occurrence density tiles per species in the picked
tree, drawn on one Leaflet panel.

**Library** — community knowledge for the species in the system.
  - Browse: every name, story, dish, pantheon, cultural connection,
    grouped + searchable
  - Add: any signed-in user (or named guest) can add multilingual names
    (with a script keyboard for non-Latin scripts), stories, dishes,
    cultural connections; editors + admins also add pantheons + deities
  - Manage (editors + admins): edit + delete every kind, with bulk-delete
    and a "Recent community additions" review feed

**Profile** — avatar, bio, activity feed of your own contributions,
follow + favorite, change-password. Admins additionally see Team
(promote users to editor) and Password resets.

## Session G: launch prep

Sub-nav gates fixed so Outputs/Customize/Listen/Footprint actually
filter what shows. Static range map now shares the blank outline
aesthetic (light coastlines on warm paper) with GBIF density
overlays and species legend layered on top. French Marigold now
reads correctly in kinship cards; a wider fix heals any species
whose iNat wikipedia_summary is degenerate (falls back to
Wikipedia's real extract, caches the fix). Rank field dropped from
every user-facing view. Name additions now carry an optional Notes
field. Region field became a multi-tag picker across the app with
free-text Other. Photo sizing in T1 + T2 scales with tip count so
sparse trees show big thumbs and dense trees stay tidy. Every
composite image now carries a small right-aligned credit strip at
the bottom. Range map species names are clickable and open a quick-
look species card. Interactive tree hover images now cover clade
nodes too (representative descendant photo).

## MYA-scaled branch lengths

Every tree now writes a sibling `<stem>_scaled_tree.nwk` alongside the
topology newick. Branch lengths reflect real divergence times in
millions of years, log-scaled with log10(1+MYA) so a Cambrian branch
does not swallow the recent ones. Renderers prefer the scaled newick
by default. Sonification already reads ages directly, so the chord
intervals inherit the same fidelity to real evolutionary distance.

## Numbered clade callouts on T1

The Photo-Spectral tree used to place clade text labels next to each
internal node, which stacked on top of each other whenever two clades
were near the same depth. Labels now live in a dedicated right-margin
legend column with numbered badges on the tree, so no two labels can
overlap regardless of tree shape.

## Inline MYA editor in the Clade Browser

Editors and admins can now set a clade's divergence age straight from
the Clade Browser expander. Writes to `clade.divergence_mya` so the
new age applies across every tree that uses this clade. Rebuild the
tree afterward to see the branch rescale.

## Range map palette (real fix)

Session E swapped in `.point` solid-color styles like `red.point` and
`blue.point`. Empirically, GBIF's tile server silently falls back to
yellow on those. Reverted to the six heat styles that actually render
(fire, greenHeat, blueHeat, purpleHeat, orangeHeat, glacier) with
swatch hex values sampled directly from real tile pixels so the
legend matches the map.

## Mobile + tablet polish

Top-level tabs bar and dashboard sub-nav radio now scroll horizontally
on narrow screens instead of wrapping badly. Interactive tree iframe
adapts to viewport. 3-column layouts collapse to 2-across on tablets.

## Access-code sign-up + guest upgrade

Public sign-up is back but gated by a shared access code. Anyone with
the code from Maya can create a full account from the auth screen or
convert a guest session into a full account from Profile.

Guests can view every tree, listen to species, build kinship reports,
and read every community contribution. Guests cannot add species,
names, stories, dishes, notes, or clade notes, and cannot follow or
favorite. Any write panel a guest sees points back at Profile to
upgrade.

## Range map palette

Switched GBIF layers to the solid-color .point styles (red, green,
blue, purple, orange, yellow) so the swatch in the legend is exactly
the color you see on the map. The species legend now lives inside
the layer toggle panel (top-right), with a colored dot next to each
name, so the same panel serves as both legend and on/off switch.

## NCBI auto-load screen

Dropped the manual "Build NCBI on this server" expander. On first
visit, the app takes over the screen with a loading card that fetches
taxa.sqlite in the background. Rotating fun facts about biology and
water rotate every few seconds while it downloads.

## Dashboard sub-nav

The Dashboard body switches between four sections via a small radio
under the tree: Outputs, Customize, Listen, Footprint. The tree and
its build controls stay visible above the radio so you always have
context. Pick lands via session_state so it survives reruns.

## Clade browser + notes

Under Customize, pick any named clade in the current tree and see:
a representative species photo (the first CC-licensed image among its
descendants), its divergence age, and up to twenty species under it.
Signed-in users can attach a short note to any clade, scoped to just
this tree or global across trees. Notes are surfaced right there
under the clade in the browser.

## Blank outline map

Next to the composite range map is a "Build blank outline map" button.
Same CARTO coastlines, no GBIF density, on warm paper stock with lined
notes gutter underneath. Print it and sketch your own observations,
migrations, or family stories.

## Theme skins

Profile now has a Color palette picker. Two alternate themes ship with
the app (River sea, Warm forest) alongside the default Crimson & amber.
Choice persists on `contributor.theme` and applies across every page.

## Invite-only accounts

Public sign-up is gone. Only admins can create new accounts, via a
form on their Profile. New users get a role (visitor / editor / admin)
and a forced-password-change flag on first sign-in.

## Auth + roles

  - **admin** (Maya + anyone she promotes): can edit anything
  - **editor**: can edit anyone's contributions except admin-owned trees
  - **visitor** (signed-in or named guest): can add to community
    datapoints and edit their own trees + contributions

Signed-in users sign up with username/password + optional email; their
session persists via a URL query token (rotates on sign out). Guests
just give a first name.

## Internationalization

  - Languages: ISO 639-3 (three-letter codes like ENG, SPA, HYE, PAN,
    SWA) via a dropdown + "Other" free text
  - Regions: ISO 3166 country/sub-region codes grouped by macro-region
    (South Asia, Mesoamerica, Indigenous North America, etc.)
  - Scripts: optional non-Latin marker per name + a click-to-compose
    keyboard for Devanagari, Gurmukhi, Bengali, Tamil, Armenian, Arabic,
    Hebrew, Cyrillic, Greek, Hiragana, Katakana

## Licensing

Every image fetched from iNaturalist is filtered to Creative Commons
licenses only (cc0, cc-by, cc-by-sa, cc-by-nc variants). Audio from
Xeno-canto is CC by platform policy. Wikipedia / Wikimedia Commons is
CC by definition. The kinship report carries per-photo and per-audio
attribution on every kin card.

## What's available where

  - Streamlit app — public at the URL Streamlit Cloud assigns
  - Postgres — your Supabase project, schema in `db/schema_v2.sql` plus
    10 idempotent migrations (see `MIGRATIONS.md`)
  - NCBI taxonomy — `taxa.sqlite.gz` from a GitHub release pointed at by
    the `NCBI_TAXA_URL` Streamlit secret
  - System apt packages — `packages.txt` requests `fonts-noto-*` (for
    non-Latin script rendering in the PDF) and `ffmpeg` (for audio
    decoding)
