"""
Spectrogram Blend: overlay every species' spectrogram in a tree into a
single composite image. Reads the cached spectrogram thumbnails from
outputs/_spec_cache/ (built by press_pdf or photo_audio_tree), aligns
them onto a common canvas, and averages with per-layer translucency so
the texture of one ecosystem's collective voice shows through.

Output: outputs/<stem>_spectrogram_blend.png on the dark panel.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

BG = "#0e1b1a"


def _spec_for_audio(audio_path: Path) -> Path | None:
    """Return the cached spectrogram PNG for an audio file, generating
    it on demand if missing. Cache shared with press_pdf."""
    if not audio_path or not Path(audio_path).exists():
        return None
    cache_dir = config.OUTPUT_DIR / "_spec_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(str(Path(audio_path).resolve()).encode()).hexdigest()[:16]
    out = cache_dir / f"{key}.png"
    if out.exists() and out.stat().st_size > 0:
        return out
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import librosa
        import numpy as np
        y, sr = librosa.load(str(audio_path), sr=None, mono=True, duration=8.0)
        if len(y) == 0:
            return None
        S = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=64,
                                              fmax=sr // 2)
        S_db = librosa.power_to_db(S, ref=np.max)
        fig, ax = plt.subplots(figsize=(3.0, 1.1), dpi=120,
                                  facecolor=BG)
        ax.imshow(S_db, aspect="auto", origin="lower", cmap="magma")
        ax.axis("off")
        fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
        fig.savefig(out, dpi=120, facecolor=BG,
                     bbox_inches="tight", pad_inches=0.02)
        plt.close(fig)
        return out
    except Exception:
        return None


def build_spectrogram_blend(tree_name: str,
                              out_dir: Path | None = None,
                              mode: str = "max") -> Path:
    """Overlay every species spectrogram in the tree onto a single image.
    Returns the path to outputs/<stem>_spectrogram_blend.png.

    mode: 'max' (default) keeps the BRIGHTEST value at every pixel
    across all layers — the composite reads as vivid as the brightest
    individual spectrogram. Use 'mean' for the older washed-out look
    (kept as opt-in for comparison)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from PIL import Image

    from src import db, species_audio
    from src.tree import _safe as _safe_stem

    out_dir = out_dir or config.OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(tree_name).lower()

    df = db.read_tree(tree_name)
    if df.empty:
        raise ValueError(f"Tree '{tree_name}' has no species")

    spec_paths: list[Path] = []
    for _, row in df.iterrows():
        sci = row.get("scientific_name")
        if not isinstance(sci, str) or not sci.strip():
            continue
        common = row.get("common_name") if isinstance(
            row.get("common_name"), str) else None
        try:
            rec = species_audio.find_recording(sci, common)
        except Exception:
            rec = None
        if not rec or not rec.get("path"):
            continue
        spec_png = _spec_for_audio(Path(rec["path"]))
        if spec_png and spec_png.exists():
            spec_paths.append(spec_png)

    if not spec_paths:
        raise RuntimeError(
            "No spectrograms available — build the chorus or the photo+"
            "audio tree first so the species' recordings are cached.")

    print(f"blending {len(spec_paths)} spectrograms...")

    # Load all spectrogram PNGs, resize to a common shape, blend
    canvas = None
    target_h, target_w = 600, 1800
    n_layers = 0
    for sp in spec_paths:
        try:
            im = Image.open(sp).convert("RGBA").resize(
                (target_w, target_h), Image.LANCZOS)
            arr = np.array(im).astype(np.float32) / 255.0
            if canvas is None:
                canvas = np.zeros_like(arr)
            if mode == "max":
                # Per-pixel maximum across all layers — vivid composite.
                canvas = np.maximum(canvas, arr)
            else:
                # Legacy mean blend — washed-out average.
                canvas = canvas + arr * (1.0 / max(len(spec_paths), 1))
            n_layers += 1
        except Exception as exc:
            print(f"  skip {sp.name}: {exc}")
    canvas = np.clip(canvas, 0, 1)
    print(f"  blended {n_layers} layers via {mode}")

    # Save
    fig, ax = plt.subplots(figsize=(14, 5), dpi=150, facecolor=BG)
    ax.imshow(canvas, aspect="auto", interpolation="bilinear")
    ax.axis("off")
    fig.subplots_adjust(left=0.02, right=0.98, top=0.92, bottom=0.06)
    ax.set_title(
        f"{tree_name} — Spectrogram Blend "
        f"({len(spec_paths)} voices overlaid)",
        color="#e8f3ef", fontsize=14, pad=12,
        family="Georgia, serif")
    fig.text(
        0.5, 0.02,
        "every species' spectrogram averaged with low alpha — "
        "the ecosystem's collective voice",
        ha="center", color="#9ab3ab", fontsize=9, style="italic")
    try:
        from src import composite_credits
        composite_credits.draw_matplotlib_credit_strip(
            fig, tree_name, text_color="#9ab3ab")
    except Exception as _exc:
        print(f"credit footer failed (non-fatal): {_exc}")
    out_path = out_dir / f"{stem}_spectrogram_blend.png"
    fig.savefig(out_path, dpi=150, facecolor=BG,
                 bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)
    print(f"wrote {out_path}")
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m src.spectrogram_blend '<tree name>'")
        sys.exit(1)
    print(build_spectrogram_blend(sys.argv[1]))
