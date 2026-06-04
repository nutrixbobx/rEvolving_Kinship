"""
Bootstrap the NCBI taxonomy SQLite on startup.

If the local file is missing AND NCBI_TAXA_URL is set (e.g. a Supabase
Storage public URL pointing at taxa.sqlite or taxa.sqlite.gz), download and
decompress it once into ~/.etetoolkit/taxa.sqlite. This is much faster than
the full NCBI build (~30 seconds vs ~5 minutes).

If NCBI_TAXA_URL is not set, the caller falls back to ete3's default build
behavior (download from NCBI FTP + rebuild local sqlite).
"""

from __future__ import annotations
import gzip
import os
import shutil
import sys
import urllib.request
from pathlib import Path


def _default_path() -> Path:
    custom = os.environ.get("NCBI_TAXA_DB")
    if custom:
        return Path(custom)
    return Path.home() / ".etetoolkit" / "taxa.sqlite"


def is_ready() -> bool:
    p = _default_path()
    return p.exists() and p.stat().st_size > 100_000_000  # ~100 MB sanity floor


def ensure_taxonomy_from_url() -> bool:
    """Try to fetch the NCBI taxonomy from NCBI_TAXA_URL. Returns True on
    success, False if no URL is configured or the download failed."""
    if is_ready():
        return True
    url = os.environ.get("NCBI_TAXA_URL")
    if not url:
        return False

    target = _default_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    print(f"Downloading NCBI taxonomy from {url}", flush=True)

    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "shared-rivers/1.0"})
        with urllib.request.urlopen(req, timeout=600) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f, length=1024 * 1024)
    except Exception as exc:
        print(f"Download failed: {exc}", flush=True)
        if tmp.exists():
            tmp.unlink()
        return False

    try:
        if url.lower().endswith(".gz"):
            print("Decompressing...", flush=True)
            with gzip.open(tmp, "rb") as gz, open(target, "wb") as out:
                shutil.copyfileobj(gz, out, length=1024 * 1024)
            tmp.unlink()
        else:
            tmp.rename(target)
    except Exception as exc:
        print(f"Decompress/move failed: {exc}", flush=True)
        return False

    print(f"NCBI taxonomy ready at {target} "
          f"({target.stat().st_size:,} bytes)", flush=True)
    return True


if __name__ == "__main__":
    if ensure_taxonomy_from_url():
        print("OK")
    else:
        print("No NCBI_TAXA_URL configured or download failed; "
              "fall back to ete3 default build.")
        sys.exit(1)
