"""
Inline-photo tip tree.

A variation of image_tree that, instead of putting photos in a side column,
puts a small circular thumbnail at each tip — right next to the species
label, masked to a circle so it doesn't overcrowd the tree's branches.

Output: outputs/<stem>_photo_tips.png on the same dark panel as the
dashboard tree, with the same header band.
"""

from __future__ import annotations

import io
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

THUMB_PX = 56  # circular thumbnail diameter in pixels


def _circular_thumb(image_path: Path | str, px: int = THUMB_PX):
    """Crop center-square + mask to circle. Returns a PIL Image with alpha
    channel set so the rendered patch is a clean disc."""
    from PIL import Image, ImageDraw
    img = Image.open(image_path).convert("RGBA")
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    img = img.resize((px, px), Image.LANCZOS)
    mask = Image.new("L", (px, px), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, px, px), fill=255)
    out = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def build_photo_tip_tree(tree_name: str,
                         out_dir: Path | None = None) -> Path:
    """Draw the tree with a small circular photo at each tip. Pulls photos
    from species_profile (cached on disk). Skips tips without an image and
    falls back to a plain dot."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.offsetbox import OffsetImage, AnnotationBbox

    from src import render, species_profile, image_tree

    out_dir = out_dir or config.OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = tree_name.strip().replace(" ", "_").lower()

    meta_path = config.OUTPUT_DIR / f"{stem}_nodes.json"
    nwk_path = config.OUTPUT_DIR / f"{stem}_named_tree.nwk"
    if not (meta_path.exists() and nwk_path.exists()):
        raise FileNotFoundError(
            f"Build the tree first: {meta_path} / {nwk_path} not found.")
    meta = render.load_meta(meta_path)
    dated = {k for k, v in meta.items()
             if not v.get("is_leaf") and v.get("mya") is not None}

    import toytree
    nwk_str = render._collapse_unary(nwk_path, dated)
    tre = toytree.tree(nwk_str)
    pos, max_depth, n = image_tree._layout(tre)

    fig_w = 14
    fig_h = max(8, 0.55 * n + 2.0)
    fig = plt.figure(figsize=(fig_w, fig_h), facecolor=BG)
    image_tree.draw_header(fig, tree_name)

    # Tree fills most of the canvas; we leave a strip on the right for
    # thumb+label so the thumbnails sit at the natural tip positions.
    ax = fig.add_axes([0.04, 0.05, 0.92, 0.88])
    ax.set_facecolor(BG)
    image_tree._draw_tree(ax, tre, pos, meta, dated, max_depth, n)

    # The tree draw above leaves labels on the right side; we want to
    # overlay our circular photos AT each tip position (just to the right
    # of the tip dot, slightly above the label text).
    tips = list(tre.get_tip_labels())
    fetched = 0
    skipped = 0
    for tip in tips:
        x, y = pos.get(tip, (None, None))
        if x is None:
            continue
        info = meta.get(tip, {})
        sci = info.get("scientific_name") or tip.replace("_", " ")
        common = info.get("common_name")
        profile = None
        try:
            profile = species_profile.find_profile(sci, common)
        except Exception:
            profile = None
        img_path = (profile or {}).get("image_path")
        if not img_path or not Path(img_path).exists():
            skipped += 1
            continue
        try:
            thumb = _circular_thumb(img_path, px=THUMB_PX)
        except Exception:
            skipped += 1
            continue
        oi = OffsetImage(thumb, zoom=0.45)
        # Place the thumb slightly to the right of the tip dot, so it
        # sits between the tip and its name without overlapping either.
        ab = AnnotationBbox(
            oi, (x + 0.18, y),
            xycoords="data", frameon=False, box_alignment=(0, 0.5),
            pad=0, zorder=10,
        )
        ax.add_artist(ab)
        fetched += 1

    print(f"photo tip tree: {fetched} thumbs, {skipped} missing")

    out_path = out_dir / f"{stem}_photo_tips.png"
    fig.savefig(out_path, dpi=160, facecolor=BG, bbox_inches="tight",
                pad_inches=0.2)
    plt.close(fig)
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m src.photo_tip_tree '<tree name>'")
        sys.exit(1)
    p = build_photo_tip_tree(sys.argv[1])
    print(f"wrote {p}")
