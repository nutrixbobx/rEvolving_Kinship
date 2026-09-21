"""
Inline-photo unrooted tip tree.

Builds the unrooted SVG via render.render_files, then post-processes the
SVG to embed a small circular photo at each leaf tip. The photo is
clipped to a circle via SVG <clipPath> and placed at the (x,y) of the
tip's marker.

We base64-encode each thumbnail so the resulting SVG is fully self-
contained — no external image references, no broken-link risk when the
SVG is shared.

Output: outputs/<stem>_photo_tips.svg + .png (rasterized via cairosvg
when available; otherwise SVG only).
"""

from __future__ import annotations

import base64
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

THUMB_PX = 72  # pixel diameter of each circular thumbnail


def _circular_thumb_data_uri(image_path: Path | str,
                              px: int = THUMB_PX) -> str | None:
    """Crop center-square + circular mask + base64-encode. Returns a
    data URI suitable to drop straight into an <image href=...>."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    try:
        img = Image.open(image_path).convert("RGBA")
    except Exception:
        return None
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
    import io
    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _photo_uri_by_label(meta: dict) -> dict[str, str]:
    """Map each leaf label (common name AND scientific name forms used
    by toytree) to its circular-thumbnail data URI. Cached per build."""
    from src import species_profile
    uris: dict[str, str] = {}
    for tip_name, info in meta.items():
        if not info.get("is_leaf"):
            continue
        sci = info.get("scientific_name") or tip_name.replace("_", " ")
        common = info.get("common_name")
        try:
            p = species_profile.find_profile(sci, common)
        except Exception:
            p = None
        if not p or not p.get("image_path"):
            continue
        uri = _circular_thumb_data_uri(p["image_path"], px=THUMB_PX)
        if not uri:
            continue
        # Toytree's tip labels are the keys we'll see in the SVG. Map
        # all reasonable forms so the regex match below catches them.
        for key in {tip_name, tip_name.replace("_", " "), sci}:
            uris[key] = uri
        if common:
            uris[common] = uri
    return uris


# Toytree wraps every tip label in this group with a translate(X,Y)
# rotate(R) transform. We match the whole group, extract the label text
# (handling single <text> and multi-<tspan>), and inject an <image> as
# the first child so it inherits the group's transform (which positions
# the image at the same rotation/translation as the label).
_TIP_GROUP_RE = re.compile(
    r'(<g class="toytree-TipLabel"[^>]*>)(.*?)(</g>)',
    re.S,
)
# Pull the label text from inside the group's <text>...</text>, including
# multi-line <tspan> labels (common name + scientific name).
_LABEL_TEXT_RE = re.compile(r'<text[^>]*>(.*?)</text>', re.S)
_TSPAN_RE = re.compile(r'<tspan[^>]*>([^<]*)</tspan>', re.S)


def _label_candidates(text_inner: str) -> list[str]:
    """Return the variant strings to try as photo-dict keys: full label,
    first line only, last line only, with/without parens."""
    # Strip any markup; the content is either bare text or <tspan>...</tspan>
    raw = text_inner.strip()
    parts = _TSPAN_RE.findall(raw)
    if not parts:
        parts = [re.sub(r"<[^>]+>", "", raw)]
    parts = [s.strip() for s in parts if s.strip()]
    out = list(parts)
    if parts:
        out.append(parts[0])
        out.append(parts[-1])
        out.append(" ".join(parts))
    # Strip surrounding parens for scientific names rendered as (Genus species)
    extras = []
    for s in out:
        extras.append(s.replace("(", "").replace(")", "").strip())
    return list({s: None for s in out + extras if s}.keys())


def _inject_thumbs_into_svg(svg: str, uris: dict[str, str],
                              thumb_px: int = 47,
                              n_tips: int | None = None) -> str:
    """Inject circular tip thumbnails into a toytree SVG.
    thumb_px is the DEFAULT; when n_tips is passed, size scales
    inversely with tip count (5 tips -> 68px, 30 tips -> 34px)."""
    if n_tips is not None:
        thumb_px = max(34, min(72, int(72 - 1.6 * max(n_tips - 5, 0))))
    # Define one clipPath we can reuse via clip-path=url(#kn_tipclip)
    clip_id = "kn_tipclip"
    clip_def = (
        f'<defs><clipPath id="{clip_id}">'
        f'<circle cx="{thumb_px/2}" cy="{thumb_px/2}" r="{thumb_px/2}"/>'
        f'</clipPath></defs>'
    )
    svg2 = re.sub(r"(<svg\b[^>]*>)",
                   lambda m: m.group(1) + clip_def, svg, count=1)

    injected = 0
    matched_labels = []
    def repl(m: re.Match) -> str:
        nonlocal injected
        open_tag, inner, close_tag = m.groups()
        tx_m = _LABEL_TEXT_RE.search(inner)
        if not tx_m:
            return m.group(0)
        candidates = _label_candidates(tx_m.group(1))
        uri = None
        chosen = None
        for c in candidates:
            if c in uris:
                uri = uris[c]; chosen = c; break
        if not uri:
            return m.group(0)
        matched_labels.append(chosen)
        # The <text> sits with x>0 (label to the right of the pivot).
        # We place the image immediately to the LEFT of the pivot so it
        # appears just before the tip dot, in front of the label.
        img_x = -thumb_px - 6
        img_y = -thumb_px / 2
        image_tag = (
            f'<g transform="translate({img_x},{img_y})">'
            f'<image href="{uri}" width="{thumb_px}" height="{thumb_px}" '
            f'clip-path="url(#{clip_id})" '
            f'preserveAspectRatio="xMidYMid slice"/>'
            f'</g>'
        )
        injected += 1
        # Inject the image as the FIRST child of the TipLabel group so
        # the text is drawn on top.
        return open_tag + image_tag + inner + close_tag

    svg3 = _TIP_GROUP_RE.sub(repl, svg2)
    print(f"  matched {len(uris)} URIs, injected {injected} thumbnails")
    if matched_labels:
        print(f"  sample matches: {matched_labels[:5]}")
    return svg3


def _unrooted_positions(tre, W=1.0, H=1.0):
    """Equal-angle unrooted layout, the same one the interactive canvas
    uses: every subtree gets a wedge proportional to its leaf count, short
    steps along a unary ladder so a deep spine stays compact, long steps at
    real branch points so the species fan has room."""
    SPINE, BRANCH = 0.22, 1.0
    pos = {}

    def leaves_under(node):
        return max(1, sum(1 for _ in node.get_leaves()))

    def rec(node, a0, span, x, y):
        pos[node.idx] = (x, y)
        kids = [c for c in node.children] if not node.is_leaf() else []
        if not kids:
            return
        total = sum(leaves_under(c) for c in kids) or 1
        step = SPINE if len(kids) == 1 else BRANCH
        a = a0
        for ch in kids:
            sp = span * leaves_under(ch) / total
            mid = a + sp / 2.0
            rec(ch, a, sp, x + step * math.cos(mid), y + step * math.sin(mid))
            a += sp
    rec(tre.treenode, -math.pi / 2, 2 * math.pi, 0.0, 0.0)
    return pos


def build_photo_tip_tree(tree_name: str,
                         out_dir: Path | None = None) -> Path:
    """T2: the unrooted tree with a circular photo at every species tip and
    the clades numbered into a right-hand legend.

    Drawn entirely with matplotlib. The previous version built an SVG and
    leaned on cairosvg to rasterize it, so on a host without system cairo
    it wrote only an SVG, reported success, and left the dashboard with no
    PNG to show ("built but not coming up"). matplotlib is a hard
    dependency already, so this always produces the PNG."""
    import matplotlib
    matplotlib.use("Agg")
    from src import env_setup
    env_setup.register_matplotlib_fonts()
    import matplotlib.pyplot as plt
    import matplotlib.image as mpimg
    from src import render, species_profile, image_tree
    from src.tree import _safe as _safe_stem

    out_dir = out_dir or config.OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(tree_name).lower()

    nwk_path = config.OUTPUT_DIR / f"{stem}_named_tree.nwk"
    meta_path = config.OUTPUT_DIR / f"{stem}_nodes.json"
    if not (nwk_path.exists() and meta_path.exists()):
        raise FileNotFoundError(f"Build the tree first: {nwk_path} missing")
    meta = render.load_meta(meta_path)
    dated = {k for k, v in meta.items()
             if not v.get("is_leaf") and v.get("mya") is not None}

    import toytree
    nwk_str = render._collapse_unary(nwk_path, dated)
    nwk_str = render._prune_ancestral_spine(nwk_str)
    tre = toytree.tree(nwk_str)
    tips = list(tre.get_tip_labels())
    n = len(tips)

    pos = _unrooted_positions(tre)

    # Photos for the tips, in parallel and tolerant of gaps.
    print(f"fetching photos for {n} tips (parallel)...")
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _fetch(tip):
        info = meta.get(tip, {})
        sci = info.get("scientific_name") or tip.replace("_", " ")
        try:
            return tip, species_profile.find_profile(sci, info.get("common_name"))
        except Exception as exc:
            print(f"  err {sci}: {exc}")
            return tip, None

    profiles = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        for fut in as_completed([ex.submit(_fetch, t) for t in tips]):
            tip, prof = fut.result()
            profiles[tip] = prof

    BG = image_tree.BG
    fig_side = max(11.0, 1.25 * n + 7.0)
    fig = plt.figure(figsize=(fig_side, fig_side * 0.66), facecolor=BG)
    image_tree.draw_header(fig, tree_name)
    ax = fig.add_axes([0.02, 0.08, 0.74, 0.83])
    ax.set_facecolor(BG)
    ax.axis("off")

    # Edges first, so dots and photos sit on top.
    for node in tre.traverse():
        if node.is_root():
            continue
        px, py = pos[node.up.idx]
        cx, cy = pos[node.idx]
        ax.plot([px, cx], [py, cy], color=image_tree.EDGE, lw=1.6,
                zorder=1, solid_capstyle="round")

    # Numbered clade dots, same scheme as T1 so the two read as a pair.
    clade_entries = []
    counter = 0
    for node in tre.traverse():
        if node.is_leaf() or not node.name:
            continue
        counter += 1
        info = meta.get(node.name, {})
        clade_entries.append({
            "number": counter,
            "name": render._format_clade_name(node.name),
            "mya": info.get("mya"),
            "is_dated": node.name in dated,
        })
        x, y = pos[node.idx]
        col = image_tree.DATED if node.name in dated else image_tree.PLAIN
        ax.plot(x, y, "o", color=col, ms=11, zorder=3)
        ax.text(x, y, str(counter), color="#0e1b1a", fontsize=6.5,
                ha="center", va="center", weight="bold", zorder=4)

    # Tip photos as circles, with the name just outside them.
    xs = [pos[nd.idx][0] for nd in tre.traverse()]
    ys = [pos[nd.idx][1] for nd in tre.traverse()]
    span = max(max(xs) - min(xs), max(ys) - min(ys)) or 1.0
    r_img = span * 0.055
    for node in tre.traverse():
        if not node.is_leaf():
            continue
        x, y = pos[node.idx]
        info = meta.get(node.name, {})
        prof = profiles.get(node.name)
        placed = False
        if prof and prof.get("image_path") and Path(prof["image_path"]).exists():
            try:
                img = mpimg.imread(prof["image_path"])
                masked = photo_audio_circular(img)
                ax.imshow(masked, extent=(x - r_img, x + r_img,
                                           y - r_img, y + r_img),
                          zorder=5, interpolation="antialiased")
                placed = True
            except Exception as exc:
                print(f"  photo skipped for {node.name}: {exc}")
        if not placed:
            ax.plot(x, y, "o", color=image_tree.LEAF, ms=7, zorder=5)
        common = info.get("common_name")
        sci = info.get("scientific_name") or node.name.replace("_", " ")
        # Push the label outward from the tree's center so names radiate.
        dx, dy = x, y
        norm = math.hypot(dx, dy) or 1.0
        lx = x + (dx / norm) * (r_img + span * 0.035)
        ly = y + (dy / norm) * (r_img + span * 0.035)
        ha = "left" if dx >= 0 else "right"
        label = common if common else sci
        ax.text(lx, ly, label, color=image_tree.TIP_TEXT, fontsize=9.5,
                ha=ha, va="center", zorder=6,
                style="normal" if common else "italic")
        if common:
            ax.text(lx, ly - span * 0.030, f"({sci})",
                    color=image_tree.TIP_TEXT, fontsize=7.5, alpha=0.75,
                    ha=ha, va="center", style="italic", zorder=6)

    pad = span * 0.30
    ax.set_xlim(min(xs) - pad, max(xs) + pad)
    ax.set_ylim(min(ys) - pad, max(ys) + pad)
    ax.set_aspect("equal")

    image_tree._draw_clade_legend(fig, clade_entries, left=0.775,
                                  width=0.205, bottom=0.10, height=0.80)
    try:
        from src import composite_credits
        composite_credits.draw_matplotlib_credit_strip(fig, tree_name)
    except Exception as exc:
        print(f"credit strip skipped (non-fatal): {exc}")

    out_png = out_dir / f"{stem}_photo_tips.png"
    fig.savefig(str(out_png), facecolor=BG, dpi=140)
    plt.close(fig)
    print(f"wrote {out_png}")
    return out_png


def photo_audio_circular(img_arr):
    """Circular alpha mask, shared shape with T1's tip thumbnails."""
    import numpy as np
    a = np.asarray(img_arr)
    if a.ndim == 2:
        a = np.dstack([a] * 3)
    h, w = a.shape[:2]
    side = min(h, w)
    y0, x0 = (h - side) // 2, (w - side) // 2
    crop = a[y0:y0 + side, x0:x0 + side, :3]
    crop = crop / 255.0 if crop.dtype.kind == "u" else crop
    yy, xx = np.ogrid[:side, :side]
    c = side / 2.0
    mask = ((xx - c) ** 2 + (yy - c) ** 2) <= (c - 1) ** 2
    rgba = np.zeros((side, side, 4), dtype=float)
    rgba[..., :3] = crop
    rgba[..., 3] = mask.astype(float)
    return rgba
