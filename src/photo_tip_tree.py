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


_TIP_TEXT_RE = re.compile(
    r'<text[^>]*\bid="t\d+"[^>]*x="([\d.\-]+)"[^>]*y="([\d.\-]+)"'
    r'[^>]*>([^<]+)</text>',
    re.S,
)


def _inject_thumbs_into_svg(svg: str, uris: dict[str, str],
                              thumb_px: int = 36) -> str:
    """Find every tip-label <text> in the SVG and inject an <image>
    immediately before it with the thumbnail clipped to a circle. The
    thumbnail sits to the LEFT of the text label (offset by thumb_px)."""
    # Toytree's tip text is rendered as <text class="toyplot-Text"...>
    # We use a more permissive matcher.
    pattern = re.compile(
        r'(<text[^>]*\b(?:class="[^"]*toyplot-Text[^"]*")?[^>]*'
        r'\sx="([\d.\-]+)"\s+y="([\d.\-]+)"[^>]*>)([^<]+)(</text>)',
        re.S,
    )
    # Add a single <clipPath> def at the top of the SVG (circular mask)
    clip_id = "kn_tipclip"
    clip_def = (
        f'<defs><clipPath id="{clip_id}">'
        f'<circle cx="{thumb_px/2}" cy="{thumb_px/2}" r="{thumb_px/2}"/>'
        f'</clipPath></defs>'
    )
    svg2 = re.sub(r"(<svg\b[^>]*>)",
                   lambda m: m.group(1) + clip_def, svg, count=1)

    injected = 0
    def repl(m: re.Match) -> str:
        nonlocal injected
        tag_open, x, y, text_content, tag_close = m.groups()
        label = text_content.strip()
        uri = (uris.get(label)
               or uris.get(label.split("\n")[0].strip())
               or uris.get(label.replace("(", "").replace(")", "").strip()))
        if not uri:
            return m.group(0)
        try:
            tx = float(x)
            ty = float(y)
        except ValueError:
            return m.group(0)
        # Place the image so its right edge meets the start of the text
        img_x = tx - thumb_px - 4
        img_y = ty - thumb_px / 2
        image_tag = (
            f'<g transform="translate({img_x:.1f},{img_y:.1f})">'
            f'<image href="{uri}" width="{thumb_px}" height="{thumb_px}" '
            f'clip-path="url(#{clip_id})" preserveAspectRatio="xMidYMid slice"/>'
            f'</g>'
        )
        injected += 1
        return image_tag + tag_open + text_content + tag_close

    svg3 = pattern.sub(repl, svg2)
    print(f"  injected {injected} tip thumbnails")
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
