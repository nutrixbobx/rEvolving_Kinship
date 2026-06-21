"""
Enrichment: fill in NCBI TaxIDs from scientific names.

Contributors only have to type a scientific name. This step asks the local NCBI
taxonomy database (the authoritative source, downloaded once by ete3) for the
matching TaxID and writes it back to the warehouse. Nothing is invented, and
anything that cannot be matched is reported so a human can look at it.

    python -m src.enrich "Goat Farm - Proctor Creek"
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import db  # noqa: E402

import threading
_ncbi_local = threading.local()


def get_ncbi():
    """Return a per-thread NCBITaxa handle.

    The underlying SQLite connection inside NCBITaxa can only be used from the
    thread that opened it. Streamlit runs callbacks across a worker pool, so a
    module-level cache breaks the second a different thread touches it. We
    keep one NCBITaxa per thread via threading.local(). Opening a connection
    to an already-built taxa.sqlite is fast (~milliseconds), so this is cheap.
    On first ever use, ete3 downloads and builds the database (a few hundred
    MB); after that, it's just open-and-go.
    """
    cached = getattr(_ncbi_local, "ncbi", None)
    if cached is not None:
        return cached
    import os
    from ete3 import NCBITaxa
    from ete3.ncbi_taxonomy.ncbiquery import DEFAULT_TAXADB
    # ete3 only auto-builds the database when called with its own default
    # path (or a brand new custom path). Passing the default path back to it
    # explicitly skips the build, so use the default unless NCBI_TAXA_DB
    # points somewhere genuinely different.
    custom = os.environ.get("NCBI_TAXA_DB")
    if custom and os.path.abspath(custom) != os.path.abspath(DEFAULT_TAXADB):
        ncbi = NCBITaxa(dbfile=custom)
    else:
        ncbi = NCBITaxa()
    _ncbi_local.ncbi = ncbi
    return ncbi


def resolve_names(names: list[str]) -> dict[str, int]:
    """Map scientific names to a single TaxID each, dropping unmatched names."""
    ncbi = get_ncbi()
    raw = ncbi.get_name_translator(names)  # {name: [taxid, ...]}
    return {name: ids[0] for name, ids in raw.items() if ids}


def backfill_lineage(tree_name: str) -> int:
    """
    Fill the clade columns (domain, kingdom .. genus) for every resolved row
    that does not have them yet. Returns the number of rows filled.
    """
    import pandas as pd
    from src import taxonomy_search as ts

    df = db.read_tree(tree_name)
    filled = 0
    for _, row in df.iterrows():
        taxid = row.get("ncbi_taxid")
        if taxid is None or pd.isna(taxid):
            continue
        if row.get("genus"):          # already has lineage
            continue
        try:
            lineage = ts.lineage_for_taxid(int(taxid))
        except Exception:
            continue
        db.update_fields(tree_name, row["scientific_name"], lineage)
        filled += 1
    if filled:
        print(f"  lineage filled for {filled} species")
    return filled


def enrich_tree(tree_name: str) -> tuple[int, list[str]]:
    """
    Resolve and persist TaxIDs for every row of one tree that lacks one, then
    fill the clade columns for every resolved row.

    Returns (number of TaxIDs filled, list of names that could not be matched).
    """
    df = db.read_tree(tree_name)
    missing = df[df["ncbi_taxid"].isna()]
    names = sorted(set(missing["scientific_name"].dropna()))

    found = resolve_names(names) if names else {}
    for name, taxid in found.items():
        db.update_taxid(tree_name, name, taxid)

    unresolved = [n for n in names if n not in found]
    if names:
        print(f"enriched {tree_name}: filled {len(found)}, "
              f"unresolved {len(unresolved)}")
        for n in unresolved:
            print(f"  could not match: {n}")

    backfill_lineage(tree_name)
    return len(found), unresolved


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('usage: python -m src.enrich "<Tree_Name>"')
        raise SystemExit(1)
    enrich_tree(sys.argv[1])
