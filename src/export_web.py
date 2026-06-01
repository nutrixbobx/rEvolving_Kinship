"""
Website export bundle.

Write a small JSON file plus the rendered SVG so the tree can be embedded back
into shared-rivers.org and keep living after the event. The JSON holds the
Newick, the species with their common names and stories, and the chronology.
A web page (or the Supabase client) can read this directly.
"""

from __future__ import annotations

import datetime
import json
import shutil
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
from src.tree import _safe  # noqa: E402


def export_bundle(tree_name: str, result: dict, out_dir: Path | None = None) -> Path:
    out_dir = (out_dir or config.OUTPUT_DIR) / "web"
    out_dir.mkdir(parents=True, exist_ok=True)

    df = result["df"]
    species = []
    for _, row in df.iterrows():
        species.append({
            "common_name": _none(row.get("common_name")),
            "scientific_name": _none(row.get("scientific_name")),
            "ncbi_taxid": _none(row.get("ncbi_taxid")),
            "domain": _none(row.get("domain")),
            "story": _none(row.get("story")),
            "notes": _none(row.get("notes")),
        })

    # Internal-node ages: the curated chronology plus any TimeTree dates that
    # were merged into the node metadata.
    meta = result.get("meta", {})
    chronology = {
        label: info["mya"]
        for label, info in meta.items()
        if not info.get("is_leaf") and info.get("mya") is not None
    } or result["internal_clades"]

    payload = {
        "tree_name": tree_name,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "species_count": len(df),
        "chronology_mya": chronology,
        "nodes": meta,
        "newick": result["newick"],
        "species": species,
    }

    stem = _safe(tree_name).lower()
    json_path = out_dir / f"{stem}.json"
    json_path.write_text(json.dumps(payload, indent=2, default=str))

    svg = config.OUTPUT_DIR / f"{stem}_tree.svg"
    if svg.exists():
        shutil.copy(svg, out_dir / f"{stem}_tree.svg")

    print(f"web bundle: {json_path.name}")
    return json_path


def _none(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
