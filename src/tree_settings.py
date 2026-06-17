"""
Per-tree settings: owner name, title template, slogan.

A tiny JSON file at outputs/tree_owners.json keeps the personalization for
each tree. Used by the graphic generators to draw a header bar reading
something like "Maya's kinship looks like:" above each rendered tree.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

SETTINGS_PATH = config.OUTPUT_DIR / "tree_owners.json"
PROJECT_MARK = "{r}Evolving Kinship"
PROJECT_SLOGAN = ("Your reliable custom phylogenetic tree generator and community science hub for {r}envisioning our self.")
DEFAULT_TEMPLATE = "{owner}'s kinship looks like:"


def _load() -> dict:
    if SETTINGS_PATH.exists():
        try:
            return json.loads(SETTINGS_PATH.read_text())
        except Exception:
            return {}
    return {}


def get_tree_settings(tree_name: str) -> dict:
    return _load().get(tree_name, {})


def set_tree_settings(tree_name: str,
                      owner: str | None = None,
                      title_template: str | None = None) -> None:
    s = _load()
    s.setdefault(tree_name, {})
    if owner is not None:
        s[tree_name]["owner"] = owner
    if title_template is not None:
        s[tree_name]["title_template"] = title_template
    SETTINGS_PATH.write_text(json.dumps(s, indent=2))


def title_for(tree_name: str) -> str:
    """Compose the header line for a tree. Falls back to the tree's own name."""
    cfg = get_tree_settings(tree_name)
    owner = (cfg.get("owner") or "").strip()
    tmpl = cfg.get("title_template") or DEFAULT_TEMPLATE
    if owner:
        return tmpl.replace("{owner}", owner).replace("{tree}", tree_name)
    return f"{tree_name} looks like:"
