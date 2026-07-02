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
    """Build the CARTO light-nolabels basemap at z=2 (4x4 tiles). Same
    coastline aesthetic as the blank outline map, so the composite +
    the blank outline read as one visual family."""
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
        bg=(250, 246, 238, 255),   # warm off-white paper
    )


def _density_layer_world(gbif_key: int, style: str):
    """One species density at z=2, all tiles fetched in parallel.

    Note: GBIF @1x tiles are 512×512, @0.5x are 256×256. CARTO tiles
    are 256×256. We use @0.5x so the two overlay at 1:1 with no
    coordinate displacement."""
    base = (
        "https://api.gbif.org/v2/map/occurrence/density/"
        f"{ZOOM}/{{x}}/{{y}}@0.5x.png?taxonKey={gbif_key}&style={style}"
    )
    urls = [base.format(x=x, y=y)
            for x in range(N_TILES) for y in range(N_TILES)]
    tiles = _fetch_many(urls)
    return _composite_tiles(tiles, base, N_TILES, bg=(0, 0, 0, 0))


def _species_legend_strip(mapped: list[dict], width: int):
    """Color-swatch + species label per row. Rendered on warm paper
    so it matches the blank outline aesthetic."""
    from PIL import Image, ImageDraw, ImageFont
    n = len(mapped)
    if n == 0:
        return None
    row_h = 22
    pad = 12
    height = n * row_h + 2 * pad
    strip = Image.new("RGB", (width, height), (250, 246, 238))
    draw = ImageDraw.Draw(strip)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
    except Exception:
        font = ImageFont.load_default()
    for i, sp in enumerate(mapped):
        y = pad + i * row_h + row_h // 2
        color = sp.get("color", "#ff2a1a")
        col = tuple(int(color.lstrip("#")[j:j+2], 16) for j in (0, 2, 4))
        draw.ellipse((pad, y - 7, pad + 14, y + 7), fill=col,
                     outline=(90, 70, 70))
        common = sp.get("common_name")
        sci = sp.get("scientific_name", "")
        lab = f"{common} ({sci})" if common else sci
        draw.text((pad + 24, y - 8), lab,
                  fill=(60, 40, 40), font=font)
    return strip


def build_range_map(tree_name: str,
                    out_dir: Path | None = None,
                    include_quadrants: bool = False) -> Path:
    """Render the composite range map. include_quadrants=False is fast
    (~10s); =True adds 4 zoomed quadrants (~50s)."""
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
          f"parallel fetches ({MAX_WORKERS} threads)")

    # 1. World basemap + per-species density at z=2
    world = _basemap_world()
    for sp in mapped:
        print(f"  density layer for {sp['scientific_name']}...")
        layer = _density_layer_world(sp["gbif_key"], sp["style"])
        world = Image.alpha_composite(world, layer)

    # 2. Legend strip (matches blank-outline aesthetic)
    legend = _species_legend_strip(mapped, width=CANVAS_W)
    legend_h = legend.size[1] if legend else 0

    # 3. Layout: title + world + legend on warm off-white paper so
    # this reads as the same visual family as the blank outline map.
    title_h = 60
    pad = 12
    total_h = title_h + CANVAS_H + pad + legend_h
    final = Image.new("RGBA", (CANVAS_W, total_h), (250, 246, 238, 255))
    draw = ImageDraw.Draw(final)
    try:
        title_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        sub_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
    except Exception:
        title_font = ImageFont.load_default()
        sub_font = ImageFont.load_default()
    draw.text((16, 12),
              f"Range map, {tree_name}",
              fill=(60, 40, 40, 255), font=title_font)
    draw.text((16, 40),
              f"{len(mapped)} species on GBIF, density overlays on "
              "the same coastlines you can sketch on.",
              fill=(120, 100, 100, 255), font=sub_font)

    y = title_h
    final.paste(world, (0, y), world)
    y += CANVAS_H + pad
    if legend:
        final.paste(legend, (0, y))

    # Credit footer (PIL variant): tiny bottom-right strip.
    try:
        from src import composite_credits
        final = composite_credits.draw_pil_credit_strip(
            final, tree_name,
            text_color=(90, 70, 70),
            bg_color=(250, 246, 238))
    except Exception as _exc:
        print(f"credit footer failed (non-fatal): {_exc}")

    out_path = out_dir / f"{stem}_range_map.png"
    final.convert("RGB").save(out_path, "PNG")
    print(f"wrote {out_path}")
    return out_path




# ────────────────────────────────────────────────────────────────────────
# Blank outline map for user drawing (no GBIF layers, no place names)
# ────────────────────────────────────────────────────────────────────────

CARTO_BLANK_TEMPLATE = (
    "https://a.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png"
)


def _basemap_blank_world():
    """CARTO light-no-labels basemap at z=2 — coastlines + muted land
    on a pale background, no place names. Meant for printing + sketching."""
    urls = [
        CARTO_BLANK_TEMPLATE.format(z=ZOOM, x=x, y=y)
        for x in range(N_TILES) for y in range(N_TILES)
    ]
    print(f"  fetching {len(urls)} blank basemap tiles (z={ZOOM})...")
    tiles = _fetch_many(urls)
    return _composite_tiles(
        tiles,
        CARTO_BLANK_TEMPLATE.replace("{z}", str(ZOOM)),
        N_TILES,
        bg=(250, 246, 238, 255),  # warm off-white paper
    )


def build_blank_outline_map(tree_name: str,
                            out_dir: Path | None = None) -> Path:
    """Render a printable blank outline map: coastlines only, no
    heatmaps, no labels, with a header naming the tree and space
    beneath for handwritten notes.

    Users can print this and sketch their own species observations,
    migration paths, family stories, whatever grows from the tree.
    Saved as outputs/<stem>_range_blank.png."""
    from PIL import Image, ImageDraw, ImageFont
    from src.tree import _safe as _safe_stem
    out_dir = out_dir or config.OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(tree_name).lower()

    world = _basemap_blank_world()

    # Header strip + note-taking gutter at the bottom
    title_h = 60
    gutter_h = 140  # blank space for notes
    total_h = title_h + CANVAS_H + gutter_h
    final = Image.new("RGBA", (CANVAS_W, total_h), (250, 246, 238, 255))
    draw = ImageDraw.Draw(final)
    try:
        title_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        sub_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
    except Exception:
        title_font = ImageFont.load_default()
        sub_font = ImageFont.load_default()
    draw.text((16, 12),
              f"Blank map — {tree_name}",
              fill=(60, 40, 40, 255), font=title_font)
    draw.text((16, 40),
              "coastlines only. sketch your species, migrations, "
              "family paths, stories.",
              fill=(120, 100, 100, 255), font=sub_font)

    final.paste(world, (0, title_h), world)

    # Ruled notes gutter (light pencil lines)
    gy0 = title_h + CANVAS_H + 20
    for row in range(4):
        y = gy0 + row * 28
        draw.line([(20, y), (CANVAS_W - 20, y)],
                  fill=(200, 190, 180, 255), width=1)

    # Blank outline map skips the per-species credit strip since it
    # has no species data. Just CARTO + OSM attributions in the header.
    out_path = out_dir / f"{stem}_range_blank.png"
    final.convert("RGB").save(out_path, "PNG")
    print(f"wrote {out_path}")
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m src.range_map_static [--blank] '<tree name>'")
        sys.exit(1)
    if sys.argv[1] == "--blank":
        print(build_blank_outline_map(sys.argv[2]))
    else:
        print(build_range_map(sys.argv[1]))
