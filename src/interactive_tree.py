"""
Draggable, rearrangeable tree (v3).

One grouped menu inside the canvas covers everything, so nothing here
needs a Streamlit rerun (which would wipe an arrangement):

  Layout   Unrooted (equal-angle, the default) / Radial / Rectangular
  Show     Clades (dated / all / none), Labels, Latin names, Photos
  View     To LCA (jump to the last common ancestor), Whole tree, Fit
  Export   PNG / SVG, with photos embedded so they survive export

Interactions: drag any node (a clade carries its subtree); click a clade
to focus on it and hide the deeper ancestors; click the focused top clade
to step back out; shift-click to flip a clade's children; scroll to zoom,
drag the background to pan.

Two things make it read cleanly at any zoom. Dots, labels, and photos are
counter-scaled so zooming changes spacing, not element size, and edges use
a non-scaling stroke. And clade labels are decluttered greedily: species
labels always draw, then clade labels by age, skipping any that would
overlap something already placed. Zoom in and more of them appear; hover
any dot for its name regardless.

Public entry: `build_interactive_html(newick_path, meta, tree_name, ...)`.
"""

from __future__ import annotations

import json
import urllib.parse
from pathlib import Path


def _q(v: str) -> str:
    return urllib.parse.quote(v, safe="")


BG = "#0e1b1a"
EDGE = "#5f7d75"
LEAF = "#46c79a"
DATED = "#f0a24a"
PLAIN = "#6f8a82"
TIP = "#e8f3ef"
LABEL = "#ffd97a"


def _hierarchy(newick_path, meta: dict) -> dict:
    from ete3 import Tree
    from src import render

    dated = {k for k, v in meta.items()
             if not v.get("is_leaf") and v.get("mya") is not None}
    nwk = render._collapse_unary(newick_path, dated)
    t = Tree(nwk, format=1)

    def conv(node) -> dict:
        name = node.name or ""
        info = meta.get(name, {})
        if node.is_leaf():
            sci = info.get("scientific_name") or name.replace("_", " ")
            return {"name": name, "is_leaf": True,
                    "common": info.get("common_name"), "sci": sci}
        return {
            "name": name, "is_leaf": False,
            "clade": render._format_clade_name(name) if name else "",
            "mya": info.get("mya"),
            "dated": name in dated,
            "children": [conv(c) for c in node.children],
        }

    return conv(t)


def build_interactive_html(newick_path, meta: dict,
                           tree_name: str | None = None,
                           height: int = 720,
                           show_scientific: bool = True,
                           photos: dict | None = None,
                           names: dict | None = None,
                           can_share: bool = False,
                           signed_in: bool = False,
                           initial_view: str | None = None,
                           initial_scope: str | None = None,
                           keep_params: dict | None = None) -> str:
    """Self-contained draggable tree page for components.html().

    show_scientific sets the initial state of the in-canvas toggle.
    photos: {scientific_name: url} or {scientific_name: [url, ...]}. With
      more than one, the canvas shows arrows to pick a preferred photo.
    names: {scientific_name: [{"t": text, "l": lang, "c": category}, ...]}
      from the Library, so a visitor can click a species and cycle through
      every name it goes by.
    can_share: this reader may write the tree's shared view (admin/editor).
    signed_in: this reader has an account, so they get a personal view.
    initial_view / initial_scope: the saved view JSON to open with, and
      whether it came from this person ("me") or the tree ("all").
    keep_params: query params to carry through the save round trip, above
      all the ?s= session token. Losing it would sign the person out."""
    data = _hierarchy(newick_path, meta)
    # Normalize photos to a list per species so the canvas has one shape.
    photo_lists: dict[str, list[str]] = {}
    for sci, val in (photos or {}).items():
        if isinstance(val, str):
            photo_lists[sci] = [val]
        elif val:
            photo_lists[sci] = [u for u in val if u][:3]
    tokens = {
        "%%DATA%%": json.dumps(data),
        "%%PHOTOS%%": json.dumps(photo_lists),
        "%%NAMES%%": json.dumps(names or {}),
        "%%SHOWSCI%%": "true" if show_scientific else "false",
        "%%CANSHARE%%": "true" if can_share else "false",
        "%%SIGNEDIN%%": "true" if signed_in else "false",
        "%%INITVIEW%%": initial_view if initial_view else "null",
        "%%INITSCOPE%%": json.dumps(initial_scope or ""),
        "%%KEEP%%": json.dumps("".join(
            "&" + _q(str(k)) + "=" + _q(str(v))
            for k, v in (keep_params or {}).items() if v)),
        "%%TITLE%%": json.dumps(tree_name or ""),
        "%%HEIGHT%%": str(int(height)),
        "%%BG%%": BG, "%%EDGE%%": EDGE, "%%LEAF%%": LEAF,
        "%%DATED%%": DATED, "%%PLAIN%%": PLAIN, "%%TIP%%": TIP,
        "%%LABEL%%": LABEL,
    }
    html = _TEMPLATE
    for k, v in tokens.items():
        html = html.replace(k, v)
    return html


_TEMPLATE = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
<style>
  html, body { margin:0; padding:0; background:%%BG%%;
    font-family: Helvetica, Arial, sans-serif; }
  #wrap { position:relative; width:100%; height:%%HEIGHT%%px;
    background:%%BG%%; border-radius:10px; overflow:hidden;
    --lbl:12.5px; --clbl:11px; }
  #bar { position:absolute; top:8px; left:8px; right:8px; z-index:5;
    display:flex; gap:8px; flex-wrap:wrap; align-items:flex-start; }
  .grp { display:flex; align-items:center; gap:4px; flex-wrap:wrap;
    background:rgba(14,27,26,0.85); border:1px solid #26403b;
    border-radius:9px; padding:4px 6px 4px 4px; }
  .gl { font-size:10px; letter-spacing:.12em; text-transform:uppercase;
    color:#7f978f; padding:0 6px 0 4px; user-select:none; }
  .grp button { background:transparent; color:%%TIP%%;
    border:1px solid transparent; border-radius:6px;
    padding:5px 9px; font-size:12px; cursor:pointer; white-space:nowrap; }
  .grp button:hover { border-color:#3a5a54; }
  .grp button.on { background:%%LABEL%%; color:#0e1b1a; font-weight:600; }
  .grp label { display:flex; align-items:center; gap:5px; color:%%TIP%%;
    font-size:11.5px; padding:0 4px; white-space:nowrap; }
  .grp input[type=range] { width:84px; accent-color:%%LABEL%%; margin:0; }
  .pop { position:absolute; z-index:8; background:rgba(14,27,26,0.97);
    border:1px solid #26403b; border-radius:10px; padding:8px;
    color:%%TIP%%; font-size:12px; box-shadow:0 6px 22px rgba(0,0,0,.55);
    display:none; }
  .pop .ph { display:flex; align-items:center; justify-content:space-between;
    gap:10px; margin:0 2px 6px 2px; }
  .pop .ph span { font-size:10px; letter-spacing:.12em; text-transform:uppercase; color:#7f978f; }
  .pop .ph button { background:transparent; border:1px solid #26403b; color:%%TIP%%;
    border-radius:6px; padding:2px 7px; font-size:11px; cursor:pointer; }
  .pop .ph button:hover { border-color:%%LABEL%%; color:%%LABEL%%; }
  .pop .list { max-height:220px; overflow:auto; }
  .pop .it { display:flex; align-items:center; gap:7px; padding:4px 6px;
    border-radius:6px; cursor:pointer; white-space:nowrap; }
  .pop .it:hover { background:rgba(255,255,255,.07); }
  .pop .it.sel { background:%%LABEL%%; color:#0e1b1a; font-weight:600; }
  .pop .it .meta { color:#9ab3ab; font-size:10.5px; }
  .pop .it.sel .meta { color:#3a3a1a; }
  .pop .it input { margin:0; accent-color:%%LABEL%%; }
  #cladepop { top:54px; left:8px; width:250px; }
  #namepop { width:250px; }
  #hint { position:absolute; bottom:8px; left:12px; right:12px; z-index:5;
    color:#7f978f; font-size:11px; line-height:1.4; }
  #toast { position:absolute; left:50%; bottom:40px; transform:translateX(-50%);
    z-index:9; background:rgba(14,27,26,0.95); color:%%LABEL%%; border:1px solid #26403b;
    border-radius:8px; padding:7px 14px; font-size:12.5px; opacity:0;
    pointer-events:none; transition:opacity .25s; }
  #tt { position:absolute; z-index:6; pointer-events:none; opacity:0;
    background:rgba(14,27,26,0.96); color:%%TIP%%; border:1px solid #26403b;
    border-radius:7px; padding:6px 9px; font-size:12px; max-width:260px;
    transition:opacity .12s; box-shadow:0 3px 12px rgba(0,0,0,.5); }
  svg { width:100%; height:100%; display:block; cursor:grab; }
  svg:active { cursor:grabbing; }
  /* The whole node group is a drag handle: dot, name, and photo alike. */
  .node { cursor:move; }
  .lbl { fill:%%TIP%%; font-size:var(--lbl); user-select:none; }
  .clbl { fill:%%LABEL%%; font-size:var(--clbl); user-select:none; }
  .sci { font-style:italic; }
  .edge { stroke:%%EDGE%%; stroke-width:1.6; fill:none; vector-effect: non-scaling-stroke; }
  .pnav text { fill:%%LABEL%%; font-size:11px; cursor:pointer; user-select:none; }
  .pnav .cnt { fill:#9ab3ab; font-size:9.5px; cursor:default; }
  @media (max-width: 640px) {
    .grp button { padding:4px 7px; font-size:11px; }
    .gl { display:none; }
    .grp input[type=range] { width:64px; }
    #hint { display:none; }
  }
</style>
</head>
<body>
<div id="wrap">
  <div id="bar">
    <div class="grp"><span class="gl">Layout</span>
      <button id="b-unrooted" class="on">Unrooted</button>
      <button id="b-radial">Radial</button>
      <button id="b-rect">Rectangular</button></div>
    <div class="grp"><span class="gl">Show</span>
      <button id="b-clades">Clades…</button>
      <button id="b-labels" class="on">Labels</button>
      <button id="b-latin">Scientific names</button>
      <button id="b-photos">Photos</button></div>
    <div class="grp"><span class="gl">Size</span>
      <label>Photos <input id="r-photo" type="range" min="22" max="110" value="34"></label>
      <label>Text <input id="r-text" type="range" min="9" max="22" step="0.5" value="12.5"></label></div>
    <div class="grp"><span class="gl">View</span>
      <button id="b-lca">To LCA</button>
      <button id="b-whole">Whole tree</button>
      <button id="b-fit">Fit</button>
      <button id="b-save">Save view…</button>
      <button id="b-reset">Reset</button></div>
    <div class="grp"><span class="gl">Export</span>
      <button id="b-png">PNG</button>
      <button id="b-svg">SVG</button></div>
  </div>

  <div class="pop" id="cladepop">
    <div class="ph"><span>Clade names</span>
      <span><button id="cp-dated">Dated</button><button id="cp-all">All</button><button id="cp-none">None</button></span></div>
    <div class="list" id="cp-list"></div>
  </div>
  <div class="pop" id="savepop" style="width:268px;">
    <div class="ph"><span>Save this arrangement</span><button id="sv-close">Close</button></div>
    <div class="list" id="sv-list"></div>
  </div>
  <div class="pop" id="namepop">
    <div class="ph"><span id="np-title">Names</span><button id="np-close">Close</button></div>
    <div class="list" id="np-list"></div>
  </div>

  <div id="tt"></div>
  <div id="toast"></div>
  <div id="hint">Drag a dot, a name, or a photo to move that node. Click a
    species to pick which of its names shows; click a clade to focus and
    hide its deeper ancestors. Arrows under a photo choose another picture.</div>
  <svg id="svg"></svg>
</div>
<script>
(function(){
  const DATA = %%DATA%%;
  const PHOTOS = %%PHOTOS%%;
  const NAMES = %%NAMES%%;
  const TITLE = %%TITLE%%;
  const BG = "%%BG%%";
  const C = { edge:"%%EDGE%%", leaf:"%%LEAF%%", dated:"%%DATED%%",
              plain:"%%PLAIN%%", tip:"%%TIP%%", label:"%%LABEL%%" };
  const HAS_PHOTOS = Object.keys(PHOTOS).length > 0;
  const CAN_SHARE = %%CANSHARE%%;
  const SIGNED_IN = %%SIGNEDIN%%;
  const INIT_VIEW = %%INITVIEW%%;
  const INIT_SCOPE = %%INITSCOPE%%;
  const KEEP = %%KEEP%%;
  const KEY = "rk_view:" + TITLE;
  const svg = d3.select("#svg");
  const wrap = document.getElementById("wrap");
  let W = wrap.clientWidth || 900, H = wrap.clientHeight || %%HEIGHT%%;
  svg.attr("viewBox", [0,0,W,H]);
  const viewport = svg.append("g");
  const gEdges = viewport.append("g");
  const gNodes = viewport.append("g");
  const tt = d3.select("#tt");
  const $ = id => document.getElementById(id);

  const root = d3.hierarchy(DATA, d => d.children);
  let idc = 0;
  root.each(d => { d.cx = 0; d.cy = 0; d.__id = idc++; });
  const allClades = root.descendants().filter(d => !d.data.is_leaf && d.data.clade);

  // ---------- state ----------
  let displayRoot = root;
  let mode = "unrooted";
  let showLabels = true;
  let showSci = %%SHOWSCI%%;
  let showPhotos = false;
  let photoSize = 34;
  let textSize = 12.5;
  let manuallyMoved = false;
  let k = 1;
  // Which clade names are ticked, by clade key. Starts at the dated ones.
  let cladeOn = new Set(allClades.filter(d => d.data.dated).map(d => d.data.name));
  // Per-species choices: which photo, and which Library name.
  const photoIdx = {}, nameIdx = {};

  function photoList(d){ return (d.data.is_leaf && PHOTOS[d.data.sci]) || []; }
  function nameList(d){ return (d.data.is_leaf && NAMES[d.data.sci]) || []; }
  function chosenPhoto(d){
    const L = photoList(d); if (!L.length) return null;
    return L[(photoIdx[d.data.sci] || 0) % L.length];
  }
  function chosenName(d){
    const L = nameList(d), i = nameIdx[d.data.sci];
    if (i != null && i >= 0 && L[i]) return L[i].t;
    return d.data.common || null;
  }

  function styleText(){
    return ".lbl{fill:"+C.tip+";font-size:"+textSize+"px;font-family:Helvetica,Arial,sans-serif;}"+
           ".clbl{fill:"+C.label+";font-size:"+(textSize*0.88).toFixed(1)+"px;font-family:Helvetica,Arial,sans-serif;}"+
           ".sci{font-style:italic;}"+
           ".edge{stroke:"+C.edge+";stroke-width:1.6;fill:none;}";
  }
  function applySizes(){
    wrap.style.setProperty("--lbl", textSize+"px");
    wrap.style.setProperty("--clbl", (textSize*0.88).toFixed(1)+"px");
  }
  function lca(){ let n = root; while (n.children && n.children.length === 1) n = n.children[0]; return n; }
  function toast(msg){
    const t = $("toast"); t.textContent = msg; t.style.opacity = 1;
    clearTimeout(t.__h); t.__h = setTimeout(() => t.style.opacity = 0, 1800);
  }

  // ---------- layouts ----------
  function layoutRect(R0){
    const dx = Math.max(26, (H - 140) / (R0.leaves().length + 1));
    const tree = d3.tree().nodeSize([dx, Math.max(90,(W-360)/(R0.height+1))]);
    tree(R0);
    let minx=Infinity, maxx=-Infinity, miny=Infinity, maxy=-Infinity;
    R0.each(d => { d.cx = d.y - R0.y; d.cy = d.x;
      minx=Math.min(minx,d.cx); maxx=Math.max(maxx,d.cx);
      miny=Math.min(miny,d.cy); maxy=Math.max(maxy,d.cy); });
    const ox = 90 - minx, oy = (H/2) - (miny+maxy)/2;
    R0.each(d => { d.cx += ox; d.cy += oy; });
  }
  function layoutRadial(R0){
    const Rr = Math.min(W,H)/2 - 100;
    const tree = d3.tree().size([2*Math.PI, Rr])
      .separation((a,b)=> (a.parent===b.parent?1:2)/Math.max(1,a.depth));
    tree(R0);
    const cxC = W/2, cyC = H/2, y0 = R0.y;
    R0.each(d => { const rad = d.y - y0;
      d.cx = cxC + rad*Math.cos(d.x - Math.PI/2);
      d.cy = cyC + rad*Math.sin(d.x - Math.PI/2); });
  }
  function layoutUnrooted(R0){
    const SPINE = 18, BRANCH = 96;
    function rec(node, a0, span, x, y){
      node.cx = x; node.cy = y;
      const kids = node.children; if (!kids) return;
      const total = node.leaves().length;
      const step = kids.length === 1 ? SPINE : BRANCH;
      let a = a0;
      kids.forEach(ch => {
        const sp = span * ch.leaves().length / total;
        const mid = a + sp/2;
        rec(ch, a, sp, x + step*Math.cos(mid), y + step*Math.sin(mid));
        a += sp;
      });
    }
    rec(R0, -Math.PI/2, 2*Math.PI, W/2, H/2);
  }
  function layout(){
    if (mode === "rect") layoutRect(displayRoot);
    else if (mode === "radial") layoutRadial(displayRoot);
    else layoutUnrooted(displayRoot);
  }

  // ---------- styling ----------
  function nodeColor(d){ return d.data.is_leaf ? C.leaf : (d.data.dated ? C.dated : C.plain); }
  function nodeR(d){ return d.data.is_leaf ? 5 : (d.data.dated ? 7 : 5); }
  function cladeShown(d){ return d.data.is_leaf ? true : cladeOn.has(d.data.name); }
  function hasPhoto(d){ return showPhotos && !!chosenPhoto(d); }
  function labelText(d){
    if (d.data.is_leaf){
      const nm = chosenName(d);
      if (nm) return showSci ? nm + " (" + d.data.sci + ")" : nm;
      return d.data.sci;
    }
    let t = d.data.clade || "";
    if (d.data.dated && d.data.mya != null) t += ", " + d.data.mya;
    return t;
  }
  function setLabel(el, d){
    while (el.firstChild) el.removeChild(el.firstChild);
    const NS = "http://www.w3.org/2000/svg";
    function span(txt, cls){ const t = document.createElementNS(NS,"tspan"); if (cls) t.setAttribute("class", cls); t.textContent = txt; el.appendChild(t); }
    if (d.data.is_leaf){
      const nm = chosenName(d);
      if (nm){ span(nm); if (showSci){ span(" ("); span(d.data.sci, "sci"); span(")"); } }
      else span(d.data.sci, "sci");
    } else span(labelText(d));
  }
  function side(d){
    if (mode === "rect" || !d.parent) return 1;
    return (d.cx - d.parent.cx) < -1 ? -1 : 1;
  }
  function labelX(d){ return nodeR(d) + 6 + (hasPhoto(d) ? photoSize + 4 : 0); }
  function labelWanted(d){
    if (!showLabels) return false;
    if (d.data.is_leaf) return true;
    return cladeShown(d) && !!d.data.clade;
  }
  function nodeTransform(d){ return "translate("+d.cx+","+d.cy+") scale("+(1/k)+")"; }

  // ---------- draw ----------
  function drawEdges(){
    const sel = gEdges.selectAll("path.edge").data(displayRoot.links(), d => d.target.__id);
    sel.enter().append("path").attr("class","edge").merge(sel)
      .attr("d", d => "M"+d.source.cx+","+d.source.cy+"L"+d.target.cx+","+d.target.cy);
    sel.exit().remove();
  }
  function drawNodes(){
    const sel = gNodes.selectAll("g.node").data(displayRoot.descendants(), d => d.__id);
    const ent = sel.enter().append("g").attr("class","node");
    ent.append("circle");
    ent.each(function(d){
      if (!d.data.is_leaf) return;
      const g = d3.select(this);
      if (HAS_PHOTOS) g.append("image").attr("class","photo");
      // photo chooser: ‹ n/m ›, only drawn when there is a choice
      const nav = g.append("g").attr("class","pnav");
      nav.append("text").attr("class","prev").text("‹");
      nav.append("text").attr("class","cnt");
      nav.append("text").attr("class","next").text("›");
    });
    ent.append("text");
    const all = ent.merge(sel);
    all.attr("transform", nodeTransform);
    all.select("circle")
      .attr("r", d => (d.data.is_leaf || cladeShown(d)) ? nodeR(d) : 0)
      .attr("fill", nodeColor)
      .attr("stroke", d => (d === displayRoot && !d.data.is_leaf) ? C.label : "#0e1b1a")
      .attr("stroke-width", d => (d === displayRoot && !d.data.is_leaf) ? 2 : 1);
    all.select("image.photo")
      .attr("href", d => chosenPhoto(d) || "")
      .attr("x", d => side(d) > 0 ? nodeR(d) + 6 : -(nodeR(d) + 6 + photoSize))
      .attr("y", -photoSize/2)
      .attr("width", photoSize).attr("height", photoSize)
      .attr("preserveAspectRatio", "xMidYMid slice")
      .style("display", d => hasPhoto(d) ? null : "none");
    all.select("g.pnav")
      .style("display", d => (hasPhoto(d) && photoList(d).length > 1) ? null : "none")
      .attr("transform", d => {
        const x = side(d) > 0 ? nodeR(d) + 6 : -(nodeR(d) + 6 + photoSize);
        return "translate("+(x + photoSize/2)+","+(photoSize/2 + 12)+")";
      });
    all.select("g.pnav .prev").attr("x", -photoSize/2 + 4).attr("y", 0);
    all.select("g.pnav .next").attr("x", photoSize/2 - 8).attr("y", 0);
    all.select("g.pnav .cnt").attr("text-anchor","middle").attr("y", 0)
      .text(d => { const L = photoList(d); return ((photoIdx[d.data.sci]||0) % L.length + 1) + "/" + L.length; });
    all.select("text")
      .attr("class", d => d.data.is_leaf ? "lbl" : "clbl")
      .attr("x", d => side(d) * labelX(d)).attr("y", 4)
      .attr("text-anchor", d => side(d) > 0 ? "start" : "end")
      .each(function(d){ setLabel(this, d); });

    // photo arrows: their own click targets, and they must not start a drag
    all.selectAll("g.pnav .prev, g.pnav .next")
      .on("mousedown", function(ev){ ev.stopPropagation(); })
      .on("click", function(ev, d){
        ev.stopPropagation();
        const L = photoList(d); if (L.length < 2) return;
        const step = d3.select(this).classed("next") ? 1 : -1;
        photoIdx[d.data.sci] = (((photoIdx[d.data.sci]||0) + step) % L.length + L.length) % L.length;
        drawNodes();
      });

    all.on("mousemove", function(ev,d){
        const html = d.data.is_leaf
          ? "<b>"+(chosenName(d)||d.data.sci)+"</b><br><i>"+d.data.sci+"</i>"
            + (nameList(d).length ? "<br><span style='color:#9ab3ab'>click for "+nameList(d).length+" name"+(nameList(d).length>1?"s":"")+" from the Library</span>" : "")
          : "<b>"+(d.data.clade||"clade")+"</b>"+
            (d.data.mya!=null ? "<br>"+d.data.mya+" million years since the last common ancestor" : "<br>age not set")+
            "<br><span style='color:#9ab3ab'>"+(d===displayRoot ? "click to step back out" : "click to focus here")+"</span>";
        tt.html(html).style("opacity",1);
        const r = wrap.getBoundingClientRect();
        tt.style("left", (ev.clientX - r.left + 12)+"px").style("top", (ev.clientY - r.top + 12)+"px");
      })
      .on("mouseleave", () => tt.style("opacity",0));

    all.call(d3.drag()
      .on("start", function(ev){ ev.sourceEvent.stopPropagation(); this.__dist = 0; })
      .on("drag", function(ev,d){
        this.__dist += Math.abs(ev.dx) + Math.abs(ev.dy);
        if (this.__dist > 3) manuallyMoved = true;
        const ddx = ev.dx / k, ddy = ev.dy / k;
        d.descendants().forEach(n => { n.cx += ddx; n.cy += ddy; });
        gNodes.selectAll("g.node").attr("transform", nodeTransform);
        drawEdges();
      })
      .on("end", function(ev,d){
        if (this.__dist > 3){ declutter(); return; }
        if (d.data.is_leaf){ openNamePop(ev, d); return; }
        if (ev.sourceEvent && ev.sourceEvent.shiftKey){
          if (d.children){ d.children.reverse(); if (d.data.children) d.data.children.reverse(); }
          if (!manuallyMoved) layout();
          drawEdges(); drawNodes(); tt.style("opacity",0);
        } else if (d === displayRoot){ setFocus(d.parent || root); }
        else { setFocus(d); }
      }));
    sel.exit().remove();
    declutter();
  }

  function declutter(){
    const t = d3.zoomTransform(svg.node());
    const placed = [];
    const cw = textSize * 0.55, ch = textSize * 0.65;
    function box(d){
      const sx = d.cx*t.k + t.x, sy = d.cy*t.k + t.y;
      const w = labelText(d).length * (d.data.is_leaf ? cw : cw*0.9) + 6;
      const x0 = side(d) > 0 ? sx + labelX(d) - 2 : sx - labelX(d) - w + 2;
      return [x0, sy-ch, x0+w, sy+ch];
    }
    function hits(b){ return placed.some(p => !(b[2]<p[0] || b[0]>p[2] || b[3]<p[1] || b[1]>p[3])); }
    const want = displayRoot.descendants().filter(labelWanted);
    const show = new Set();
    const order = []
      .concat(want.filter(d => d === displayRoot))
      .concat(want.filter(d => d.data.is_leaf && d !== displayRoot).sort((a,b) => a.cy - b.cy))
      .concat(want.filter(d => !d.data.is_leaf && d !== displayRoot)
        .sort((a,b) => ((b.data.mya||0) - (a.data.mya||0)) || (a.depth - b.depth)));
    order.forEach(d => { const b = box(d); if (d === displayRoot || !hits(b)){ placed.push(b); show.add(d.__id); } });
    gNodes.selectAll("g.node text.lbl, g.node text.clbl").style("display", d => show.has(d.__id) ? null : "none");
  }

  function setFocus(node){
    displayRoot = node;
    if (!manuallyMoved){ layout(); drawEdges(); drawNodes(); fit(); }
    else { drawEdges(); drawNodes(); }
    tt.style("opacity",0);
  }
  function render(){ layout(); drawEdges(); drawNodes(); }

  // ---------- clade name panel ----------
  function buildCladePanel(){
    const list = $("cp-list"); list.innerHTML = "";
    allClades.slice().sort((a,b) => (b.data.mya||0) - (a.data.mya||0)).forEach(d => {
      const row = document.createElement("div");
      row.className = "it" ;
      row.innerHTML = '<input type="checkbox"'+(cladeOn.has(d.data.name)?" checked":"")+'>'
        + '<span>'+d.data.clade+'</span>'
        + '<span class="meta">'+(d.data.mya!=null ? d.data.mya+" mya" : "no age")+'</span>';
      row.querySelector("input").addEventListener("change", function(){
        if (this.checked) cladeOn.add(d.data.name); else cladeOn.delete(d.data.name);
        drawNodes();
      });
      row.addEventListener("click", function(ev){
        if (ev.target.tagName === "INPUT") return;
        const cb = row.querySelector("input"); cb.checked = !cb.checked;
        cb.dispatchEvent(new Event("change"));
      });
      list.appendChild(row);
    });
  }
  function syncCladePanel(){
    $("cp-list").querySelectorAll(".it").forEach((row, i) => {
      const sorted = allClades.slice().sort((a,b) => (b.data.mya||0) - (a.data.mya||0));
      row.querySelector("input").checked = cladeOn.has(sorted[i].data.name);
    });
  }
  function cladePreset(which){
    cladeOn = new Set(
      which === "all" ? allClades.map(d => d.data.name)
      : which === "dated" ? allClades.filter(d => d.data.dated).map(d => d.data.name)
      : []);
    syncCladePanel(); drawNodes();
  }
  $("cp-all").onclick = () => cladePreset("all");
  $("cp-dated").onclick = () => cladePreset("dated");
  $("cp-none").onclick = () => cladePreset("none");

  // ---------- name picker ----------
  let namePopFor = null;
  function openNamePop(ev, d){
    const L = nameList(d);
    if (!L.length){ toast("No Library names for this species yet"); return; }
    namePopFor = d;
    $("np-title").textContent = d.data.sci;
    const list = $("np-list"); list.innerHTML = "";
    const rows = [{t: d.data.common || d.data.sci, l:"", c:"default", i:-1}]
      .concat(L.map((n,i) => ({t:n.t, l:n.l, c:n.c, i:i})));
    const cur = (nameIdx[d.data.sci] == null ? -1 : nameIdx[d.data.sci]);
    rows.forEach(r => {
      const row = document.createElement("div");
      row.className = "it" + (r.i === cur ? " sel" : "");
      row.innerHTML = '<span>'+r.t+'</span><span class="meta">'
        + (r.c === "default" ? "default" : [r.l, r.c].filter(Boolean).join(" / ")) + '</span>';
      row.addEventListener("click", () => {
        if (r.i < 0) delete nameIdx[d.data.sci]; else nameIdx[d.data.sci] = r.i;
        closeNamePop(); drawNodes();
      });
      list.appendChild(row);
    });
    const r = wrap.getBoundingClientRect();
    const pop = $("namepop");
    pop.style.display = "block";
    const px = Math.min(Math.max(8, ev.sourceEvent.clientX - r.left + 12), r.width - 262);
    const py = Math.min(Math.max(8, ev.sourceEvent.clientY - r.top + 10), r.height - 120);
    pop.style.left = px + "px"; pop.style.top = py + "px";
    tt.style("opacity", 0);
  }
  function closeNamePop(){ $("namepop").style.display = "none"; namePopFor = null; }
  $("np-close").onclick = closeNamePop;
  svg.on("mousedown.pop", () => { closeNamePop(); $("savepop").style.display = "none"; });

  // ---------- zoom ----------
  let rafPending = false;
  const zoom = d3.zoom().scaleExtent([0.25, 5])
    .on("zoom", ev => {
      viewport.attr("transform", ev.transform);
      k = ev.transform.k;
      gNodes.selectAll("g.node").attr("transform", nodeTransform);
      if (!rafPending){ rafPending = true; requestAnimationFrame(() => { rafPending = false; declutter(); }); }
    });
  svg.call(zoom);
  function fitTransform(){
    const ds = displayRoot.descendants();
    const xs = ds.map(d=>d.cx), ys = ds.map(d=>d.cy);
    const x0=Math.min.apply(null,xs), x1=Math.max.apply(null,xs);
    const y0=Math.min.apply(null,ys), y1=Math.max.apply(null,ys);
    const bw=Math.max(1,x1-x0), bh=Math.max(1,y1-y0);
    let kk = 0.80*Math.min((W-220)/bw, (H-170)/bh);
    kk = Math.max(0.45, Math.min(2.4, kk));
    const tx = W/2 - kk*(x0+x1)/2 - 40, ty = H/2 - kk*(y0+y1)/2 + 30;
    return d3.zoomIdentity.translate(tx,ty).scale(kk);
  }
  function fit(animate){
    const t = fitTransform();
    if (animate === false) svg.call(zoom.transform, t);
    else svg.transition().duration(420).call(zoom.transform, t);
  }

  // ---------- save / restore ----------
  function syncButtons(){
    ["unrooted","radial","rect"].forEach(x => d3.select("#b-"+x).classed("on", x===mode));
    $("b-clades").classList.toggle("on", cladeOn.size > 0);
    $("b-labels").classList.toggle("on", showLabels);
    $("b-latin").classList.toggle("on", showSci);
    $("b-photos").classList.toggle("on", showPhotos);
    $("r-photo").value = photoSize; $("r-text").value = textSize;
    applySizes();
  }
  // The current arrangement, as a compact object. withPos=false drops node
  // positions, which are the bulky part, for when a URL round trip needs to
  // stay inside a safe length.
  function viewState(withPos){
    const z = d3.zoomTransform(svg.node());
    const st = { v: 1, mode, showLabels, showSci, showPhotos,
                 photoSize, textSize, clades: [...cladeOn],
                 photoIdx, nameIdx, root: displayRoot.__id,
                 z: {k: +z.k.toFixed(3), x: Math.round(z.x), y: Math.round(z.y)} };
    if (withPos){
      st.pos = {};
      root.each(d => { st.pos[d.__id] = [Math.round(d.cx), Math.round(d.cy)]; });
    }
    return st;
  }
  function saveLocal(){
    try {
      localStorage.setItem(KEY, JSON.stringify(viewState(true)));
      toast("Saved on this device");
    } catch(e){ toast("Could not save in this browser"); }
  }
  // Hand the view to Streamlit through the address bar. The component runs
  // in a same-origin iframe, so navigating the top window is allowed (the
  // range map's species links already rely on it). KEEP carries the ?s=
  // session token through, or the round trip would sign the person out.
  function saveRemote(scope){
    let st = viewState(true);
    let enc = encodeURIComponent(btoa(unescape(encodeURIComponent(JSON.stringify(st)))));
    if (enc.length > 1700){            // too long for a comfortable URL
      st = viewState(false);
      enc = encodeURIComponent(btoa(unescape(encodeURIComponent(JSON.stringify(st)))));
      if (enc.length > 1700){
        saveLocal();
        toast("This tree is too big to publish; saved on this device");
        return;
      }
      toast(scope === "all" ? "Publishing settings (positions stayed local)"
                            : "Saving settings (positions stayed local)");
      saveLocal();                      // keep the exact positions here
    }
    try {
      // Navigating reloads the app, which starts a fresh Streamlit session,
      // so the tree name rides along too: session_state is empty on arrival.
      window.top.location.search = "?rk_view=" + enc + "&rk_scope=" + scope
        + "&rk_tree=" + encodeURIComponent(TITLE) + KEEP;
    } catch(e){ saveLocal(); }
  }
  function openSavePop(){
    const list = $("sv-list"); list.innerHTML = "";
    const opts = [];
    if (CAN_SHARE) opts.push({k:"all", t:"Save for everyone",
      m:"the tree opens like this for every visitor"});
    if (SIGNED_IN) opts.push({k:"me", t:"Save for me",
      m:"follows your account on any device"});
    opts.push({k:"local", t:"Save on this device",
      m:"this browser only, no account needed"});
    opts.forEach(o => {
      const row = document.createElement("div");
      row.className = "it";
      row.innerHTML = '<span>'+o.t+'</span><span class="meta">'+o.m+'</span>';
      row.addEventListener("click", () => {
        $("savepop").style.display = "none";
        if (o.k === "local") saveLocal(); else saveRemote(o.k);
      });
      list.appendChild(row);
    });
    const pop = $("savepop");
    pop.style.display = "block";
    pop.style.left = "auto"; pop.style.right = "8px"; pop.style.top = "54px";
  }
  $("sv-close").onclick = () => { $("savepop").style.display = "none"; };
  function applyState(st){
    try {
      mode = st.mode || mode;
      showLabels = !!st.showLabels; showSci = !!st.showSci;
      showPhotos = !!st.showPhotos && HAS_PHOTOS;
      photoSize = st.photoSize || photoSize; textSize = st.textSize || textSize;
      if (Array.isArray(st.clades)) cladeOn = new Set(st.clades);
      Object.assign(photoIdx, st.photoIdx || {});
      Object.assign(nameIdx, st.nameIdx || {});
      layout();
      root.each(d => { const p = st.pos && st.pos[d.__id]; if (p){ d.cx = p[0]; d.cy = p[1]; } });
      displayRoot = root.descendants().find(d => d.__id === st.root) || root;
      manuallyMoved = true;
      syncButtons(); syncCladePanel(); drawEdges(); drawNodes();
      if (st.z) svg.call(zoom.transform, d3.zoomIdentity.translate(st.z.x, st.z.y).scale(st.z.k));
      else fit(false);
      return true;
    } catch(e){ return false; }
  }
  // Load order: a view saved for this person, else the tree's shared view
  // (both arrive from the database as INIT_VIEW), else whatever this browser
  // has, else the default layout.
  function loadInitial(){
    if (INIT_VIEW && applyState(INIT_VIEW)){
      if (INIT_SCOPE === "all") toast("Showing the shared view for this tree");
      return true;
    }
    try {
      const raw = localStorage.getItem(KEY);
      if (raw && applyState(JSON.parse(raw))) return true;
    } catch(e){}
    return false;
  }
  function resetView(){
    try { localStorage.removeItem(KEY); } catch(e){}
    mode = "unrooted"; showLabels = true; showSci = %%SHOWSCI%%;
    showPhotos = false; photoSize = 34; textSize = 12.5;
    cladeOn = new Set(allClades.filter(d => d.data.dated).map(d => d.data.name));
    Object.keys(photoIdx).forEach(kk => delete photoIdx[kk]);
    Object.keys(nameIdx).forEach(kk => delete nameIdx[kk]);
    displayRoot = root; manuallyMoved = false;
    closeNamePop();
    syncButtons(); syncCladePanel(); render(); fit(); toast("Back to the default view");
  }

  // ---------- export ----------
  function download(blob, name){
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
  }
  async function dataUrlMap(){
    const map = {};
    const urls = [...new Set([].concat.apply([], Object.values(PHOTOS)))];
    await Promise.all(urls.map(async u => {
      try {
        const r = await fetch(u, {mode:"cors"}); const b = await r.blob();
        map[u] = await new Promise(res => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.readAsDataURL(b); });
      } catch(e) {}
    }));
    return map;
  }
  async function exportImg(asPng){
    const NS = "http://www.w3.org/2000/svg";
    const clone = svg.node().cloneNode(true);
    clone.setAttribute("width", W); clone.setAttribute("height", H);
    clone.querySelectorAll("text").forEach(t => { if (t.style.display === "none") t.remove(); });
    clone.querySelectorAll("g.pnav").forEach(g => g.remove());   // UI, not artwork
    if (HAS_PHOTOS && showPhotos){
      const map = await dataUrlMap();
      clone.querySelectorAll("image").forEach(im => {
        const h = im.getAttribute("href");
        if (im.style.display === "none"){ im.remove(); return; }
        if (h && map[h]) im.setAttribute("href", map[h]);
      });
    } else clone.querySelectorAll("image").forEach(im => im.remove());
    const bg = document.createElementNS(NS, "rect");
    bg.setAttribute("x",0); bg.setAttribute("y",0);
    bg.setAttribute("width",W); bg.setAttribute("height",H); bg.setAttribute("fill", BG);
    clone.insertBefore(bg, clone.firstChild);
    const styleEl = document.createElementNS(NS, "style");
    styleEl.textContent = styleText();
    clone.insertBefore(styleEl, clone.firstChild);
    let src = new XMLSerializer().serializeToString(clone);
    if (!/^<svg[^>]*\sxmlns=/.test(src)) src = src.replace(/^<svg/, '<svg xmlns="'+NS+'"');
    const stem = (TITLE || "kinship_tree").replace(/[^\w\-]+/g, "_");
    if (!asPng){ download(new Blob([src], {type:"image/svg+xml;charset=utf-8"}), stem+"_tree.svg"); return; }
    const img = new Image();
    img.onload = function(){
      const c = document.createElement("canvas"); c.width = W*2; c.height = H*2;
      const ctx = c.getContext("2d"); ctx.setTransform(2,0,0,2,0,0); ctx.drawImage(img, 0, 0);
      try { c.toBlob(function(b){ download(b, stem+"_tree.png"); }); }
      catch(e){ alert("A photo's host blocked embedding. Use Export SVG."); }
    };
    img.onerror = function(){ alert("Could not rasterize. Try Export SVG."); };
    img.src = "data:image/svg+xml;base64," + btoa(unescape(encodeURIComponent(src)));
  }

  // ---------- menu wiring ----------
  function setMode(m){ mode = m; manuallyMoved = false; syncButtons(); render(); fit(); }
  $("b-unrooted").onclick = () => setMode("unrooted");
  $("b-radial").onclick = () => setMode("radial");
  $("b-rect").onclick = () => setMode("rect");
  $("b-clades").onclick = function(){
    const p = $("cladepop");
    p.style.display = p.style.display === "block" ? "none" : "block";
  };
  $("b-labels").onclick = function(){ showLabels = !showLabels; syncButtons(); drawNodes(); };
  $("b-latin").onclick = function(){ showSci = !showSci; syncButtons(); drawNodes(); };
  $("b-photos").onclick = function(){
    if (!HAS_PHOTOS){ toast("No photos cached yet: rebuild the tree to fetch them"); return; }
    showPhotos = !showPhotos; syncButtons(); drawNodes();
  };
  $("r-photo").oninput = function(){ photoSize = +this.value; drawNodes(); };
  $("r-text").oninput = function(){ textSize = +this.value; applySizes(); drawNodes(); };
  $("b-lca").onclick = () => { manuallyMoved = false; setFocus(lca()); };
  $("b-whole").onclick = () => { manuallyMoved = false; setFocus(root); };
  $("b-fit").onclick = () => fit();
  $("b-save").onclick = openSavePop;
  $("b-reset").onclick = resetView;
  $("b-png").onclick = () => exportImg(true);
  $("b-svg").onclick = () => exportImg(false);
  if (!HAS_PHOTOS) $("b-photos").style.opacity = 0.45;

  window.addEventListener("resize", () => {
    W = wrap.clientWidth || W; H = wrap.clientHeight || H;
    svg.attr("viewBox",[0,0,W,H]);
    if (!manuallyMoved){ render(); fit(false); } else { drawEdges(); drawNodes(); }
  });

  buildCladePanel();
  syncButtons();
  render();
  if (!loadInitial()) fit(false);
})();
</script>
</body>
</html>
"""
