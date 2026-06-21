"""
Inline HTML5 player with a synced spectrogram playhead.

For each species with a recording, build a self-contained HTML block that
shows the spectrogram as a background image and overlays a vertical line that
tracks the audio's `currentTime` as it plays. Audio and image bytes are
embedded as data URIs so nothing has to be served separately, and each player
is independent — you can have several playing at once if you want to mix them
in your ear.

Spectrograms are cached as PNG next to the audio file so the first view of a
tree is slow but every subsequent view is instant.
"""

from __future__ import annotations

import base64
import hashlib
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

CACHE = config.OUTPUT_DIR / "audio_cache"
SPEC_WIDTH_PX = 900
SPEC_HEIGHT_PX = 160


def _spectrogram_png_bytes(audio_path: Path) -> bytes:
    """Compute (and cache) a spectrogram PNG for one audio file."""
    from src import species_audio
    import librosa
    import scipy.signal as sps
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    audio_path = Path(audio_path)
    key = hashlib.md5(str(audio_path).encode()).hexdigest()[:10]
    png_path = CACHE / f"{key}.spec.png"
    if png_path.exists():
        return png_path.read_bytes()

    wav = species_audio.ensure_wav(audio_path)
    y, sr = librosa.load(str(wav), sr=22050, mono=True, duration=15.0)
    f, t, sxx = sps.spectrogram(y, sr, nperseg=512, noverlap=384)
    sxx_db = 10 * np.log10(sxx + 1e-10)

    dpi = 110
    fig, ax = plt.subplots(
        figsize=(SPEC_WIDTH_PX / dpi, SPEC_HEIGHT_PX / dpi),
        dpi=dpi, facecolor="#0e1b1a")
    ax.set_facecolor("#0e1b1a")
    ax.pcolormesh(t, f, sxx_db, cmap="magma", shading="auto",
                  vmin=sxx_db.max() - 50, vmax=sxx_db.max())
    ax.set_ylim(0, 8000)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    fig.tight_layout(pad=0)
    fig.savefig(str(png_path), facecolor="#0e1b1a", dpi=dpi)
    plt.close(fig)
    return png_path.read_bytes()


def _audio_bytes_for_browser(audio_path: Path) -> bytes:
    """Return WAV bytes the browser will play (convert via ffmpeg if needed)."""
    from src import species_audio
    wav = species_audio.ensure_wav(audio_path)
    return wav.read_bytes()


def player_html(common: str | None, scientific: str,
                audio_path: Path,
                attribution: str | None = None) -> str:
    """Return a self-contained HTML block: spectrogram, audio, synced playhead."""
    spec_b64 = base64.b64encode(_spectrogram_png_bytes(audio_path)).decode()
    wav_b64 = base64.b64encode(_audio_bytes_for_browser(audio_path)).decode()
    uid = hashlib.md5(f"{common}|{scientific}".encode()).hexdigest()[:8]
    label = common or scientific
    sci_html = f' <span style="color:#9ab3ab;font-style:italic">({scientific})</span>' if common else ""
    cred = (f'<div style="font-size:10px;color:#5b6e69;margin-top:4px">{attribution}</div>'
            if attribution else "")
    return f'''
<div style="background:#0e1b1a;padding:12px;border-radius:10px;color:#e8f3ef;
            font-family:Helvetica,Arial,sans-serif;margin-bottom:14px;
            box-sizing:border-box">
  <div style="font-size:14px;margin-bottom:6px"><b>{label}</b>{sci_html}</div>
  <div style="position:relative;width:100%;height:{SPEC_HEIGHT_PX}px;
              background:#0e1b1a;border-radius:6px;overflow:hidden">
    <img src="data:image/png;base64,{spec_b64}"
         style="width:100%;height:100%;display:block;pointer-events:none">
    <div id="ph_{uid}" style="position:absolute;top:0;left:0;width:2px;
                              height:100%;background:#ffd97a;
                              box-shadow:0 0 6px #ffd97a;opacity:0;
                              pointer-events:none;transition:opacity 0.2s"></div>
  </div>
  <audio id="au_{uid}" controls preload="metadata"
         src="data:audio/wav;base64,{wav_b64}"
         style="width:100%;margin-top:8px;display:block"></audio>
  {cred}
  <script>
    (function() {{
      var a = document.getElementById('au_{uid}');
      var p = document.getElementById('ph_{uid}');
      function upd() {{
        if (!isFinite(a.duration) || a.duration === 0) return;
        p.style.left = (a.currentTime / a.duration * 100) + '%';
        p.style.opacity = '1';
      }}
      a.addEventListener('timeupdate', upd);
      a.addEventListener('play', upd);
      a.addEventListener('seeked', upd);
      a.addEventListener('pause', upd);
      a.addEventListener('ended', function() {{ p.style.opacity = '0.4'; }});
    }})();
  </script>
</div>'''

