"""
iTOL dataset files.

iTOL is a free web tool, not a Google product, so it stays as one way to show
the tree (handy for the press kit). These functions write the three drag-and-drop
text files. They are plain text, so they are easy to read and version.

  1. itol_common_names.txt   common names sitting outside each leaf
  2. itol_internal_node_mya.txt   deep-time labels on the named clades, in red
  3. itol_options.txt   TREE_COLORS that tints each named clade

Switching the tree to a circular or unrooted shape is one click in iTOL under
Controls -> Mode, and the offline render (render.py) already draws it circular.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

# A small, calm palette for the clade tints.
_CLADE_COLORS = [
    "#1b9e77", "#7570b3", "#d95f02", "#e7298a", "#66a61e", "#e6ab02",
]


def _safe(name: str) -> str:
    return name.strip().replace(" ", "_")


def _common_map(df: pd.DataFrame) -> dict[str, str]:
    """Newick leaf label -> common name."""
    out = {}
    for _, row in df.iterrows():
        sci = row.get("scientific_name")
        common = row.get("common_name")
        if pd.notna(sci) and pd.notna(common) and str(common).strip():
            out[_safe(str(sci))] = str(common).strip()
    return out


def write_common_names(df: pd.DataFrame, leaves: list[str], out_dir: Path) -> Path:
    mapping = _common_map(df)
    lines = [
        "DATASET_TEXT",
        "SEPARATOR COMMA",
        "DATASET_LABEL,Common names",
        "COLOR,#1b9e77",
        "DATA",
    ]
    # ID,label,position,color,style,size_factor,rotation
    for leaf in leaves:
        if leaf in mapping:
            lines.append(f"{leaf},{mapping[leaf]},1,#000000,normal,1,0")
    path = out_dir / "itol_common_names.txt"
    path.write_text("\n".join(lines) + "\n")
    return path


def write_internal_mya(internal_clades: dict[str, int], out_dir: Path) -> Path:
    lines = [
        "DATASET_TEXT",
        "SEPARATOR COMMA",
        "DATASET_LABEL,Deep-time chronology (MYA)",
        "COLOR,#ff0000",
        "DATA",
    ]
    # Position -1 places the label directly on the internal node, in red.
    for clade, mya in internal_clades.items():
        lines.append(f"{clade},{mya} MYA,-1,#ff0000,bold,1,0")
    path = out_dir / "itol_internal_node_mya.txt"
    path.write_text("\n".join(lines) + "\n")
    return path


def write_options(internal_clades: dict[str, int], out_dir: Path) -> Path:
    lines = [
        "TREE_COLORS",
        "SEPARATOR COMMA",
        "DATA",
    ]
    for i, clade in enumerate(internal_clades):
        color = _CLADE_COLORS[i % len(_CLADE_COLORS)]
        # tint the whole clade range, and thicken its branch
        lines.append(f"{clade},range,{color},{clade}")
        lines.append(f"{clade},branch,{color},normal,3")
    path = out_dir / "itol_options.txt"
    path.write_text("\n".join(lines) + "\n")
    return path


def export_all(df: pd.DataFrame, leaves: list[str],
               internal_clades: dict[str, int], out_dir: Path | None = None,
               stem: str | None = None):
    out_dir = out_dir or config.OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    _prefix = f"itol_{stem}_" if stem else "itol_"
    paths = [
        write_common_names(df, leaves, out_dir),
        write_internal_mya(internal_clades, out_dir),
        write_options(internal_clades, out_dir),
    ]
    for p in paths:
        print(f"wrote {p.name}")
    return paths
