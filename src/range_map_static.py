"""
Static range-map snapshot for the kinship report PDF.

Builds a composite world image:
  - CARTO dark-matter basemap tile at z=1 (1 tile = 256x256 of the
    whole world, dark background)
  - One GBIF occurrence-density tile per species at z=1, blended on
    top in the species' assigned palette color

Saved as outputs/<stem>_range_map.png. Embedded in the kinship report
right under the Spectrogram Blend.

Why a static image (rather than a live Leaflet embed): PDFs can't
render JavaScript. A static composite keeps the same visual information
without needing a headless browser.
"""

from __future__ import annotations

import sys
import urllib.request
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

UA = {"User-Agent": "shared-rivers/1.0 (https://shared-rivers.org)"}

# Use z=3 (8 tiles wide = 2048px world) so we can actually read
# continents. Quadrants render at z=4 over their quadrant only.
ZOOM = 3
TILE_SIDE = 256
N_TILES = 1 << ZOOM   # = 8 at z=3
CANVAS_W = TILE_SIDE * N_TILES   # 2048
CANVAS_H = CANVAS_W

CARTO_TEMPLATE = (
    "https://a.basemaps.cartocdn.com/dark_all/"
    "{z}/{x}/{y}.png"
)


def _fetch(url: str, timeout: int = 15) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers=UA)
        return urllib.request.urlopen(req, timeout=timeout).read()
    except Exception as exc:
        print(f"  fetch failed for {url}: {exc}")
        return None


def _basemap_canvas():
    """Composite N×N CARTO dark tiles into one world image."""
    from PIL import Image
    canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), (14, 27, 26, 255))
    for x in range(N_TILES):
        for y in range(N_TILES):
            url = CARTO_TEMPLATE.format(z=ZOOM, x=x, y=y)
            data = _fetch(url)
            if not data:
                continue
            try:
                tile = Image.open(BytesIO(data)).convert("RGBA")
                canvas.paste(tile, (x * TILE_SIDE, y * TILE_SIDE), tile)
            except Exception as exc:
                print(f"  basemap tile decode failed: {exc}")
    return canvas


def _gbif_density_canvas(gbif_key: int, style: str = "fire.point"):
    """Composite the GBIF density layer for one species into a single
    image of the same dims as the basemap."""
    from PIL import Image
    canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    for x in range(N_TILES):
        for y in range(N_TILES):
            url = (
                "https://api.gbif.org/v2/map/occurrence/density/"
                f"{ZOOM}/{x}/{y}@1x.png"
                f"?taxonKey={gbif_key}&style={style}"
            )
            data = _fetch(url)
            if not data:
                continue
            try:
                tile = Image.open(BytesIO(data)).convert("RGBA")
                canvas.paste(tile, (x * TILE_SIDE, y * TILE_SIDE), tile)
            except Exception as exc:
                print(f"  density tile decode failed: {exc}")
    return canvas





def _quadrant_canvas(quad: str, mapped: list[dict]):
    """Render one of NW/NE/SW/SE quadrants at z=4 for more detail.
    Each quadrant is a 4x4 tile grid (1024x1024) of half the world."""
    from PIL import Image
    z = 4
    side = 256
    n = 1 << z  # 16 tiles wide at z=4
    half = n // 2  # 8 tiles per quadrant
    if quad == "NW":
        x0, y0 = 0, 0
    elif quad == "NE":
        x0, y0 = half, 0
    elif quad == "SW":
        x0, y0 = 0, half
    else:  # SE
        x0, y0 = half, half
    canvas = Image.new("RGBA",
                        (side * half, side * half),
                        (14, 27, 26, 255))
    # basemap
    for dx in range(half):
        for dy in range(half):
            url = CARTO_TEMPLATE.format(z=z, x=x0 + dx, y=y0 + dy)
            data = _fetch(url)
            if not data:
                continue
            try:
                tile = (
                    __import__("PIL.Image").Image.open(
                        __import__("io").BytesIO(data)
                    ).convert("RGBA"))
                canvas.paste(tile, (dx * side, dy * side), tile)
            except Exception:
                pass
    # density overlay per species
    for sp in mapped:
        layer = Image.new("RGBA",
                           (side * half, side * half),
                           (0, 0, 0, 0))
        for dx in range(half):
            for dy in range(half):
                url = (
                    "https://api.gbif.org/v2/map/occurrence/density/"
                    f"{z}/{x0 + dx}/{y0 + dy}@1x.png"
                    f"?taxonKey={sp['gbif_key']}&style={sp['style']}"
                )
                data = _fetch(url)
                if not data:
                    continue
                try:
                    tile = (
                        __import__("PIL.Image").Image.open(
                            __import__("io").BytesIO(data)
                        ).convert("RGBA"))
                    layer.paste(tile, (dx * side, dy * side), tile)
                except Exception:
                    pass
        canvas = Image.alpha_composite(canvas, layer)
    return canvas


def _species_legend_strip(mapped: list[dict], width: int):
    """Compact swatch + label strip — one row per species, color-coded
    to its GBIF style palette color. Returns a PIL image."""
    from PIL import Image, ImageDraw, ImageFont
    n = len(mapped)
    if n == 0:
        return None
    row_h = 22
    pad = 12
    height = n * row_h + 2 * pad
    strip = Image.new("RGB", (width, height), (14, 27, 26))
    draw = ImageDraw.Draw(strip)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
    except Exception:
        font = ImageFont.load_default()
    for i, sp in enumerate(mapped):
        y = pad + i * row_h + row_h // 2
        # color swatch
        color = sp.get("color", "#ffd97a")
        # Convert hex to RGB
        col = tuple(int(color.lstrip("#")[j:j+2], 16) for j in (0, 2, 4))
        draw.ellipse((pad, y - 7, pad + 14, y + 7), fill=col)
        # label
        common = sp.get("common_name")
        sci = sp.get("scientific_name", "")
        lab = f"{common} ({sci})" if common else sci
        draw.text((pad + 24, y - 8), lab,
                   fill=(232, 243, 239), font=font)
    return strip



def build_range_map(tree_name: str,
                     out_dir: Path | None = None) -> Path:
    """Render the composite world map for this tree to disk.
    Returns the output path."""
    from PIL import Image, ImageDraw, ImageFont
    from src import db, gbif_map
    from src.tree import _safe as _safe_stem
    out_dir = out_dir or config.OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(tree_name).lower()

    df = db.read_tree(tree_name)
    if df.empty:
        raise ValueError(f"Tree '{tree_name}' has no species")

    species_for_map = []
    for _, row in df.iterrows():
        sci = row.get("scientific_name")
        if not isinstance(sci, str):
            continue
        species_for_map.append({
            "scientific_name": sci.strip(),
            "common_name": row.get("common_name") if isinstance(
                row.get("common_name"), str) else None,
        })
    mapped, unmapped = gbif_map.resolve_species(species_for_map)
    if not mapped:
        raise RuntimeError("No species in this tree are in GBIF.")

    print(f"composing range map (world + 4 quadrants): basemap + "
           f"{len(mapped)} species ...")
    # World overview at z=3
    world = _basemap_canvas()
    for sp in mapped:
        layer = _gbif_density_canvas(sp["gbif_key"], style=sp["style"])
        world = Image.alpha_composite(world, layer)

    # 2x2 quadrant grid at z=4 for actual detail
    print("  composing 4 quadrants (NW/NE/SW/SE) at z=4...")
    quads = {}
    for q in ("NW", "NE", "SW", "SE"):
        quads[q] = _quadrant_canvas(q, mapped)
        print(f"  {q} ready")
    q_w, q_h = quads["NW"].size
    quad_canvas = Image.new("RGBA", (q_w * 2, q_h * 2), (14, 27, 26, 255))
    quad_canvas.paste(quads["NW"], (0, 0), quads["NW"])
    quad_canvas.paste(quads["NE"], (q_w, 0), quads["NE"])
    quad_canvas.paste(quads["SW"], (0, q_h), quads["SW"])
    quad_canvas.paste(quads["SE"], (q_w, q_h), quads["SE"])

    # Species legend strip
    legend = _species_legend_strip(mapped, width=CANVAS_W)
    legend_h = legend.size[1] if legend else 0

    # Final layout: title + world + legend + quadrants. Width = world.
    title_h = 56
    pad = 12
    total_h = title_h + CANVAS_H + pad + legend_h + pad + q_h * 2
    final = Image.new("RGBA", (CANVAS_W, total_h), (14, 27, 26, 255))

    # Title strip
    draw = ImageDraw.Draw(final)
    try:
        title_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        sub_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except Exception:
        title_font = ImageFont.load_default()
        sub_font = ImageFont.load_default()
    draw.text((16, 12),
               f"Range map — {tree_name}",
               fill=(232, 243, 239, 255), font=title_font)
    draw.text((16, 38),
               f"{len(mapped)} species on GBIF · world overview + 4 quadrants",
               fill=(154, 179, 171, 255), font=sub_font)

    y = title_h
    final.paste(world, (0, y), world)
    y += CANVAS_H + pad
    if legend:
        final.paste(legend, (0, y))
        y += legend_h + pad
    final.paste(quad_canvas, (0, y), quad_canvas)

    out_path = out_dir / f"{stem}_range_map.png"
    final.convert("RGB").save(out_path, "PNG")
    print(f"wrote {out_path}")
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m src.range_map_static '<tree name>'")
        sys.exit(1)
    print(build_range_map(sys.argv[1]))
