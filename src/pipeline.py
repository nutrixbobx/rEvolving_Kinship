"""
Run the whole pipeline for one tree, end to end.

    python -m src.pipeline "<Your Tree Name>"

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


def warm_kin_cards(df, max_workers: int = 6) -> int:
    """Fetch and cache every species' profile (photo, summary, credits) and
    its recording, in parallel, so the tree has its images the moment it
    finishes building. This is the work the "Load kin cards" button used to
    do by hand, which meant building a tree, going back, and refreshing
    before any photo appeared.

    Failures are per-species and non-fatal: a species with no photo simply
    has none. Returns how many profiles landed in the cache."""
    from concurrent.futures import ThreadPoolExecutor
    from src import species_profile, species_audio

    pairs = []
    for _, row in df.iterrows():
        sci = row.get("scientific_name")
        if isinstance(sci, str) and sci.strip():
            common = row.get("common_name")
            pairs.append((sci.strip(),
                          common if isinstance(common, str) else None))
    if not pairs:
        return 0

    print(f"  warming kin cards for {len(pairs)} species (parallel)...")
    ok = 0

    def _one(pair):
        sci, common = pair
        got = False
        try:
            prof = species_profile.find_profile(sci, common)
            got = bool(prof and prof.get("image_url"))
        except Exception as exc:
            print(f"    profile failed {sci}: {exc}")
        try:
            species_audio.find_recording(sci, common)
        except Exception:
            pass
        return got

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for got in ex.map(_one, pairs):
            ok += 1 if got else 0
    print(f"  kin cards warmed: {ok}/{len(pairs)} have a photo")
    return ok


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

    warm_kin_cards(df)                                 # 1b. photos + audio
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
