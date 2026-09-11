"""
Draggable, rearrangeable tree.

A live D3 canvas the visitor can arrange by hand:

  - drag any node to move it (dragging a clade carries its subtree),
  - click a clade to focus on it and hide the deeper ancestors above it,
  - "To LCA" jumps to the tree's last common ancestor, hiding the whole
    deep-time ladder above it in one press,
  - click the focused top clade again, or "Whole tree", to step back,
  - shift-click a clade to flip its children,
  - dial the clade dots between all / dated only / none,
  - turn labels (species AND clades) on or off together,
  - optionally show a photo beside each species, which travels with it,
  - switch a rectangular and a radial layout, pan, zoom,
  - export the current arrangement as PNG or SVG (photos embedded).

Toggling visibility or focusing keeps the arrangement and zoom you set;
only the layout buttons and the first, untouched render reframe the tree.

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
    """Self-contained draggable tree page for components.html()."""
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
  #bar { position:absolute; top:10px; left:10px; right:10px; z-index:5;
    display:flex; gap:6px; flex-wrap:wrap; align-items:center; }
  #bar button {
    background:rgba(14,27,26,0.85); color:%%TIP%%;
    border:1px solid #26403b; border-radius:7px;
    padding:6px 11px; font-size:12.5px; cursor:pointer; }
  #bar button:hover { border-color:%%LABEL%%; }
  #bar button.on { background:%%LABEL%%; color:#0e1b1a; border-color:%%LABEL%%;
    font-weight:600; }
  #bar .sep { width:1px; height:20px; background:#26403b; margin:0 2px; }
  #hint { position:absolute; bottom:10px; left:12px; right:12px; z-index:5;
    color:#7f978f; font-size:11.5px; line-height:1.4; }
  #tt { position:absolute; z-index:6; pointer-events:none; opacity:0;
    background:rgba(14,27,26,0.96); color:%%TIP%%; border:1px solid #26403b;
    border-radius:7px; padding:6px 9px; font-size:12px; max-width:240px;
    transition:opacity .12s; box-shadow:0 3px 12px rgba(0,0,0,.5); }
  svg { width:100%; height:100%; display:block; cursor:grab; }
  svg:active { cursor:grabbing; }
  .node { cursor:move; }
  .lbl { fill:%%TIP%%; font-size:12px; user-select:none; pointer-events:none; }
  .clbl { fill:%%LABEL%%; font-size:11px; user-select:none; pointer-events:none; }
  .edge { stroke:%%EDGE%%; stroke-width:1.7; fill:none; }
  .photo { pointer-events:none; }
  @media (max-width: 560px) {
    #bar button { padding:5px 8px; font-size:11.5px; }
    #hint { font-size:10.5px; }
  }
</style>
</head>
<body>
<div id="wrap">
  <div id="bar">
    <button id="b-radial" class="on">Radial</button>
    <button id="b-rect">Rectangular</button>
    <button id="b-fit">Fit</button>
    <span class="sep"></span>
    <button id="b-clades">Clades: dated</button>
    <button id="b-labels">Labels: on</button>
    <button id="b-lca">To LCA</button>
    <button id="b-whole">Whole tree</button>
    <span class="sep"></span>
    <button id="b-png">Export PNG</button>
    <button id="b-svg">Export SVG</button>
  </div>
  <div id="tt"></div>
  <div id="hint">Click a clade to focus and hide the deeper ancestors.
    "To LCA" jumps to the last common ancestor. Shift-click a clade to flip
    it. Drag to move, scroll to zoom. Toggles keep your arrangement.</div>
  <svg id="svg"></svg>
</div>
<script>
(function(){
  const DATA = %%DATA%%;
  const PHOTOS = %%PHOTOS%%;
  const SHOWSCI = %%SHOWSCI%%;
  const BG = "%%BG%%";
  const C = { edge:"%%EDGE%%", leaf:"%%LEAF%%", dated:"%%DATED%%",
              plain:"%%PLAIN%%", tip:"%%TIP%%", label:"%%LABEL%%" };
  const STYLE_TEXT =
    ".lbl{fill:"+C.tip+";font-size:12px;font-family:Helvetica,Arial,sans-serif;}"+
    ".clbl{fill:"+C.label+";font-size:11px;font-family:Helvetica,Arial,sans-serif;}"+
    ".edge{stroke:"+C.edge+";stroke-width:1.7;fill:none;}";
  const HAS_PHOTOS = Object.keys(PHOTOS).length > 0;
  const PHOTO_SIZE = 34;   // was 28; 20% larger per request
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
  let mode = "radial";
  let showLabels = true;
  let cladeMode = "dated";
  let manuallyMoved = false;   // once true, we stop reflowing on focus

  // Last common ancestor of all leaves: descend from the true root while
  // there is only one child, i.e. the top of the branching part of the tree.
  function lca(){
    let n = root;
    while (n.children && n.children.length === 1) n = n.children[0];
    return n;
  }

  function layout(){
    const R0 = displayRoot;
    if (mode === "rect"){
      const dx = Math.max(16, (H - 120) / (R0.leaves().length + 1));
      const tree = d3.tree().nodeSize([dx, Math.max(90,(W-340)/(R0.height+1))]);
      tree(R0);
      let minx=Infinity, maxx=-Infinity, miny=Infinity, maxy=-Infinity;
      R0.each(d => { d.cx = d.y - R0.y; d.cy = d.x;
        minx=Math.min(minx,d.cx); maxx=Math.max(maxx,d.cx);
        miny=Math.min(miny,d.cy); maxy=Math.max(maxy,d.cy); });
      const ox = 90 - minx, oy = (H/2) - (miny+maxy)/2;
      R0.each(d => { d.cx += ox; d.cy += oy; });
    } else {
      const Rr = Math.min(W,H)/2 - 90;
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
  }

  function nodeColor(d){
    if (d.data.is_leaf) return C.leaf;
    return d.data.dated ? C.dated : C.plain;
  }
  function nodeR(d){
    if (d.data.is_leaf) return 5;
    return d.data.dated ? 7 : 5;
  }
  function cladeShown(d){
    if (d.data.is_leaf) return true;
    if (cladeMode === "none") return false;
    if (cladeMode === "dated") return !!d.data.dated;
    return true;
  }
  function hasPhoto(d){ return d.data.is_leaf && !!PHOTOS[d.data.sci]; }
  function labelText(d){
    if (d.data.is_leaf){
      if (SHOWSCI) return d.data.common
        ? d.data.common + " (" + d.data.sci + ")" : d.data.sci;
      return d.data.common ? d.data.common : d.data.sci;
    }
    let t = d.data.clade || "";
    if (d.data.dated && d.data.mya != null) t += ", " + d.data.mya;
    return t;
  }
  function labelX(d){
    if (hasPhoto(d)) return nodeR(d) + 6 + PHOTO_SIZE + 4;
    return nodeR(d) + 6;
  }

  function drawEdges(){
    const links = displayRoot.links();
    const sel = gEdges.selectAll("path.edge").data(links, d => d.target.__id);
    sel.enter().append("path").attr("class","edge")
      .merge(sel)
      .attr("d", d => "M"+d.source.cx+","+d.source.cy+"L"+d.target.cx+","+d.target.cy);
    sel.exit().remove();
  }

  function drawNodes(){
    const nodes = displayRoot.descendants();
    const sel = gNodes.selectAll("g.node").data(nodes, d => d.__id);
    const ent = sel.enter().append("g").attr("class","node");
    ent.append("circle");
    ent.each(function(d){
      if (d.data.is_leaf && HAS_PHOTOS) d3.select(this).append("image").attr("class","photo");
    });
    ent.append("text");
    const all = ent.merge(sel);
    all.attr("transform", d => "translate("+d.cx+","+d.cy+")");
    all.select("circle")
      .attr("r", d => (d.data.is_leaf || cladeShown(d)) ? nodeR(d) : 0)
      .attr("fill", nodeColor)
      .attr("stroke", d => (d === displayRoot && !d.data.is_leaf) ? C.label : "#0e1b1a")
      .attr("stroke-width", d => (d === displayRoot && !d.data.is_leaf) ? 2 : 1);
    all.select("image.photo")
      .attr("href", d => PHOTOS[d.data.sci] || "")
      .attr("x", d => nodeR(d) + 6)
      .attr("y", -PHOTO_SIZE/2)
      .attr("width", PHOTO_SIZE).attr("height", PHOTO_SIZE)
      .attr("preserveAspectRatio", "xMidYMid slice")
      .style("display", d => hasPhoto(d) ? null : "none");
    all.select("text")
      .attr("class", d => d.data.is_leaf ? "lbl" : "clbl")
      .attr("x", labelX).attr("y", 4)
      .style("display", d => {
        if (!showLabels) return "none";
        if (d.data.is_leaf) return null;
        if (!cladeShown(d)) return "none";
        return d.data.clade ? null : "none";
      })
      .text(labelText);

    all.on("mousemove", function(ev,d){
        const html = d.data.is_leaf
          ? "<b>"+(d.data.common||d.data.sci)+"</b><br><i>"+d.data.sci+"</i>"
          : "<b>"+(d.data.clade||"clade")+"</b>"+
            (d.data.mya!=null ? "<br>"+d.data.mya+" million years since the last common ancestor" : "<br>age not set")+
            "<br><span style='color:#9ab3ab'>"+
            (d===displayRoot ? "click to step back out" : "click to focus here")+"</span>";
        tt.html(html).style("opacity",1);
        const r = wrap.getBoundingClientRect();
        tt.style("left", (ev.clientX - r.left + 12)+"px")
          .style("top", (ev.clientY - r.top + 12)+"px");
      })
      .on("mouseleave", () => tt.style("opacity",0));

    all.call(d3.drag()
      .on("start", function(ev){ ev.sourceEvent.stopPropagation(); this.__dist = 0; })
      .on("drag", function(ev,d){
        this.__dist += Math.abs(ev.dx) + Math.abs(ev.dy);
        if (this.__dist > 3) manuallyMoved = true;
        const set = d.descendants();
        set.forEach(n => { n.cx += ev.dx; n.cy += ev.dy; });
        gNodes.selectAll("g.node")
          .attr("transform", x => "translate("+x.cx+","+x.cy+")");
        drawEdges();
      })
      .on("end", function(ev,d){
        if (this.__dist > 3) return;
        if (d.data.is_leaf) return;
        if (ev.sourceEvent && ev.sourceEvent.shiftKey){
          if (d.children){ d.children.reverse();
            if(d.data.children) d.data.children.reverse(); }
        } else if (d === displayRoot){
          setFocus(d.parent || root);
          return;
        } else {
          setFocus(d);
          return;
        }
        // flip only: reflow just this subtree if untouched, else keep
        if (!manuallyMoved) layout();
        drawEdges(); drawNodes(); tt.style("opacity",0);
      }));
    sel.exit().remove();
  }

  // Change the visible subtree. Keep the user's arrangement + zoom when
  // they have moved things; reflow + reframe only for an untouched tree.
  function setFocus(node){
    displayRoot = node;
    if (!manuallyMoved){ layout(); drawEdges(); drawNodes(); fit(); }
    else { drawEdges(); drawNodes(); }
    tt.style("opacity",0);
  }

  function render(){ layout(); drawEdges(); drawNodes(); }

  const zoom = d3.zoom().scaleExtent([0.15, 6])
    .on("zoom", ev => viewport.attr("transform", ev.transform));
  svg.call(zoom);

  function fitTransform(){
    const ds = displayRoot.descendants();
    const xs = ds.map(d=>d.cx), ys = ds.map(d=>d.cy);
    const x0=Math.min.apply(null,xs), x1=Math.max.apply(null,xs);
    const y0=Math.min.apply(null,ys), y1=Math.max.apply(null,ys);
    const bw=Math.max(1,x1-x0), bh=Math.max(1,y1-y0);
    const k=Math.min(6, 0.86*Math.min(W/bw, H/bh));
    const tx=W/2 - k*(x0+x1)/2, ty=H/2 - k*(y0+y1)/2;
    return d3.zoomIdentity.translate(tx,ty).scale(k);
  }
  function fit(animate){
    const t = fitTransform();
    if (animate === false) svg.call(zoom.transform, t);
    else svg.transition().duration(400).call(zoom.transform, t);
  }

  function download(blob, name){
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
  }
  async function dataUrlMap(){
    // Fetch each photo once and turn it into a data URL so it survives
    // being drawn into a canvas (external hrefs break the raster).
    const map = {};
    const urls = [...new Set(Object.values(PHOTOS))];
    await Promise.all(urls.map(async u => {
      try {
        const r = await fetch(u, {mode:"cors"});
        const b = await r.blob();
        map[u] = await new Promise(res => {
          const fr = new FileReader();
          fr.onload = () => res(fr.result);
          fr.readAsDataURL(b);
        });
      } catch(e) { /* leave external; may not rasterize */ }
    }));
    return map;
  }
  async function exportImg(asPng){
    fit(false);
    const NS = "http://www.w3.org/2000/svg";
    const clone = svg.node().cloneNode(true);
    clone.setAttribute("xmlns", NS);
    clone.setAttribute("width", W); clone.setAttribute("height", H);
    if (HAS_PHOTOS){
      const map = await dataUrlMap();
      clone.querySelectorAll("image").forEach(im => {
        const h = im.getAttribute("href") || im.getAttributeNS("http://www.w3.org/1999/xlink","href");
        if (h && map[h]){ im.setAttribute("href", map[h]); }
      });
    }
    const bg = document.createElementNS(NS, "rect");
    bg.setAttribute("x",0); bg.setAttribute("y",0);
    bg.setAttribute("width",W); bg.setAttribute("height",H);
    bg.setAttribute("fill", BG);
    clone.insertBefore(bg, clone.firstChild);
    const styleEl = document.createElementNS(NS, "style");
    styleEl.textContent = STYLE_TEXT;
    clone.insertBefore(styleEl, clone.firstChild);
    const src = new XMLSerializer().serializeToString(clone);
    if (!asPng){
      download(new Blob([src], {type:"image/svg+xml;charset=utf-8"}), "kinship_tree.svg");
      return;
    }
    const img = new Image();
    img.onload = function(){
      const c = document.createElement("canvas");
      c.width = W*2; c.height = H*2;
      const ctx = c.getContext("2d");
      ctx.setTransform(2,0,0,2,0,0);
      ctx.drawImage(img, 0, 0);
      try { c.toBlob(function(b){ download(b, "kinship_tree.png"); }); }
      catch(e){ alert("A photo could not be embedded (its host blocks it). Use Export SVG."); }
    };
    img.onerror = function(){ alert("Could not rasterize. Try Export SVG."); };
    img.src = "data:image/svg+xml;base64," + btoa(unescape(encodeURIComponent(src)));
  }

  function setMode(m){
    mode = m; manuallyMoved = false;
    d3.select("#b-radial").classed("on", m==="radial");
    d3.select("#b-rect").classed("on", m==="rect");
    render(); fit();
  }
  document.getElementById("b-radial").onclick = () => setMode("radial");
  document.getElementById("b-rect").onclick = () => setMode("rect");
  document.getElementById("b-fit").onclick = () => fit();
  document.getElementById("b-clades").onclick = function(){
    cladeMode = cladeMode==="all" ? "dated" : (cladeMode==="dated" ? "none" : "all");
    this.textContent = "Clades: " + cladeMode;
    this.classList.toggle("on", cladeMode !== "all");
    drawNodes();   // visibility only, no reflow
  };
  document.getElementById("b-labels").onclick = function(){
    showLabels = !showLabels;
    this.textContent = "Labels: " + (showLabels ? "on":"off");
    this.classList.toggle("on", !showLabels);
    drawNodes();   // visibility only, no reflow
  };
  document.getElementById("b-lca").onclick = function(){
    manuallyMoved = false; setFocus(lca());
  };
  document.getElementById("b-whole").onclick = function(){
    manuallyMoved = false; setFocus(root);
  };
  document.getElementById("b-png").onclick = () => exportImg(true);
  document.getElementById("b-svg").onclick = () => exportImg(false);

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
