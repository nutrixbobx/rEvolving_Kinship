"""
Warehouse layer (v2 — 4NF+ schema on Supabase Postgres).

The public API is intentionally the same as v1 (init_db, read_tree,
list_trees, insert_request, rename_tree, delete_species, delete_tree,
update_fields, append_dedup) so consumers (tree.py, pipeline.py, station.py,
etl.py) keep working without changes. Internally the calls translate between
the old flat row shape and the new normalized tables:

    contributor                                 — anyone who writes data
    species              (PK species_id)        — one row per real species
    clade                (PK clade_id)          — taxonomic ancestry, shared
    species_clade        (M2M)                  — species → clades
    species_name         (PK name_id)           — multilingual / multicultural
    tree                 (PK tree_id)           — first-class trees with slug
    tree_species         (PK tree_id, species_id) — m2m + per-tree note

NCBI taxonomy stays where it was (taxa.sqlite via ete3, file-based).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

_engine: Engine | None = None

# Column names the v1 code expects on a read_tree() DataFrame. The
# v_legacy_species_rows view in schema_v2.sql produces all but `domain` and
# `story` which we add on the read path below.
WRITE_COLUMNS = [
    "tree_name", "common_name", "scientific_name", "ncbi_taxid",
    "domain", "kingdom", "phylum", "class_", "order_", "family", "genus",
    "story", "submitted_by", "notes",
]

EDITABLE_COLUMNS = [c for c in WRITE_COLUMNS
                    if c not in ("tree_name", "scientific_name")]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(config.DATABASE_URL, future=True,
                                pool_pre_ping=True)
    return _engine


def is_postgres() -> bool:
    return get_engine().dialect.name == "postgresql"


# ---------------------------------------------------------------------------
# Slug + safe-name helpers (kept here so the DB layer can guarantee uniqueness)
# ---------------------------------------------------------------------------
_SLUG_UNSAFE = re.compile(r'[\s/\\:*?"<>|#%&{}\(\),;]+')


def _safe_slug(name: str) -> str:
    if not isinstance(name, str):
        return "tree"
    s = name.strip().lower()
    s = _SLUG_UNSAFE.sub("_", s)
    s = re.sub(r"[^a-z0-9_\-]+", "", s)
    s = re.sub(r"_+", "_", s).strip("_-")
    return s or "tree"


# ---------------------------------------------------------------------------
# init_db — verify the v2 schema is present in Supabase
# ---------------------------------------------------------------------------
def init_db() -> None:
    """Verify the v2 schema is applied. wipe_and_init.sql + schema_v2.sql must
    be run in the Supabase SQL editor before the app starts."""
    engine = get_engine()
    with engine.connect() as conn:
        n = conn.execute(text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'public' "
            "AND table_name IN ('tree','species','species_name',"
            "'tree_species','clade','contributor')"
        )).scalar() or 0
    if int(n) < 6:
        raise RuntimeError(
            "v2 schema missing. Run db/wipe_and_init.sql then "
            "db/schema_v2.sql in the Supabase SQL editor.")
    where = "Postgres/Supabase" if is_postgres() else "SQLite"
    print(f"warehouse ready ({where}, schema v2): "
          f"{config.DATABASE_URL.split('@')[-1]}")


# ---------------------------------------------------------------------------
# Contributors
# ---------------------------------------------------------------------------
def get_or_create_contributor(display_name: str | None) -> str | None:
    """Return contributor_id (UUID string) or None if no name supplied."""
    if not display_name:
        return None
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT contributor_id FROM contributor "
                 "WHERE display_name = :n LIMIT 1"),
            {"n": display_name},
        ).fetchone()
        if row:
            return str(row[0])
        new = conn.execute(
            text("INSERT INTO contributor (display_name, role) "
                 "VALUES (:n, 'visitor') RETURNING contributor_id"),
            {"n": display_name},
        ).fetchone()
        return str(new[0])


# ---------------------------------------------------------------------------
# Trees
# ---------------------------------------------------------------------------
def get_tree_id(tree_name: str) -> str | None:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT tree_id FROM tree WHERE name = :n LIMIT 1"),
            {"n": tree_name.strip()},
        ).fetchone()
    return str(row[0]) if row else None


def get_or_create_tree(tree_name: str,
                       owner_display_name: str | None = None) -> str:
    name = tree_name.strip()
    existing = get_tree_id(name)
    if existing:
        return existing
    slug = _safe_slug(name)
    owner_id = get_or_create_contributor(owner_display_name) if owner_display_name else None
    # If the slug collides (different display name, same slug) append a suffix.
    engine = get_engine()
    with engine.begin() as conn:
        attempt = slug
        for i in range(1, 50):
            row = conn.execute(
                text("SELECT 1 FROM tree WHERE slug = :s"),
                {"s": attempt},
            ).fetchone()
            if not row:
                break
            attempt = f"{slug}-{i}"
        new = conn.execute(
            text("INSERT INTO tree (name, slug, owner_id) "
                 "VALUES (:n, :s, :o) RETURNING tree_id"),
            {"n": name, "s": attempt, "o": owner_id},
        ).fetchone()
        return str(new[0])


def rename_tree(old: str, new: str) -> int:
    """Rename a tree by string-old / string-new for back-compat with the kiosk.
    Returns 1 on success, 0 if no such tree."""
    old, new = old.strip(), new.strip()
    if not new:
        raise ValueError("New tree name is empty.")
    if old == new:
        return 0
    engine = get_engine()
    with engine.begin() as conn:
        # Collision check
        col = conn.execute(
            text("SELECT count(*) FROM tree WHERE name = :n"),
            {"n": new},
        ).scalar()
        if col:
            raise ValueError(f"A tree named '{new}' already exists.")
        # Update both name and slug
        new_slug = _safe_slug(new)
        attempt = new_slug
        for i in range(1, 50):
            row = conn.execute(
                text("SELECT 1 FROM tree WHERE slug = :s AND name <> :o"),
                {"s": attempt, "o": old},
            ).fetchone()
            if not row:
                break
            attempt = f"{new_slug}-{i}"
        result = conn.execute(
            text("UPDATE tree SET name = :n, slug = :s WHERE name = :o"),
            {"n": new, "s": attempt, "o": old},
        )
        return int(result.rowcount or 0)


def delete_tree(tree_name: str) -> int:
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM tree WHERE name = :n"),
            {"n": tree_name},
        )
        return int(result.rowcount or 0)


# ---------------------------------------------------------------------------
# Species
# ---------------------------------------------------------------------------
def get_or_create_species(ncbi_taxid: int, scientific_name: str,
                          rank: str | None = None) -> str:
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT species_id FROM species WHERE ncbi_taxid = :t"),
            {"t": int(ncbi_taxid)},
        ).fetchone()
        if row:
            return str(row[0])
        new = conn.execute(
            text("INSERT INTO species (ncbi_taxid, canonical_scientific_name, rank) "
                 "VALUES (:t, :n, :r) RETURNING species_id"),
            {"t": int(ncbi_taxid), "n": scientific_name, "r": rank},
        ).fetchone()
        return str(new[0])


def add_species_name(species_id: str, name_text: str,
                     language: str = "en",
                     category: str = "common",
                     source: str = "community",
                     is_preferred: bool = False,
                     contributor_id: str | None = None) -> None:
    if not name_text or not name_text.strip():
        return
    name_text = name_text.strip()
    engine = get_engine()
    with engine.begin() as conn:
        # If marking this as preferred, demote any others first so there is
        # only one preferred name per (species, language, category).
        if is_preferred:
            conn.execute(
                text("""
                    UPDATE species_name
                    SET is_preferred = false
                    WHERE species_id = :s
                      AND language_code = :l
                      AND name_category = :c
                      AND lower(name_text) <> lower(:n)
                """),
                {"s": species_id, "l": language, "c": category, "n": name_text},
            )
        conn.execute(
            text("""
                INSERT INTO species_name
                    (species_id, name_text, language_code, name_category,
                     source, is_preferred, contributed_by)
                VALUES (:s, :n, :l, :c, :src, :p, :by)
                ON CONFLICT (species_id, name_text, language_code, name_category)
                DO UPDATE SET is_preferred = EXCLUDED.is_preferred
            """),
            {"s": species_id, "n": name_text, "l": language,
             "c": category, "src": source, "p": is_preferred,
             "by": contributor_id},
        )


# ---------------------------------------------------------------------------
# tree_species (the actual link rows)
# ---------------------------------------------------------------------------
def add_species_to_tree(tree_id: str, species_id: str,
                        note: str | None = None,
                        added_by: str | None = None) -> bool:
    engine = get_engine()
    with engine.begin() as conn:
        # Check existing
        row = conn.execute(
            text("SELECT 1 FROM tree_species "
                 "WHERE tree_id = :t AND species_id = :s"),
            {"t": tree_id, "s": species_id},
        ).fetchone()
        if row:
            return False
        conn.execute(
            text("INSERT INTO tree_species (tree_id, species_id, note, added_by) "
                 "VALUES (:t, :s, :n, :a)"),
            {"t": tree_id, "s": species_id, "n": note, "a": added_by},
        )
        return True


def link_species_to_clades(species_id: str,
                            clade_chain: list[dict]) -> int:
    """Given an ordered chain of clade dicts (root -> species), upsert each
    clade and link species_clade. Sets clade.parent_clade_id to the previous
    surviving clade so the in-table tree reflects ancestry filtered to the
    ranks we store. Returns the number of clades linked. Idempotent."""
    if not clade_chain:
        return 0
    n = 0
    parent_id: str | None = None
    engine = get_engine()
    with engine.begin() as conn:
        for cl in clade_chain:
            taxid_int = int(cl["taxid"])
            existing = conn.execute(
                text("SELECT clade_id FROM clade WHERE ncbi_taxid = :t"),
                {"t": taxid_int},
            ).fetchone()
            if existing:
                clade_id = str(existing[0])
                # Backfill mya/parent if missing
                conn.execute(
                    text("""
                        UPDATE clade
                        SET parent_clade_id = COALESCE(parent_clade_id, :p),
                            divergence_mya  = COALESCE(divergence_mya, :m)
                        WHERE clade_id = :c
                    """),
                    {"p": parent_id, "m": cl.get("mya"), "c": clade_id},
                )
            else:
                row = conn.execute(
                    text("""
                        INSERT INTO clade
                          (ncbi_taxid, name, rank, parent_clade_id,
                           divergence_mya)
                        VALUES (:t, :n, :r, :p, :m)
                        ON CONFLICT (ncbi_taxid) DO NOTHING
                        RETURNING clade_id
                    """),
                    {"t": taxid_int, "n": cl["name"], "r": cl.get("rank"),
                     "p": parent_id, "m": cl.get("mya")},
                ).fetchone()
                if row:
                    clade_id = str(row[0])
                else:
                    # Race: someone else inserted between our SELECT and INSERT.
                    re_row = conn.execute(
                        text("SELECT clade_id FROM clade WHERE ncbi_taxid = :t"),
                        {"t": taxid_int},
                    ).fetchone()
                    clade_id = str(re_row[0])
            # Link species_clade (no-op if already there)
            conn.execute(
                text("""
                    INSERT INTO species_clade (species_id, clade_id)
                    VALUES (:s, :c)
                    ON CONFLICT DO NOTHING
                """),
                {"s": species_id, "c": clade_id},
            )
            parent_id = clade_id
            n += 1
    return n


def _link_clades_for_taxid(species_id: str, ncbi_taxid: int) -> int:
    """Resolve the NCBI lineage for a taxid and link the filtered clade chain
    to one species. Used by insert_request and backfill_clades. Best-effort:
    if NCBI lookup fails, returns 0 without raising."""
    try:
        from src import taxonomy_search as ts
        lin = ts.lineage_clades_for_taxid(int(ncbi_taxid))
    except Exception as exc:
        print(f"  clade lookup failed for taxid {ncbi_taxid}: {exc}")
        return 0
    if not lin or not lin.get("clades"):
        return 0
    return link_species_to_clades(species_id, lin["clades"])


def delete_species(tree_name: str, scientific_name: str) -> int:
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                DELETE FROM tree_species ts
                USING tree t, species s
                WHERE ts.tree_id = t.tree_id
                  AND ts.species_id = s.species_id
                  AND t.name = :tn
                  AND lower(s.canonical_scientific_name) = lower(:sn)
            """),
            {"tn": tree_name, "sn": scientific_name.strip()},
        )
        return int(result.rowcount or 0)


# ---------------------------------------------------------------------------
# The "back-compat insert" path used by the kiosk and the dashboard editor.
# ---------------------------------------------------------------------------
def insert_request(
    tree_name: str,
    scientific_name: str,
    common_name: str | None = None,
    ncbi_taxid: int | None = None,
    domain: str | None = None,        # ignored in v2 (lives in cultural layer)
    story: str | None = None,         # routed into the story table
    submitted_by: str | None = None,
    lineage: dict | None = None,      # ignored in v2 for now (TODO: upsert clade)
    notes: str | None = None,
) -> bool:
    """Add a species to a tree. Same signature as v1 so the kiosk's
    add-to-tree path keeps working without a rewrite. Returns True if a new
    tree_species row was created, False if the species was already in the tree.

    The taxid + scientific name path is required (we can't dedup without
    a taxid). If you don't have one, raise.
    """
    if ncbi_taxid is None:
        raise ValueError(
            "v2 requires an NCBI TaxID for every species. The kiosk's "
            "species search returns one; the manual-name path is no "
            "longer supported.")

    contributor_id = get_or_create_contributor(submitted_by)
    tree_id = get_or_create_tree(tree_name, owner_display_name=submitted_by)
    species_id = get_or_create_species(int(ncbi_taxid), scientific_name.strip())
    # Populate clade + species_clade. Idempotent: re-adding the same species
    # to a different tree just no-ops on the conflicts.
    _link_clades_for_taxid(species_id, int(ncbi_taxid))

    if common_name:
        add_species_name(species_id, common_name, language="en",
                         category="common", source="community",
                         is_preferred=True, contributor_id=contributor_id)

    is_new = add_species_to_tree(tree_id, species_id,
                                 note=notes,
                                 added_by=contributor_id)
    # Story optional: if supplied, write to story table
    if story:
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO story (species_id, tree_id, body_text,
                                       contributed_by)
                    VALUES (:s, :t, :b, :c)
                """),
                {"s": species_id, "t": tree_id, "b": story,
                 "c": contributor_id},
            )
    return is_new


# ---------------------------------------------------------------------------
# Edits (back-compat for the dashboard editor)
# ---------------------------------------------------------------------------
def update_fields(tree_name: str, scientific_name: str, fields: dict) -> int:
    """Update editable fields on a species in a tree. v1 wrote to columns;
    v2 distributes the changes:
        common_name → upserted into species_name (en, common, preferred=true)
        notes       → updated in tree_species.note
        story       → inserted into story table
        ncbi_taxid  → ignored (species is keyed by taxid; changing it is a
                      delete + re-add)
        kingdom..genus → TODO: upsert clade + species_clade (logged for now)
    Returns the number of underlying writes performed."""
    fields = {k: v for k, v in fields.items() if k in EDITABLE_COLUMNS}
    if not fields:
        return 0

    engine = get_engine()
    n_writes = 0
    with engine.begin() as conn:
        row = conn.execute(
            text("""SELECT s.species_id, t.tree_id
                    FROM tree t, species s, tree_species ts
                    WHERE ts.tree_id = t.tree_id
                      AND ts.species_id = s.species_id
                      AND t.name = :tn
                      AND lower(s.canonical_scientific_name) = lower(:sn)
                    LIMIT 1"""),
            {"tn": tree_name, "sn": scientific_name},
        ).fetchone()
        if not row:
            return 0
        species_id, tree_id = str(row[0]), str(row[1])

        if "common_name" in fields:
            new_name = (fields["common_name"] or "").strip()
            # Always demote any other preferred common name for this species
            # in this language, so there's only ever one preferred at a time.
            conn.execute(
                text("""
                    UPDATE species_name
                    SET is_preferred = false
                    WHERE species_id = :s
                      AND language_code = 'en'
                      AND name_category = 'common'
                      AND lower(name_text) <> lower(:n)
                """),
                {"s": species_id, "n": new_name},
            )
            n_writes += 1
            if new_name:
                # Insert or promote the new preferred name
                conn.execute(
                    text("""
                        INSERT INTO species_name
                            (species_id, name_text, language_code,
                             name_category, source, is_preferred)
                        VALUES (:s, :n, 'en', 'common', 'community', true)
                        ON CONFLICT (species_id, name_text, language_code, name_category)
                        DO UPDATE SET is_preferred = true
                    """),
                    {"s": species_id, "n": new_name},
                )
                n_writes += 1

        if "notes" in fields:
            conn.execute(
                text("UPDATE tree_species SET note = :n "
                     "WHERE tree_id = :t AND species_id = :s"),
                {"n": fields["notes"], "t": tree_id, "s": species_id},
            )
            n_writes += 1

        if "story" in fields and fields["story"]:
            conn.execute(
                text("""
                    INSERT INTO story (species_id, tree_id, body_text)
                    VALUES (:s, :t, :b)
                """),
                {"s": species_id, "t": tree_id, "b": fields["story"]},
            )
            n_writes += 1
        # kingdom..genus / domain: TODO in next phase (clade upsert)
    return n_writes


def update_taxid(*args, **kwargs) -> None:
    """No-op in v2 — species is keyed by ncbi_taxid; you can't change it."""
    return None


# ---------------------------------------------------------------------------
# Reads (back-compat: same DataFrame shape as v1)
# ---------------------------------------------------------------------------
_READ_TREE_SQL = text("""
    SELECT
        t.name                              AS tree_name,
        (SELECT sn.name_text FROM species_name sn
            WHERE sn.species_id = s.species_id
              AND sn.language_code = 'en'
              AND sn.name_category = 'common'
              AND sn.is_preferred = true
            ORDER BY sn.contributed_at DESC LIMIT 1)
                                            AS common_name,
        s.canonical_scientific_name         AS scientific_name,
        s.ncbi_taxid                        AS ncbi_taxid,
        (CASE
            WHEN s.ncbi_taxid = 9606 THEN 'Human'
            WHEN EXISTS (SELECT 1 FROM species_clade sc JOIN clade c
                            ON c.clade_id = sc.clade_id
                            WHERE sc.species_id = s.species_id
                              AND c.ncbi_taxid = 50557) THEN 'Insect'
            WHEN EXISTS (SELECT 1 FROM species_clade sc JOIN clade c
                            ON c.clade_id = sc.clade_id
                            WHERE sc.species_id = s.species_id
                              AND c.ncbi_taxid = 33208) THEN 'Animal'
            WHEN EXISTS (SELECT 1 FROM species_clade sc JOIN clade c
                            ON c.clade_id = sc.clade_id
                            WHERE sc.species_id = s.species_id
                              AND c.ncbi_taxid = 33090) THEN 'Plant'
            WHEN EXISTS (SELECT 1 FROM species_clade sc JOIN clade c
                            ON c.clade_id = sc.clade_id
                            WHERE sc.species_id = s.species_id
                              AND c.ncbi_taxid = 4751) THEN 'Fungi'
            ELSE 'Other'
        END)                                AS domain,
        (SELECT c.name FROM species_clade sc JOIN clade c
            ON c.clade_id = sc.clade_id
            WHERE sc.species_id = s.species_id AND c.rank = 'kingdom' LIMIT 1)
                                            AS kingdom,
        (SELECT c.name FROM species_clade sc JOIN clade c
            ON c.clade_id = sc.clade_id
            WHERE sc.species_id = s.species_id AND c.rank = 'phylum' LIMIT 1)
                                            AS phylum,
        (SELECT c.name FROM species_clade sc JOIN clade c
            ON c.clade_id = sc.clade_id
            WHERE sc.species_id = s.species_id AND c.rank = 'class' LIMIT 1)
                                            AS class_,
        (SELECT c.name FROM species_clade sc JOIN clade c
            ON c.clade_id = sc.clade_id
            WHERE sc.species_id = s.species_id AND c.rank = 'order' LIMIT 1)
                                            AS order_,
        (SELECT c.name FROM species_clade sc JOIN clade c
            ON c.clade_id = sc.clade_id
            WHERE sc.species_id = s.species_id AND c.rank = 'family' LIMIT 1)
                                            AS family,
        (SELECT c.name FROM species_clade sc JOIN clade c
            ON c.clade_id = sc.clade_id
            WHERE sc.species_id = s.species_id AND c.rank = 'genus' LIMIT 1)
                                            AS genus,
        (SELECT st.body_text FROM story st
            WHERE st.species_id = s.species_id AND st.is_published = true
            ORDER BY st.contributed_at DESC LIMIT 1)
                                            AS story,
        co.display_name                     AS submitted_by,
        ts.note                             AS notes,
        ts.added_at                         AS created_at
    FROM tree_species ts
    JOIN tree t        ON t.tree_id     = ts.tree_id
    JOIN species s     ON s.species_id  = ts.species_id
    LEFT JOIN contributor co ON co.contributor_id = ts.added_by
    WHERE t.name = :tn
    ORDER BY s.canonical_scientific_name
""")


def read_tree(tree_name: str) -> pd.DataFrame:
    """All rows for one tree, in v1-compatible column shape."""
    return pd.read_sql(_READ_TREE_SQL, get_engine(), params={"tn": tree_name})


def list_trees() -> pd.DataFrame:
    """One row per tree with a species count. v1-compatible shape."""
    return pd.read_sql(
        text("""
            SELECT
                t.name                                       AS tree_name,
                (SELECT count(*) FROM tree_species ts
                    WHERE ts.tree_id = t.tree_id)            AS species_count,
                (SELECT count(*) FROM tree_species ts JOIN species s
                    ON s.species_id = ts.species_id
                    WHERE ts.tree_id = t.tree_id
                      AND s.ncbi_taxid IS NOT NULL)          AS resolved_count
            FROM tree t
            ORDER BY t.name
        """),
        get_engine(),
    )


# ---------------------------------------------------------------------------
# Bulk loader (back-compat for etl.py)
# ---------------------------------------------------------------------------
def append_dedup(df: pd.DataFrame) -> int:
    """Append rows from a CSV-shaped DataFrame, skipping species already in
    that tree. Same return semantics as v1: number of new rows added."""
    if df.empty:
        return 0
    init_db()
    inserted = 0
    for _, row in df.iterrows():
        sci = row.get("scientific_name")
        tree_name = row.get("tree_name")
        if not isinstance(sci, str) or not sci.strip():
            continue
        if not isinstance(tree_name, str) or not tree_name.strip():
            continue
        taxid = row.get("ncbi_taxid")
        try:
            taxid_int = int(taxid) if taxid not in (None, "") and pd.notna(taxid) else None
        except (TypeError, ValueError):
            taxid_int = None
        if taxid_int is None:
            # Try to resolve from taxonomy_search at load time
            try:
                from src import taxonomy_search as ts
                hit = ts.resolve_exact(sci.strip())
                if hit:
                    taxid_int = hit["taxid"]
            except Exception:
                pass
        if taxid_int is None:
            print(f"  skip {sci}: no NCBI TaxID resolved")
            continue
        try:
            is_new = insert_request(
                tree_name=tree_name.strip(),
                scientific_name=sci.strip(),
                common_name=(row.get("common_name") or None),
                ncbi_taxid=taxid_int,
                domain=row.get("domain"),
                story=row.get("story"),
                submitted_by=row.get("submitted_by") or "csv-import",
                notes=row.get("notes"),
            )
            if is_new:
                inserted += 1
        except Exception as exc:
            print(f"  err {sci}: {exc}")
    return inserted


def backfill_clades() -> tuple[int, int]:
    """Walk every species and re-run the clade link. For species inserted
    before the v2 clade pipeline landed, this is the one-shot to populate
    their kingdom..genus rows. Returns (species_processed, clades_linked)."""
    engine = get_engine()
    init_db()
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT species_id, ncbi_taxid, canonical_scientific_name "
                 "FROM species ORDER BY canonical_scientific_name")
        ).fetchall()
    total_linked = 0
    for r in rows:
        species_id = str(r[0])
        taxid = int(r[1]) if r[1] is not None else None
        sci = r[2]
        if not taxid:
            print(f"  skip {sci}: no NCBI taxid")
            continue
        n = _link_clades_for_taxid(species_id, taxid)
        print(f"  {sci:40} linked {n} clades")
        total_linked += n
    return len(rows), total_linked




# ---------------------------------------------------------------------------
# Community-layer reads (Library tab)
#
# All return pandas DataFrames suitable for st.dataframe. Joins resolve
# species + tree + contributor display so the dataframes are self-explanatory
# without extra UI work.
# ---------------------------------------------------------------------------
def list_stories() -> pd.DataFrame:
    return pd.read_sql(text("""
        SELECT st.story_id, st.title,
               s.canonical_scientific_name        AS species,
               t.name                              AS tree,
               st.language_code                    AS language,
               st.region_code                      AS region,
               SUBSTRING(st.body_text, 1, 240)     AS body_preview,
               co.display_name                     AS contributor,
               st.contributed_at
        FROM story st
        LEFT JOIN species s     ON s.species_id = st.species_id
        LEFT JOIN tree t        ON t.tree_id    = st.tree_id
        LEFT JOIN contributor co ON co.contributor_id = st.contributed_by
        WHERE st.is_published = true
        ORDER BY st.contributed_at DESC
    """), get_engine())


def list_dishes() -> pd.DataFrame:
    return pd.read_sql(text("""
        SELECT d.dish_id, d.name, d.cuisine, d.origin_region, d.description,
               (SELECT count(DISTINCT ds.species_id) FROM dish_species ds
                  WHERE ds.dish_id = d.dish_id) AS ingredient_count,
               co.display_name AS contributor,
               d.contributed_at
        FROM dish d
        LEFT JOIN contributor co ON co.contributor_id = d.contributed_by
        ORDER BY d.contributed_at DESC
    """), get_engine())


def list_dish_ingredients(dish_id: str | None = None) -> pd.DataFrame:
    base = """
        SELECT d.name AS dish, d.cuisine,
               s.canonical_scientific_name AS species_scientific,
               (SELECT sn.name_text FROM species_name sn
                  WHERE sn.species_id = s.species_id
                    AND sn.language_code = 'en'
                    AND sn.name_category = 'common'
                    AND sn.is_preferred = true LIMIT 1) AS species_common,
               ds.role, ds.quantity_note
        FROM dish_species ds
        JOIN dish d    ON d.dish_id    = ds.dish_id
        JOIN species s ON s.species_id = ds.species_id
    """
    if dish_id:
        return pd.read_sql(
            text(base + " WHERE d.dish_id = :d ORDER BY ds.role"),
            get_engine(), params={"d": dish_id})
    return pd.read_sql(
        text(base + " ORDER BY d.name, ds.role"), get_engine())


def list_pantheons() -> pd.DataFrame:
    return pd.read_sql(text("""
        SELECT p.pantheon_id, p.name, p.region, p.tradition_type,
               (SELECT count(*) FROM deity
                  WHERE pantheon_id = p.pantheon_id) AS deities_count,
               (SELECT count(DISTINCT sd.species_id)
                  FROM deity de
                  JOIN species_deity sd ON sd.deity_id = de.deity_id
                  WHERE de.pantheon_id = p.pantheon_id) AS species_count
        FROM pantheon p
        ORDER BY p.name
    """), get_engine())


def list_species_deities() -> pd.DataFrame:
    return pd.read_sql(text("""
        SELECT s.canonical_scientific_name AS species,
               (SELECT sn.name_text FROM species_name sn
                  WHERE sn.species_id = s.species_id
                    AND sn.language_code = 'en'
                    AND sn.name_category = 'common'
                    AND sn.is_preferred = true LIMIT 1) AS common_name,
               de.name AS deity, p.name AS pantheon,
               sd.relationship, sd.note
        FROM species_deity sd
        JOIN species s   ON s.species_id   = sd.species_id
        JOIN deity de    ON de.deity_id    = sd.deity_id
        JOIN pantheon p  ON p.pantheon_id  = de.pantheon_id
        ORDER BY s.canonical_scientific_name, p.name, de.name
    """), get_engine())


def list_cultural_connections() -> pd.DataFrame:
    return pd.read_sql(text("""
        SELECT cc.connection_id,
               s.canonical_scientific_name AS species,
               (SELECT sn.name_text FROM species_name sn
                  WHERE sn.species_id = s.species_id
                    AND sn.language_code = 'en'
                    AND sn.name_category = 'common'
                    AND sn.is_preferred = true LIMIT 1) AS common_name,
               cc.culture, cc.significance_type, cc.description, cc.source,
               co.display_name AS contributor
        FROM cultural_connection cc
        JOIN species s ON s.species_id = cc.species_id
        LEFT JOIN contributor co ON co.contributor_id = cc.contributed_by
        ORDER BY s.canonical_scientific_name, cc.culture
    """), get_engine())


def list_all_names() -> pd.DataFrame:
    return pd.read_sql(text("""
        SELECT s.canonical_scientific_name AS species,
               sn.name_text,
               sn.language_code   AS language,
               sn.name_category   AS category,
               sn.region_code     AS region,
               sn.is_preferred,
               sn.source,
               co.display_name    AS contributor
        FROM species_name sn
        JOIN species s ON s.species_id = sn.species_id
        LEFT JOIN contributor co ON co.contributor_id = sn.contributed_by
        ORDER BY s.canonical_scientific_name, sn.language_code,
                 sn.is_preferred DESC, sn.name_text
    """), get_engine())


def list_species_for_picker() -> pd.DataFrame:
    """For dropdowns: species_id + canonical + preferred common name."""
    return pd.read_sql(text("""
        SELECT s.species_id, s.canonical_scientific_name,
               (SELECT sn.name_text FROM species_name sn
                  WHERE sn.species_id = s.species_id
                    AND sn.language_code = 'en'
                    AND sn.name_category = 'common'
                    AND sn.is_preferred = true LIMIT 1) AS common_name
        FROM species s
        ORDER BY common_name NULLS LAST, s.canonical_scientific_name
    """), get_engine())




def list_species_overview() -> pd.DataFrame:
    """Every canonical species with counts across the community layer.
    Lets the Library tab show how rich each species' kinship layer is."""
    return pd.read_sql(text("""
        SELECT
            s.canonical_scientific_name AS scientific_name,
            (SELECT sn.name_text FROM species_name sn
                WHERE sn.species_id = s.species_id
                  AND sn.language_code = 'en'
                  AND sn.name_category = 'common'
                  AND sn.is_preferred = true LIMIT 1) AS common_name,
            s.rank,
            s.ncbi_taxid,
            (CASE
              WHEN s.ncbi_taxid = 9606 THEN 'Human'
              WHEN EXISTS (SELECT 1 FROM species_clade sc JOIN clade c
                  ON c.clade_id = sc.clade_id
                  WHERE sc.species_id = s.species_id
                    AND c.ncbi_taxid = 50557) THEN 'Insect'
              WHEN EXISTS (SELECT 1 FROM species_clade sc JOIN clade c
                  ON c.clade_id = sc.clade_id
                  WHERE sc.species_id = s.species_id
                    AND c.ncbi_taxid = 33208) THEN 'Animal'
              WHEN EXISTS (SELECT 1 FROM species_clade sc JOIN clade c
                  ON c.clade_id = sc.clade_id
                  WHERE sc.species_id = s.species_id
                    AND c.ncbi_taxid = 33090) THEN 'Plant'
              WHEN EXISTS (SELECT 1 FROM species_clade sc JOIN clade c
                  ON c.clade_id = sc.clade_id
                  WHERE sc.species_id = s.species_id
                    AND c.ncbi_taxid = 4751) THEN 'Fungi'
              ELSE 'Other'
            END) AS "group",
            (SELECT count(*) FROM species_name sn
                WHERE sn.species_id = s.species_id) AS names_count,
            (SELECT count(DISTINCT sn.language_code) FROM species_name sn
                WHERE sn.species_id = s.species_id) AS languages_count,
            (SELECT count(*) FROM story st
                WHERE st.species_id = s.species_id) AS stories_count,
            (SELECT count(*) FROM dish_species ds
                WHERE ds.species_id = s.species_id) AS dishes_count,
            (SELECT count(*) FROM species_deity sd
                WHERE sd.species_id = s.species_id) AS deities_count,
            (SELECT count(*) FROM cultural_connection cc
                WHERE cc.species_id = s.species_id) AS connections_count,
            (SELECT count(DISTINCT tree_id) FROM tree_species ts
                WHERE ts.species_id = s.species_id) AS trees_count
        FROM species s
        ORDER BY s.canonical_scientific_name
    """), get_engine())


# ---------------------------------------------------------------------------
# Community-layer writes (Library admin entry forms)
# ---------------------------------------------------------------------------
def add_story(body_text: str,
              species_id: str | None = None,
              tree_id: str | None = None,
              title: str | None = None,
              language: str = "en",
              region: str | None = None,
              contributor_id: str | None = None) -> str:
    if not body_text or not body_text.strip():
        raise ValueError("Story body text is required.")
    if not species_id and not tree_id:
        raise ValueError("Story must be linked to a species or a tree.")
    engine = get_engine()
    with engine.begin() as conn:
        new = conn.execute(
            text("""INSERT INTO story (species_id, tree_id, title, body_text,
                                       language_code, region_code,
                                       contributed_by)
                    VALUES (:s, :t, :ti, :b, :l, :r, :c)
                    RETURNING story_id"""),
            {"s": species_id, "t": tree_id, "ti": title,
             "b": body_text.strip(), "l": language,
             "r": region, "c": contributor_id},
        ).fetchone()
        return str(new[0])


def add_dish(name: str,
             origin_region: str | None = None,
             cuisine: str | None = None,
             description: str | None = None,
             contributor_id: str | None = None) -> str:
    if not name or not name.strip():
        raise ValueError("Dish name is required.")
    engine = get_engine()
    with engine.begin() as conn:
        new = conn.execute(
            text("""INSERT INTO dish (name, origin_region, cuisine,
                                       description, contributed_by)
                    VALUES (:n, :o, :c, :d, :by)
                    RETURNING dish_id"""),
            {"n": name.strip(), "o": origin_region, "c": cuisine,
             "d": description, "by": contributor_id},
        ).fetchone()
        return str(new[0])


def link_dish_species(dish_id: str, species_id: str,
                      role: str = "ingredient",
                      quantity_note: str | None = None) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO dish_species
                       (dish_id, species_id, role, quantity_note)
                    VALUES (:d, :s, :r, :q)
                    ON CONFLICT (dish_id, species_id, role)
                    DO UPDATE SET quantity_note = EXCLUDED.quantity_note"""),
            {"d": dish_id, "s": species_id, "r": role, "q": quantity_note},
        )


def add_pantheon(name: str, region: str | None = None,
                 tradition_type: str = "mythological") -> str:
    if not name or not name.strip():
        raise ValueError("Pantheon name is required.")
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT pantheon_id FROM pantheon WHERE name = :n"),
            {"n": name.strip()},
        ).fetchone()
        if row:
            return str(row[0])
        new = conn.execute(
            text("""INSERT INTO pantheon (name, region, tradition_type)
                    VALUES (:n, :r, :t)
                    RETURNING pantheon_id"""),
            {"n": name.strip(), "r": region, "t": tradition_type},
        ).fetchone()
        return str(new[0])


def add_deity(pantheon_id: str, name: str,
              aliases: list[str] | None = None,
              domain: str | None = None) -> str:
    if not name or not name.strip():
        raise ValueError("Deity name is required.")
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT deity_id FROM deity "
                 "WHERE pantheon_id = :p AND name = :n"),
            {"p": pantheon_id, "n": name.strip()},
        ).fetchone()
        if row:
            return str(row[0])
        new = conn.execute(
            text("""INSERT INTO deity (pantheon_id, name, aliases, domain)
                    VALUES (:p, :n, :a, :d)
                    RETURNING deity_id"""),
            {"p": pantheon_id, "n": name.strip(),
             "a": aliases or [], "d": domain},
        ).fetchone()
        return str(new[0])


def link_species_deity(species_id: str, deity_id: str,
                       relationship: str = "sacred_to",
                       note: str | None = None,
                       contributor_id: str | None = None) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO species_deity
                       (species_id, deity_id, relationship,
                        note, contributed_by)
                    VALUES (:s, :d, :r, :n, :c)
                    ON CONFLICT (species_id, deity_id, relationship)
                    DO UPDATE SET note = EXCLUDED.note"""),
            {"s": species_id, "d": deity_id, "r": relationship,
             "n": note, "c": contributor_id},
        )


def add_cultural_connection(species_id: str, culture: str,
                            significance_type: str | None = None,
                            description: str | None = None,
                            source: str | None = None,
                            contributor_id: str | None = None) -> str:
    if not culture or not culture.strip():
        raise ValueError("Culture is required.")
    engine = get_engine()
    with engine.begin() as conn:
        new = conn.execute(
            text("""INSERT INTO cultural_connection
                       (species_id, culture, significance_type, description,
                        source, contributed_by)
                    VALUES (:s, :c, :t, :d, :src, :by)
                    RETURNING connection_id"""),
            {"s": species_id, "c": culture.strip(),
             "t": significance_type, "d": description,
             "src": source, "by": contributor_id},
        ).fetchone()
        return str(new[0])



if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "init"
    if cmd == "init":
        init_db()
    elif cmd == "trees":
        print(list_trees().to_string(index=False))
    elif cmd == "backfill-clades":
        n_species, n_links = backfill_clades()
        print(f"done. {n_species} species walked, {n_links} clade links written.")
    else:
        print(f"unknown command: {cmd}  "
              "(try: init, trees, backfill-clades)")
