"""
Runtime setup that used to come from apt (packages.txt).

We dropped packages.txt so a deploy no longer breaks when a Debian mirror's
Release file expires mid-build. The two things apt gave us are restored here
from pip plus bundled files, and both helpers are idempotent so they are safe
to call on every render:

  - ffmpeg, for decoding the mp3 recordings (Xeno-canto) that feed the
    spectrograms and the chorus. imageio-ffmpeg ships a static binary; we put
    it on PATH under the name 'ffmpeg' so librosa and audioread find it.
  - fonts, so non-Latin names render in the generated tree images and the PDF
    instead of empty boxes. matplotlib's built-in DejaVu already covers the
    Latin, Greek, and Cyrillic scripts; the bundled Noto Sans Armenian fills
    the gap the collective's own data actually hits, and Noto Sans rides along
    for broader coverage.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
BUNDLED_FONTS = ["NotoSans-Regular.ttf", "NotoSansArmenian-Regular.ttf"]


@lru_cache(maxsize=1)
def ensure_ffmpeg():
    """Put a usable ffmpeg on PATH from imageio-ffmpeg. Returns the exe path
    or None. No-op when a system ffmpeg is already present."""
    from shutil import which
    if which("ffmpeg"):
        return which("ffmpeg")
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None
    d = os.path.dirname(exe)
    # audioread/librosa shell out to the command 'ffmpeg'; the bundled binary
    # has a versioned name, so expose it under the plain name via a symlink.
    link = os.path.join(d, "ffmpeg")
    try:
        if not os.path.exists(link):
            os.symlink(exe, link)
    except Exception:
        pass
    os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
    os.environ.setdefault("IMAGEIO_FFMPEG_EXE", exe)
    os.environ.setdefault("FFMPEG_BINARY", exe)
    return exe


@lru_cache(maxsize=1)
def register_matplotlib_fonts() -> None:
    """Register the bundled Noto fonts with matplotlib and set a fallback
    chain so a glyph missing from the primary font is drawn from another
    registered font instead of a box (matplotlib 3.6+ per-glyph fallback)."""
    try:
        import matplotlib
        from matplotlib import font_manager
        for name in BUNDLED_FONTS:
            p = FONT_DIR / name
            if p.exists():
                try:
                    font_manager.fontManager.addfont(str(p))
                except Exception:
                    pass
        matplotlib.rcParams["font.family"] = "sans-serif"
        chain = ["DejaVu Sans", "Noto Sans", "Noto Sans Armenian"]
        existing = list(matplotlib.rcParams.get("font.sans-serif", []))
        matplotlib.rcParams["font.sans-serif"] = (
            chain + [f for f in existing if f not in chain])
    except Exception:
        pass


def bundled_font_path(prefer_armenian: bool = False):
    """Absolute path to a bundled TTF for PIL/ReportLab, or None."""
    order = (["NotoSansArmenian-Regular.ttf"] if prefer_armenian else []) \
        + BUNDLED_FONTS
    for name in order:
        p = FONT_DIR / name
        if p.exists():
            return str(p)
    return None
