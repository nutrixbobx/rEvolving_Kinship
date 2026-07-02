"""
Species photo tree.

Same composition as the sound kinship tree, with photos on the right instead
of spectrograms. Pulls the image from species_profile (iNaturalist + Wikipedia
+ admin overrides). Header bar reads "{r}Evolving Kinship" plus the per-tree
title (owner-personalized via tree_settings).

Saved as outputs/<stem>_photo_tree.png on the same dark panel as the dashboard.
"""

from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
from src import usage_log  # noqa: E402

BG = "#0e1b1a"
EDGE = "#5f7d75"
LEAF = "#46c79a"
DATED = "#f0a24a"
PLAIN = "#6f8a82"
TIP_TEXT = "#e8f3ef"
LABEL = "#ffd97a"


def _layout(tre):
    tips = list(tre.get_tip_labels())
    n = len(tips)
    y_of_tip = {name: i for i, name in enumerate(tips)}

    def depth(node):
        d = 0
        while node.up:
            node = node.up
            d += 1
        return d

    max_depth = max(depth(x) for x in tre.traverse() if x.is_leaf())
    pos = {}
    for node in tre.traverse("postorder"):
        if node.is_leaf():
            pos[node.idx] = (max_depth, y_of_tip[node.name])
        else:
            ys = [pos[c.idx][1] for c in node.children]
            pos[node.idx] = (depth(node), sum(ys) / len(ys))
    return pos, max_depth, n


def _draw_tree(ax, tre, pos, meta, dated, max_depth, n):
    """Draw the rectangular tree with numbered callouts on clade nodes
    instead of inline text labels. Returns the ordered list of clade
    entries so callers can render a matching right-margin legend.

    Returns: list[dict] with keys number, name, mya, is_dated. Root
    first, then depth-ordered."""
    # Branches
    for node in tre.traverse():
        if node.is_leaf() or len(node.children) < 2:
            continue
        nx, _ = pos[node.idx]
        ys = [pos[c.idx][1] for c in node.children]
        ax.plot([nx, nx], [min(ys), max(ys)], color=EDGE, lw=1.6)
    for node in tre.traverse():
        if node.is_root():
            continue
        px, _ = pos[node.up.idx]
        cx, cy = pos[node.idx]
        ax.plot([px, cx], [cy, cy], color=EDGE, lw=1.6)

    # Collect internal-node clades in traversal order (root down),
    # numbered starting at 1. Only named internal nodes get numbers.
    from src.render import _format_clade_name
    clade_entries: list[dict] = []
    number_for_node: dict[int, int] = {}
    counter = 0
    for node in tre.traverse():
        if node.is_leaf() or not node.name:
            continue
        counter += 1
        info = meta.get(node.name, {})
        mya = info.get("mya")
        clade_entries.append({
            "number": counter,
            "name": _format_clade_name(node.name),
            "mya": mya,
            "is_dated": node.name in dated,
        })
        number_for_node[node.idx] = counter

    # Nodes: leaves keep their inline text (species names), clades get
    # numbered badges. Numbers sit dead-center on the dot in white for
    # perfect readability regardless of clade colour.
    for node in tre.traverse():
        nx, ny = pos[node.idx]
        info = meta.get(node.name, {})
        if node.is_leaf():
            ax.plot(nx, ny, "o", color=LEAF, ms=6, zorder=3)
            common = info.get("common_name")
            sci = info.get("scientific_name") or node.name.replace("_", " ")
            # Wrap long common names so they never overrun the photo
            # column. 42 chars keeps even very compound names within
            # the label band before the photo strip.
            import textwrap as _tw
            if common:
                wrapped_common = "\n".join(_tw.wrap(common, width=42)
                                              or [common])
                ax.text(nx + 0.18, ny - 0.08, wrapped_common,
                         color=TIP_TEXT, fontsize=9.5,
                         va="center", wrap=True)
                # Scientific name as small italic underneath.
                ax.text(nx + 0.18, ny + 0.24, f"({sci})",
                         color=TIP_TEXT, fontsize=8,
                         va="center", style="italic", alpha=0.75)
            else:
                wrapped_sci = "\n".join(_tw.wrap(sci, width=42) or [sci])
                ax.text(nx + 0.18, ny, wrapped_sci,
                         color=TIP_TEXT, fontsize=9.5,
                         va="center", style="italic")
            continue
        num = number_for_node.get(node.idx)
        if node.name in dated:
            ax.plot(nx, ny, "o", color=DATED, ms=12, zorder=3)
        elif node.name:
            ax.plot(nx, ny, "o", color=PLAIN, ms=10, zorder=3)
        else:
            ax.plot(nx, ny, "o", color=PLAIN, ms=4, zorder=3)
        if num is not None:
            ax.text(nx, ny, str(num), color="#0e1b1a",
                    fontsize=6.5, ha="center", va="center",
                    weight="bold", zorder=4)

    ax.set_xlim(-0.6, max_depth + 6)
    ax.set_ylim(n - 0.5, -0.5)
    ax.set_facecolor(BG)
    ax.axis("off")
    return clade_entries


def _draw_clade_legend(fig, clade_entries, left=0.905, width=0.09,
                        bottom=0.10, height=0.80):
    """Render the numbered clade legend column on the right margin.
    Never overlaps the tree because it lives in its own axes."""
    if not clade_entries:
        return
    ax = fig.add_axes([left, bottom, width, height])
    ax.set_facecolor(BG)
    ax.axis("off")
    ax.text(0, 1.0, "Clades",
            color=LABEL, fontsize=10, weight="bold",
            transform=ax.transAxes, va="top")
    # Wrap: fit up to N entries evenly in the column height. Font
    # scales down if there are many.
    n_entries = len(clade_entries)
    row_pitch = 0.94 / max(n_entries, 1)
    fs = max(5.5, min(8, 100 / max(n_entries, 1) * 0.06))
    for i, e in enumerate(clade_entries):
        y = 0.96 - i * row_pitch
        # Colored dot
        color = DATED if e["is_dated"] else PLAIN
        ax.text(0, y, str(e["number"]),
                 color="#0e1b1a", fontsize=fs, weight="bold",
                 bbox=dict(boxstyle="circle,pad=0.15",
                           fc=color, ec="none"),
                 va="center", transform=ax.transAxes)
        # Name + mya
        label = e["name"]
        if e["mya"] is not None:
            label += f", {e['mya']}"
        ax.text(0.13, y, label,
                 color=TIP_TEXT, fontsize=fs,
                 va="center", transform=ax.transAxes)


def draw_header(fig, tree_name):
    """Project mark + 2-line slogan top-left, per-tree title top-center.
    Mirrors the unrooted SVG header band so the rectangular T1 output
    feels polished and consistent with T0/T2."""
    from src import tree_settings
    fig.text(0.02, 0.985, tree_settings.PROJECT_MARK, color=LABEL,
             fontsize=13, weight="bold", ha="left", va="top",
             family="serif")
    slogan = tree_settings.PROJECT_SLOGAN
    words = slogan.split()
    target = len(slogan) // 2
    running, split_at = 0, 1
    for i, w in enumerate(words):
        running += len(w) + 1
        if running >= target:
            split_at = i + 1
            break
    line1 = " ".join(words[:split_at])
    line2 = " ".join(words[split_at:])
    fig.text(0.02, 0.965, line1, color=TIP_TEXT,
             fontsize=8, ha="left", va="top", alpha=0.62, style="italic")
    fig.text(0.02, 0.948, line2, color=TIP_TEXT,
             fontsize=8, ha="left", va="top", alpha=0.62, style="italic")
    fig.text(0.50, 0.985, tree_settings.title_for(tree_name),
             color=TIP_TEXT, fontsize=14, ha="center", va="top",
             style="italic")



def _draw_legend(fig):
    """Bottom-RIGHT legend for T1. Stacks upward from bottom:
    row 0 (bottom-most): credit strip (added by composite_credits)
    row 1: mya footnote
    row 2: legend rows (3)
    Nothing collides because each layer has its own reserved y band."""
    # Legend axes sit ABOVE the credit strip zone (which uses y<0.04)
    # so they can never collide.
    legend_ax = fig.add_axes([0.45, 0.048, 0.52, 0.048])
    legend_ax.set_facecolor("#13211f")
    legend_ax.axis("off")
    rows = [
        (LEAF, 6, "Common Name", "(Scientific name)",
         "— a species (green tip)"),
        (DATED, 9, "Clade, ###", "",
         "— ancestral node with a known divergence age (amber)"),
        (PLAIN, 5, "Clade", "",
         "— ancestral node, divergence age not added (teal)"),
    ]
    y_positions = [0.86, 0.51, 0.16]
    for (color, size, bold, italic, rest), y in zip(rows, y_positions):
        text = bold
        if italic:
            text += f"  $\\it{{{italic}}}$"
        text += f"  {rest}"
        legend_ax.text(
            0.965, y, text, color="#e8f3ef",
            fontsize=8, va="center", ha="right",
            transform=legend_ax.transAxes)
        legend_ax.scatter(
            [0.985], [y], s=size**2, c=color,
            zorder=3, transform=legend_ax.transAxes)
    # mya footnote — sits between the legend and the credit strip.
    fig.text(
        0.98, 0.038,
        "numbers are millions of years (mya) since the last common ancestor",
        color="#9ab3ab", fontsize=7, ha="right", va="bottom",
        style="italic")



def build_image_tree(tree_name: str, out_dir: Path | None = None) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.image as mpimg
    from src import render, species_profile

    out_dir = out_dir or config.OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    from src.tree import _safe as _safe_stem
    stem = _safe_stem(tree_name).lower()

    meta_path = config.OUTPUT_DIR / f"{stem}_nodes.json"
    nwk_path = config.OUTPUT_DIR / f"{stem}_named_tree.nwk"
    if not (meta_path.exists() and nwk_path.exists()):
        raise FileNotFoundError(f"Build {tree_name} first.")
    meta = render.load_meta(meta_path)
    dated = {k for k, v in meta.items()
             if not v.get("is_leaf") and v.get("mya") is not None}

    import toytree
    nwk_str = render._collapse_unary(nwk_path, dated)
    tre = toytree.tree(nwk_str)
    pos, max_depth, n = _layout(tre)
    tips = list(tre.get_tip_labels())

    print(f"fetching photos for {n} tips ...")
    profiles_by_tip = {}
    for tip in tips:
        info = meta.get(tip, {})
        sci = info.get("scientific_name") or tip.replace("_", " ")
        common = info.get("common_name")
        try:
            p = species_profile.find_profile(sci, common)
        except Exception as exc:
            p = None
            print(f"  err {sci}: {exc}")
        profiles_by_tip[tip] = p
        print(f"  {sci:30} -> {'OK' if (p and p.get('image_path')) else '-'}")

    fig_w = 14
    fig_h = max(8, 1.05 * n + 2.0)
    fig = plt.figure(figsize=(fig_w, fig_h), facecolor=BG)
    draw_header(fig, tree_name)

    # Wide tree column, tight square photo immediately after it, attribution
    # filling the rest of the row. No internal margins around the photo.
    ax_tree = fig.add_axes([0.02, 0.05, 0.58, 0.88])
    _draw_tree(ax_tree, tre, pos, meta, dated, max_depth, n)

    top, bot = 0.07, 0.05
    row_h = (1 - top - bot) / n
    photo_left = 0.62
    photo_h_in = row_h * 0.92 * fig_h
    photo_w_frac = min(0.18, photo_h_in / fig_w)
    attr_left = photo_left + photo_w_frac + 0.012

    for i, tip in enumerate(tips):
        y_bottom = 1 - top - (i + 1) * row_h
        h = row_h * 0.92
        ax = fig.add_axes([photo_left, y_bottom + (row_h - h) / 2,
                           photo_w_frac, h])
        ax.set_facecolor(BG)
        p = profiles_by_tip.get(tip)
        if p and p.get("image_path"):
            try:
                img = mpimg.imread(p["image_path"])
                h_img, w_img = img.shape[:2]
                side = min(h_img, w_img)
                y0 = (h_img - side) // 2
                x0 = (w_img - side) // 2
                img = img[y0:y0 + side, x0:x0 + side]
                ax.imshow(img, aspect="equal")
                ax.set_xlim(0, side)
                ax.set_ylim(side, 0)
                attr_raw = (p.get("image_attribution") or "")
                if attr_raw:
                    import textwrap as _tw
                    wrapped = "\n".join(
                        _tw.wrap(attr_raw, width=68, max_lines=3,
                                 placeholder="…"))
                    fig.text(attr_left, y_bottom + row_h / 2,
                             wrapped, color="#9ab3ab", fontsize=7,
                             ha="left", va="center", linespacing=1.35)
            except Exception:
                ax.text(0.5, 0.5, "image failed to load", ha="center",
                        va="center", color="#5b6e69", fontsize=9,
                        transform=ax.transAxes)
        else:
            ax.text(0.5, 0.5, "no photo available", ha="center", va="center",
                    color="#5b6e69", fontsize=9, transform=ax.transAxes)
        ax.set_xticks([])
        ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_visible(False)

    fig.text(0.5, 0.012,
             "CC BY-SA Maya · Shared Rivers · {r}Evolving Kinship",
             color="#6b7d76", fontsize=8, ha="center", va="bottom",
             family="Helvetica")
    out = out_dir / f"{stem}_photo_tree.png"
    fig.savefig(str(out), facecolor=BG, dpi=130)
    plt.close(fig)
    usage_log.log_event("build_photo_tree", tree_name)
    print(f"wrote {out.name}")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('usage: python -m src.image_tree "Tree Name"')
        raise SystemExit(1)
    build_image_tree(sys.argv[1])
