"""
Tree building.

Pull a tree's resolved TaxIDs from the warehouse, ask ete3 for the topology
that connects them through the NCBI taxonomy, name every node (leaves and
internal clades) with its scientific name, and write a Newick file.

This is the same idea as the old Colab step, just reading from our own
warehouse instead of a Google Sheet, and running anywhere Python runs.

    python -m src.tree "Goat Farm - Proctor Creek"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
from src import db, enrich  # noqa: E402


import re as _re
_UNSAFE_CHARS = _re.compile(r'[\s/\\:*?"<>|#%&{}\(\),;]+')


def _safe(name: str) -> str:
    """Filesystem- and Newick-safe slug. Strips path-dangerous characters,
    collapses runs of separators, leaves ASCII letters / digits / underscores /
    hyphens. Used for output file stems and Newick node labels.
    """
    if not isinstance(name, str):
        return "tree"
    s = name.strip()
    s = _UNSAFE_CHARS.sub("_", s)
    s = _re.sub(r"[^A-Za-z0-9_\-]+", "", s)
    s = _re.sub(r"_+", "_", s).strip("_-")
    return s or "tree"


def name_tree(topo, taxid_translator=None):
    """
    Walk an ete3 topology, replace each node name with its scientific name, and
    gather per-node metadata.

    ete3's get_topology attaches a sci_name (and rank) to every node, so usually
    no lookup is needed. taxid_translator is the fallback for the rare node that
    only has a TaxID. Kept separate from build_tree so it can be tested without
    the NCBI database.

    Returns (newick, leaves, internal_clades, node_meta) where node_meta maps a
    Newick label to {is_leaf, scientific_name, rank}. Common names and ages get
    merged in later by build_tree.
    """
    internal_clades: dict[str, int] = {}
    leaves: list[str] = []
    node_meta: dict[str, dict] = {}
    for node in topo.traverse():
        sci = getattr(node, "sci_name", "") or ""
        if not sci and str(node.name).isdigit() and taxid_translator:
            sci = taxid_translator([int(node.name)]).get(
                int(node.name), str(node.name)
            )
        rank = getattr(node, "rank", "") or ""
        if rank in ("no rank", "clade"):
            rank = ""
        label = _safe(sci or str(node.name))
        node.name = label
        node_meta[label] = {
            "is_leaf": node.is_leaf(),
            "scientific_name": (sci or label.replace("_", " ")),
            "rank": rank,
            "common_name": None,
            "mya": None,
        }
        if node.is_leaf():
            leaves.append(label)
        elif label in config.LCA_CHRONOLOGY_MYA:
            internal_clades[label] = config.LCA_CHRONOLOGY_MYA[label]

    # format=1 keeps internal node names; format_root_node keeps the root's
    # name too, so a root-level clade (often Eukaryota) still gets its label.
    newick = topo.write(format=1, format_root_node=True)
    return newick, leaves, internal_clades, node_meta


def build_tree(tree_name: str, auto_enrich: bool = True):
    """
    Build the named tree for one Tree_Name.

    Returns a dict with the Newick string, the output path, the list of leaf
    labels, and the internal clades present that we have a chronology for.
    """
    if auto_enrich:
        enrich.enrich_tree(tree_name)

    df = db.read_tree(tree_name)
    taxids = sorted({int(t) for t in df["ncbi_taxid"].dropna().tolist()})
    if len(taxids) < 2:
        raise SystemExit(
            f'"{tree_name}" has fewer than two resolved species. '
            f"Load more data or check the scientific names."
        )

    ncbi = enrich.get_ncbi()
    # intermediate_nodes=True keeps the named clades (Carnivora, Amniota, ...)
    # so we can label and sonify them.
    topo = ncbi.get_topology(taxids, intermediate_nodes=True)
    newick, leaves, internal_clades, node_meta = name_tree(
        topo, ncbi.get_taxid_translator
    )

    stem = _safe(tree_name).lower()
    out_path = config.OUTPUT_DIR / f"{stem}_named_tree.nwk"
    out_path.write_text(newick)

    # Merge common names from the warehouse into the leaf metadata.
    common_by_sci = {
        str(r["scientific_name"]).strip(): r["common_name"]
        for _, r in df.iterrows()
        if r.get("scientific_name") and r.get("common_name")
    }
    for label, info in node_meta.items():
        if info["is_leaf"]:
            info["common_name"] = common_by_sci.get(info["scientific_name"])

    # Merge divergence ages. Use the curated chronology first, then overlay any
    # ages from a TimeTree dated tree if one has been downloaded for this tree.
    for label, mya in internal_clades.items():
        if label in node_meta:
            node_meta[label]["mya"] = mya
    try:
        from src import timetree
        ages = timetree.ages_for_tree(stem, newick)
        for label, mya in ages.items():
            if label in node_meta:
                node_meta[label]["mya"] = mya
        if ages:
            print(f"  TimeTree ages applied to {len(ages)} node(s)")
    except Exception as exc:
        print(f"  (no TimeTree ages: {exc})")

    meta_path = config.OUTPUT_DIR / f"{stem}_nodes.json"
    meta_path.write_text(json.dumps(node_meta, indent=2))

    # Also write the MYA-scaled sister newick so renderers can draw
    # branches at real evolutionary distance instead of uniform depth.
    # Failures here are non-fatal: renderers fall back to the plain
    # topology newick.
    try:
        from src import scale_tree
        scale_tree.build_scaled_tree(tree_name)
    except Exception as _exc:
        print(f"  scaled newick build failed (non-fatal): {_exc}")

    print(f"tree built for {tree_name}: {len(leaves)} leaves -> {out_path.name}")
    if internal_clades:
        print(f"  named clades with chronology: {', '.join(internal_clades)}")
    return {
        "newick": newick,
        "path": out_path,
        "leaves": leaves,
        "internal_clades": internal_clades,
        "meta": node_meta,
        "meta_path": meta_path,
        "df": df,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('usage: python -m src.tree "<Tree_Name>"')
        raise SystemExit(1)
    build_tree(sys.argv[1])
