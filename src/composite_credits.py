"""
Shared helper: minimal credit footer for composite images.

Every composite (T1, T2, spec blend, range maps) gets a small
bottom-right footer with per-species photo + audio attributions,
formatted as a footnote strip. Reuses format_credit() from credits.py
so the tone matches everywhere.
"""

from __future__ import annotations


def collect_credits(tree_name: str) -> list[str]:
    """Return a list of short 'Species: (c) Author, LICENSE' strings
    for every species in the tree that has any credit."""
    from src import db, species_profile, species_audio, credits
    df = db.read_tree(tree_name)
    lines: list[str] = []
    if df.empty:
        return lines
    for _, row in df.iterrows():
        sci = row.get("scientific_name")
        if not isinstance(sci, str) or not sci.strip():
            continue
        common = row.get("common_name") if isinstance(
            row.get("common_name"), str) else None
        label = common or sci
        try:
            prof = species_profile.find_profile(sci, common)
        except Exception:
            prof = None
        if prof and prof.get("image_attribution"):
            lines.append(f"{label} photo: "
                          f"{credits.format_credit(prof['image_attribution'], markdown=False)}")
        try:
            rec = species_audio.find_recording(sci, common)
        except Exception:
            rec = None
        if rec and rec.get("attribution"):
            lines.append(f"{label} audio: "
                          f"{credits.format_credit(rec['attribution'], markdown=False)}")
    return lines


def draw_pil_credit_strip(image, tree_name: str,
                          text_color=(90, 70, 70),
                          bg_color=(250, 246, 238),
                          max_lines: int = 6):
    """Composite a small footer strip at the bottom-right of a PIL
    image with credit lines. Truncates to max_lines with a '+N more'
    tail. Returns a new image (does not mutate the input)."""
    from PIL import Image, ImageDraw, ImageFont
    lines = collect_credits(tree_name)
    if not lines:
        return image
    shown = lines[:max_lines]
    remainder = len(lines) - len(shown)
    if remainder > 0:
        shown.append(f"+{remainder} more, see credits (.txt)")

    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 8)
    except Exception:
        font = ImageFont.load_default()

    row_h = 11
    pad = 8
    strip_h = row_h * len(shown) + 2 * pad
    strip_w = image.width
    new_img = Image.new(image.mode if image.mode in ("RGB", "RGBA")
                        else "RGB",
                        (strip_w, image.height + strip_h),
                        bg_color if image.mode == "RGB" else bg_color + (255,))
    new_img.paste(image, (0, 0))
    draw = ImageDraw.Draw(new_img)
    for i, line in enumerate(shown):
        # Right-align the text
        y = image.height + pad + i * row_h
        try:
            w = draw.textlength(line, font=font)
        except Exception:
            w = 8 * len(line)
        x = max(pad, strip_w - int(w) - pad)
        draw.text((x, y), line, fill=text_color, font=font)
    return new_img


def draw_matplotlib_credit_strip(fig, tree_name: str,
                                  text_color="#5a4646",
                                  max_lines: int = 6) -> None:
    """Draw a right-aligned credit footnote strip on a matplotlib
    figure. Places it in the bottom-right ~35% of the width with
    tiny italic text so it never encroaches on the main content."""
    lines = collect_credits(tree_name)
    if not lines:
        return
    shown = lines[:max_lines]
    if len(lines) > max_lines:
        shown.append(f"+{len(lines) - max_lines} more, see credits.txt")
    footer = "\n".join(shown)
    fig.text(0.98, 0.01, footer,
              color=text_color, fontsize=5, ha="right",
              va="bottom", style="italic", alpha=0.8)
