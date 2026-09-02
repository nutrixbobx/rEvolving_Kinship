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

# Six distinct species colors. Both maps (interactive Leaflet tab and
# the static composite) now use the same trick: fetch GBIF
# `scaled.circles` tiles (solid, visible even for sparsely-observed
# species), keep only the alpha channel as a density mask, and paint
# it in the species color. The legend swatch is therefore literally
# the pixel color on the map, on both maps, always.
#
# History: the heat-gradient styles (fire.point, greenHeat.point...)
# render server-side as multi-hue ramps. fire peaks at amber-yellow,
# orangeHeat peaks at pale yellow, so dense areas of two different
# species became indistinguishable, and no single swatch hex could
# honestly describe a ramp. That was the "colors don't match the
# legend" bug. The .point solid styles (red.point etc.) are worse:
# they silently fall back to yellow server-side.
GBIF_STYLES = [
    ("scaled.circles", "#ff4136", "red"),
    ("scaled.circles", "#2ecc71", "green"),
    ("scaled.circles", "#339cff", "blue"),
    ("scaled.circles", "#ff5fd7", "magenta"),
    ("scaled.circles", "#ffb340", "orange"),
    ("scaled.circles", "#3fe0d0", "turquoise"),
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
    # Deterministic color by alphabetical rank of the scientific name, not
    # by resolution order. So a species is the same color on the live map
    # and on the static composite, and stays that color across rebuilds.
    # That was the "colors don't match the legend" confusion: the two maps
    # resolved species in different orders and handed out different hues.
    _ranked = sorted({
        sp.get("scientific_name", "").strip()
        for sp in species_list if sp.get("scientific_name")})
    _color_index = {name: i for i, name in enumerate(_ranked)}
    for sp in species_list:
        sci = sp.get("scientific_name")
        if not sci:
            continue
        key = get_gbif_key(sci)
        if key:
            _idx = _color_index.get(sci.strip(), len(mapped)) % len(GBIF_STYLES)
            style, color, color_name = GBIF_STYLES[_idx]
            mapped.append({
                **sp,
                "gbif_key": key,
                "style": style,
                "color": color,
                "color_name": color_name,
                "rgb": [int(color.lstrip("#")[j:j + 2], 16)
                        for j in (0, 2, 4)],
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


def build_map_html(species_list: list[dict], height: int = 620,
                   keep_params: dict | None = None) -> str:
    """Return a self-contained Leaflet HTML page with one GBIF density layer
    per species. The page goes straight into st.components.v1.html().

    keep_params: query params to preserve on the species quick-look links
    (the links target _top, so a bare ?species=... would wipe the whole
    query string, including the ?s= remember-me token; that signed
    people out)."""
    mapped, _ = resolve_species(species_list)
    species_json = json.dumps(mapped)
    keep = "".join(
        "&" + urllib.parse.quote(str(k)) + "=" + urllib.parse.quote(str(v))
        for k, v in (keep_params or {}).items() if v)
    keep_json = json.dumps(keep)
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

// Hand-rolled species panel: Leaflet's built-in L.control.layers
// wraps every label in a <label> element that intercepts anchor
// clicks. This custom control keeps the toggle checkbox and the
// species link as separate hit targets.
var KEEP_PARAMS = {keep_json};
var layerByKey = {{}};
// Canvas layer that fetches a GBIF density tile, keeps its alpha
// channel as the density mask, and paints it in the species' legend
// color. What the legend shows is exactly what the map draws.
var SpeciesLayer = L.GridLayer.extend({{
  createTile: function(coords, done) {{
    var size = this.getTileSize();
    var tile = document.createElement('canvas');
    tile.width = size.x; tile.height = size.y;
    var ctx = tile.getContext('2d', {{ willReadFrequently: true }});
    var rgb = this.options.rgb;
    var img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = function() {{
      ctx.drawImage(img, 0, 0, size.x, size.y);
      var id = ctx.getImageData(0, 0, size.x, size.y);
      var d = id.data;
      for (var i = 0; i < d.length; i += 4) {{
        if (d[i + 3] > 0) {{
          d[i] = rgb[0]; d[i + 1] = rgb[1]; d[i + 2] = rgb[2];
          d[i + 3] = Math.min(255, d[i + 3] * 1.6);
        }}
      }}
      ctx.putImageData(id, 0, 0);
      done(null, tile);
    }};
    img.onerror = function() {{ done(null, tile); }};
    img.src = 'https://api.gbif.org/v2/map/occurrence/density/'
      + coords.z + '/' + coords.x + '/' + coords.y + '@1x.png'
      + '?taxonKey=' + this.options.taxonKey + '&style=scaled.circles';
    return tile;
  }}
}});
species.forEach(function(s) {{
  var layer = new SpeciesLayer({{
    taxonKey: s.gbif_key, rgb: s.rgb,
    attribution: '<a href="https://www.gbif.org/" target="_blank">GBIF</a>',
    opacity: 0.9, maxZoom: 14
  }});
  layer.addTo(map);
  layerByKey[s.scientific_name] = layer;
}});

var speciesPanel = L.control({{ position: 'topright' }});
speciesPanel.onAdd = function() {{
  var div = L.DomUtil.create('div', 'leaflet-control-layers');
  div.style.padding = '8px 10px';
  div.style.background = 'rgba(14,27,26,0.92)';
  div.style.color = '#e8f3ef';
  div.style.borderRadius = '8px';
  div.style.maxWidth = '320px';
  var html = '';
  species.forEach(function(s, i) {{
    var enc = encodeURIComponent(s.scientific_name);
    var linkBody = s.common_name
      ? s.common_name + ' (<em>' + s.scientific_name + '</em>)'
      : '<em>' + s.scientific_name + '</em>';
    html += (
      '<div class="sp-row" style="display:flex;align-items:center;'
      + 'gap:6px;padding:3px 0;">'
      + '<input type="checkbox" id="sp-cb-' + i + '" data-key="'
      + s.scientific_name.replace(/"/g, '&quot;')
      + '" checked style="margin:0;">'
      + '<span class="swatch" style="background:' + s.color + '"></span>'
      + '<a href="?species=' + enc + KEEP_PARAMS + '" target="_top" '
      + 'style="color:#e8f3ef;text-decoration:none;flex:1;">'
      + linkBody + '</a>'
      + '</div>'
    );
  }});
  div.innerHTML = html;
  // Stop map from panning/zooming when interacting with the panel.
  L.DomEvent.disableClickPropagation(div);
  L.DomEvent.disableScrollPropagation(div);
  // Wire checkboxes to add/remove layers
  setTimeout(function() {{
    var cbs = div.querySelectorAll('input[type=checkbox]');
    cbs.forEach(function(cb) {{
      cb.addEventListener('change', function() {{
        var key = cb.getAttribute('data-key');
        var layer = layerByKey[key];
        if (!layer) return;
        if (cb.checked) layer.addTo(map);
        else map.removeLayer(layer);
      }});
    }});
  }}, 50);
  return div;
}};
speciesPanel.addTo(map);
</script>
</body>
</html>
"""
