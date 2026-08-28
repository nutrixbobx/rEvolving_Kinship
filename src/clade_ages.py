"""
Reference divergence ages for well-known clades.

Three layers of truth feed a clade's age (`mya` in nodes.json), applied
in this order so the more deliberate sources win:

  1. data/clade_ages_reference.json (this module's table): median
     published estimates, mostly TimeTree of Life. Broad coverage,
     nobody had to type them in.
  2. config.LCA_CHRONOLOGY_MYA + a downloaded TimeTree dated tree:
     the original pilot values and any per-tree TimeTree upload.
  3. clade.divergence_mya in the warehouse: ages entered by hand in
     the Clade Browser. A person looked at this number. It wins.

Every age here is an estimate with real scientific uncertainty around
it. The point is honest proportion, not false precision: a coyote and
a fox parted ways about twelve million years ago, a coyote and an oak
closer to 1.6 billion. The tree and the chord should carry that.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import config


REFERENCE_PATH = config.DATA_DIR / "clade_ages_reference.json"


def norm_clade(name: str | None) -> str:
    """Normalize a clade label for matching: NCBI names arrive both as
    'cellular organisms' and 'cellular_organisms' depending on which
    file they passed through."""
    if not name:
        return ""
    return str(name).strip().replace("_", " ").lower()


@lru_cache(maxsize=1)
def reference_ages() -> dict[str, float]:
    """{normalized clade name: mya} from the bundled reference table.
    Returns {} when the file is missing so callers never break."""
    try:
        raw = json.loads(REFERENCE_PATH.read_text())
    except Exception:
        return {}
    out: dict[str, float] = {}
    for k, v in raw.items():
        if k.startswith("_"):
            continue
        try:
            out[norm_clade(k)] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def apply_ages(node_meta: dict) -> dict[str, int]:
    """Fill divergence ages into node_meta in priority order. Mutates
    node_meta in place. Returns {"reference": n, "community": n} counts
    for logging.

    Call AFTER the curated-chronology and TimeTree merges: the
    reference table only fills nodes still missing an age, while
    community values from the warehouse override everything."""
    counts = {"reference": 0, "community": 0}

    ref = reference_ages()
    if ref:
        for label, info in node_meta.items():
            if info.get("is_leaf") or info.get("mya") is not None:
                continue
            mya = ref.get(norm_clade(label))
            if mya is not None:
                info["mya"] = mya
                counts["reference"] += 1

    try:
        from src import db
        community = db.get_clade_ages()
    except Exception:
        community = {}
    if community:
        for label, info in node_meta.items():
            if info.get("is_leaf"):
                continue
            mya = community.get(norm_clade(label))
            if mya is not None and info.get("mya") != mya:
                info["mya"] = mya
                counts["community"] += 1

    return counts
