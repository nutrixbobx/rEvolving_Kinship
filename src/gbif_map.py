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
    per species, and one grouped menu inside the map so nothing needs a
    Streamlit rerun: species toggles with solo and hover-highlight, a dark
    or light basemap, softer or bolder dots, a "Tour" that walks through
    the species one at a time, and a reset. Same play-space feel as the
    interactive tree.

    keep_params: query params to preserve on the species quick-look links
    (the links target _top, so a bare ?species=... would wipe the whole
    query string, including the ?s= remember-me token)."""
    mapped, _ = resolve_species(species_list)
    keep = "".join(
        "&" + urllib.parse.quote(str(k)) + "=" + urllib.parse.quote(str(v))
        for k, v in (keep_params or {}).items() if v)
    tokens = {
        "%%SPECIES%%": json.dumps(mapped),
        "%%KEEP%%": json.dumps(keep),
        "%%HEIGHT%%": str(int(height)),
        "%%CARTO%%": config.carto_key_suffix(),
    }
    html = _MAP_TEMPLATE
    for k, v in tokens.items():
        html = html.replace(k, v)
    return html


_MAP_TEMPLATE = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html, body, #map { margin:0; padding:0; height:%%HEIGHT%%px; width:100%;
    background:#0e1b1a; font-family:Helvetica,Arial,sans-serif; }
  .leaflet-container { background:#0e1b1a; }
  .leaflet-control-attribution { background:rgba(14,27,26,0.7)!important; color:#9ab3ab!important; font-size:10px; }
  .leaflet-control-attribution a { color:#ffd97a!important; }
  #menu { position:absolute; top:10px; left:10px; z-index:1000;
    display:flex; flex-direction:column; gap:8px; max-width:340px; }
  .grp { background:rgba(14,27,26,0.9); border:1px solid #26403b; border-radius:9px;
    padding:6px 8px; color:#e8f3ef; font-size:12px; }
  .gl { font-size:10px; letter-spacing:.12em; text-transform:uppercase; color:#7f978f;
    margin:0 0 4px 2px; user-select:none; display:flex; justify-content:space-between; align-items:center; }
  .row { display:flex; align-items:center; gap:6px; padding:3px 2px; border-radius:6px; cursor:pointer; }
  .row:hover { background:rgba(255,255,255,0.06); }
  .row input { margin:0; accent-color:#ffd97a; }
  .sw { display:inline-block; width:12px; height:12px; border-radius:50%; flex-shrink:0;
    box-shadow:0 0 0 1px rgba(255,255,255,0.25); }
  .row a { color:#e8f3ef; text-decoration:none; flex:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .row a em { color:#9ab3ab; }
  .row .solo { font-size:10px; color:#9ab3ab; border:1px solid #26403b; border-radius:5px; padding:1px 6px; }
  .row .solo:hover { border-color:#ffd97a; color:#ffd97a; }
  .btns { display:flex; gap:4px; flex-wrap:wrap; }
  .btns button { background:transparent; color:#e8f3ef; border:1px solid #26403b; border-radius:6px;
    padding:4px 9px; font-size:11.5px; cursor:pointer; white-space:nowrap; }
  .btns button:hover { border-color:#ffd97a; }
  .btns button.on { background:#ffd97a; color:#0e1b1a; font-weight:600; border-color:#ffd97a; }
  #spl { max-height:220px; overflow:auto; }
  #banner { position:absolute; left:50%; bottom:26px; transform:translateX(-50%); z-index:1000;
    background:rgba(14,27,26,0.92); border:1px solid #26403b; border-radius:12px;
    padding:10px 18px; color:#e8f3ef; text-align:center; pointer-events:none; opacity:0;
    transition:opacity .35s; box-shadow:0 4px 18px rgba(0,0,0,.5); max-width:70%; }
  #banner b { font-size:18px; display:block; }
  #banner i { color:#9ab3ab; font-size:13px; }
  @media (max-width:640px){ #menu { max-width:78%; } #spl { max-height:140px; } .btns button { padding:4px 7px; font-size:11px; } }
</style>
</head>
<body>
<div id="map"></div>
<div id="menu">
  <div class="grp">
    <div class="gl"><span>Species</span>
      <span class="btns"><button id="b-all">All</button><button id="b-none">None</button></span></div>
    <div id="spl"></div>
  </div>
  <div class="grp">
    <div class="gl"><span>Map</span></div>
    <div class="btns">
      <button id="b-dark" class="on">Dark</button><button id="b-light">Light</button>
      <button id="b-soft">Softer dots</button><button id="b-bold" class="on">Bolder dots</button>
      <button id="b-tour">Tour ▶</button><button id="b-reset">Reset view</button>
    </div>
  </div>
  <div class="grp">
    <div class="gl"><span>Export</span></div>
    <div class="btns">
      <button id="b-png">PNG of this view</button>
      <button id="b-csv">Species CSV</button>
    </div>
  </div>
</div>
<div id="banner"><b id="bn-name"></b><i id="bn-sci"></i></div>
<script>
(function(){
  var species = %%SPECIES%%;
  var KEEP = %%KEEP%%;
  var CARTO = "%%CARTO%%";
  var map = L.map('map', { worldCopyJump:true, preferCanvas:true, zoomControl:true }).setView([20, 0], 2);
  map.zoomControl.setPosition('topright');

  var base = {
    dark:  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'+CARTO,
             { attribution:'&copy; OpenStreetMap, &copy; CARTO', maxZoom:18, subdomains:'abcd', crossOrigin:true }),
    light: L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png'+CARTO,
             { attribution:'&copy; OpenStreetMap, &copy; CARTO', maxZoom:18, subdomains:'abcd', crossOrigin:true })
  };
  var isDark = true;
  base.dark.addTo(map);

  // Density tile recolored to the species' legend color (alpha = density).
  var SpeciesLayer = L.GridLayer.extend({
    createTile: function(coords, done){
      var size = this.getTileSize();
      var tile = document.createElement('canvas');
      tile.width = size.x; tile.height = size.y;
      var ctx = tile.getContext('2d', { willReadFrequently:true });
      var rgb = this.options.rgb;
      var img = new Image(); img.crossOrigin = 'anonymous';
      img.onload = function(){
        ctx.drawImage(img, 0, 0, size.x, size.y);
        var id = ctx.getImageData(0, 0, size.x, size.y), d = id.data;
        for (var i = 0; i < d.length; i += 4){
          if (d[i+3] > 0){ d[i]=rgb[0]; d[i+1]=rgb[1]; d[i+2]=rgb[2]; d[i+3]=Math.min(255, d[i+3]*1.6); }
        }
        ctx.putImageData(id, 0, 0); done(null, tile);
      };
      img.onerror = function(){ done(null, tile); };
      img.src = 'https://api.gbif.org/v2/map/occurrence/density/'+coords.z+'/'+coords.x+'/'+coords.y
        + '@1x.png?taxonKey='+this.options.taxonKey+'&style=scaled.circles';
      return tile;
    }
  });

  var layers = {}, on = {}, dotOpacity = 1.0;
  species.forEach(function(s){
    var ly = new SpeciesLayer({ taxonKey:s.gbif_key, rgb:s.rgb, opacity:dotOpacity, maxZoom:14,
      attribution:'<a href="https://www.gbif.org/" target="_blank">GBIF</a>' });
    ly.addTo(map); layers[s.scientific_name] = ly; on[s.scientific_name] = true;
  });

  function applyOpacity(){
    species.forEach(function(s){
      var ly = layers[s.scientific_name];
      if (on[s.scientific_name]){ if(!map.hasLayer(ly)) ly.addTo(map); ly.setOpacity(dotOpacity); }
      else if (map.hasLayer(ly)) map.removeLayer(ly);
    });
  }
  function setOn(key, v){ on[key] = v; var cb = document.getElementById('cb-'+idx(key)); if (cb) cb.checked = v; applyOpacity(); }
  function idx(key){ return species.findIndex(function(s){ return s.scientific_name===key; }); }
  function solo(key){ species.forEach(function(s){ setOn(s.scientific_name, s.scientific_name===key); }); }
  function highlight(key){
    species.forEach(function(s){
      var ly = layers[s.scientific_name];
      if (!map.hasLayer(ly)) return;
      ly.setOpacity(key==null ? dotOpacity : (s.scientific_name===key ? 1.0 : 0.18));
    });
  }

  // Species panel
  var spl = document.getElementById('spl'), html = '';
  species.forEach(function(s, i){
    var enc = encodeURIComponent(s.scientific_name);
    var body = s.common_name ? s.common_name + ' (<em>' + s.scientific_name + '</em>)' : '<em>' + s.scientific_name + '</em>';
    html += '<div class="row" data-key="'+s.scientific_name.replace(/"/g,'&quot;')+'">'
      + '<input type="checkbox" id="cb-'+i+'" checked>'
      + '<span class="sw" style="background:'+s.color+'"></span>'
      + '<a href="?species='+enc+KEEP+'" target="_top" title="Open a quick look">'+body+'</a>'
      + '<span class="solo">solo</span></div>';
  });
  spl.innerHTML = html;
  L.DomEvent.disableClickPropagation(document.getElementById('menu'));
  L.DomEvent.disableScrollPropagation(document.getElementById('menu'));
  spl.querySelectorAll('.row').forEach(function(row){
    var key = row.getAttribute('data-key');
    row.querySelector('input').addEventListener('change', function(){ setOn(key, this.checked); });
    row.querySelector('.solo').addEventListener('click', function(ev){ ev.preventDefault(); stopTour(); solo(key); });
    row.addEventListener('mouseenter', function(){ highlight(key); });
    row.addEventListener('mouseleave', function(){ highlight(null); });
  });
  document.getElementById('b-all').onclick = function(){ stopTour(); species.forEach(function(s){ setOn(s.scientific_name, true); }); };
  document.getElementById('b-none').onclick = function(){ stopTour(); species.forEach(function(s){ setOn(s.scientific_name, false); }); };

  // Basemap + dot weight
  function setBase(which){
    ['dark','light'].forEach(function(k){ if (map.hasLayer(base[k])) map.removeLayer(base[k]); });
    base[which].addTo(map); base[which].bringToBack();
    document.getElementById('b-dark').classList.toggle('on', which==='dark');
    document.getElementById('b-light').classList.toggle('on', which==='light');
    document.body.style.background = which==='dark' ? '#0e1b1a' : '#eaf3fb';
    isDark = which==='dark';
  }
  document.getElementById('b-dark').onclick = function(){ setBase('dark'); };
  document.getElementById('b-light').onclick = function(){ setBase('light'); };
  function setDots(v){
    dotOpacity = v; applyOpacity();
    document.getElementById('b-soft').classList.toggle('on', v < 1);
    document.getElementById('b-bold').classList.toggle('on', v >= 1);
  }
  document.getElementById('b-soft').onclick = function(){ setDots(0.55); };
  document.getElementById('b-bold').onclick = function(){ setDots(1.0); };
  document.getElementById('b-reset').onclick = function(){ map.setView([20,0],2); };

  // Tour: walk through the species one at a time, each shown alone with
  // its name on a banner. A small ritual for reading the map together.
  var tourTimer = null, tourI = 0, banner = document.getElementById('banner');
  function showBanner(s){
    document.getElementById('bn-name').textContent = s.common_name || s.scientific_name;
    document.getElementById('bn-sci').textContent = s.common_name ? s.scientific_name : '';
    banner.style.opacity = 1;
  }
  function tourStep(){
    var s = species[tourI % species.length]; tourI++;
    solo(s.scientific_name); showBanner(s);
  }
  function startTour(){
    if (!species.length) return;
    tourI = 0; tourStep();
    tourTimer = setInterval(tourStep, 3600);
    document.getElementById('b-tour').textContent = 'Stop ■';
    document.getElementById('b-tour').classList.add('on');
  }
  function stopTour(){
    if (!tourTimer) return;
    clearInterval(tourTimer); tourTimer = null;
    banner.style.opacity = 0;
    document.getElementById('b-tour').textContent = 'Tour ▶';
    document.getElementById('b-tour').classList.remove('on');
    species.forEach(function(s){ setOn(s.scientific_name, true); });
  }
  document.getElementById('b-tour').onclick = function(){ tourTimer ? stopTour() : startTour(); };

  // ---------- export ----------
  function download(blob, name){
    var a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
  }
  function exportPng(){
    // Compose exactly what is on screen: every loaded tile (basemap <img>
    // and our recolored density canvases) at its screen position, then a
    // legend of the species currently shown. Basemap tiles are requested
    // with crossOrigin so the canvas stays exportable.
    var mapEl = document.getElementById('map'); var r = mapEl.getBoundingClientRect();
    var c = document.createElement('canvas'); c.width = Math.round(r.width*2); c.height = Math.round(r.height*2);
    var ctx = c.getContext('2d'); ctx.scale(2,2);
    ctx.fillStyle = isDark ? '#0e1b1a' : '#eaf3fb'; ctx.fillRect(0,0,r.width,r.height);
    var tiles = mapEl.querySelectorAll('.leaflet-tile-loaded');
    var failed = 0;
    tiles.forEach(function(t){
      var tr = t.getBoundingClientRect(); var layerEl = t.closest('.leaflet-layer');
      var op = layerEl && layerEl.style.opacity !== '' ? parseFloat(layerEl.style.opacity) : 1;
      ctx.globalAlpha = isNaN(op) ? 1 : op;
      try { ctx.drawImage(t, tr.left - r.left, tr.top - r.top, tr.width, tr.height); } catch(e){ failed++; }
    });
    ctx.globalAlpha = 1;
    // legend
    var shown = species.filter(function(s){ return on[s.scientific_name]; });
    var pad = 10, rowH = 18, w = 0;
    ctx.font = '12px Helvetica, Arial, sans-serif';
    shown.forEach(function(s){ var t = (s.common_name ? s.common_name + '  ' : '') + s.scientific_name; w = Math.max(w, ctx.measureText(t).width); });
    var lh = shown.length*rowH + pad*2 + 16, lw = w + 34 + pad*2;
    var lx = r.width - lw - 12, ly = r.height - lh - 12;
    ctx.fillStyle = isDark ? 'rgba(14,27,26,0.92)' : 'rgba(255,255,255,0.92)';
    ctx.fillRect(lx, ly, lw, lh);
    ctx.strokeStyle = isDark ? '#26403b' : '#c8d6e2'; ctx.strokeRect(lx, ly, lw, lh);
    ctx.fillStyle = isDark ? '#9ab3ab' : '#4a5d6a'; ctx.font = '10px Helvetica, Arial, sans-serif';
    ctx.fillText('WHERE THESE KIN LIVE  ·  GBIF occurrence density', lx+pad, ly+pad+8);
    ctx.font = '12px Helvetica, Arial, sans-serif';
    shown.forEach(function(s, i){
      var y = ly + pad + 16 + i*rowH + 12;
      ctx.fillStyle = s.color; ctx.beginPath(); ctx.arc(lx+pad+7, y-4, 6, 0, Math.PI*2); ctx.fill();
      ctx.fillStyle = isDark ? '#e8f3ef' : '#1f2d36';
      ctx.fillText((s.common_name ? s.common_name + '  ' : ''), lx+pad+22, y);
      var cw = ctx.measureText(s.common_name ? s.common_name + '  ' : '').width;
      ctx.font = 'italic 12px Helvetica, Arial, sans-serif';
      ctx.fillText(s.scientific_name, lx+pad+22+cw, y);
      ctx.font = '12px Helvetica, Arial, sans-serif';
    });
    ctx.fillStyle = isDark ? '#7f978f' : '#6b7d8a'; ctx.font = '10px Helvetica, Arial, sans-serif';
    ctx.fillText('© OpenStreetMap, © CARTO · Occurrence data © GBIF', 10, r.height - 8);
    try { c.toBlob(function(b){ if (b) download(b, 'range_map.png'); else alert('Export failed. Try again after the tiles finish loading.'); }); }
    catch(e){ alert('The basemap blocked export in this browser. The static composite in Outputs is the fallback.'); }
    if (failed) console.warn('tiles skipped in export:', failed);
  }
  function exportCsv(){
    var rows = [['common_name','scientific_name','gbif_taxon_key','color','shown']];
    species.forEach(function(s){ rows.push([s.common_name||'', s.scientific_name, s.gbif_key, s.color, on[s.scientific_name] ? 'yes':'no']); });
    var csv = rows.map(function(r){ return r.map(function(v){ v = String(v); return /[",\n]/.test(v) ? '"'+v.replace(/"/g,'""')+'"' : v; }).join(','); }).join('\n');
    download(new Blob([csv], {type:'text/csv;charset=utf-8'}), 'range_map_species.csv');
  }
  document.getElementById('b-png').onclick = exportPng;
  document.getElementById('b-csv').onclick = exportCsv;
})();
</script>
</body>
</html>
"""
