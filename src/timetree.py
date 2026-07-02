"""
TimeTree divergence dates.

TimeTree of Life (timetree.org) is the standard open source for when lineages
split. It has no clean API, but it does take a list of species and hand back a
dated tree, which is a reliable way to get real numbers.

The flow is two steps:

  1. Export the species list for a tree:
         python -m src.timetree export "<Your Tree Name>"
     Upload that file at timetree.org under "Load a List of Species", then save
     the dated tree it returns as  data/<stem>_timetree.nwk

  2. From then on, every pipeline run reads that dated tree and puts a real
     divergence age (in millions of years) on each internal node, matched by
     finding the same group of species in the TimeTree result.

If no dated tree is present, the pipeline just falls back to the curated
chronology in config.py, so nothing breaks.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402


def _norm(name: str) -> str:
    return str(name).strip().replace(" ", "_").lower()


def dated_tree_path(stem: str) -> Path | None:
    """Find a downloaded TimeTree dated tree for this stem, if any."""
    for folder in (config.DATA_DIR, config.OUTPUT_DIR):
        for ext in ("nwk", "nex", "newick", "tree"):
            p = folder / f"{stem}_timetree.{ext}"
            if p.exists():
                return p
    return None


def _load_dated_tree(path: Path):
    from ete3 import Tree
    text = Path(path).read_text()
    for fmt in (1, 0, 5, 3, 2):
        try:
            return Tree(text, format=fmt)
        except Exception:
            continue
    return Tree(text, format=1)  # let the final error surface


def ages_for_tree(stem: str, our_newick: str) -> dict[str, int]:
    """
    Map a divergence age onto each internal node of our tree.

    For every internal node we take the species beneath it, find that same set
    in the TimeTree result, and read the age of their common ancestor. Returns
    {node_label: mya}. Empty dict if there is no dated tree yet.
    """
    path = dated_tree_path(stem)
    if not path:
        return {}

    from ete3 import Tree

    dated = _load_dated_tree(path)
    ours = Tree(our_newick, format=1)
    dated_by_norm = {_norm(lf.name): lf for lf in dated.get_leaves()}

    ages: dict[str, int] = {}
    for node in ours.traverse():
        if node.is_leaf() or not node.name:
            continue
        present = [
            dated_by_norm[_norm(lf.name)]
            for lf in node.get_leaves()
            if _norm(lf.name) in dated_by_norm
        ]
        if len(present) < 2:
            continue
        mrca = dated.get_common_ancestor(present)
        age = mrca.get_distance(present[0])   # ultrametric: depth to any tip
        ages[node.name] = int(round(age))
    return ages


def export_species_list(tree_name: str, out_dir: Path | None = None) -> Path:
    from src import db

    out_dir = out_dir or config.OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    df = db.read_tree(tree_name)
    names = sorted({
        str(r["scientific_name"]).strip()
        for _, r in df.iterrows()
        if r.get("scientific_name")
    })
    stem = tree_name.strip().replace(" ", "_").lower()
    path = out_dir / f"{stem}_species_for_timetree.txt"
    path.write_text("\n".join(names) + "\n")
    print(f"wrote {path.name} with {len(names)} species.")
    print("Next: upload it at timetree.org under 'Load a List of Species',")
    print(f"then save the dated tree it returns as  data/{stem}_timetree.nwk")
    return path


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "export":
        export_species_list(sys.argv[2])
    else:
        print('usage: python -m src.timetree export "<Tree_Name>"')
        raise SystemExit(1)
