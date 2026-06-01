"""
Warehouse layer.

One SQLAlchemy engine, two homes:

  - SQLite when DATABASE_URL is unset. Zero install, runs offline on the
    gallery mini-PC. This is the default.
  - Postgres / Supabase when DATABASE_URL points at one. Same code, plus the
    governance views and a path to embed results back into the website.

This module replaces the old Google BigQuery layer. Everything the rest of the
pipeline needs from the database goes through the functions here, so the BI
tools, the website, and the kiosk all read from one stable surface.

Run `python -m src.db init` to create the table (and, on Postgres, the views).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

try:  # load a local .env if python-dotenv is installed
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Allow running as a module (`python -m src.db`) or a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

_engine: Engine | None = None

# The columns the pipeline writes. id, created_at are filled by the database.
# class and order are SQL reserved words, so those columns carry a trailing _.
WRITE_COLUMNS = [
    "tree_name",
    "common_name",
    "scientific_name",
    "ncbi_taxid",
    "domain",
    "kingdom",
    "phylum",
    "class_",
    "order_",
    "family",
    "genus",
    "story",
    "submitted_by",
    "notes",
]

# Columns added after the first release. init_db backfills any that are missing
# on an existing database, so older warehouses upgrade in place.
_OPTIONAL_COLUMNS = {
    "domain": "TEXT", "kingdom": "TEXT", "phylum": "TEXT", "class_": "TEXT",
    "order_": "TEXT", "family": "TEXT", "genus": "TEXT",
    "story": "TEXT", "submitted_by": "TEXT", "notes": "TEXT",
}

# Columns the editor in the dashboard is allowed to change. The natural key
# (tree_name, scientific_name) is protected; rename a tree with rename_tree().
EDITABLE_COLUMNS = [c for c in WRITE_COLUMNS
                    if c not in ("tree_name", "scientific_name")]


def get_engine() -> Engine:
    """Return the shared engine, building it from DATABASE_URL on first use."""
    global _engine
    if _engine is None:
        _engine = create_engine(config.DATABASE_URL, future=True)
    return _engine


def is_postgres() -> bool:
    return get_engine().dialect.name == "postgresql"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
_SQLITE_DDL = [
    f"""
    CREATE TABLE IF NOT EXISTS {config.TABLE_NAME} (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        tree_name       TEXT    NOT NULL,
        common_name     TEXT,
        scientific_name TEXT    NOT NULL,
        ncbi_taxid      INTEGER,
        domain          TEXT,
        kingdom         TEXT,
        phylum          TEXT,
        class_          TEXT,
        order_          TEXT,
        family          TEXT,
        genus           TEXT,
        story           TEXT,
        submitted_by    TEXT,
        notes           TEXT,
        created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    f"""
    CREATE UNIQUE INDEX IF NOT EXISTS uq_tree_species
        ON {config.TABLE_NAME} (tree_name, lower(scientific_name))
    """,
]

_POSTGRES_DDL = [
    f"""
    CREATE TABLE IF NOT EXISTS {config.TABLE_NAME} (
        id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        tree_name       TEXT        NOT NULL,
        common_name     TEXT,
        scientific_name TEXT        NOT NULL,
        ncbi_taxid      INTEGER,
        domain          TEXT,
        kingdom         TEXT,
        phylum          TEXT,
        class_          TEXT,
        order_          TEXT,
        family          TEXT,
        genus           TEXT,
        story           TEXT,
        submitted_by    TEXT,
        notes           TEXT,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    f"""
    CREATE UNIQUE INDEX IF NOT EXISTS uq_tree_species
        ON {config.TABLE_NAME} (tree_name, lower(scientific_name))
    """,
    f"""
    CREATE OR REPLACE VIEW v_tree_summary AS
    SELECT tree_name,
           count(*) AS species_count,
           count(*) FILTER (WHERE ncbi_taxid IS NOT NULL) AS resolved_count,
           min(created_at) AS first_request,
           max(created_at) AS latest_request
    FROM {config.TABLE_NAME}
    GROUP BY tree_name
    """,
    f"""
    CREATE OR REPLACE VIEW v_species_public AS
    SELECT tree_name, common_name, scientific_name, ncbi_taxid, domain,
           kingdom, phylum, class_, order_, family, genus, notes
    FROM {config.TABLE_NAME}
    WHERE ncbi_taxid IS NOT NULL
    ORDER BY tree_name, scientific_name
    """,
]


def _ensure_columns(conn, pg: bool) -> None:
    """Add any optional columns missing from an existing table (migration)."""
    if pg:
        rows = conn.execute(
            text("SELECT column_name FROM information_schema.columns "
                 "WHERE table_name = :t"),
            {"t": config.TABLE_NAME},
        ).fetchall()
        have = {r[0] for r in rows}
    else:
        rows = conn.execute(
            text(f"PRAGMA table_info({config.TABLE_NAME})")
        ).fetchall()
        have = {r[1] for r in rows}
    for col, sqltype in _OPTIONAL_COLUMNS.items():
        if col not in have:
            conn.execute(
                text(f"ALTER TABLE {config.TABLE_NAME} ADD COLUMN {col} {sqltype}")
            )


def init_db() -> None:
    """Create the table, migrate missing columns, and (Postgres) the views."""
    pg = is_postgres()
    statements = _POSTGRES_DDL if pg else _SQLITE_DDL
    engine = get_engine()
    with engine.begin() as conn:
        for stmt in statements:
            if "CREATE OR REPLACE VIEW" not in stmt:
                conn.execute(text(stmt))
        _ensure_columns(conn, pg)
        if pg:
            for stmt in statements:
                if "CREATE OR REPLACE VIEW" in stmt:
                    conn.execute(text(stmt))
    where = "Postgres/Supabase" if pg else "SQLite"
    print(f"warehouse ready ({where}): {config.DATABASE_URL.split('@')[-1]}")


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------
def _existing_keys() -> set[tuple[str, str]]:
    """Set of (tree_name, lowercased scientific_name) already in the table."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"SELECT tree_name, scientific_name FROM {config.TABLE_NAME}")
        ).fetchall()
    return {(r[0], (r[1] or "").strip().lower()) for r in rows}


def append_dedup(df: pd.DataFrame) -> int:
    """Append rows, skipping any species already recorded for that tree."""
    init_db()
    df = df.copy()
    for col in WRITE_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df = df[WRITE_COLUMNS]

    df["scientific_name"] = df["scientific_name"].astype(str).str.strip()
    df["tree_name"] = df["tree_name"].astype(str).str.strip()
    df = df[df["scientific_name"] != ""]
    df["_key"] = list(zip(df["tree_name"], df["scientific_name"].str.lower()))
    df = df.drop_duplicates(subset="_key")

    have = _existing_keys()
    df = df[~df["_key"].isin(have)].drop(columns="_key")
    if df.empty:
        return 0

    df["ncbi_taxid"] = (
        pd.to_numeric(df["ncbi_taxid"], errors="coerce").astype("Int64")
    )
    df = df.astype(object).where(pd.notna(df), None)
    df.to_sql(config.TABLE_NAME, get_engine(), if_exists="append", index=False)
    return len(df)


def insert_request(
    tree_name: str,
    scientific_name: str,
    common_name: str | None = None,
    ncbi_taxid: int | None = None,
    domain: str | None = None,
    story: str | None = None,
    submitted_by: str | None = None,
    lineage: dict | None = None,
    notes: str | None = None,
) -> bool:
    """Add a single kiosk request. Returns True if it was new, False if a
    duplicate for that tree."""
    row = {
        "tree_name": tree_name,
        "common_name": common_name,
        "scientific_name": scientific_name,
        "ncbi_taxid": ncbi_taxid,
        "domain": domain,
        "story": story,
        "submitted_by": submitted_by,
        "notes": notes,
    }
    if lineage:
        for col in ("kingdom", "phylum", "class_", "order_", "family", "genus"):
            if lineage.get(col) is not None:
                row[col] = lineage[col]
        if lineage.get("domain") and not domain:
            row["domain"] = lineage["domain"]
    return append_dedup(pd.DataFrame([row])) == 1


def update_fields(tree_name: str, scientific_name: str, fields: dict) -> int:
    """Set arbitrary editable columns on one row. Returns rows updated. The
    natural key (tree_name, scientific_name) is protected; use rename_tree or
    delete + re-add to change those.
    """
    fields = {k: v for k, v in fields.items() if k in EDITABLE_COLUMNS}
    if not fields:
        return 0
    assignments = ", ".join(f"{k} = :{k}" for k in fields)
    params = dict(fields)
    params["tn"] = tree_name
    params["sn"] = scientific_name.strip().lower()
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text(
                f"UPDATE {config.TABLE_NAME} SET {assignments} "
                f"WHERE tree_name = :tn AND lower(scientific_name) = :sn"
            ),
            params,
        )
        return result.rowcount or 0


def update_taxid(tree_name: str, scientific_name: str, taxid: int) -> None:
    """Persist a resolved NCBI TaxID back to the row (used by enrichment)."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                f"UPDATE {config.TABLE_NAME} SET ncbi_taxid = :tid "
                f"WHERE tree_name = :tn AND lower(scientific_name) = :sn"
            ),
            {"tid": int(taxid), "tn": tree_name,
             "sn": scientific_name.strip().lower()},
        )


def rename_tree(old: str, new: str) -> int:
    """Rename a tree. Returns the number of rows updated. Fails gracefully if
    the new name collides with an existing tree by raising (the caller decides
    how to surface that in the UI)."""
    old, new = old.strip(), new.strip()
    if not new:
        raise ValueError("New tree name is empty.")
    if old == new:
        return 0
    engine = get_engine()
    with engine.begin() as conn:
        collision = conn.execute(
            text(f"SELECT count(*) FROM {config.TABLE_NAME} "
                 f"WHERE tree_name = :n"),
            {"n": new},
        ).scalar()
        if collision:
            raise ValueError(f"A tree named '{new}' already exists.")
        result = conn.execute(
            text(f"UPDATE {config.TABLE_NAME} SET tree_name = :n "
                 f"WHERE tree_name = :o"),
            {"n": new, "o": old},
        )
        return result.rowcount or 0


# ---------------------------------------------------------------------------
# Deletes
# ---------------------------------------------------------------------------
def delete_species(tree_name: str, scientific_name: str) -> int:
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text(
                f"DELETE FROM {config.TABLE_NAME} "
                f"WHERE tree_name = :tn AND lower(scientific_name) = :sn"
            ),
            {"tn": tree_name, "sn": scientific_name.strip().lower()},
        )
        return result.rowcount or 0


def delete_tree(tree_name: str) -> int:
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text(f"DELETE FROM {config.TABLE_NAME} WHERE tree_name = :tn"),
            {"tn": tree_name},
        )
        return result.rowcount or 0


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------
def read_tree(tree_name: str) -> pd.DataFrame:
    return pd.read_sql(
        text(
            f"SELECT * FROM {config.TABLE_NAME} "
            f"WHERE tree_name = :tn ORDER BY scientific_name"
        ),
        get_engine(),
        params={"tn": tree_name},
    )


def list_trees() -> pd.DataFrame:
    return pd.read_sql(
        text(
            f"SELECT tree_name, count(*) AS species_count, "
            f"sum(CASE WHEN ncbi_taxid IS NOT NULL THEN 1 ELSE 0 END) "
            f"AS resolved_count FROM {config.TABLE_NAME} "
            f"GROUP BY tree_name ORDER BY tree_name"
        ),
        get_engine(),
    )


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "init"
    if cmd == "init":
        init_db()
    elif cmd == "trees":
        print(list_trees().to_string(index=False))
    else:
        print(f"unknown command: {cmd}  (try: init, trees)")
