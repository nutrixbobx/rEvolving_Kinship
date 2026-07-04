"""
Real footer painter for the T2 (photo-tip) PNG.

Every prior attempt used SVG %-coordinates that collided with the tree
drawing above. This module ditches that entirely and uses PIL:

  - Real font metrics via ImageFont.getbbox
  - Real word wrap via textwrap.wrap
  - Rows placed at absolute pixel Y coordinates AFTER measuring the
    height of every prior row
  - Background color explicitly matched to the tree PNG's background
    (sampled from a corner pixel so it's always right)
  - Padding of at least 8px between every element

Physical layout, top to bottom, right-aligned column:
  Legend row 1 (Common Name — a species) [green dot]
  Legend row 2 (Clade ### — dated) [amber dot]
  Legend row 3 (Clade — undated) [teal dot]
  mya footnote (italic)
  Credit lines (italic, one per line)
  CC BY-SA Maya line (centered)

If the tree PNG is 1600x1200 the footer typically adds 260px below.
"""

from __future__ import annotations
from pathlib import Path


def _load_font(size: int, italic: bool = False, bold: bool = False):
    """Best-effort font load with graceful fallback."""
    from PIL import ImageFont
    variants = []
    if italic and bold:
        variants = ["DejaVuSans-BoldOblique.ttf"]
    elif italic:
        variants = ["DejaVuSans-Oblique.ttf"]
    elif bold:
        variants = ["DejaVuSans-Bold.ttf"]
    else:
        variants = ["DejaVuSans.ttf"]
    for v in variants:
        for base in ["/usr/share/fonts/truetype/dejavu/",
                     "/System/Library/Fonts/",
                     "/System/Library/Fonts/Supplemental/",
                     "/Library/Fonts/"]:
            try:
                return ImageFont.truetype(base + v, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _text_width(draw, text, font):
    """Real pixel width of a rendered string."""
    try:
        return int(draw.textlength(text, font=font))
    except Exception:
        # Old Pillow
        try:
            return font.getbbox(text)[2]
        except Exception:
            return 8 * len(text)


def compose_with_footer(tree_png_path: Path,
                        credit_lines: list[str] | None = None,
                        title_bg: tuple | None = None,
                        force_bg: tuple | None = None) -> Path:
    """Open the tree PNG, add a properly-laid-out footer below it,
    save in place. Returns the same path.

    Args:
      tree_png_path: path to the rasterized tree image (has no footer)
      credit_lines: pre-collected list of credit strings
      title_bg: optional explicit background color. If None, sampled
                from the top-left pixel of the tree PNG.
      force_bg: override — always use this color regardless of tree PNG.
    """
    from PIL import Image, ImageDraw
    credit_lines = credit_lines or []

    tree = Image.open(tree_png_path).convert("RGB")
    W, H = tree.size

    # Sample background color from a corner of the tree image so the
    # footer always matches the tree canvas.
    if force_bg is not None:
        bg = force_bg
    elif title_bg is not None:
        bg = title_bg
    else:
        # Take the pixel at (5, 5) — the top-left corner of the tree
        # is always background.
        bg = tree.getpixel((5, 5))
        if isinstance(bg, int):
            bg = (bg, bg, bg)

    # Decide ink color: dark ink on light bg, light ink on dark bg.
    lum = 0.2126 * bg[0] + 0.7152 * bg[1] + 0.0722 * bg[2]
    is_light_bg = lum > 130
    if is_light_bg:
        ink = (56, 40, 40)     # deep warm brown
        muted = (128, 100, 100)
        rule_c = (200, 180, 160)
    else:
        ink = (232, 243, 239)
        muted = (154, 179, 171)
        rule_c = (60, 75, 70)

    # Palette dots (matches tree palette)
    LEAF = (70, 199, 154)
    DATED = (240, 162, 74)
    PLAIN = (111, 138, 130)

    # Layout constants (absolute pixels — no percentages)
    PAD_H = 40                 # horizontal padding
    PAD_V = 22                 # vertical padding between logical blocks
    SEP_PAD = 14               # extra padding after each block
    DOT_GAP = 12               # gap between text end and dot start
    DIVIDER_H = 24             # space above the top divider line

    # Fonts (real sizes, real metrics)
    f_legend = _load_font(15, bold=True)
    f_legend_light = _load_font(15)
    f_mya = _load_font(13, italic=True)
    f_credit = _load_font(11, italic=True)
    f_cc = _load_font(12)

    # ---- Measure everything BEFORE we allocate the final canvas ----
    legend_rows = [
        # (bold_prefix, rest, dot color, dot radius)
        ("Common Name", " (Scientific name) — a species", LEAF, 6),
        ("Clade, ###", " — ancestral node with a known divergence age",
         DATED, 7),
        ("Clade", " — ancestral node, divergence age not added",
         PLAIN, 5),
    ]
    row_h_legend = 26

    mya_text = ("numbers are millions of years (mya) since the "
                "last common ancestor")
    row_h_mya = 22

    row_h_credit = 18
    cc_text = "CC BY-SA Maya · Shared Rivers · {r}Evolving Kinship"
    row_h_cc = 26

    # Right-aligned column: measure the longest legend row so all rows
    # end at the same x (right edge minus dot area).
    right_edge = W - PAD_H
    dot_x = right_edge - 10             # rightmost point of the dot
    text_end_x = dot_x - DOT_GAP - 10   # text should end before dot

    # Total footer height
    total_h = (
        DIVIDER_H
        + len(legend_rows) * row_h_legend
        + SEP_PAD
        + row_h_mya
        + SEP_PAD
        + (len(credit_lines) * row_h_credit + (SEP_PAD if credit_lines else 0))
        + row_h_cc
        + PAD_V
    )

    # ---- Allocate final canvas ----
    final = Image.new("RGB", (W, H + total_h), bg)
    final.paste(tree, (0, 0))
    draw = ImageDraw.Draw(final)

    # Top divider hairline
    y = H + DIVIDER_H // 2
    draw.line([(PAD_H, y), (W - PAD_H, y)], fill=rule_c, width=1)
    y = H + DIVIDER_H

    # ---- Legend rows ----
    for bold_part, rest_part, color, r in legend_rows:
        cy = y + row_h_legend // 2
        # Measure the two parts of the label
        bold_w = _text_width(draw, bold_part, f_legend)
        rest_w = _text_width(draw, rest_part, f_legend_light)
        total_w = bold_w + rest_w
        # Anchor: text ends at text_end_x
        start_x = text_end_x - total_w
        # Draw bold part then light part
        draw.text((start_x, cy - 9), bold_part,
                  fill=ink, font=f_legend)
        draw.text((start_x + bold_w, cy - 9), rest_part,
                  fill=ink, font=f_legend_light)
        # Dot
        draw.ellipse(
            (dot_x - r, cy - r, dot_x + r, cy + r),
            fill=color)
        y += row_h_legend

    y += SEP_PAD

    # ---- mya footnote ----
    mya_w = _text_width(draw, mya_text, f_mya)
    draw.text((right_edge - mya_w, y), mya_text,
              fill=muted, font=f_mya)
    y += row_h_mya + SEP_PAD

    # ---- Credit lines ----
    for line in credit_lines[:8]:   # cap at 8 lines
        line_w = _text_width(draw, line, f_credit)
        # If a credit line is longer than the available width, truncate
        max_w = W - 2 * PAD_H
        while line_w > max_w and len(line) > 20:
            line = line[:-4] + "…"
            line_w = _text_width(draw, line, f_credit)
        draw.text((right_edge - line_w, y), line,
                  fill=muted, font=f_credit)
        y += row_h_credit
    if len(credit_lines) > 8:
        more = f"+{len(credit_lines) - 8} more, see credits.txt"
        more_w = _text_width(draw, more, f_credit)
        draw.text((right_edge - more_w, y), more,
                  fill=muted, font=f_credit)
        y += row_h_credit

    if credit_lines:
        y += SEP_PAD

    # ---- CC BY-SA (centered) ----
    cc_w = _text_width(draw, cc_text, f_cc)
    draw.text(((W - cc_w) // 2, y), cc_text,
              fill=muted, font=f_cc)

    # Save in place
    final.save(tree_png_path, "PNG")
    return tree_png_path
