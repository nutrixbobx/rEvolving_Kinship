"""
Species profile cards: image + summary + taxonomy + reference links.

Pulls from iNaturalist (rich single endpoint: photo, wikipedia_summary,
ancestors, observation counts) and from Wikipedia's REST summary endpoint as a
supplement. Both are free and key-less.

Caches per scientific name under outputs/profile_cache/.

Admin overrides live in outputs/species_overrides.json. Use save_override() to
pin a different image URL or summary text for any species without touching
code, and clear_override() to revert.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

UA = {"User-Agent": "shared-rivers/1.0 (https://shared-rivers.org)"}
CACHE = config.OUTPUT_DIR / "profile_cache"
CACHE.mkdir(parents=True, exist_ok=True)
OVERRIDES_PATH = config.OUTPUT_DIR / "species_overrides.json"


def _get(url: str, timeout: int = 20) -> bytes:
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=timeout).read()


def _strip_html(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text).strip()


def _inat_search(query: str) -> dict | None:
    url = (f"https://api.inaturalist.org/v1/taxa?q={urllib.parse.quote(query)}"
           "&rank=species,subspecies&per_page=1")
    try:
        d = json.loads(_get(url))
        return (d.get("results") or [None])[0]
    except Exception:
        return None


def _inat_taxon(tid: int) -> dict | None:
    try:
        d = json.loads(_get(f"https://api.inaturalist.org/v1/taxa/{tid}"))
        return (d.get("results") or [None])[0]
    except Exception:
        return None


def _wiki_summary(title: str) -> dict | None:
    if not title:
        return None
    try:
        return json.loads(_get(
            "https://en.wikipedia.org/api/rest_v1/page/summary/"
            f"{urllib.parse.quote(title.replace(' ', '_'))}"))
    except Exception:
        return None


def _load_overrides() -> dict:
    if OVERRIDES_PATH.exists():
        try:
            return json.loads(OVERRIDES_PATH.read_text())
        except Exception:
            return {}
    return {}


def save_override(scientific_name: str, **fields) -> None:
    """Pin custom fields (image_url, image_path, summary, wikipedia_url, etc.)
    for a species. Empty strings/None are ignored."""
    overrides = _load_overrides()
    cleaned = {k: v for k, v in fields.items() if v not in ("", None)}
    if not cleaned:
        return
    overrides.setdefault(scientific_name, {}).update(cleaned)
    OVERRIDES_PATH.write_text(json.dumps(overrides, indent=2))


def clear_override(scientific_name: str, field: str | None = None) -> None:
    overrides = _load_overrides()
    if scientific_name not in overrides:
        return
    if field:
        overrides[scientific_name].pop(field, None)
        if not overrides[scientific_name]:
            overrides.pop(scientific_name)
    else:
        overrides.pop(scientific_name)
    OVERRIDES_PATH.write_text(json.dumps(overrides, indent=2))


def list_overrides() -> dict:
    return _load_overrides()


def _download_image(url: str, key: str) -> Path | None:
    if not url:
        return None
    ext = url.rsplit(".", 1)[-1].lower().split("?")[0]
    if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
        ext = "jpg"
    out = CACHE / f"{key}.{ext}"
    if out.exists():
        return out
    try:
        out.write_bytes(_get(url, timeout=30))
    except Exception:
        return None
    return out


def _empty_profile(sci: str, common: str | None) -> dict:
    return {
        "scientific_name": sci,
        "common_name": common,
        "image_url": None,
        "image_path": None,
        "image_attribution": None,
        "image_license": None,
        "summary": "",
        "wikipedia_url": None,
        "inaturalist_url": None,
        "gbif_url": f"https://www.gbif.org/species/search?q="
                    f"{urllib.parse.quote(sci)}",
        "ancestors": [],
        "observations_count": None,
    }


def find_profile(scientific_name: str, common_name: str | None = None,
                 force_refresh: bool = False) -> dict | None:
    """Return a merged profile dict. Cached on disk and merged with overrides."""
    sci_key = hashlib.md5(scientific_name.encode()).hexdigest()[:10]
    cache_path = CACHE / f"{sci_key}.json"

    profile: dict = {}
    if cache_path.exists() and not force_refresh:
        try:
            profile = json.loads(cache_path.read_text())
        except Exception:
            profile = {}

    if not profile:
        inat = None
        for q in (scientific_name, common_name):
            if not q:
                continue
            inat = _inat_search(q)
            if inat:
                break

        if inat and inat.get("id"):
            full = _inat_taxon(int(inat["id"]))
            if full:
                inat = full
            photo = inat.get("default_photo") or {}
            wiki_title = (inat.get("preferred_common_name")
                          or inat.get("name") or scientific_name)
            wiki = _wiki_summary(wiki_title)
            profile = _empty_profile(scientific_name, common_name)
            profile.update({
                "scientific_name": inat.get("name") or scientific_name,
                "common_name": inat.get("preferred_common_name") or common_name,
                "image_url": photo.get("medium_url") or photo.get("square_url"),
                "image_attribution": photo.get("attribution"),
                "image_license": photo.get("license_code"),
                "summary": _strip_html(
                    inat.get("wikipedia_summary")
                    or (wiki or {}).get("extract", "")),
                "wikipedia_url": (inat.get("wikipedia_url")
                                  or (wiki or {}).get("content_urls", {})
                                  .get("desktop", {}).get("page")),
                "inaturalist_url": f"https://www.inaturalist.org/taxa/{inat['id']}",
                "observations_count": inat.get("observations_count"),
                "ancestors": [{"rank": a.get("rank"), "name": a.get("name")}
                              for a in (inat.get("ancestors") or [])],
            })
        else:
            wiki = (_wiki_summary(common_name) if common_name
                    else None) or _wiki_summary(scientific_name)
            profile = _empty_profile(scientific_name, common_name)
            if wiki:
                profile.update({
                    "image_url": (wiki.get("thumbnail") or {}).get("source"),
                    "image_attribution": "Wikimedia Commons",
                    "summary": wiki.get("extract", ""),
                    "wikipedia_url": (wiki.get("content_urls") or {})
                                     .get("desktop", {}).get("page"),
                })

        if profile.get("image_url"):
            p = _download_image(profile["image_url"], sci_key)
            if p:
                profile["image_path"] = str(p)

        cache_path.write_text(json.dumps(profile, indent=2))

    overrides = _load_overrides().get(scientific_name, {})
    if overrides:
        # Merge but only for known keys, and re-cache image if URL changed
        merged = {**profile, **overrides}
        if "image_url" in overrides and overrides["image_url"] != profile.get("image_url"):
            p = _download_image(overrides["image_url"], sci_key)
            if p:
                merged["image_path"] = str(p)
        merged["overridden_fields"] = sorted(overrides.keys())
        return merged

    return profile


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('usage: python -m src.species_profile "Scientific name" [common]')
        raise SystemExit(1)
    sci = sys.argv[1]
    common = sys.argv[2] if len(sys.argv) > 2 else None
    p = find_profile(sci, common)
    print(json.dumps({k: v for k, v in p.items() if k != "summary"}, indent=2))
    print("\nSUMMARY:", (p or {}).get("summary", "")[:400])
