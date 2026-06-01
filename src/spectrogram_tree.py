"""
Sound kinship tree.

Render the rectangular cladogram on the left and a stacked column of
spectrograms on the right, one per tip, in tip order. Each spectrogram is
computed from the species' recording on Wikipedia (cached by species_audio).
Where no recording is available, the row notes that clearly.

Saved as outputs/<stem>_sound_tree.png on the same dark panel as the dashboard.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402


# Palette matched to the dashboard tree.
BG = "#0e1b1a"
EDGE = "#5f7d75"
LEAF = "#46c79a"
DATED = "#f0a24a"
PLAIN = "#6f8a82"
TIP_TEXT = "#e8f3ef"
LABEL = "#ffd97a"


def _layout(tre):
    """Return (positions dict by node.idx, max_depth, n_tips)."""
    tips = list(tre.get_tip_labels())
    n = len(tips)
    y_of_tip = {name: i for i, name in enumerate(tips)}
    def depth(node):
        d = 0
        while node.up:
            node = node.up; d += 1
        return d
    max_depth = max(depth(n) for n in tre.traverse() if n.is_leaf())
    pos = {}
    for node in tre.traverse("postorder"):
        if node.is_leaf():
            pos[node.idx] = (max_depth, y_of_tip[node.name])
        else:
            ys = [pos[c.idx][1] for c in node.children]
            pos[node.idx] = (depth(node), sum(ys) / len(ys))
    return pos, max_depth, n


def _draw_tree(ax, tre, pos, meta, dated, max_depth, n):
    """Draw a rectangular cladogram into a matplotlib axis."""
    # vertical bars at each internal split
    for node in tre.traverse():
        if node.is_leaf() or len(node.children) < 2:
            continue
        nx, _ = pos[node.idx]
        ys = [pos[c.idx][1] for c in node.children]
        ax.plot([nx, nx], [min(ys), max(ys)], color=EDGE, lw=1.6)

    # horizontal segments from parent to each child
    for node in tre.traverse():
        if node.is_root():
            continue
        px, _ = pos[node.up.idx]
        cx, cy = pos[node.idx]
        ax.plot([px, cx], [cy, cy], color=EDGE, lw=1.6)

    # node dots + tip labels + dated clade labels
    for node in tre.traverse():
        nx, ny = pos[node.idx]
        info = meta.get(node.name, {})
        if node.is_leaf():
            ax.plot(nx, ny, "o", color=LEAF, ms=6, zorder=3)
            common = info.get("common_name")
            sci = info.get("scientific_name") or node.name.replace("_", " ")
            if common:
                ax.text(nx + 0.18, ny, common, color=TIP_TEXT, fontsize=10,
                        va="center")
            else:
                ax.text(nx + 0.18, ny, sci, color=TIP_TEXT, fontsize=10,
                        va="center", style="italic")
        elif node.name in dated:
            ax.plot(nx, ny, "o", color=DATED, ms=9, zorder=3)
            mya = info.get("mya")
            ax.text(nx - 0.12, ny - 0.28, f"{node.name} {mya}",
                    color=LABEL, fontsize=8, ha="right", weight="bold")
        else:
            ax.plot(nx, ny, "o", color=PLAIN, ms=4, zorder=3)

    ax.set_xlim(-0.6, max_depth + 6)
    ax.set_ylim(n - 0.5, -0.5)
    ax.set_facecolor(BG)
    ax.axis("off")


def _spectrogram_strip(ax, audio_path: Path):
    """Compute and draw a magma spectrogram into one axis."""
    import librosa
    import scipy.signal as sps
    from src.species_audio import ensure_wav
    y, sr = librosa.load(str(ensure_wav(audio_path)), sr=22050, mono=True, duration=8.0)
    f, t, sxx = sps.spectrogram(y, sr, nperseg=512, noverlap=384)
    sxx_db = 10 * np.log10(sxx + 1e-10)
    ax.pcolormesh(t, f, sxx_db, cmap="magma", shading="auto",
                  vmin=sxx_db.max() - 50, vmax=sxx_db.max())
    ax.set_ylim(0, 8000)


def build_sound_tree(tree_name: str, out_dir: Path | None = None) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from src import render
    from src import species_audio

    out_dir = out_dir or config.OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = tree_name.strip().replace(" ", "_").lower()

    meta_path = config.OUTPUT_DIR / f"{stem}_nodes.json"
    nwk_path = config.OUTPUT_DIR / f"{stem}_named_tree.nwk"
    if not meta_path.exists() or not nwk_path.exists():
        raise FileNotFoundError(f"Build {tree_name} first (no nwk/meta).")
    meta = render.load_meta(meta_path)

    dated = {k for k, v in meta.items()
             if not v.get("is_leaf") and v.get("mya") is not None}

    import toytree
    nwk_str = render._collapse_unary(nwk_path, dated)
    tre = toytree.tree(nwk_str)
    pos, max_depth, n = _layout(tre)
    tips = list(tre.get_tip_labels())

    # Fetch (or load from cache) one recording per tip, using its scientific
    # name from the tree's metadata (the canonical NCBI name where it differs
    # from the CSV input).
    print(f"finding recordings for {n} tips ...")
    rec_by_tip = {}
    for tip in tips:
        info = meta.get(tip, {})
        sci = info.get("scientific_name") or tip.replace("_", " ")
        common = info.get("common_name")
        try:
            rec = species_audio.find_recording(sci, common)
        except Exception as exc:
            print(f"  err {sci}: {exc}"); rec = None
        rec_by_tip[tip] = rec
        print(f"  {sci:30} -> {'OK' if rec else '-'}")

    # Figure layout: tree on left ~40%, spectrograms on right ~55%.
    fig_w = 16
    fig_h = max(6, 0.6 * n + 1.5)
    fig = plt.figure(figsize=(fig_w, fig_h), facecolor=BG)

    ax_tree = fig.add_axes([0.02, 0.03, 0.43, 0.94])
    _draw_tree(ax_tree, tre, pos, meta, dated, max_depth, n)

    top, bot = 0.03, 0.03
    row_h = (1 - top - bot) / n
    for i, tip in enumerate(tips):
        y_bottom = 1 - top - (i + 1) * row_h
        h = row_h * 0.84
        ax = fig.add_axes([0.47, y_bottom + (row_h - h) / 2, 0.51, h])
        ax.set_facecolor(BG)
        rec = rec_by_tip.get(tip)
        if rec:
            try:
                _spectrogram_strip(ax, rec["path"])
            except Exception as exc:
                ax.text(0.5, 0.5, f"decode failed", ha="center", va="center",
                        color="#7a7a7a", fontsize=9, transform=ax.transAxes)
        else:
            ax.text(0.5, 0.5, "no open recording found",
                    ha="center", va="center", color="#5b6e69", fontsize=9,
                    transform=ax.transAxes)
        ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values():
            s.set_visible(False)

    out = out_dir / f"{stem}_sound_tree.png"
    fig.savefig(str(out), facecolor=BG, dpi=130)
    plt.close(fig)
    print(f"wrote {out.name}")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('usage: python -m src.spectrogram_tree "Tree Name"')
        raise SystemExit(1)
    build_sound_tree(sys.argv[1])
