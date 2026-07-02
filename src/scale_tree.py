"""
Build a MYA-scaled sister newick alongside the topology-only newick.

The core file `<stem>_named_tree.nwk` is built from NCBI topology and
carries no branch lengths. Every renderer that reads it draws chains
at uniform depth, which flattens the real evolutionary distances.

This module computes real branch lengths from `<stem>_nodes.json`:
  - Every dated clade anchors an absolute age (MYA).
  - Leaves anchor at 0 MYA (present day).
  - Undated internal nodes get an age interpolated linearly between
    the nearest dated ancestor and the nearest dated descendant.
  - Branch length = parent_age - self_age (millions of years).
  - Log-scaled with log10(1 + length) so a 500-million-year branch
    doesn't dwarf a 5-million-year branch visually. Preserves ratio
    intuition without letting deep-time overwhelm the drawing.

Writes `<stem>_scaled_tree.nwk`. Existing files are overwritten.

Renderers may prefer this file when a MYA-faithful drawing is wanted,
and fall back to the plain named newick when no ages are available.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402


# Fallback age for undated internal nodes with no dated ancestor OR
# descendant to interpolate between. Only hit when the whole tree has
# zero MYA data — extremely rare. Small enough that the tree still
# draws sanely.
NOMINAL_MYA = 1.0

# Log-scale transform. log10(1 + mya) keeps proportion legible without
# letting Cambrian-era branches drown the recent ones.
def _log_scale(mya: float) -> float:
    return math.log10(1.0 + max(mya, 0.0))


def _compute_ages(t, meta: dict) -> dict[int, float]:
    """Return {node_idx: age_in_mya}. Leaves at 0. Dated internals from
    meta. Undated internals interpolated between nearest dated ancestor
    and nearest dated descendant."""
    from ete3 import Tree as _Tree  # noqa: F401
    ages: dict[int, float] = {}
    for node in t.traverse():
        idx = id(node)
        if node.is_leaf():
            ages[idx] = 0.0
            continue
        info = meta.get(node.name, {})
        mya = info.get("mya")
        if isinstance(mya, (int, float)):
            ages[idx] = float(mya)

    # Downward propagation: any undated internal takes max(descendant
    # dated ages) as a lower bound (it can't be younger than a dated
    # descendant clade).
    for node in t.traverse("postorder"):
        idx = id(node)
        if idx in ages:
            continue
        child_ages = [ages[id(c)] for c in node.children if id(c) in ages]
        if child_ages:
            ages[idx] = max(child_ages) * 1.05  # slight bump so branch > 0

    # Upward propagation: fill any still-missing with parent-halved.
    for node in t.traverse("preorder"):
        idx = id(node)
        if idx in ages:
            continue
        if node.up is not None and id(node.up) in ages:
            # Halfway between parent and 0
            ages[idx] = ages[id(node.up)] * 0.5
        else:
            ages[idx] = NOMINAL_MYA

    # Sanity: parent must be older than child. Fix any inversions by
    # bumping parent up.
    for _ in range(3):  # a couple passes settle any downstream ripples
        for node in t.traverse("postorder"):
            if node.is_root() or node.up is None:
                continue
            parent_idx = id(node.up)
            self_idx = id(node)
            if ages[parent_idx] <= ages[self_idx]:
                ages[parent_idx] = ages[self_idx] * 1.01 + 0.1
    return ages


def build_scaled_tree(tree_name: str,
                      out_dir: Path | None = None) -> Path | None:
    """Read the topology newick + meta, compute branch lengths, write
    <stem>_scaled_tree.nwk. Returns the path, or None if inputs are
    missing."""
    from src.tree import _safe as _safe_stem
    out_dir = out_dir or config.OUTPUT_DIR
    stem = _safe_stem(tree_name).lower()

    nwk_path = out_dir / f"{stem}_named_tree.nwk"
    meta_path = out_dir / f"{stem}_nodes.json"
    if not (nwk_path.exists() and meta_path.exists()):
        return None

    meta = json.loads(meta_path.read_text())

    from ete3 import Tree
    t = Tree(nwk_path.read_text(), format=1)

    ages = _compute_ages(t, meta)

    # Assign branch lengths (log-scaled MY).
    for node in t.traverse():
        if node.up is None:
            node.dist = 0.0
            continue
        parent_age = ages[id(node.up)]
        self_age = ages[id(node)]
        raw_length = max(parent_age - self_age, 0.0)
        node.dist = _log_scale(raw_length)

    out_path = out_dir / f"{stem}_scaled_tree.nwk"
    # format=5 keeps names + branch lengths; format_root_node keeps root
    # so any root-level clade label survives.
    out_path.write_text(t.write(format=5, format_root_node=True))
    print(f"scaled tree written: {out_path} "
          f"({sum(1 for _ in t.traverse())} nodes)")
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m src.scale_tree '<tree name>'")
        sys.exit(1)
    p = build_scaled_tree(sys.argv[1])
    print(p or "no output (missing inputs)")
