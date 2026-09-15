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
    background:%%BG%%; border-radius:10px; overflow:hidden; }
  #bar { position:absolute; top:8px; left:8px; right:8px; z-index:5;
    display:flex; gap:8px; flex-wrap:wrap; align-items:flex-start; }
  .grp { display:flex; align-items:center; gap:4px; flex-wrap:wrap;
    background:rgba(14,27,26,0.82); border:1px solid #26403b;
    border-radius:9px; padding:4px 6px 4px 4px; }
  .gl { font-size:10px; letter-spacing:.12em; text-transform:uppercase;
    color:#7f978f; padding:0 6px 0 4px; user-select:none; }
  .grp button {
    background:transparent; color:%%TIP%%;
    border:1px solid transparent; border-radius:6px;
    padding:5px 9px; font-size:12px; cursor:pointer; white-space:nowrap; }
  .grp button:hover { border-color:#3a5a54; }
  .grp button.on { background:%%LABEL%%; color:#0e1b1a; font-weight:600; }
  #hint { position:absolute; bottom:8px; left:12px; right:12px; z-index:5;
    color:#7f978f; font-size:11px; line-height:1.4; }
  #tt { position:absolute; z-index:6; pointer-events:none; opacity:0;
    background:rgba(14,27,26,0.96); color:%%TIP%%; border:1px solid #26403b;
    border-radius:7px; padding:6px 9px; font-size:12px; max-width:260px;
    transition:opacity .12s; box-shadow:0 3px 12px rgba(0,0,0,.5); }
  svg { width:100%; height:100%; display:block; cursor:grab; }
  svg:active { cursor:grabbing; }
  .node { cursor:move; }
  .lbl { fill:%%TIP%%; font-size:12.5px; user-select:none; pointer-events:none; }
  .clbl { fill:%%LABEL%%; font-size:11px; user-select:none; pointer-events:none; }
  .edge { stroke:%%EDGE%%; stroke-width:1.6; fill:none;
    vector-effect: non-scaling-stroke; }
  .photo { pointer-events:none; }
  @media (max-width: 640px) {
    .grp button { padding:4px 7px; font-size:11px; }
    .gl { display:none; }
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
      <button id="b-latin">Latin names</button>
      <button id="b-photos">Photos</button></div>
    <div class="grp"><span class="gl">View</span>
      <button id="b-lca">To LCA</button>
      <button id="b-whole">Whole tree</button>
      <button id="b-fit">Fit</button></div>
    <div class="grp"><span class="gl">Export</span>
      <button id="b-png">PNG</button>
      <button id="b-svg">SVG</button></div>
  </div>
  <div id="tt"></div>
  <div id="hint">Click a clade to focus and hide its deeper ancestors; click
    the top clade to step back. Shift-click flips a clade. Drag to move,
    scroll to zoom. Zooming in reveals more clade names.</div>
  <svg id="svg"></svg>
</div>
<script>
(function(){
  const DATA = %%DATA%%;
  const PHOTOS = %%PHOTOS%%;
  const BG = "%%BG%%";
  const C = { edge:"%%EDGE%%", leaf:"%%LEAF%%", dated:"%%DATED%%",
              plain:"%%PLAIN%%", tip:"%%TIP%%", label:"%%LABEL%%" };
  const STYLE_TEXT =
    ".lbl{fill:"+C.tip+";font-size:12.5px;font-family:Helvetica,Arial,sans-serif;}"+
    ".clbl{fill:"+C.label+";font-size:11px;font-family:Helvetica,Arial,sans-serif;}"+
    ".edge{stroke:"+C.edge+";stroke-width:1.6;fill:none;}";
  const HAS_PHOTOS = Object.keys(PHOTOS).length > 0;
  const PHOTO_SIZE = 34;
  const svg = d3.select("#svg");
  const wrap = document.getElementById("wrap");
  let W = wrap.clientWidth || 900, H = wrap.clientHeight || %%HEIGHT%%;
  svg.attr("viewBox", [0,0,W,H]);
  const viewport = svg.append("g");
  const gEdges = viewport.append("g");
  const gNodes = viewport.append("g");
  const tt = d3.select("#tt");

  const root = d3.hierarchy(DATA, d => d.children);
  let idc = 0;
  root.each(d => { d.cx = 0; d.cy = 0; d.__id = idc++; });

  let displayRoot = root;
  let mode = "unrooted";
  let showLabels = true;
  let showSci = %%SHOWSCI%%;
  let showPhotos = false;
  let cladeMode = "dated";
  let manuallyMoved = false;
  let k = 1;   // current zoom scale, used for counter-scaling + declutter

  function lca(){
    let n = root;
    while (n.children && n.children.length === 1) n = n.children[0];
    return n;
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
  // Equal-angle unrooted: every subtree gets a wedge proportional to its
  // leaf count, so the drawing has no implied top and reads as kinship.
  function layoutUnrooted(R0){
    // A long unary ladder (one child per node) should stay compact so it
    // doesn't push the species fan into a corner; real branch points get
    // room so the leaves have space for their labels.
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

  // ---------- styling helpers ----------
  function nodeColor(d){ return d.data.is_leaf ? C.leaf : (d.data.dated ? C.dated : C.plain); }
  function nodeR(d){ return d.data.is_leaf ? 5 : (d.data.dated ? 7 : 5); }
  function cladeShown(d){
    if (d.data.is_leaf) return true;
    if (cladeMode === "none") return false;
    if (cladeMode === "dated") return !!d.data.dated;
    return true;
  }
  function hasPhoto(d){ return showPhotos && d.data.is_leaf && !!PHOTOS[d.data.sci]; }
  function labelText(d){
    if (d.data.is_leaf){
      if (showSci) return d.data.common ? d.data.common + " (" + d.data.sci + ")" : d.data.sci;
      return d.data.common ? d.data.common : d.data.sci;
    }
    let t = d.data.clade || "";
    if (d.data.dated && d.data.mya != null) t += ", " + d.data.mya;
    return t;
  }
  // Which side a label sits on: outward from the parent in the round
  // layouts (so a leaf on the left reads to the left), always right in
  // rectangular. Keeps fan labels from crossing each other.
  function side(d){
    if (mode === "rect" || !d.parent) return 1;
    return (d.cx - d.parent.cx) < -1 ? -1 : 1;
  }
  function labelX(d){ return nodeR(d) + 6 + (hasPhoto(d) ? PHOTO_SIZE + 4 : 0); }
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
      .attr("x", d => side(d) > 0 ? nodeR(d) + 6 : -(nodeR(d) + 6 + PHOTO_SIZE))
      .attr("y", -PHOTO_SIZE/2)
      .attr("width", PHOTO_SIZE).attr("height", PHOTO_SIZE)
      .attr("preserveAspectRatio", "xMidYMid slice")
      .style("display", d => hasPhoto(d) ? null : "none");
    all.select("text")
      .attr("class", d => d.data.is_leaf ? "lbl" : "clbl")
      .attr("x", d => side(d) * labelX(d)).attr("y", 4)
      .attr("text-anchor", d => side(d) > 0 ? "start" : "end")
      .text(labelText);

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
        // pointer delta is in screen px; convert to canvas units
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
          drawEdges(); drawNodes(); declutter(); tt.style("opacity",0);
        } else if (d === displayRoot){ setFocus(d.parent || root); }
        else { setFocus(d); }
      }));
    sel.exit().remove();
    declutter();
  }

  // Greedy label decluttering in SCREEN space. Species labels always draw;
  // clade labels are placed by age (deep landmarks first) and skipped when
  // they would overlap anything already placed. Re-run on zoom.
  function declutter(){
    const t = d3.zoomTransform(svg.node());
    const placed = [];
    function box(d){
      const sx = d.cx*t.k + t.x, sy = d.cy*t.k + t.y;
      const w = labelText(d).length * (d.data.is_leaf ? 6.9 : 6.1) + 6;
      const x0 = side(d) > 0 ? sx + labelX(d) - 2 : sx - labelX(d) - w + 2;
      return [x0, sy-8, x0+w, sy+8];
    }
    function hits(b){ return placed.some(p => !(b[2]<p[0] || b[0]>p[2] || b[3]<p[1] || b[1]>p[3])); }
    const want = displayRoot.descendants().filter(labelWanted);
    const show = new Set();
    // focused root first, then species (top to bottom on screen), then
    // clades by age. Anything that would overlap something already placed
    // waits for a closer zoom; its dot and hover stay.
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

  // ---------- zoom (counter-scaled) ----------
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
    // leave room for labels on the right + top bar; clamp so a tiny tree
    // never balloons and a deep one never becomes a speck
    let kk = 0.80*Math.min((W-220)/bw, (H-150)/bh);
    kk = Math.max(0.45, Math.min(2.4, kk));
    const tx = W/2 - kk*(x0+x1)/2 - 40, ty = H/2 - kk*(y0+y1)/2 + 20;
    return d3.zoomIdentity.translate(tx,ty).scale(kk);
  }
  function fit(animate){
    const t = fitTransform();
    if (animate === false) svg.call(zoom.transform, t);
    else svg.transition().duration(420).call(zoom.transform, t);
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
    fit(false);
    const NS = "http://www.w3.org/2000/svg";
    const clone = svg.node().cloneNode(true);
    clone.setAttribute("width", W); clone.setAttribute("height", H);
    if (HAS_PHOTOS && showPhotos){
      const map = await dataUrlMap();
      clone.querySelectorAll("image").forEach(im => {
        const h = im.getAttribute("href");
        if (h && map[h]) im.setAttribute("href", map[h]);
      });
    }
    const bg = document.createElementNS(NS, "rect");
    bg.setAttribute("x",0); bg.setAttribute("y",0);
    bg.setAttribute("width",W); bg.setAttribute("height",H); bg.setAttribute("fill", BG);
    clone.insertBefore(bg, clone.firstChild);
    const styleEl = document.createElementNS(NS, "style");
    styleEl.textContent = STYLE_TEXT;
    clone.insertBefore(styleEl, clone.firstChild);
    let src = new XMLSerializer().serializeToString(clone);
    // The serializer normally emits the SVG namespace itself; adding it by
    // hand as well produced a duplicate attribute and an invalid file.
    // Inject it only when it is genuinely missing.
    if (!/^<svg[^>]*\sxmlns=/.test(src)) src = src.replace(/^<svg/, '<svg xmlns="'+NS+'"');
    if (!asPng){ download(new Blob([src], {type:"image/svg+xml;charset=utf-8"}), "kinship_tree.svg"); return; }
    const img = new Image();
    img.onload = function(){
      const c = document.createElement("canvas"); c.width = W*2; c.height = H*2;
      const ctx = c.getContext("2d"); ctx.setTransform(2,0,0,2,0,0); ctx.drawImage(img, 0, 0);
      try { c.toBlob(function(b){ download(b, "kinship_tree.png"); }); }
      catch(e){ alert("A photo's host blocked embedding. Use Export SVG."); }
    };
    img.onerror = function(){ alert("Could not rasterize. Try Export SVG."); };
    img.src = "data:image/svg+xml;base64," + btoa(unescape(encodeURIComponent(src)));
  }

  // ---------- menu wiring ----------
  function setMode(m){
    mode = m; manuallyMoved = false;
    ["unrooted","radial","rect"].forEach(x => d3.select("#b-"+x).classed("on", x===m));
    render(); fit();
  }
  const $ = id => document.getElementById(id);
  $("b-unrooted").onclick = () => setMode("unrooted");
  $("b-radial").onclick = () => setMode("radial");
  $("b-rect").onclick = () => setMode("rect");
  $("b-clades").onclick = function(){
    cladeMode = cladeMode==="dated" ? "all" : (cladeMode==="all" ? "none" : "dated");
    this.textContent = "Clades: " + cladeMode;
    this.classList.toggle("on", cladeMode !== "none");
    drawNodes();
  };
  $("b-labels").onclick = function(){
    showLabels = !showLabels; this.classList.toggle("on", showLabels); drawNodes();
  };
  $("b-latin").onclick = function(){
    showSci = !showSci; this.classList.toggle("on", showSci); drawNodes();
  };
  $("b-photos").onclick = function(){
    if (!HAS_PHOTOS){ alert("No photos are cached for this tree yet. Load kin cards once on the Dashboard, then rebuild the interactive view."); return; }
    showPhotos = !showPhotos; this.classList.toggle("on", showPhotos); drawNodes();
  };
  $("b-lca").onclick = () => { manuallyMoved = false; setFocus(lca()); };
  $("b-whole").onclick = () => { manuallyMoved = false; setFocus(root); };
  $("b-fit").onclick = () => fit();
  $("b-png").onclick = () => exportImg(true);
  $("b-svg").onclick = () => exportImg(false);
  if (showSci) $("b-latin").classList.add("on");
  if (!HAS_PHOTOS) $("b-photos").style.opacity = 0.45;

  window.addEventListener("resize", () => {
    W = wrap.clientWidth || W; H = wrap.clientHeight || H;
    svg.attr("viewBox",[0,0,W,H]); manuallyMoved = false; render(); fit(false);
  });

  render(); fit(false);
})();
</script>
</body>
</html>
"""
