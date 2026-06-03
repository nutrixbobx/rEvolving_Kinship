"""
Run the whole pipeline for one tree, end to end.

    python -m src.pipeline "Goat Farm - Proctor Creek"

Steps, in order:
  1. enrich + build the named tree (Newick)        -> outputs/*_named_tree.nwk
  2. iTOL drag-and-drop files                       -> outputs/itol_*.txt
  3. offline render                        -> outputs/*_tree.svg (+ .png)
  4. ecosystem chord                                -> outputs/*_chord.mid
  5. website bundle (JSON + SVG)                    -> outputs/web/*.json

Reads from whatever DATABASE_URL points at, so the same command works on the
offline SQLite database and on Supabase.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
from src import itol_export, render, sonify, export_web  # noqa: E402
from src import tree as tree_mod  # noqa: E402
from src.tree import _safe  # noqa: E402


def run(tree_name: str, layout: str = "r") -> dict:
    result = tree_mod.build_tree(tree_name)            # 1. enrich + tree
    df, leaves, meta = result["df"], result["leaves"], result["meta"]
    stem = _safe(tree_name).lower()

    # Every internal node that has a divergence age, from the curated chronology
    # and from TimeTree if a dated tree was downloaded.
    ages = {
        label: info["mya"]
        for label, info in meta.items()
        if not info["is_leaf"] and info.get("mya") is not None
    }

    itol_export.export_all(df, leaves, ages)                      # 2. iTOL files
    render.render_files(result["path"], meta, f"{stem}_tree", layout=layout, tree_name=tree_name)  # 3.
    sonify.sonify_tree(ages or result["internal_clades"], stem)  # 4. chord
    export_web.export_bundle(tree_name, result)                  # 5. web bundle

    print(f"\ndone. outputs are in {config.OUTPUT_DIR}")
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('usage: python -m src.pipeline "<Tree_Name>"')
        raise SystemExit(1)
    run(sys.argv[1])
