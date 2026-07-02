"""
Interactive species range maps via GBIF.

Two GBIF APIs do the heavy lifting, both public, neither needs a key:

  - species/match   resolves a scientific name into GBIF's taxonKey
  - v2/map/occurrence/density   serves PNG tiles of occurrence density

The map is a Leaflet page with one tile layer per species, each rendered in a
different GBIF heatmap palette so the visitor can read overlap and isolation
at a glance. A layer panel on the right toggles species on and off; a small
legend on the left names the colors.

GBIF taxonKeys are looked up once per scientific name and cached on disk at
outputs/gbif_keys.json so the second visit is instant.
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

UA = {"User-Agent": "shared-rivers/1.0 (https://shared-rivers.org)"}
CACHE_PATH = config.OUTPUT_DIR / "gbif_keys.json"

# Six distinct GBIF heatmap styles. Each species in a tree gets one in order
# so neighboring species read as visually different on the same map.
# GBIF v2 heat styles we've verified actually render on-server. The
# .point solid-color variants (red.point, blue.point, orange.point,
# etc.) silently fall back to yellow at the tile server level, which
# was why Session E's palette all rendered as yellow. Swatches here
# are peak-density colors sampled directly from real tile pixels so
# the legend matches what the eye reads on the map.
GBIF_STYLES = [
    ("fire.point",        "#ff2a1a", "red heat"),
    ("greenHeat.point",   "#369617", "green heat"),
    ("blueHeat.point",    "#206eff", "blue heat"),
    ("purpleHeat.point",  "#ff21fd", "magenta heat"),
    ("orangeHeat.point",  "#c06719", "orange heat"),
    ("glacier.point",     "#0a5680", "glacier blue"),
]


def _get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout).read()


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text())
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2))


def get_gbif_key(scientific_name: str) -> int | None:
    """Resolve a scientific name to a GBIF taxonKey. Cached on disk so the
    second visit costs nothing."""
    if not scientific_name or not scientific_name.strip():
        return None
    name = scientific_name.strip()
    cache = _load_cache()
    if name in cache:
        v = cache[name]
        return int(v) if v else None
    url = ("https://api.gbif.org/v1/species/match"
           f"?name={urllib.parse.quote(name)}")
    try:
        data = json.loads(_get(url))
        key = data.get("usageKey")
    except Exception as exc:
        print(f"  GBIF match failed for {name}: {exc}")
        return None
    cache[name] = int(key) if key else None
    _save_cache(cache)
    return int(key) if key else None


def resolve_species(species_list: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split into (mapped, unmapped). Mapped rows gain gbif_key + visual style.
    The style is picked from GBIF_STYLES cycling through the palette in order
    of resolution, so neighboring species look different on the map."""
    mapped: list[dict] = []
    unmapped: list[dict] = []
    for sp in species_list:
        sci = sp.get("scientific_name")
        if not sci:
            continue
        key = get_gbif_key(sci)
        if key:
            style, color, color_name = GBIF_STYLES[len(mapped) % len(GBIF_STYLES)]
            mapped.append({
                **sp,
                "gbif_key": key,
                "style": style,
                "color": color,
                "color_name": color_name,
            })
        else:
            unmapped.append(sp)
    return mapped, unmapped


def species_for_tree(tree_name: str) -> list[dict]:
    """Pull the species rows for a tree into the simple shape build_map_html
    expects: [{scientific_name, common_name}, ...]."""
    from src import db
    df = db.read_tree(tree_name)
    if df.empty:
        return []
    out = []
    for _, row in df.iterrows():
        sci = row.get("scientific_name")
        if not isinstance(sci, str) or not sci.strip():
            continue
        common = row.get("common_name")
        if not isinstance(common, str):
            common = None
        out.append({
            "scientific_name": sci.strip(),
            "common_name": common,
        })
    return out


def build_map_html(species_list: list[dict], height: int = 620) -> str:
    """Return a self-contained Leaflet HTML page with one GBIF density layer
    per species. The page goes straight into st.components.v1.html()."""
    mapped, _ = resolve_species(species_list)
    species_json = json.dumps(mapped)
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html, body, #map {{
    margin:0; padding:0; height:{height}px; width:100%;
    background:#0e1b1a; font-family:Helvetica,Arial,sans-serif;
  }}
  .leaflet-container {{ background:#0e1b1a; }}
  .leaflet-control-layers {{
    background:rgba(14,27,26,0.92)!important;
    color:#e8f3ef!important; font-size:12px; border-radius:8px!important;
    border:1px solid #1c2e2b!important;
  }}
  .leaflet-control-layers-overlays label {{
    display:block; padding:3px 0; color:#e8f3ef;
    display:flex; align-items:center; gap:6px;
  }}
  /* Bigger, more visible swatches next to each toggle */
  .leaflet-control-layers-overlays .swatch {{
    display:inline-block; width:12px; height:12px; border-radius:50%;
    box-shadow:0 0 0 1px rgba(255,255,255,0.25);
    flex-shrink:0;
  }}
  .leaflet-control-attribution {{
    background:rgba(14,27,26,0.7)!important; color:#9ab3ab!important;
  }}
  .leaflet-control-attribution a {{ color:#ffd97a!important; }}
  .legend {{
    background:rgba(14,27,26,0.92); padding:10px 12px; border-radius:8px;
    color:#e8f3ef; font-size:11px; line-height:1.6; max-width:260px;
    box-shadow:0 2px 8px rgba(0,0,0,0.4); border:1px solid #1c2e2b;
  }}
  .legend-title {{ font-weight:bold; margin-bottom:6px; font-size:12px; }}
  .swatch {{
    display:inline-block; width:10px; height:10px; border-radius:50%;
    margin-right:6px; vertical-align:middle;
  }}
  .legend em {{ color:#9ab3ab; }}
</style>
</head>
<body>
<div id="map"></div>
<script>
var species = {species_json};
var map = L.map('map', {{ worldCopyJump:true, preferCanvas:true }})
            .setView([20, 0], 2);

L.tileLayer(
  'https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png',
  {{
    attribution: '&copy; OpenStreetMap, &copy; CARTO',
    maxZoom: 18, subdomains: 'abcd'
  }}
).addTo(map);

var overlays = {{}};
species.forEach(function(s) {{
  var url = 'https://api.gbif.org/v2/map/occurrence/density/{{z}}/{{x}}/{{y}}@1x.png'
    + '?taxonKey=' + s.gbif_key + '&style=' + s.style;
  var layer = L.tileLayer(url, {{
    attribution: '<a href="https://www.gbif.org/" target="_blank">GBIF</a>',
    opacity: 0.85, maxZoom: 14
  }});
  layer.addTo(map);
  // Species name links to the quick-look via ?species=... URL param
  // read by station.py. Uses parent.postMessage since the leaflet
  // iframe can't touch the parent URL directly under Streamlit's
  // sandbox. Fallback: plain visible name if messaging fails.
  var enc = encodeURIComponent(s.scientific_name);
  var linkBody = s.common_name
    ? s.common_name + ' (<em>' + s.scientific_name + '</em>)'
    : '<em>' + s.scientific_name + '</em>';
  var lbl = '<a href="?species=' + enc + '" target="_top" '
    + 'style="color:inherit;text-decoration:none;">'
    + linkBody + '</a>';
  var swatch = '<span class="swatch" style="background:' + s.color + '"></span>';
  overlays[swatch + lbl] = layer;
}});

L.control.layers(null, overlays, {{
  collapsed: false, position: 'topright'
}}).addTo(map);
</script>
</body>
</html>
"""
