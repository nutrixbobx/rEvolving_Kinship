"""
Combined photo + audio square tree.

The third of Maya's three core outputs (alongside the unrooted SVG and
the unrooted-with-photos SVG). Same layout as image_tree.py but each
species row carries BOTH its photo AND a small spectrogram of its
recorded voice — a single image that shows the kinship + the visual +
the sonic at once.

Output: outputs/<stem>_photo_audio.png
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

BG = "#0e1b1a"
EDGE = "#5f7d75"
LEAF = "#46c79a"
DATED = "#f0a24a"
PLAIN = "#6f8a82"
TIP_TEXT = "#e8f3ef"
LABEL = "#ffd97a"


def _spec_png(audio_path: Path) -> Path | None:
    """Cached small spectrogram. Same cache as press_pdf's _spec_cache so
    repeated runs reuse the same thumbnails."""
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
        y, sr = librosa.load(str(audio_path), sr=None, mono=True,
                              duration=8.0)
        if len(y) == 0:
            return None
        S = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=64,
                                              fmax=sr // 2)
        S_db = librosa.power_to_db(S, ref=np.max)
        fig, ax = plt.subplots(figsize=(3.0, 1.0), dpi=120,
                                  facecolor="#0e1b1a")
        ax.imshow(S_db, aspect="auto", origin="lower", cmap="magma")
        ax.axis("off")
        fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
        fig.savefig(out, dpi=120, facecolor="#0e1b1a",
                     bbox_inches="tight", pad_inches=0.02)
        plt.close(fig)
        return out
    except Exception as exc:
        print(f"  spec failed for {audio_path}: {exc}")
        return None




def _circular_mask(img_arr):
    """Apply a circular alpha mask to a numpy image array (h, w, 3 or 4)
    so the photo renders as a clean circle matching T3's thumbnails."""
    import numpy as np
    h, w = img_arr.shape[:2]
    side = min(h, w)
    # Center-crop to square
    y0 = (h - side) // 2
    x0 = (w - side) // 2
    cropped = img_arr[y0:y0+side, x0:x0+side]
    # Build alpha
    yy, xx = np.ogrid[:side, :side]
    cy, cx = side / 2, side / 2
    mask = ((xx - cx) ** 2 + (yy - cy) ** 2) <= (side / 2 - 1) ** 2
    rgba = np.zeros((side, side, 4), dtype=np.float32)
    if cropped.ndim == 2:
        # grayscale -> stack
        for c in range(3):
            rgba[..., c] = cropped
    else:
        rgba[..., :3] = cropped[..., :3] / (255.0 if cropped.dtype.kind == "u" else 1.0)
    rgba[..., 3] = mask.astype(np.float32)
    return rgba


def build_photo_audio_tree(tree_name: str,
                            out_dir: Path | None = None) -> Path:
    """Build a square layout tree with photo + spectrogram per species
    row. Skips species without a photo or audio gracefully (renders an
    empty cell instead)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.image as mpimg

    from src import render, species_profile, species_audio, image_tree
    from src.tree import _safe as _safe_stem

    out_dir = out_dir or config.OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(tree_name).lower()

    meta_path = config.OUTPUT_DIR / f"{stem}_nodes.json"
    nwk_path = config.OUTPUT_DIR / f"{stem}_named_tree.nwk"
    if not (meta_path.exists() and nwk_path.exists()):
        raise FileNotFoundError(f"Build {tree_name} first.")
    meta = render.load_meta(meta_path)
    dated = {k for k, v in meta.items()
             if not v.get("is_leaf") and v.get("mya") is not None}

    import toytree
    nwk_str = render._collapse_unary(nwk_path, dated)
    tre = toytree.tree(nwk_str)
    pos, max_depth, n = image_tree._layout(tre)
    tips = list(tre.get_tip_labels())

    print(f"fetching photos + audio for {n} tips ...")
    rows = {}
    for tip in tips:
        info = meta.get(tip, {})
        sci = info.get("scientific_name") or tip.replace("_", " ")
        common = info.get("common_name")
        try:
            p = species_profile.find_profile(sci, common)
        except Exception:
            p = None
        try:
            a = species_audio.find_recording(sci, common)
        except Exception:
            a = None
        rows[tip] = {"profile": p, "audio": a}
        photo_status = "OK" if (p and p.get("image_path")) else "-"
        audio_status = "OK" if (a and a.get("path")) else "-"
        print(f"  {sci:30}  photo={photo_status}  audio={audio_status}")

    fig_w = 16
    fig_h = max(8, 1.15 * n + 2.6)
    fig = plt.figure(figsize=(fig_w, fig_h), facecolor=BG)
    image_tree.draw_header(fig, tree_name)
    image_tree._draw_legend(fig)

    # Detect whether any species in the tree has an audio recording.
    # When none do, the spec column becomes dead space, so we drop it
    # entirely and reallocate that width to the tree + photos.
    has_any_audio = any(
        rows[tip].get("audio") and rows[tip]["audio"].get("path")
        for tip in tips)

    tree_l, tree_b, tree_h = 0.02, 0.08, 0.80
    # Photo width scales inversely with tip count (sparse -> big).
    # When there's no spec column, photos can be bigger since they get
    # all the space that used to belong to spec.
    if has_any_audio:
        photo_w = max(0.06, min(0.11, 0.11 - 0.005 * max(n - 5, 0)))
        tree_w = 0.37 - (photo_w - 0.07) * 0.5
    else:
        photo_w = max(0.12, min(0.22, 0.22 - 0.008 * max(n - 5, 0)))
        tree_w = 0.42 - (photo_w - 0.13) * 0.4
    ax_tree = fig.add_axes([tree_l, tree_b, tree_w, tree_h])
    clade_entries = image_tree._draw_tree(
        ax_tree, tre, pos, meta, dated, max_depth, n)
    image_tree._draw_clade_legend(
        fig, clade_entries,
        left=0.895, width=0.10,
        bottom=tree_b, height=tree_h)

    # Photo + spec columns. No equal-row-height heuristic — instead we
    # use the tree's actual tip Y positions so every photo lines up
    # vertically with its tip dot.
    photo_left = tree_l + tree_w + 0.01
    if has_any_audio:
        spec_left = photo_left + photo_w + 0.012
        spec_w = 0.895 - spec_left - 0.005
    else:
        # No spec column at all
        spec_left = 0.0
        spec_w = 0.0

    # tree axes span: figure_y(tip i) = tree_b + tree_h - (i/(n-1)) * tree_h
    # for n>=2. For n=1, center the single row.
    def _tip_fig_y(i: int) -> float:
        if n <= 1:
            return tree_b + tree_h / 2
        return tree_b + tree_h - (i / (n - 1)) * tree_h
    # Row height in figure coords: half the spacing between two tips
    row_pitch_fig = tree_h / max(n - 1, 1)
    # Cap scales with photo_w so wide photos are also tall (roughly square).
    _photo_h_cap = photo_w * 1.6
    h = min(row_pitch_fig * 0.85, _photo_h_cap)

    for i, tip in enumerate(tips):
        info = meta.get(tip, {})
        common = info.get("common_name") or info.get("scientific_name") or tip
        sci = info.get("scientific_name") or tip.replace("_", " ")
        y_center = _tip_fig_y(i)
        y_bottom = y_center - h / 2

        # Photo (circular masked)
        ax_p = fig.add_axes([photo_left, y_bottom, photo_w, h])
        ax_p.set_facecolor(BG)
        p = rows[tip].get("profile")
        if p and p.get("image_path") and Path(p["image_path"]).exists():
            try:
                img = mpimg.imread(p["image_path"])
                masked = _circular_mask(img)
                ax_p.imshow(masked, aspect="equal")
            except Exception:
                pass
        ax_p.axis("off")

        # Spectrogram strip — only if the tree has any audio at all
        if has_any_audio and spec_w > 0:
            ax_s = fig.add_axes([spec_left, y_bottom, spec_w, h])
            ax_s.set_facecolor(BG)
            a = rows[tip].get("audio")
            if a and a.get("path"):
                spec = _spec_png(Path(a["path"]))
                if spec and spec.exists():
                    try:
                        sp_img = mpimg.imread(spec)
                        ax_s.imshow(sp_img, aspect="auto")
                    except Exception:
                        pass
            ax_s.axis("off")

        # Credits no longer rendered inline — they live on the
        # dedicated page in the kinship report and in the sibling
        # <stem>_credits.txt file written next to this image.

    # Minimal credits footer at the bottom-right so every export
    # carries its per-species attributions inline.
    try:
        from src import composite_credits
        composite_credits.draw_matplotlib_credit_strip(fig, tree_name)
    except Exception as _exc:
        print(f"credit footer failed (non-fatal): {_exc}")
    out_path = out_dir / f"{stem}_photo_audio.png"
    fig.savefig(out_path, dpi=140, facecolor=BG, bbox_inches="tight",
                pad_inches=0.2)
    plt.close(fig)
    print(f"wrote {out_path}")

    # Sibling credits file alongside the image so every export carries
    # its credits with it.
    try:
        from src.credits import write_credits_txt
        credits_path = out_dir / f"{stem}_credits.txt"
        write_credits_txt(tree_name, credits_path)
        print(f"wrote {credits_path}")
    except Exception as exc:
        print(f"credits.txt write failed: {exc}")

    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m src.photo_audio_tree '<tree name>'")
        sys.exit(1)
    print(build_photo_audio_tree(sys.argv[1]))
