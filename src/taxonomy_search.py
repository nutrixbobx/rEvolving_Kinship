"""
Species name search and validation.

This reads ete3's local NCBI database directly (read only), so it is fast enough
for type-ahead. It powers two things:

  - search_species: the kiosk type-ahead. A visitor types part of a common or
    scientific name and gets back real matches to choose from.
  - resolve_exact / suggest: the submit-time check. Before a row is saved we
    confirm it maps to a real NCBI TaxID, so the warehouse never holds a null.

The database is the same taxa.sqlite ete3 builds on first run. If it is not
there yet, these functions say so clearly instead of failing oddly.
"""

from __future__ import annotations

import os
import sqlite3


def db_path() -> str:
    """Path to ete3's taxonomy SQLite, honoring a custom NCBI_TAXA_DB."""
    from ete3.ncbi_taxonomy.ncbiquery import DEFAULT_TAXADB
    custom = os.environ.get("NCBI_TAXA_DB")
    if custom and os.path.exists(custom):
        return custom
    return DEFAULT_TAXADB


def is_ready() -> bool:
    return os.path.exists(db_path())


def _connect() -> sqlite3.Connection:
    path = db_path()
    if not os.path.exists(path):
        raise FileNotFoundError(
            "The NCBI database is not built yet. Run the pipeline once, or "
            "`python -m src.build_taxonomy` (see the README if downloads are "
            "blocked)."
        )
    # read only, so the kiosk can never corrupt the taxonomy
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True,
                           check_same_thread=False)


def search_species(query: str, limit: int = 10) -> list[dict]:
    """
    Type-ahead search by common or scientific name.

    Returns a list of dicts: taxid, scientific_name, common_name, rank.
    Prefix matches come first, then species before genus, then shorter names.
    """
    query = (query or "").strip().replace("%", "")
    if len(query) < 2:
        return []
    prefix = query + "%"
    contains = "%" + query + "%"
    sql = """
        SELECT taxid, spname, common, rank FROM species
        WHERE rank IN ('species', 'subspecies', 'genus')
          AND (spname LIKE ? OR common LIKE ?)
        ORDER BY
          CASE WHEN spname LIKE ? OR common LIKE ? THEN 0 ELSE 1 END,
          CASE rank WHEN 'species' THEN 0 WHEN 'subspecies' THEN 1 ELSE 2 END,
          length(spname)
        LIMIT ?
    """
    con = _connect()
    try:
        rows = con.execute(
            sql, (contains, contains, prefix, prefix, limit)
        ).fetchall()
    finally:
        con.close()
    return [
        {
            "taxid": int(taxid),
            "scientific_name": spname,
            "common_name": common or "",
            "rank": rank,
        }
        for taxid, spname, common, rank in rows
    ]


def resolve_exact(name: str) -> dict | None:
    """
    Confirm an exact name (scientific name or a known synonym).

    Returns taxid, scientific_name, common_name, or None if there is no match.
    The species table is case-insensitive, so capitalization does not matter.
    """
    name = (name or "").strip()
    if not name:
        return None
    con = _connect()
    try:
        row = con.execute(
            "SELECT taxid, spname, common FROM species WHERE spname = ? LIMIT 1",
            (name,),
        ).fetchone()
        if not row:
            row = con.execute(
                "SELECT sp.taxid, sp.spname, sp.common FROM synonym sy "
                "JOIN species sp ON sp.taxid = sy.taxid "
                "WHERE sy.spname = ? LIMIT 1",
                (name,),
            ).fetchone()
    finally:
        con.close()
    if not row:
        return None
    return {
        "taxid": int(row[0]),
        "scientific_name": row[1],
        "common_name": row[2] or "",
    }


def suggest(name: str, limit: int = 5) -> list[dict]:
    """Close matches to offer when an exact lookup fails."""
    return search_species(name, limit=limit)


# ---------------------------------------------------------------------------
# Lineage: the major clade ranks plus a simple group, from a TaxID
# ---------------------------------------------------------------------------
# Warehouse columns for the Linnaean ranks. class and order are SQL reserved
# words, so the columns carry a trailing underscore.
LINEAGE_COLUMNS = ["kingdom", "phylum", "class_", "order_", "family", "genus"]

# NCBI rank name -> warehouse column.
_RANK_TO_COLUMN = {
    "kingdom": "kingdom",
    "phylum": "phylum",
    "class": "class_",
    "order": "order_",
    "family": "family",
    "genus": "genus",
}

# Reference TaxIDs for the simple group, checked most specific first.
_GROUP_TAXIDS = [
    (9606, "Human"),     # Homo sapiens
    (50557, "Insect"),   # Insecta
    (33208, "Animal"),   # Metazoa
    (33090, "Plant"),    # Viridiplantae
    (4751, "Fungi"),     # Fungi
]


def _group_for(lineage: set[int]) -> str:
    for taxid, group in _GROUP_TAXIDS:
        if taxid in lineage:
            return group
    return "Other"


def lineage_for_taxid(taxid: int) -> dict:
    """
    Return the major clade ranks and a simple group for one TaxID.

    Keys: kingdom, phylum, class_, order_, family, genus, domain. Missing ranks
    come back as None. Uses ete3's NCBI database (the same one the tree uses).
    """
    from src import enrich

    ncbi = enrich.get_ncbi()
    taxid = int(taxid)
    lineage = ncbi.get_lineage(taxid) or []
    ranks = ncbi.get_rank(lineage)
    names = ncbi.get_taxid_translator(lineage)

    out = {col: None for col in LINEAGE_COLUMNS}
    for tid in lineage:
        col = _RANK_TO_COLUMN.get(ranks.get(tid))
        if col:
            out[col] = names.get(tid)
    out["domain"] = _group_for(set(lineage))
    return out


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "coyote"
    if not is_ready():
        print("NCBI database not built yet.")
        raise SystemExit(1)
    for hit in search_species(q):
        print(f"  {hit['taxid']:>8}  {hit['scientific_name']}  "
              f"({hit['common_name']})  [{hit['rank']}]")


def lineage_clades_for_taxid(taxid: int) -> dict:
    """Return the ordered clade chain (root -> species) for one taxid.

    Filters to the Linnaean major ranks (kingdom, phylum, class, order, family,
    genus) plus any clade name that lives in config.LCA_CHRONOLOGY_MYA. This is
    what db.insert_request walks to populate the clade + species_clade tables.

    Returns
    -------
    {
        "clades": [{"taxid": int, "name": str, "rank": str | None,
                    "mya": float | None}, ...],   # root -> species
        "domain": "Human" | "Insect" | "Animal" | "Plant" | "Fungi" | "Other"
    }
    """
    from src import enrich
    import config as _config

    ncbi = enrich.get_ncbi()
    taxid = int(taxid)
    lineage = ncbi.get_lineage(taxid) or []
    if not lineage:
        return {"clades": [], "domain": "Other"}

    ranks = ncbi.get_rank(lineage)
    names = ncbi.get_taxid_translator(lineage)
    chronology = _config.LCA_CHRONOLOGY_MYA
    keep_ranks = set(_RANK_TO_COLUMN.keys())  # kingdom..genus

    out = []
    for tid in lineage:
        name = names.get(tid)
        if not name:
            continue
        rank = (ranks.get(tid) or "").strip()
        in_keeper_rank = rank in keep_ranks
        in_chronology  = name in chronology
        if not (in_keeper_rank or in_chronology):
            continue
        out.append({
            "taxid": int(tid),
            "name": name,
            "rank": rank if rank not in ("no rank", "clade", "") else None,
            "mya": float(chronology[name]) if name in chronology else None,
        })

    return {"clades": out, "domain": _group_for(set(lineage))}

