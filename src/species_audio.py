"""
Find one CC-licensed recording per species, with a graceful chain of sources.

Order of preference, with automatic fallback to the next when a source has no
hit:

  1. Xeno-canto v3  (when XENO_CANTO_API_KEY is set in .env). Curated archive
     with the largest body of bird, frog, bat, and orthopteran recordings.
  2. Wikipedia / Wikimedia Commons. Open and key-free. Many of the same
     Xeno-canto recordings are re-deposited here under CC, plus the long tail
     of mammal and chicken articles.

Downloads are cached under outputs/audio_cache/ keyed by a hash of the
scientific name, so a tree only ever hits the network for species it has not
seen before.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

UA = {"User-Agent": "shared-rivers/1.0 (https://shared-rivers.org)"}
AUDIO_CACHE = config.OUTPUT_DIR / "audio_cache"
AUDIO_CACHE.mkdir(parents=True, exist_ok=True)
SLEEP = 0.4


def _get(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout).read()


# ---------------------------------------------------------------------------
# Xeno-canto v3 (preferred source when key is present)
# ---------------------------------------------------------------------------
def _parse_xc_length(s: str) -> int:
    try:
        m, _, ss = (s or "").partition(":")
        return int(m) * 60 + int(ss)
    except Exception:
        return 9999


def _xc_find(scientific_name: str) -> dict | None:
    """Query Xeno-canto v3 for a recording. Returns dict with url + meta."""
    key = os.environ.get("XENO_CANTO_API_KEY")
    if not key:
        return None
    parts = scientific_name.split(maxsplit=1)
    if len(parts) != 2:
        return None
    gen, sp = parts
    # Pull q:A first, then any quality. Pick the recording closest to ~10 sec.
    for q_filter in (" q:A len:5-30", " q:A len:5-90", " len:5-90", ""):
        query = f"gen:{gen} sp:{sp}{q_filter}".strip()
        url = ("https://xeno-canto.org/api/3/recordings"
               f"?query={urllib.parse.quote(query)}&key={key}")
        try:
            d = json.loads(_get(url, timeout=20))
        except Exception:
            continue
        recs = [r for r in d.get("recordings") or [] if r.get("file")]
        if not recs:
            continue
        rank = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "no score": 5}
        recs.sort(key=lambda r: (
            rank.get(r.get("q", ""), 5),
            abs(_parse_xc_length(r.get("length", "")) - 10),
        ))
        rec = recs[0]
        return {
            "url": rec["file"],
            "title": f"XC{rec.get('id', '')} {rec.get('file-name', '')}",
            "attribution": (f"Xeno-canto XC{rec.get('id')} - "
                            f"{rec.get('rec', '')} - {rec.get('lic', '')}"),
            "source": "xeno-canto",
        }
    return None


# ---------------------------------------------------------------------------
# Wikipedia / Commons (fallback)
# ---------------------------------------------------------------------------
def _opensearch(query: str) -> str | None:
    url = ("https://en.wikipedia.org/w/api.php?action=opensearch"
           f"&search={urllib.parse.quote(query)}&limit=1&format=json")
    try:
        d = json.loads(_get(url))
        return d[1][0] if d[1] else None
    except Exception:
        return None


def _media_audio(title: str) -> list[dict]:
    url = ("https://en.wikipedia.org/api/rest_v1/page/media-list/"
           f"{urllib.parse.quote(title.replace(' ', '_'))}")
    try:
        d = json.loads(_get(url))
    except Exception:
        return []
    return [m for m in d.get("items", []) if m.get("type") == "audio"]


def _wiki_file_info(file_title: str) -> tuple[str | None, dict]:
    name = file_title.replace(" ", "_")
    url = ("https://en.wikipedia.org/w/api.php?action=query"
           f"&titles={urllib.parse.quote(name)}"
           "&prop=imageinfo&iiprop=url|extmetadata&format=json")
    try:
        d = json.loads(_get(url))
        page = list(d["query"]["pages"].values())[0]
        ii = (page.get("imageinfo") or [{}])[0]
        return ii.get("url"), ii.get("extmetadata", {})
    except Exception:
        return None, {}


def _wiki_find(scientific_name: str, common_name: str | None) -> dict | None:
    title = _opensearch(common_name) if common_name else None
    time.sleep(SLEEP)
    if not title:
        title = _opensearch(scientific_name)
        time.sleep(SLEEP)
    if not title:
        return None
    audios = _media_audio(title)
    time.sleep(SLEEP)
    if not audios:
        return None
    file_title = audios[0].get("title")
    if not file_title:
        return None
    url, meta = _wiki_file_info(file_title)
    time.sleep(SLEEP)
    if not url:
        return None
    artist = (meta.get("Artist") or {}).get("value", "") or ""
    lic = (meta.get("LicenseShortName") or {}).get("value", "") or ""
    return {
        "url": url,
        "title": file_title,
        "attribution": f"{file_title} | {artist} | {lic}".strip(" |"),
        "source": "wikipedia",
        "article": title,
    }


# ---------------------------------------------------------------------------
# Cache + public API
# ---------------------------------------------------------------------------
def _cache_key(scientific_name: str) -> str:
    return hashlib.md5(scientific_name.encode()).hexdigest()[:10]


def _cached(scientific_name: str) -> dict | None:
    key = _cache_key(scientific_name)
    for p in AUDIO_CACHE.glob(f"{key}.*"):
        if p.suffix == ".json" or p.name.endswith(".cv.wav"):
            continue
        meta_path = AUDIO_CACHE / f"{key}.json"
        meta = (json.loads(meta_path.read_text())
                if meta_path.exists() else {"attribution": "(cached)"})
        return {"path": p, **meta}
    return None


def find_recording(scientific_name: str,
                   common_name: str | None = None) -> dict | None:
    """Return {path, attribution, source, title} for one species, or None."""
    cached = _cached(scientific_name)
    if cached:
        return cached

    found = _xc_find(scientific_name) or _wiki_find(scientific_name, common_name)
    if not found:
        return None

    url = found["url"]
    ext = url.rsplit(".", 1)[-1].lower()
    # XC URLs end in /download with no extension; assume mp3.
    if len(ext) > 6 or "/" in ext or not ext.isalpha():
        ext = "mp3"
    key = _cache_key(scientific_name)
    out = AUDIO_CACHE / f"{key}.{ext}"
    try:
        out.write_bytes(_get(url, timeout=60))
    except Exception:
        return None

    info = {k: v for k, v in found.items() if k != "url"}
    (AUDIO_CACHE / f"{key}.json").write_text(json.dumps(info))
    info["path"] = out
    return info


def find_for_tree(tree_name: str, df=None) -> list[tuple[dict, dict | None]]:
    """Return [(row_dict, recording_or_None)] for every species in the tree."""
    from src import db
    if df is None:
        df = db.read_tree(tree_name)
    results = []
    for _, row in df.iterrows():
        sci = row.get("scientific_name")
        common = row.get("common_name")
        if not sci:
            results.append((row.to_dict(), None))
            continue
        try:
            rec = find_recording(sci, common)
        except Exception as exc:
            print(f"  err {sci}: {exc}")
            rec = None
        tag = rec.get("source") if rec else "no audio"
        print(f"  {sci:30} -> {tag}")
        results.append((row.to_dict(), rec))
    return results


def ensure_wav(path):
    """Convert any audio file to mono 22.05 kHz WAV via ffmpeg (cached)."""
    import subprocess
    path = Path(path)
    if path.suffix.lower() == ".wav":
        return path
    wav = path.with_suffix(".cv.wav")
    if wav.exists():
        return wav
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(path), "-ar", "22050", "-ac", "1",
         str(wav)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return wav


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('usage: python -m src.species_audio "Tree Name"')
        raise SystemExit(1)
    items = find_for_tree(sys.argv[1])
    n = sum(1 for _, r in items if r)
    print(f"\n{n} of {len(items)} species have a recording.")
