"""
ETL: load a CSV of species into the warehouse.

This replaces the old Google Sheets to BigQuery step. Contributors fill a plain
CSV in any spreadsheet app (LibreOffice, Numbers, Excel, or the kiosk export),
and this loads it with dedup-append so the full history of a tree is kept.

Column headers are forgiving. "Scientific Name", "scientific_name", "species",
and "latin" all land in the same place.

    python -m src.etl data/goat_farm_proctor_creek.csv
    python -m src.etl data/*.csv
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
from src import db  # noqa: E402

# Friendly header -> warehouse column.
ALIASES = {
    "tree_name": "tree_name", "tree": "tree_name",
    "common_name": "common_name", "common": "common_name",
    "scientific_name": "scientific_name", "scientific": "scientific_name",
    "species": "scientific_name", "latin": "scientific_name",
    "ncbi_taxid": "ncbi_taxid", "taxid": "ncbi_taxid", "ncbi": "ncbi_taxid",
    "domain": "domain", "kingdom": "domain", "group": "domain",
    "story": "story", "note": "story", "notes": "story",
    "submitted_by": "submitted_by", "by": "submitted_by",
}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename = {}
    for col in df.columns:
        key = str(col).strip().lower().replace(" ", "_")
        rename[col] = ALIASES.get(key, key)
    return df.rename(columns=rename)


def load_csv(path: str) -> int:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df = normalize_columns(df)
    df = df.replace("", None)
    if "scientific_name" not in df.columns:
        raise SystemExit(
            f"{path}: needs a scientific name column "
            f"(scientific_name / species / latin)"
        )
    if "tree_name" not in df.columns:
        raise SystemExit(f"{path}: needs a tree_name column")
    inserted = db.append_dedup(df)
    print(f"loaded {Path(path).name}: {inserted} new row(s)")
    return inserted


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m src.etl <csv> [<csv> ...]")
        raise SystemExit(1)
    total = sum(load_csv(p) for p in sys.argv[1:])
    print(f"done. {total} new row(s) total in {config.TABLE_NAME}.")
