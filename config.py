"""
Central configuration for the {r}Evolving Kinship pipeline.

One place for paths, the deep-time chronology, the musical scale, and the
database connection. Nothing here is tied to Google or any paid service.

The database is chosen by the DATABASE_URL environment variable:

  - Offline at the gallery (default): a local SQLite file, zero setup.
        DATABASE_URL is unset  ->  sqlite:///revolving_kinship.db
  - Online / website version: Supabase or any Postgres connection string.
        export DATABASE_URL="postgresql+psycopg2://user:pass@host:5432/postgres"

Both modes run the exact same pipeline code.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "outputs"

# ete3 keeps its NCBI taxonomy copy here. Set NCBI_TAXA_DB to move it.
NCBI_TAXA_DB = os.environ.get(
    "NCBI_TAXA_DB", str(Path.home() / ".etetoolkit" / "taxa.sqlite")
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Database connection
# ---------------------------------------------------------------------------
# Default to a local SQLite file so the piece runs with nothing installed and
# no internet. Point DATABASE_URL at Supabase/Postgres for the online version.
DEFAULT_SQLITE_PATH = BASE_DIR / "revolving_kinship.db"
DATABASE_URL = os.environ.get(
    "DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE_PATH}"
)

# Main table that holds every species request, across every tree.
TABLE_NAME = "user_species_requests"

# Columns of the master table, in order. common_name and the carried story are
# honored alongside the scientific data, never dropped.
COLUMNS = [
    "tree_name",        # e.g. "Goat Farm - Proctor Creek"
    "common_name",      # e.g. "Coyote"
    "scientific_name",  # e.g. "Canis latrans"
    "ncbi_taxid",       # e.g. 9614  (filled from scientific_name if blank)
    "domain",           # e.g. "Animal" / "Plant" / "Fungi" / "Human"
    "story",            # optional: what a person carries about this species
    "submitted_by",     # optional: who named it (kiosk or batch import)
]

# ---------------------------------------------------------------------------
# Deep-time chronology (millions of years ago)
# ---------------------------------------------------------------------------
# Last-common-ancestor depths for the clades we label and sonify. These are the
# values from the original Yaanga pilot, kept so the two trees stay comparable.
# Add a clade here and it shows up in both the iTOL labels and the chord.
LCA_CHRONOLOGY_MYA = {
    "Sauria": 260,
    "Boreoeutheria": 96,
    "Carnivora": 43,
    "Eumetazoa": 600,
    "Amniota": 312,
    "Eukaryota": 1500,
}

# ---------------------------------------------------------------------------
# Sonification
# ---------------------------------------------------------------------------
# Pentatonic scale degrees, used to snap raw pitches so the chord stays
# consonant no matter which clades are present.
PENTATONIC_INTERVALS = [0, 2, 4, 7, 9]

# MIDI pitch window the deep-time range gets mapped into.
MIDI_PITCH_LOW = 36    # ancient splits sit low
MIDI_PITCH_HIGH = 96   # recent splits sit high

MIDI_TEMPO_BPM = 60
MIDI_VELOCITY = 90
MIDI_CHORD_DURATION_BEATS = 8  # one long sustained chord
