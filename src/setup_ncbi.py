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


def validate_sqlite(path: Path) -> bool:
    """Open the SQLite file and run a tiny SELECT to confirm it isn't
    corrupted. Returns False if SQLite raises 'database disk image is
    malformed' or any other read error."""
    if not path.exists() or path.stat().st_size < 100_000_000:
        return False
    import sqlite3
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        # ete3's taxa.sqlite has a species table; any small query will do
        cur = con.execute("SELECT 1 FROM species LIMIT 1")
        cur.fetchone()
        con.close()
        return True
    except sqlite3.DatabaseError as exc:
        print(f"taxa.sqlite validation failed: {exc}", flush=True)
        return False
    except Exception as exc:
        print(f"taxa.sqlite read error: {exc}", flush=True)
        return False


def is_ready() -> bool:
    """True only when the taxa.sqlite file exists AND parses cleanly. A
    corrupt file (size check passes but SQLite errors) deletes itself so
    the next ensure_*() call re-downloads."""
    p = _default_path()
    if not p.exists() or p.stat().st_size < 100_000_000:
        return False
    if validate_sqlite(p):
        return True
    # Corrupted: clean it up so the next ensure_taxonomy_from_url() fetches
    # a fresh copy.
    try:
        print(f"Removing corrupt taxa.sqlite at {p}", flush=True)
        p.unlink()
    except Exception:
        pass
    return False


def force_redownload() -> bool:
    """Admin-triggered: delete any existing taxa.sqlite (corrupt or not)
    and re-fetch from NCBI_TAXA_URL. Returns True on success."""
    p = _default_path()
    if p.exists():
        try:
            p.unlink()
            print(f"Deleted {p} for forced re-download", flush=True)
        except Exception as exc:
            print(f"Could not delete {p}: {exc}", flush=True)
            return False
    return ensure_taxonomy_from_url()


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
