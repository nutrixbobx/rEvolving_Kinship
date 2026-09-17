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
from pathlib import Path


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
                           photos: dict | None = None) -> str:
    """Self-contained draggable tree page for components.html().
    show_scientific sets the initial state of the in-canvas Latin toggle.
    photos: {scientific_name: image_url}; the in-canvas Photos toggle
    shows or hides them without a rerun."""
    data = _hierarchy(newick_path, meta)
    tokens = {
        "%%DATA%%": json.dumps(data),
        "%%PHOTOS%%": json.dumps(photos or {}),
        "%%SHOWSCI%%": "true" if show_scientific else "false",
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
  .grp button {
    background:transparent; color:%%TIP%%;
    border:1px solid transparent; border-radius:6px;
    padding:5px 9px; font-size:12px; cursor:pointer; white-space:nowrap; }
  .grp button:hover { border-color:#3a5a54; }
  .grp button.on { background:%%LABEL%%; color:#0e1b1a; font-weight:600; }
  .grp label { display:flex; align-items:center; gap:5px; color:%%TIP%%;
    font-size:11.5px; padding:0 4px; white-space:nowrap; }
  .grp input[type=range] { width:84px; accent-color:%%LABEL%%; margin:0; }
  #hint { position:absolute; bottom:8px; left:12px; right:12px; z-index:5;
    color:#7f978f; font-size:11px; line-height:1.4; }
  #toast { position:absolute; left:50%; bottom:40px; transform:translateX(-50%);
    z-index:7; background:rgba(14,27,26,0.95); color:%%LABEL%%; border:1px solid #26403b;
    border-radius:8px; padding:7px 14px; font-size:12.5px; opacity:0; pointer-events:none;
    transition:opacity .25s; }
  #tt { position:absolute; z-index:6; pointer-events:none; opacity:0;
    background:rgba(14,27,26,0.96); color:%%TIP%%; border:1px solid #26403b;
    border-radius:7px; padding:6px 9px; font-size:12px; max-width:260px;
    transition:opacity .12s; box-shadow:0 3px 12px rgba(0,0,0,.5); }
  svg { width:100%; height:100%; display:block; cursor:grab; }
  svg:active { cursor:grabbing; }
  .node { cursor:move; }
  .lbl { fill:%%TIP%%; font-size:var(--lbl); user-select:none; pointer-events:none; }
  .clbl { fill:%%LABEL%%; font-size:var(--clbl); user-select:none; pointer-events:none; }
  .sci { font-style:italic; }
  .edge { stroke:%%EDGE%%; stroke-width:1.6; fill:none; vector-effect: non-scaling-stroke; }
  .photo { pointer-events:none; }
  @media (max-width: 640px) {
    .grp button { padding:4px 7px; font-size:11px; }
    .gl { display:none; }
    .grp input[type=range] { width:64px; }
    #hint { font-size:10px; }
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
      <button id="b-clades" class="on">Clades: dated</button>
      <button id="b-labels" class="on">Labels</button>
      <button id="b-latin">Scientific names</button>
      <button id="b-photos">Photos</button></div>
    <div class="grp"><span class="gl">Size</span>
      <label>Photos <input id="r-photo" type="range" min="22" max="90" value="34"></label>
      <label>Text <input id="r-text" type="range" min="9" max="22" step="0.5" value="12.5"></label></div>
    <div class="grp"><span class="gl">View</span>
      <button id="b-lca">To LCA</button>
      <button id="b-whole">Whole tree</button>
      <button id="b-fit">Fit</button>
      <button id="b-save">Save view</button>
      <button id="b-reset">Reset</button></div>
    <div class="grp"><span class="gl">Export</span>
      <button id="b-png">PNG</button>
      <button id="b-svg">SVG</button></div>
  </div>
  <div id="tt"></div>
  <div id="toast"></div>
  <div id="hint">Click a clade to focus and hide its deeper ancestors; click
    the top clade to step back. Shift-click flips a clade. Drag to move,
    scroll to zoom. Save view keeps your arrangement on this device.</div>
  <svg id="svg"></svg>
</div>
<script>
(function(){
  const DATA = %%DATA%%;
  const PHOTOS = %%PHOTOS%%;
  const TITLE = %%TITLE%%;
  const BG = "%%BG%%";
  const C = { edge:"%%EDGE%%", leaf:"%%LEAF%%", dated:"%%DATED%%",
              plain:"%%PLAIN%%", tip:"%%TIP%%", label:"%%LABEL%%" };
  const HAS_PHOTOS = Object.keys(PHOTOS).length > 0;
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

  // ---------- state ----------
  let displayRoot = root;
  let mode = "unrooted";
  let showLabels = true;
  let showSci = %%SHOWSCI%%;
  let showPhotos = false;
  let cladeMode = "dated";
  let photoSize = 34;
  let textSize = 12.5;
  let manuallyMoved = false;
  let k = 1;

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
  function lca(){
    let n = root;
    while (n.children && n.children.length === 1) n = n.children[0];
    return n;
  }
  function toast(msg){
    const t = $("toast"); t.textContent = msg; t.style.opacity = 1;
    clearTimeout(t.__h); t.__h = setTimeout(() => t.style.opacity = 0, 1600);
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
    R0.each(d => {
      const rad = d.y - y0;
      d.cx = cxC + rad*Math.cos(d.x - Math.PI/2);
      d.cy = cyC + rad*Math.sin(d.x - Math.PI/2);
    });
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
  function cladeShown(d){
    if (d.data.is_leaf) return true;
    if (cladeMode === "none") return false;
    if (cladeMode === "dated") return !!d.data.dated;
    return true;
  }
  function hasPhoto(d){ return showPhotos && d.data.is_leaf && !!PHOTOS[d.data.sci]; }
  // plain string, for width estimates only
  function labelText(d){
    if (d.data.is_leaf){
      if (d.data.common) return showSci ? d.data.common + " (" + d.data.sci + ")" : d.data.common;
      return d.data.sci;
    }
    let t = d.data.clade || "";
    if (d.data.dated && d.data.mya != null) t += ", " + d.data.mya;
    return t;
  }
  // the real label: scientific name in italics via tspan
  function setLabel(el, d){
    while (el.firstChild) el.removeChild(el.firstChild);
    const NS = "http://www.w3.org/2000/svg";
    function span(txt, cls){ const t = document.createElementNS(NS,"tspan"); if (cls) t.setAttribute("class", cls); t.textContent = txt; el.appendChild(t); }
    if (d.data.is_leaf){
      if (d.data.common){ span(d.data.common); if (showSci){ span(" ("); span(d.data.sci, "sci"); span(")"); } }
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
    ent.each(function(d){ if (d.data.is_leaf && HAS_PHOTOS) d3.select(this).append("image").attr("class","photo"); });
    ent.append("text");
    const all = ent.merge(sel);
    all.attr("transform", nodeTransform);
    all.select("circle")
      .attr("r", d => (d.data.is_leaf || cladeShown(d)) ? nodeR(d) : 0)
      .attr("fill", nodeColor)
      .attr("stroke", d => (d === displayRoot && !d.data.is_leaf) ? C.label : "#0e1b1a")
      .attr("stroke-width", d => (d === displayRoot && !d.data.is_leaf) ? 2 : 1);
    all.select("image.photo")
      .attr("href", d => PHOTOS[d.data.sci] || "")
      .attr("x", d => side(d) > 0 ? nodeR(d) + 6 : -(nodeR(d) + 6 + photoSize))
      .attr("y", -photoSize/2)
      .attr("width", photoSize).attr("height", photoSize)
      .attr("preserveAspectRatio", "xMidYMid slice")
      .style("display", d => hasPhoto(d) ? null : "none");
    all.select("text")
      .attr("class", d => d.data.is_leaf ? "lbl" : "clbl")
      .attr("x", d => side(d) * labelX(d)).attr("y", 4)
      .attr("text-anchor", d => side(d) > 0 ? "start" : "end")
      .each(function(d){ setLabel(this, d); });

    all.on("mousemove", function(ev,d){
        const html = d.data.is_leaf
          ? "<b>"+(d.data.common||d.data.sci)+"</b><br><i>"+d.data.sci+"</i>"
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
        if (d.data.is_leaf) return;
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
    gNodes.selectAll("g.node text").style("display", d => show.has(d.__id) ? null : "none");
  }

  function setFocus(node){
    displayRoot = node;
    if (!manuallyMoved){ layout(); drawEdges(); drawNodes(); fit(); }
    else { drawEdges(); drawNodes(); }
    tt.style("opacity",0);
  }
  function render(){ layout(); drawEdges(); drawNodes(); }

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
    $("b-clades").textContent = "Clades: " + cladeMode;
    $("b-clades").classList.toggle("on", cladeMode !== "none");
    $("b-labels").classList.toggle("on", showLabels);
    $("b-latin").classList.toggle("on", showSci);
    $("b-photos").classList.toggle("on", showPhotos);
    $("r-photo").value = photoSize; $("r-text").value = textSize;
    applySizes();
  }
  function saveView(){
    try {
      const z = d3.zoomTransform(svg.node());
      const st = { mode, cladeMode, showLabels, showSci, showPhotos, photoSize, textSize,
                   root: displayRoot.__id, pos: {}, z: {k:z.k, x:z.x, y:z.y} };
      root.each(d => { st.pos[d.__id] = [Math.round(d.cx*10)/10, Math.round(d.cy*10)/10]; });
      localStorage.setItem(KEY, JSON.stringify(st));
      toast("View saved on this device");
    } catch(e){ toast("Could not save here"); }
  }
  function restoreView(){
    try {
      const raw = localStorage.getItem(KEY); if (!raw) return false;
      const st = JSON.parse(raw);
      mode = st.mode || mode; cladeMode = st.cladeMode || cladeMode;
      showLabels = !!st.showLabels; showSci = !!st.showSci;
      showPhotos = !!st.showPhotos && HAS_PHOTOS;
      photoSize = st.photoSize || photoSize; textSize = st.textSize || textSize;
      layout();
      root.each(d => { const p = st.pos && st.pos[d.__id]; if (p){ d.cx = p[0]; d.cy = p[1]; } });
      displayRoot = root.descendants().find(d => d.__id === st.root) || root;
      manuallyMoved = true;
      syncButtons(); drawEdges(); drawNodes();
      if (st.z) svg.call(zoom.transform, d3.zoomIdentity.translate(st.z.x, st.z.y).scale(st.z.k));
      else fit(false);
      return true;
    } catch(e){ return false; }
  }
  function resetView(){
    try { localStorage.removeItem(KEY); } catch(e){}
    mode = "unrooted"; cladeMode = "dated"; showLabels = true; showSci = %%SHOWSCI%%;
    showPhotos = false; photoSize = 34; textSize = 12.5; displayRoot = root; manuallyMoved = false;
    syncButtons(); render(); fit(); toast("Back to the default view");
  }

  // ---------- export ----------
  function download(blob, name){
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
  }
  async function dataUrlMap(){
    const map = {};
    const urls = [...new Set(Object.values(PHOTOS))];
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
    cladeMode = cladeMode==="dated" ? "all" : (cladeMode==="all" ? "none" : "dated");
    syncButtons(); drawNodes();
  };
  $("b-labels").onclick = function(){ showLabels = !showLabels; syncButtons(); drawNodes(); };
  $("b-latin").onclick = function(){ showSci = !showSci; syncButtons(); drawNodes(); };
  $("b-photos").onclick = function(){
    if (!HAS_PHOTOS){ toast("No photos cached yet: open Quick look or Load kin cards once, then rebuild"); return; }
    showPhotos = !showPhotos; syncButtons(); drawNodes();
  };
  $("r-photo").oninput = function(){ photoSize = +this.value; drawNodes(); };
  $("r-text").oninput = function(){ textSize = +this.value; applySizes(); drawNodes(); };
  $("b-lca").onclick = () => { manuallyMoved = false; setFocus(lca()); };
  $("b-whole").onclick = () => { manuallyMoved = false; setFocus(root); };
  $("b-fit").onclick = () => fit();
  $("b-save").onclick = saveView;
  $("b-reset").onclick = resetView;
  $("b-png").onclick = () => exportImg(true);
  $("b-svg").onclick = () => exportImg(false);
  if (!HAS_PHOTOS) $("b-photos").style.opacity = 0.45;

  window.addEventListener("resize", () => {
    W = wrap.clientWidth || W; H = wrap.clientHeight || H;
    svg.attr("viewBox",[0,0,W,H]);
    if (!manuallyMoved){ render(); fit(false); } else { drawEdges(); drawNodes(); }
  });

  syncButtons();
  render();
  if (!restoreView()) fit(false);
})();
</script>
</body>
</html>
"""
