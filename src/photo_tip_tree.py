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
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

THUMB_PX = 56  # pixel diameter of each circular thumbnail


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
                              thumb_px: int = 30) -> str:
    """Inject circular tip thumbnails into a toytree SVG."""
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


def build_photo_tip_tree(tree_name: str,
                         out_dir: Path | None = None) -> Path:
    """Generate the unrooted SVG, inject circular tip photos, save as
    both .svg and .png (when cairosvg is available)."""
    from src import render
    out_dir = out_dir or config.OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    from src.tree import _safe as _safe_stem
    stem = _safe_stem(tree_name).lower()
    nwk_path = config.OUTPUT_DIR / f"{stem}_named_tree.nwk"
    meta_path = config.OUTPUT_DIR / f"{stem}_nodes.json"
    if not (nwk_path.exists() and meta_path.exists()):
        raise FileNotFoundError(f"Build the tree first: {nwk_path} missing")
    meta = render.load_meta(meta_path)

    # Render the unrooted SVG via the existing pipeline (so we get the
    # same header band + clade nodes + colors).
    out_stem = f"{stem}_photo_tips_base"
    render.render_files(nwk_path, meta, out_stem, layout="unrooted",
                         tree_name=tree_name)
    base_svg_path = out_dir / f"{out_stem}.svg"
    if not base_svg_path.exists():
        raise RuntimeError("render_files did not produce the unrooted SVG.")
    base_svg = base_svg_path.read_text()

    print(f"building photo URIs for tips in {tree_name}...")
    uris = _photo_uri_by_label(meta)
    print(f"  {len(uris)} label→thumbnail mappings ready")

    enhanced = _inject_thumbs_into_svg(base_svg, uris)

    out_svg = out_dir / f"{stem}_photo_tips.svg"
    out_svg.write_text(enhanced)
    print(f"wrote {out_svg}")

    # Rasterize via cairosvg if available
    out_png = out_dir / f"{stem}_photo_tips.png"
    try:
        import cairosvg
        cairosvg.svg2png(bytestring=enhanced.encode("utf-8"),
                          write_to=str(out_png), output_width=1600)
        print(f"wrote {out_png}")
        # Clean up the base intermediate
        try:
            base_svg_path.unlink()
            (out_dir / f"{out_stem}.png").unlink(missing_ok=True)
        except Exception:
            pass
        return out_png
    except Exception as exc:
        print(f"  PNG rasterization skipped ({exc}); SVG ready at {out_svg}")
        return out_svg


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m src.photo_tip_tree '<tree name>'")
        sys.exit(1)
    p = build_photo_tip_tree(sys.argv[1])
    print(f"final: {p}")
