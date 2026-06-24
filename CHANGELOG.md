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
