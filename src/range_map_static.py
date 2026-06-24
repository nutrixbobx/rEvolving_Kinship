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

# Use z=2 (4 tiles wide) so the whole world fits in 1024px. Enough to
# read continents but light on bandwidth.
ZOOM = 2
TILE_SIDE = 256
N_TILES = 1 << ZOOM   # = 4 at z=2
CANVAS_W = TILE_SIDE * N_TILES   # 1024
CANVAS_H = CANVAS_W                # square, mercator

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

    print(f"composing range map: basemap + {len(mapped)} species ...")
    canvas = _basemap_canvas()
    for sp in mapped:
        layer = _gbif_density_canvas(sp["gbif_key"], style=sp["style"])
        canvas = Image.alpha_composite(canvas, layer)

    # Title strip at top
    final = Image.new("RGBA",
                       (CANVAS_W, CANVAS_H + 48),
                       (14, 27, 26, 255))
    final.paste(canvas, (0, 48), canvas)
    draw = ImageDraw.Draw(final)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
    except Exception:
        font = ImageFont.load_default()
    draw.text((12, 14),
               f"Range map — {tree_name}  ({len(mapped)} species, GBIF)",
               fill=(232, 243, 239, 255), font=font)

    out_path = out_dir / f"{stem}_range_map.png"
    final.convert("RGB").save(out_path, "PNG")
    print(f"wrote {out_path}")
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m src.range_map_static '<tree name>'")
        sys.exit(1)
    print(build_range_map(sys.argv[1]))
