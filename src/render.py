"""
Tree rendering, two ways.

  - render_html: an interactive view for the dashboard, on a dark panel.
    Every node (species or clade, dated or not) is hoverable for its info.
  - render_files: a still SVG (and PNG) for the gallery projection and the
    kinship report, on a warm light background.

Both read the Newick written by tree.py plus the per-node metadata sidecar
(<stem>_nodes.json).

Layout strategy, per shape:
  - Rectangular (default): the long rank-by-rank chains are collapsed for the
    drawing only, so the tree shows real branch points, species, and the dated
    clades. Tips align in a clean column; dated clades carry a name + age.
  - Unrooted: same collapse, no tip alignment so labels sit at the leaves.
  - Circular: full chains kept so the radial layout has room to breathe; the
    dated clades show as bigger orange dots without text labels (hover gives
    the age). Tip labels sit around the ring.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

# Layout names the dashboard offers, mapped to toytree's codes. Rectangular reads
# best for this kind of tree, so it leads.
LAYOUTS = {"Unrooted": "unrooted", "Rectangular": "r"}

# Legend colors the dashboard reads (matched to the dark palette below).


def _format_clade_name(raw: str | None) -> str:
    """Format a raw clade name from NCBI for display:
      - replace underscores with spaces
      - title-case multi-word ('cellular_organism' -> 'Cellular Organism')
      - keep single-word names that are already capitalized as-is
        ('Eukaryota' stays 'Eukaryota')
      - lowercase-only single words get capitalized ('commelinids' ->
        'Commelinids')."""
    if not raw:
        return ""
    name = raw.replace("_", " ").strip()
    if not name:
        return ""
    # If the whole string is lowercase, title-case it. Otherwise leave
    # the existing casing alone (NCBI gives most names already cased
    # correctly; we only want to fix the obvious lowercase outliers).
    if name == name.lower():
        return name.title()
    # Mixed/upper case already — replace underscores then return
    return " ".join(w[0].upper() + w[1:] if w and w[0].isalpha() and
                       w[0].islower() else w
                       for w in name.split(" "))


def _chain_combined_label(node, dated: set, meta: dict) -> str:
    """In rectangular layouts, label ONLY the innermost dated clade per
    single-child chain. Other chain members stay as amber dots without
    text — keeps the layout readable. Innermost = no dated non-leaf
    child.

    Ancestry info still available via the Unrooted layout (T0/T2),
    which has room to label every clade individually."""
    for child in (node.children or []):
        if child.name in dated and not child.is_leaf():
            return ""  # not innermost — suppress
    info = meta.get(node.name, {})
    return f"{_format_clade_name(node.name)}, {info.get('mya')}"



LEAF_COLOR = "#46c79a"          # species (leaf)
DATED_NODE_COLOR = "#f0a24a"    # clade with a divergence age
PLAIN_NODE_COLOR = "#6f8a82"    # clade without one

# Two palettes plus sizing. Dark is the dashboard; light is the kinship report.
_DARK = {
    "bg": "#0e1b1a", "leaf": LEAF_COLOR, "dated": DATED_NODE_COLOR,
    "plain": PLAIN_NODE_COLOR, "edge": "#5f7d75", "tip": "#e8f3ef",
    "label": "#ffd97a", "align": "#26352f", "nodestroke": "#0e1b1a",
    "w": 1000, "h": 820, "shrink": 150,
    # plain dots are bigger here so the hover hit area is easy to land on
    "leaf_size": 7, "dated_size": 10, "plain_size": 9,
}
_LIGHT = {
    "bg": "#f7f3ec", "leaf": "#1f8f6a", "dated": "#d27d2c",
    "plain": "#b9c4bd", "edge": "#7e988f", "tip": "#23332e",
    "label": "#a85a1f", "align": "#d4ddd6", "nodestroke": "#ffffff",
    "w": 1200, "h": 1180, "shrink": 240,
    # plain dots stay small in the static render (no hover to worry about)
    "leaf_size": 7, "dated_size": 9, "plain_size": 4,
}


def load_meta(meta_path) -> dict:
    p = Path(meta_path)
    return json.loads(p.read_text()) if p.exists() else {}


def _hover_text(label: str, info: dict) -> str:
    if info.get("is_leaf"):
        sci = info.get("scientific_name") or label.replace("_", " ")
        common = info.get("common_name")
        return f"{common} ({sci})" if common else sci
    clade = info.get("scientific_name") or label.replace("_", " ") or "node"
    parts = [clade]
    if info.get("rank"):
        parts.append(info["rank"])
    parts.append(f"{info['mya']} MYA" if info.get("mya") is not None
                 else "age not set")
    return ", ".join(parts)


def _resolve_newick_path(newick_path, use_scaled: bool = True):
    """Given a `<stem>_named_tree.nwk` path, prefer the MYA-scaled
    sibling `<stem>_scaled_tree.nwk` when it exists AND use_scaled
    is True. Falls back to the plain topology newick otherwise."""
    p = Path(newick_path)
    if not use_scaled:
        return p
    scaled = p.parent / p.name.replace("_named_tree.nwk", "_scaled_tree.nwk")
    if scaled.exists():
        return scaled
    return p


def _collapse_unary(newick_path, dated: set) -> str:
    """Collapse single-child internal nodes (the long rank chains) so the
    drawing shows clean branches, the species, and the dated clades. Dated
    clades are kept even when they end up unary. Newick on disk is untouched.
    """
    from ete3 import Tree
    t = Tree(Path(newick_path).read_text(), format=1)
    for node in t.traverse("postorder"):
        if (not node.is_leaf() and not node.is_root()
                and len(node.children) == 1 and node.name not in dated):
            node.delete(preserve_branch_length=True,
                        prevent_nondicotomic=False)
    return t.write(format=1, format_root_node=True)


def _prepare(newick_path, meta: dict, pal: dict, *,
             collapse: bool, plain_visible: bool, show_dated_labels: bool,
             show_undated_labels: bool = True,
             show_scientific: bool = True,
             layout: str = "r",
             use_scaled: bool = True):
    """Build the toytree object plus the idx-ordered style lists. The flags let
    each layout (rectangular / unrooted / circular) choose how dense to draw.
    """
    import toytree

    dated = {k for k, v in meta.items()
             if not v.get("is_leaf") and v.get("mya") is not None}
    resolved_nwk = _resolve_newick_path(newick_path, use_scaled=use_scaled)
    nwk_str = (_collapse_unary(resolved_nwk, dated) if collapse
               else Path(resolved_nwk).read_text())
    tre = toytree.tree(nwk_str)
    nnodes = tre.nnodes

    hover = {}
    sizes = [pal["plain_size"] if plain_visible else 0] * nnodes
    colors = [pal["plain"]] * nnodes
    nlabels = [""] * nnodes

    for node in tre.traverse():
        i = node.idx
        info = meta.get(node.name, {"is_leaf": node.is_leaf()})
        hover[i] = _hover_text(node.name, info)
        if node.is_leaf():
            sizes[i] = pal["leaf_size"]
            colors[i] = pal["leaf"]
        elif node.name in dated:
            sizes[i] = pal["dated_size"]
            colors[i] = pal["dated"]
            if show_dated_labels:
                # Chain-combine ONLY in rectangular (where labels stack
                # at the same Y for chains of single-child dated nodes).
                # In unrooted/circular each clade has its own spatial
                # position so we render labels individually.
                if layout == "r":
                    nlabels[i] = _chain_combined_label(node, dated, meta)
                else:
                    nlabels[i] = (
                        f"{_format_clade_name(node.name)}, "
                        f"{info.get('mya')}")
        else:
            sizes[i] = pal["plain_size"] if plain_visible else 0
            colors[i] = pal["plain"]
            # Label undated clades with just the clade name (no age
            # suffix), but only when show_undated_labels is on. The dot
            # color (PLAIN_NODE_COLOR vs DATED_NODE_COLOR) already
            # differentiates them visually in dense layouts.
            if (show_dated_labels and plain_visible and node.name
                    and show_undated_labels):
                nlabels[i] = _format_clade_name(node.name)

    tre = tre.set_node_data("meta", hover, default="")

    tip_labels = []
    for tname in tre.get_tip_labels():
        info = meta.get(tname, {})
        common = info.get("common_name")
        sci = info.get("scientific_name") or tname.replace("_", " ")
        if show_scientific and common:
            tip_labels.append(f"{common}\n({sci})")
        elif show_scientific:
            tip_labels.append(f"({sci})")
        else:
            tip_labels.append(common or sci)

    return tre, tip_labels, sizes, colors, nlabels


def _layout_settings(layout: str, pal: dict):
    """Per-layout drawing knobs."""
    if layout == "c":
        # Keep the full chain so the radial layout has structure to spread.
        side = max(pal["w"], pal["h"])
        return dict(
            collapse=False, plain_visible=False, show_dated_labels=False,
            align=True, use_edges=False, edge_type="c",
            w=side, h=side, padding=30, shrink=90,
        )
    if layout == "unrooted":
        side = max(pal["w"], pal["h"])
        return dict(
            collapse=True, plain_visible=True, show_dated_labels=True,
            show_undated_labels=True,
            align=False, use_edges=False, edge_type="p",
            w=side, h=side, padding=60, shrink=120,
        )
    # rectangular: show undated labels too (dated are now chain-
    # collapsed to innermost-only so the overlap problem is gone).
    return dict(
        collapse=True, plain_visible=True, show_dated_labels=True,
        show_undated_labels=True,
        align=True, use_edges=False, edge_type="p",
        w=pal["w"], h=pal["h"], padding=70, shrink=pal["shrink"],
    )


def _draw(newick_path, meta: dict, layout: str,
          show_scientific: bool = True, dark: bool = True):
    pal = _DARK if dark else _LIGHT
    s = _layout_settings(layout, pal)
    tre, tip_labels, sizes, colors, nlabels = _prepare(
        newick_path, meta, pal,
        collapse=s["collapse"], plain_visible=s["plain_visible"],
        show_dated_labels=s["show_dated_labels"],
        show_undated_labels=s.get("show_undated_labels", True),
        layout=layout,
        show_scientific=show_scientific,
    )
    return tre.draw(
        width=s["w"], height=s["h"], layout=layout, edge_type=s["edge_type"],
        use_edge_lengths=s["use_edges"], tip_labels_align=s["align"],
        tip_labels=tip_labels,
        tip_labels_style={"font-size": "12.5px", "fill": pal["tip"],
                          "-toyplot-anchor-shift": "14px"},
        node_hover="meta",
        node_mask=False,
        node_labels=nlabels,
        node_labels_style={"font-size": "10.5px", "fill": pal["label"],
                           "font-weight": "bold",
                           "-toyplot-anchor-shift": "-7px",
                           "baseline-shift": "8px", "text-anchor": "end"},
        node_sizes=sizes,
        node_colors=colors,
        node_style={"stroke": pal["nodestroke"], "stroke-width": 1.0},
        edge_style={"stroke": pal["edge"], "stroke-width": 1.7},
        edge_align_style={"stroke": pal["align"], "stroke-width": 0.8,
                          "stroke-dasharray": "1,4"},
        padding=s["padding"],
        shrink=s["shrink"],
    )


_TEXT_RE = re.compile(r"<text ([^>]*)>([^<]*)</text>", re.S)


def _two_line(svg_or_html: str) -> str:
    """SVG ignores raw newlines in <text>, so turn "common\\n(scientific)" into
    stacked <tspan>s with the scientific line italicized. A lone parenthesized
    scientific name (no common name) is italicized in place.
    """
    def repl(m):
        attrs, body = m.group(1), m.group(2)
        if "\n" in body:
            lines = body.split("\n")
            xm = re.search(r'x="(-?[0-9.]+)"', attrs)
            x = xm.group(1) if xm else "0"
            rest = "".join(
                f'<tspan x="{x}" dy="1.2em" style="font-style:italic">'
                f"{ln}</tspan>"
                for ln in lines[1:]
            )
            return f"<text {attrs}>{lines[0]}{rest}</text>"
        if body.startswith("(") and body.endswith(")"):
            return (f'<text {attrs}><tspan style="font-style:italic">'
                    f"{body}</tspan></text>")
        return m.group(0)
    return _TEXT_RE.sub(repl, svg_or_html)


def _bg_rect(svg_or_html: str, color: str) -> str:
    """Paint the panel color as the first element inside the SVG itself so the
    background covers the whole drawing regardless of the panel around it.
    """
    rect = (f'<rect x="0" y="0" width="100%" height="100%" '
            f'fill="{color}" stroke="none"></rect>')
    return re.sub(r"(<svg\b[^>]*>)", lambda m: m.group(1) + rect,
                  svg_or_html, count=1)




_EMPTY_LABEL_RE = re.compile(
    r'(<g class="toytree-NodeLabel"\s+transform="translate\([^)]+\)">'
    r'<title>[^<]+</title>)</g>')


def _hover_targets(svg_or_html: str) -> str:
    """Toyplot/toytree puts the hover <title> on the NodeLabel group. For
    plain (undated) internal nodes that group has no visible <text>, so the
    browser has nothing to hover over. Inject a transparent circle inside each
    empty NodeLabel so the cursor can land near the marker and trigger the
    tooltip. Dated nodes already carry a <text> child and are unaffected.
    """
    return _EMPTY_LABEL_RE.sub(
        r'\1<circle r="14" fill="transparent" stroke="none" '
        r'pointer-events="all"/></g>',
        svg_or_html)




def _header_band(svg_or_html: str, tree_name: str | None) -> str:
    """Inject a small header band into the SVG with the project mark, slogan,
    and per-tree title. Read at the gallery, on kinship reports, on the dashboard."""
    if tree_name is None:
        return svg_or_html
    try:
        from src import tree_settings
        mark = tree_settings.PROJECT_MARK
        slogan = tree_settings.PROJECT_SLOGAN
        title = tree_settings.title_for(tree_name)
    except Exception:
        return svg_or_html
    # Hand-wrap the slogan to two lines so it doesn't run into the title.
    # SVG <text> doesn't auto-wrap; we split on the closest space to the
    # midpoint for visually balanced lines.
    slogan_lines = ["", ""]
    if slogan:
        words = slogan.split()
        if len(words) <= 2:
            slogan_lines = [slogan, ""]
        else:
            target = len(slogan) // 2
            running = 0
            split_at = 1
            for i, w in enumerate(words):
                running += len(w) + 1
                if running >= target:
                    split_at = i + 1
                    break
            slogan_lines = [" ".join(words[:split_at]),
                             " ".join(words[split_at:])]
    band = (
        f'<g class="kinship-header" pointer-events="none">'
        f'  <text x="14" y="22" fill="#a85a1f" font-family="Georgia,serif" '
        f'font-weight="bold" font-size="14">{mark}</text>'
        f'  <text x="14" y="40" fill="#5e6f68" font-family="Helvetica,Arial,sans-serif" '
        f'font-size="10" font-style="italic">{slogan_lines[0]}</text>'
        f'  <text x="14" y="54" fill="#5e6f68" font-family="Helvetica,Arial,sans-serif" '
        f'font-size="10" font-style="italic">{slogan_lines[1]}</text>'
        f'  <text x="50%" y="32" fill="#243b34" font-family="Helvetica,Arial,sans-serif" '
        f'font-size="14" text-anchor="middle" font-style="italic">{title}</text>'
        f'</g>'
    )
    return re.sub(r"(<svg\b[^>]*>(?:<rect[^>]*></rect>)?)",
                  lambda m: m.group(1) + band, svg_or_html, count=1)




def _build_image_map(meta: dict) -> dict:
    """Map each tip's common name and scientific name to its image URL,
    drawing on the species_profile disk cache. Returns a JSON-safe dict."""
    try:
        from src import species_profile
    except Exception:
        return {}
    out = {}
    for tip_name, info in meta.items():
        if not info.get("is_leaf"):
            continue
        sci = info.get("scientific_name") or tip_name.replace("_", " ")
        common = info.get("common_name")
        try:
            p = species_profile.find_profile(sci, common)
        except Exception:
            p = None
        if not p:
            continue
        url = p.get("image_url")
        if not url:
            continue
        if common:
            out[common] = url
        out[sci] = url
        out[tip_name.replace("_", " ")] = url
    return out


def _hover_image_overlay(svg_or_html: str, image_map: dict) -> str:
    """Inject a floating image preview that fades in when the cursor enters
    a tip label. Image URLs come from species_profile."""
    if not image_map:
        return svg_or_html
    import json as _json
    js_map = _json.dumps(image_map)
    overlay = f"""
<div id="kinship-hover" style="position:fixed;pointer-events:none;opacity:0;
     transition:opacity 0.2s ease;z-index:9999;background:#0e1b1a;
     padding:6px;border-radius:8px;box-shadow:0 6px 18px rgba(0,0,0,0.6);
     font-family:Helvetica,Arial,sans-serif;">
  <img id="kinship-hover-img" style="display:block;width:200px;height:200px;
       object-fit:cover;border-radius:4px;background:#0e1b1a;">
  <div id="kinship-hover-cap" style="color:#e8f3ef;font-size:11px;
       margin-top:4px;text-align:center;max-width:200px;"></div>
</div>
<script>
(function() {{
  var IMG = {js_map};
  var box = document.getElementById('kinship-hover');
  var img = document.getElementById('kinship-hover-img');
  var cap = document.getElementById('kinship-hover-cap');
  function bareKey(t) {{
    t = (t || '').trim();
    var idx = t.indexOf('(');
    if (idx >= 0) t = t.substring(0, idx).trim();
    return t;
  }}
  document.addEventListener('mousemove', function(e) {{
    box.style.left = Math.min(window.innerWidth - 220, e.clientX + 14) + 'px';
    box.style.top  = Math.min(window.innerHeight - 240, e.clientY + 14) + 'px';
  }});
  var texts = document.querySelectorAll('text');
  texts.forEach(function(t) {{
    var raw = t.textContent || '';
    var key = bareKey(raw);
    // tip-label tspans hold the italic (sci) line; check both
    if (!IMG[key]) {{
      var insideKey = bareKey(raw.replace(/[()]/g, ''));
      if (IMG[insideKey]) key = insideKey;
      else return;
    }}
    t.style.cursor = 'pointer';
    t.addEventListener('mouseenter', function() {{
      img.src = IMG[key]; cap.textContent = key; box.style.opacity = '1';
    }});
    t.addEventListener('mouseleave', function() {{
      box.style.opacity = '0';
    }});
  }});
}})();
</script>
"""
    return svg_or_html + overlay






def _legend_band(svg_or_html: str) -> str:
    """Inject a small legend along the bottom-left of the SVG, just above
    the CC footer. Three colored dots + labels + the 'mya' explanation
    so every exported PNG/SVG/PDF carries its own key."""
    leg = (
        '<g class="kinship-legend" pointer-events="none">'
        # Background plate (rounded rect)
        # Row 1: species dot
        f'<circle cx="28" cy="89.6%" r="5" fill="{LEAF_COLOR}"/>'
        '<text x="40" y="89.6%" fill="#5e6f68" '
        'font-family="Helvetica,Arial,sans-serif" font-size="10" '
        'dominant-baseline="middle">'
        '<tspan font-weight="bold">Common Name</tspan> '
        '<tspan font-style="italic">(Scientific name)</tspan> '
        '— a species (green tip)</text>'
        # Row 2: dated clade dot
        f'<circle cx="28" cy="92.5%" r="6.5" fill="{DATED_NODE_COLOR}"/>'
        '<text x="40" y="92.5%" fill="#5e6f68" '
        'font-family="Helvetica,Arial,sans-serif" font-size="10" '
        'dominant-baseline="middle">'
        '<tspan font-weight="bold">Clade, ###</tspan> '
        '— ancestral node with a known divergence age (amber)</text>'
        # Row 3: undated clade dot
        f'<circle cx="28" cy="95.3%" r="4" fill="{PLAIN_NODE_COLOR}"/>'
        '<text x="40" y="95.3%" fill="#5e6f68" '
        'font-family="Helvetica,Arial,sans-serif" font-size="10" '
        'dominant-baseline="middle">'
        '<tspan font-weight="bold">Clade</tspan> '
        '— ancestral node, divergence age not added (teal)</text>'
        '</g>'
        # mya footnote — bottom-right corner of the SVG
        '<text x="98%" y="97%" fill="#9ab3ab" '
        'font-family="Helvetica,Arial,sans-serif" font-size="9" '
        'font-style="italic" text-anchor="end">'
        'numbers are millions of years (mya) since the last common ancestor'
        '</text>'
    )
    # Insert right before the CC footer text (which ends just before </svg>).
    # Easiest: insert just before </svg>.
    return re.sub(r"(</svg>)", leg + r"\1", svg_or_html, count=1)

def _cc_footer(svg_or_html: str) -> str:
    """Append a small CC BY-SA notice as a <text> near the bottom of the SVG."""
    footer = ('<text x="50%" y="99.2%" fill="#6b7d76" '
              'font-family="Helvetica,Arial,sans-serif" font-size="9" '
              'text-anchor="middle">CC BY-SA Maya · Shared Rivers · '
              '{r}Evolving Kinship</text>')
    return re.sub(r"(</svg>)", footer + r"\1", svg_or_html, count=1)


def render_html(newick_path, meta: dict, layout: str = "r",
                show_scientific: bool = True,
                tree_name: str | None = None,
                zoom: float = 0.85) -> str:
    """Return interactive HTML on a dark panel for the dashboard.

    zoom: visual scaling factor applied via CSS transform. 1.0 = native
    toyplot size. 0.85 (default) shrinks the tree so the whole thing
    fits in the dashboard iframe without horizontal scrolling. The
    actual SVG isn't re-rendered — just visually scaled — so hover
    targets and downloads remain at native resolution."""
    import toyplot.html

    canvas, _, _ = _draw(newick_path, meta, layout, show_scientific, dark=True)
    html = toyplot.html.tostring(canvas).replace("meta: ", "")
    html = _two_line(html)
    bg = _DARK["bg"]
    html = _bg_rect(html, bg)
    html = _hover_targets(html)
    html = _header_band(html, tree_name)
    html = _hover_image_overlay(html, _build_image_map(meta))
    html = _legend_band(html)
    html = _cc_footer(html)
    return (
        f'<div style="background:{bg};border-radius:10px;padding:10px;'
        f'display:inline-block;min-width:100%;box-sizing:border-box;'
        f'overflow:auto">'
        f'<div style="transform:scale({zoom});transform-origin:top left;'
        f'width:{100/zoom:.1f}%">'
        f'{html}'
        f'</div></div>')


def render_files(newick_path, meta: dict, out_stem: str,
                 layout: str = "r", out_dir: Path | None = None,
                 show_scientific: bool = True,
                 tree_name: str | None = None) -> Path:
    """Save a still SVG (and PNG) on a warm light background for the kinship report."""
    import toyplot.svg

    out_dir = out_dir or config.OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    canvas, _, _ = _draw(newick_path, meta, layout, show_scientific, dark=False)

    svg_path = out_dir / f"{out_stem}.svg"
    toyplot.svg.render(canvas, str(svg_path))
    svg = _bg_rect(_two_line(svg_path.read_text()), _LIGHT["bg"])
    svg = _hover_targets(svg)
    svg = _header_band(svg, tree_name)
    svg = _legend_band(svg)
    svg = _cc_footer(svg)
    svg_path.write_text(svg)
    print(f"rendered {svg_path.name}")

    png_path = out_dir / f"{out_stem}.png"
    s = _layout_settings(layout, _LIGHT)
    try:
        import cairosvg
        cairosvg.svg2png(bytestring=svg.encode("utf-8"),
                         write_to=str(png_path),
                         output_width=s["w"], output_height=s["h"])
        print(f"rendered {out_stem}.png")
    except Exception:
        try:
            import toyplot.png
            toyplot.png.render(canvas, str(png_path))
            print(f"rendered {out_stem}.png (toyplot)")
        except Exception:
            pass
    return svg_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('usage: python -m src.render "<Tree_Name>"')
        raise SystemExit(1)
    from src import tree as tree_mod
    result = tree_mod.build_tree(sys.argv[1])
    stem = sys.argv[1].strip().replace(" ", "_").lower()
    render_files(result["path"], result["meta"], f"{stem}_tree", tree_name=sys.argv[1])
