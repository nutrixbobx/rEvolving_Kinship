"""
Static range-map snapshot for the kinship report.

Fast version: parallelized tile fetches via ThreadPoolExecutor.
Render the world overview at z=2 (16 tiles), then optionally render
4 zoomed quadrants at z=3 (4x4 tiles each = 16 per quadrant).

Total tiles for a tree with N species, with quadrants=False:
  basemap: 16 + N * 16 = 16 * (1 + N)
For N=12: 208 tiles, ~10 sec parallel.

With quadrants=True (4 quadrants × 16 basemap + 16 per species each):
  208 (world) + 4 × 16 × (1 + N) = 208 + 832 = 1040 tiles
  ~50 sec parallel.

Saved as outputs/<stem>_range_map.png. Embedded in the kinship report
right under the Spectrogram Blend.
"""

from __future__ import annotations

import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

UA = {"User-Agent": "shared-rivers/1.0 (https://shared-rivers.org)"}

# z=2: 4x4 tiles = 1024px world. Fast + readable. z=3 was way too many
# fetches and was hanging.
ZOOM = 2
TILE_SIDE = 256
N_TILES = 1 << ZOOM           # 4 at z=2
CANVAS_W = TILE_SIDE * N_TILES  # 1024
CANVAS_H = CANVAS_W

QUADRANT_ZOOM = 3              # 8x8 world; per quadrant = 4x4 = 16 tiles
QUADRANT_TILES = 1 << QUADRANT_ZOOM // 2  # =4 per quadrant side

CARTO_TEMPLATE = (
    "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png"
    + config.carto_key_suffix()
)

# Light coastlines basemap (was: build_blank_outline_map's basemap).
# Session G composite migrated to this for the blank-outline visual
# family. Kept as a module constant after the blank-outline builder
# was deleted in Session J.
CARTO_BLANK_TEMPLATE = (
    "https://a.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png"
    + config.carto_key_suffix()
)

# Concurrent tile fetches. 8 keeps GBIF + CARTO happy without 429s.
MAX_WORKERS = 8

# Per-tile timeout (each one's own). Whole build can be > sum since we
# parallelize.
TILE_TIMEOUT = 10


def _fetch(url: str) -> tuple[str, bytes | None]:
    """Fetch one tile, return (url, bytes-or-None). Wraps exceptions so
    the executor doesn't choke on a single failing tile. Logs failures
    with the URL so we can see why a composite might come out empty."""
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=TILE_TIMEOUT) as r:
            data = r.read()
            if not data:
                print(f"  tile empty: {url}")
            return (url, data)
    except Exception as exc:
        print(f"  tile FETCH FAIL ({exc.__class__.__name__}): {url}")
        return (url, None)


def _fetch_many(urls: list[str]) -> dict[str, bytes]:
    """Fetch a batch of URLs in parallel. Returns {url: bytes} for
    successful fetches only."""
    out: dict[str, bytes] = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(_fetch, u) for u in urls]
        for fut in as_completed(futures):
            url, data = fut.result()
            if data:
                out[url] = data
    return out


def _composite_tiles(tile_bytes: dict[str, bytes],
                     base_url: str,
                     n_tiles: int,
                     x0: int = 0, y0: int = 0,
                     bg=(14, 27, 26, 255)):
    """Composite an n×n grid of fetched tiles into one image. base_url
    is the URL template substituted for the tile bytes lookup. x0/y0
    let us assemble a sub-grid (used for quadrants at higher zoom)."""
    from PIL import Image
    side = TILE_SIDE
    canvas = Image.new("RGBA", (side * n_tiles, side * n_tiles), bg)
    for dx in range(n_tiles):
        for dy in range(n_tiles):
            url = base_url.format(x=x0 + dx, y=y0 + dy)
            data = tile_bytes.get(url)
            if not data:
                continue
            try:
                tile = Image.open(BytesIO(data)).convert("RGBA")
                canvas.paste(tile, (dx * side, dy * side), tile)
            except Exception:
                pass
    return canvas


def _basemap_world():
    """Build the CARTO dark basemap at z=2 (4x4 tiles). Dark because
    GBIF's heat gradients (fire, greenHeat, blueHeat, etc.) are
    calibrated for dark backgrounds — on light backgrounds low-density
    pixels are near-black with low alpha and disappear entirely."""
    urls = [
        CARTO_TEMPLATE.format(z=ZOOM, x=x, y=y)
        for x in range(N_TILES) for y in range(N_TILES)
    ]
    print(f"  fetching {len(urls)} dark basemap tiles (z={ZOOM})...")
    tiles = _fetch_many(urls)
    return _composite_tiles(
        tiles,
        CARTO_TEMPLATE.replace("{z}", str(ZOOM)),
        N_TILES,
    )


def _basemap_world_light():
    """Light coastlines basemap at z=2 on near-white paper. For the
    printable outline map people draw and take notes on: thin gray
    coastlines, no labels, lots of open space to sketch ranges."""
    urls = [
        CARTO_BLANK_TEMPLATE.format(z=ZOOM, x=x, y=y)
        for x in range(N_TILES) for y in range(N_TILES)
    ]
    print(f"  fetching {len(urls)} light basemap tiles (z={ZOOM})...")
    tiles = _fetch_many(urls)
    return _composite_tiles(
        tiles,
        CARTO_BLANK_TEMPLATE.replace("{z}", str(ZOOM)),
        N_TILES,
        bg=(235, 244, 250, 255),
    )


def _density_layer_world(gbif_key: int, style: str,
                          color: str = "#ff2a1a",
                          alpha_scale: float = 1.6):
    """One species density at z=2, all tiles fetched in parallel and
    then re-colorized to the species' legend color.

    Two important tricks here:

    1. We fetch `scaled.circles` (not the heat-gradient point styles)
       because at global zoom sparse-observation species render as
       near-invisible dark pixels on gradients. scaled.circles gives
       solid visible dots regardless of density.

    2. We take the alpha channel of the returned tile as a density
       mask and re-color it with the species' legend hex. Result: the
       legend swatch is literally the color the eye sees on the map,
       and every species that has any observations at all shows up.

    GBIF v2 only serves @1x (512x512) or larger. We downscale to
    256x256 to align with the CARTO basemap."""
    base = (
        "https://api.gbif.org/v2/map/occurrence/density/"
        f"{ZOOM}/{{x}}/{{y}}@1x.png?taxonKey={gbif_key}"
        "&style=scaled.circles"
    )
    urls = [base.format(x=x, y=y)
            for x in range(N_TILES) for y in range(N_TILES)]
    tiles = _fetch_many(urls)

    # Parse the species color hex -> RGB
    rgb = tuple(int(color.lstrip("#")[j:j+2], 16) for j in (0, 2, 4))

    from io import BytesIO as _BytesIO
    from PIL import Image as _Image
    recolored: dict[str, bytes] = {}
    for url, data in tiles.items():
        try:
            im = _Image.open(_BytesIO(data)).convert("RGBA")
            if im.size != (TILE_SIDE, TILE_SIDE):
                im = im.resize((TILE_SIDE, TILE_SIDE), _Image.LANCZOS)
            # Take alpha as density mask, boost so faint dots become
            # visible, and use it as the alpha of a solid-colored image
            # in the species color.
            alpha = im.split()[-1]
            # Gamma-correct the alpha so low-density pixels don't
            # disappear entirely. Multiplying by 1.6 clipping at 255.
            import numpy as _np
            arr = _np.array(alpha, dtype=_np.float32) * alpha_scale
            arr = _np.clip(arr, 0, 255).astype(_np.uint8)
            boosted = _Image.fromarray(arr, mode="L")
            solid = _Image.new("RGBA", im.size, rgb + (0,))
            solid.putalpha(boosted)
            buf = _BytesIO()
            solid.save(buf, "PNG")
            recolored[url] = buf.getvalue()
        except Exception:
            continue
    return _composite_tiles(recolored, base, N_TILES, bg=(0, 0, 0, 0))


def _species_legend_strip(mapped: list[dict], width: int,
                          paper=(14, 27, 26, 255)):
    """Color swatch + species label per entry, laid out in as many columns
    as the width comfortably allows. A one-per-row list wasted most of a
    1024px-wide composite and pushed the map up; twelve species now fit in
    three short columns instead of twelve near-empty rows.

    Drawn on the same paper as the map so it reads on dark or warm-white."""
    from PIL import Image, ImageDraw, ImageFont
    n = len(mapped)
    if n == 0:
        return None
    bg = tuple(paper[:3])
    text_col = (60, 40, 40) if sum(bg) > 384 else (232, 243, 239)
    row_h = 22
    pad = 12
    swatch_w = 24

    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
    except Exception:
        from src import env_setup
        _fp = env_setup.bundled_font_path()
        font = ImageFont.truetype(_fp, 13) if _fp else ImageFont.load_default()

    def label_for(sp):
        common = sp.get("common_name")
        sci = sp.get("scientific_name", "")
        return f"{common} ({sci})" if common else sci

    # Widest label decides the column width, so nothing is clipped.
    probe = Image.new("RGB", (8, 8))
    pd = ImageDraw.Draw(probe)
    longest = 0
    for sp in mapped:
        try:
            longest = max(longest, int(pd.textlength(label_for(sp), font=font)))
        except Exception:
            longest = max(longest, len(label_for(sp)) * 7)
    col_w = min(max(220, longest + swatch_w + pad * 2), width - pad * 2)
    n_cols = max(1, min(n, (width - pad) // col_w))
    rows = (n + n_cols - 1) // n_cols

    height = rows * row_h + 2 * pad
    strip = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(strip)
    for i, sp in enumerate(mapped):
        col, row = divmod(i, rows)          # fill down, then across
        x = pad + col * col_w
        y = pad + row * row_h + row_h // 2
        color = sp.get("color", "#ff2a1a")
        rgb = tuple(int(color.lstrip("#")[j:j+2], 16) for j in (0, 2, 4))
        draw.ellipse((x, y - 7, x + 14, y + 7), fill=rgb)
        draw.text((x + swatch_w, y - 8), label_for(sp), fill=text_col,
                  font=font)
    return strip


def build_range_map(tree_name: str,
                    out_dir: Path | None = None,
                    include_quadrants: bool = False,
                    outline: bool = False) -> Path:
    """Render the composite range map. include_quadrants=False is fast
    (~10s); =True adds 4 zoomed quadrants (~50s).

    outline=True builds the printable version: light coastlines on warm
    paper, faint density so the observed ranges read as a reference, and
    an open notes band at the bottom. Made to print and draw on."""
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

    print(f"range map: {len(mapped)} species, "
          f"parallel fetches ({MAX_WORKERS} threads), "
          f"{'outline' if outline else 'dark'} style")

    # Palette per style. Outline = warm paper + dark ink + faint density
    # so there is room to draw. Dark = the same basemap the live tab uses.
    if outline:
        # Light blue-white so it reads as water and prints clean for
        # hand annotation.
        paper = (235, 244, 250, 255)
        ink = (40, 55, 70, 255)
        sub_ink = (120, 100, 100, 255)
        alpha_scale = 0.85
        subtitle = (f"{len(mapped)} species on GBIF. Faint dots are the "
                    "observed range; the rest is yours to draw and note.")
    else:
        paper = (14, 27, 26, 255)
        ink = (232, 243, 239, 255)
        sub_ink = (154, 179, 171, 255)
        alpha_scale = 1.6
        subtitle = (f"{len(mapped)} species on GBIF, density overlays on "
                    "the same dark basemap the live tab uses.")

    # 1. World basemap + per-species density at z=2
    world = _basemap_world_light() if outline else _basemap_world()
    for sp in mapped:
        print(f"  density layer for {sp['scientific_name']}...")
        layer = _density_layer_world(sp["gbif_key"], sp["style"],
                                       color=sp.get("color", "#ff2a1a"),
                                       alpha_scale=alpha_scale)
        world = Image.alpha_composite(world, layer)

    # 2. Legend strip. On the outline map it sits on the same warm paper.
    legend = _species_legend_strip(mapped, width=CANVAS_W, paper=paper)
    legend_h = legend.size[1] if legend else 0

    try:
        title_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        sub_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
    except Exception:
        from src import env_setup
        _fp = env_setup.bundled_font_path()
        title_font = ImageFont.truetype(_fp, 22) if _fp else ImageFont.load_default()
        sub_font = ImageFont.truetype(_fp, 13) if _fp else ImageFont.load_default()

    # Crop blank Antarctica so it doesn't eat a quarter of the drawing.
    ANTARCTIC_CROP = int(CANVAS_H * 0.22)
    world_visible_h = CANVAS_H - ANTARCTIC_CROP
    world_cropped = world.crop((0, 0, CANVAS_W, world_visible_h))

    # Open notes band under everything on the outline map.
    notes_h = 220 if outline else 0
    title_h = 60
    pad = 12
    total_h = title_h + world_visible_h + pad + legend_h + notes_h
    final = Image.new("RGBA", (CANVAS_W, total_h), paper)
    draw = ImageDraw.Draw(final)
    draw.text((16, 12), f"Range map, {tree_name}", fill=ink,
              font=title_font)
    draw.text((16, 40), subtitle, fill=sub_ink, font=sub_font)
    y = title_h
    final.paste(world_cropped, (0, y), world_cropped)
    y += world_visible_h + pad
    if legend:
        final.paste(legend, (0, y))
        y += legend_h
    if notes_h:
        draw.text((16, y + 10), "Notes", fill=sub_ink, font=sub_font)
        # Faint ruled lines to write on.
        for ly in range(y + 40, y + notes_h - 10, 34):
            draw.line([(16, ly), (CANVAS_W - 16, ly)],
                      fill=(200, 214, 226, 255), width=1)

    suffix = "range_outline" if outline else "range_map"
    out_path = out_dir / f"{stem}_{suffix}.png"
    final.convert("RGB").save(out_path, "PNG")
    print(f"wrote {out_path}")
    return out_path






if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m src.range_map_static '<tree name>'")
        sys.exit(1)
    print(build_range_map(sys.argv[1]))
