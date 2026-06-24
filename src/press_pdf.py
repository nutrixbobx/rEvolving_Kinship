"""
Comprehensive press-kit PDF for a single tree.

Layout (US Letter, portrait):

  Page 1 — unrooted kinship layout (full-page tree image)
  Page 2 — short blurb about THIS tree (template or LLM-generated)
            + the About box for {r}Evolving Kinship + Shared Rivers
            + CC license, donation links, water/energy footprint
  Page 3+ — one species "listening card" per page (or two per page when
            they're compact): photo on the left, common+scientific name,
            short profile summary, audio attribution if a recording exists.

Built on ReportLab. The PNG of the unrooted layout is rendered fresh by
render.render_files if it's not on disk yet, so the PDF is always current
with the latest tree data.
"""

from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

# Letter page dims (points)
PAGE_W, PAGE_H = 612, 792
MARGIN = 36

ACCENT = "#a85a1f"
INK = "#243b34"
MUTED = "#5e6f68"


def _stem(name: str) -> str:
    from src.tree import _safe as _tree_safe
    return _tree_safe(name).lower()


def _ensure_tree_png(tree_name: str) -> Path:
    """Build the unrooted PNG if it doesn't exist yet (used as p1)."""
    from src import render
    stem = _stem(tree_name)
    nwk = config.OUTPUT_DIR / f"{stem}_named_tree.nwk"
    meta_path = config.OUTPUT_DIR / f"{stem}_nodes.json"
    if not (nwk.exists() and meta_path.exists()):
        raise FileNotFoundError(
            f"Build the tree first: {nwk} / {meta_path} missing.")
    meta = render.load_meta(meta_path)
    png_path = config.OUTPUT_DIR / f"{stem}_tree_unrooted.png"
    if not png_path.exists():
        # render_files draws + saves both SVG and PNG to OUTPUT_DIR
        render.render_files(
            nwk, meta, f"{stem}_tree_unrooted",
            layout="unrooted", tree_name=tree_name,
        )
    return png_path


def _tree_blurb(tree_name: str) -> str:
    """Best-effort tree blurb from ai_blurb. Falls back to a template note."""
    try:
        from src import ai_blurb
        b = ai_blurb.blurb_for_tree(tree_name)
        return b.get("text", "")
    except Exception:
        return ""


def _footprint_lines(tree_name: str) -> list[str]:
    """Compact strings describing the build's energy + water footprint."""
    out = []
    try:
        from src import usage_log
        wh = usage_log.tree_total(tree_name)
        if wh > 0:
            ml = usage_log.wh_to_water_ml(wh)
            out.append(f"~{wh:.0f} Wh of electricity "
                       f"({usage_log.relatable(wh)})")
            out.append(f"~{ml:.0f} mL of water "
                       f"({usage_log.water_relatable(wh)})")
    except Exception:
        pass
    return out


def _species_records(tree_name: str) -> list[dict]:
    """Per-species data for the listening cards: name, photo path, summary,
    audio attribution. Falls back gracefully when any piece is missing."""
    from src import db, render
    df = db.read_tree(tree_name)
    if df.empty:
        return []
    records = []
    try:
        from src import species_profile
    except Exception:
        species_profile = None
    try:
        from src import species_audio
    except Exception:
        species_audio = None
    for _, row in df.iterrows():
        sci = row.get("scientific_name")
        if not isinstance(sci, str) or not sci.strip():
            continue
        common = row.get("common_name") if isinstance(
            row.get("common_name"), str) else None
        profile = None
        if species_profile:
            try:
                profile = species_profile.find_profile(sci, common)
            except Exception:
                profile = None
        rec = {
            "scientific": sci.strip(),
            "common": common,
            "summary": (profile or {}).get("summary"),
            "image_path": (profile or {}).get("image_path"),
            "image_attribution": (profile or {}).get("image_attribution"),
            "wikipedia": (profile or {}).get("wikipedia_url"),
            "inaturalist": (profile or {}).get("inaturalist_url"),
            "audio_attribution": None,
        }
        if species_audio:
            try:
                rec_audio = species_audio.find_recording(sci, common)
                if rec_audio:
                    rec["audio_attribution"] = rec_audio.get("attribution")
            except Exception:
                pass
        records.append(rec)
    return records


def build_press_pdf(tree_name: str,
                    out_dir: Path | None = None) -> Path:
    """Generate the multi-page press PDF. Returns the file path."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
    from reportlab.platypus import (
        SimpleDocTemplate, Image, Paragraph, Spacer, PageBreak,
        KeepTogether, Table, TableStyle,
    )
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    # Register a Unicode-capable font so non-Latin species names (Devanagari,
    # Armenian, Han, Arabic, etc.) render in the PDF. Falls back to
    # Helvetica silently if no Unicode font is on the filesystem.
    _BASE_FONT = "Helvetica"
    _BODY_FONT = "Helvetica"
    _ITALIC_FONT = "Helvetica-Oblique"
    for _fontfile in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ):
        if Path(_fontfile).exists():
            try:
                pdfmetrics.registerFont(TTFont("KinshipSans", _fontfile))
                # Look for matching italic
                _italic = _fontfile.replace(
                    "DejaVuSans.ttf", "DejaVuSans-Oblique.ttf")
                if Path(_italic).exists() and _italic != _fontfile:
                    pdfmetrics.registerFont(
                        TTFont("KinshipSans-Italic", _italic))
                    _ITALIC_FONT = "KinshipSans-Italic"
                else:
                    _ITALIC_FONT = "KinshipSans"
                _BODY_FONT = "KinshipSans"
                _BASE_FONT = "KinshipSans"
                break
            except Exception:
                continue

    out_dir = out_dir or config.OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = _stem(tree_name)
    out_path = out_dir / f"{stem}_press_kit.pdf"

    styles = getSampleStyleSheet()
    h_title = ParagraphStyle(
        "h_title", parent=styles["Title"], fontName=_BASE_FONT, fontSize=22,
        textColor=colors.HexColor(ACCENT), spaceAfter=4, alignment=TA_CENTER,
        leading=26)
    h_slogan = ParagraphStyle(
        "h_slogan", parent=styles["Normal"], fontSize=10,
        textColor=colors.HexColor(MUTED), fontName=_ITALIC_FONT,
        spaceAfter=12, alignment=TA_CENTER, leading=13)
    h_sec = ParagraphStyle(
        "h_sec", parent=styles["Heading2"], fontName=_BASE_FONT, fontSize=14,
        textColor=colors.HexColor(INK), spaceAfter=8, spaceBefore=10)
    h_body = ParagraphStyle(
        "h_body", parent=styles["Normal"], fontName=_BODY_FONT, fontSize=10.5,
        textColor=colors.HexColor(INK), leading=15, alignment=TA_JUSTIFY)
    h_caption = ParagraphStyle(
        "h_caption", parent=styles["Normal"], fontName=_BODY_FONT, fontSize=8,
        textColor=colors.HexColor(MUTED), leading=11, alignment=TA_LEFT)
    h_species_name = ParagraphStyle(
        "h_species", parent=styles["Heading3"], fontName=_BASE_FONT, fontSize=13,
        textColor=colors.HexColor(INK), spaceAfter=2)
    h_sci_name = ParagraphStyle(
        "h_sci", parent=styles["Normal"], fontSize=10,
        textColor=colors.HexColor(MUTED), fontName=_ITALIC_FONT,
        spaceAfter=6)

    story = []

    # ---- Page 1: title + the unrooted tree image ----
    from src import tree_settings
    title_text = tree_settings.title_for(tree_name)
    story.append(Paragraph(tree_settings.PROJECT_MARK, h_title))
    story.append(Paragraph(tree_settings.PROJECT_SLOGAN, h_slogan))
    story.append(Paragraph(title_text, h_sec))
    try:
        png_path = _ensure_tree_png(tree_name)
        # Scale the tree to fit ~6.5 x 7.5 inch area
        max_w = (PAGE_W - 2 * MARGIN)
        max_h = (PAGE_H - 2 * MARGIN - 100)  # leave room for title+slogan
        img = Image(str(png_path), width=max_w, height=max_h,
                     kind="proportional")
        story.append(img)
    except Exception as exc:
        story.append(Paragraph(
            f"<i>Tree image unavailable: {exc}</i>", h_caption))
    story.append(PageBreak())

    # ---- Page 2: the sound kinship tree (auto-built if missing) ----
    sound_png = config.OUTPUT_DIR / f"{stem}_sound_tree.png"
    if not sound_png.exists():
        # Try to build it now. Skip silently if the chorus / recordings
        # aren't available — the PDF still has the species cards.
        try:
            from src import spectrogram_tree
            spectrogram_tree.build_sound_tree(tree_name)
        except Exception as exc:
            print(f"sound tree build failed during PDF: {exc}")
    if sound_png.exists() and sound_png.stat().st_size > 0:
        story.append(Paragraph(
            f"{title_text} — sound kinship", h_sec))
        story.append(Paragraph(
            "The same tree, with each species' actual recorded voice "
            "shown as a spectrogram at its tip. Branch lengths read "
            "as deep-time silences; spectrograms read as the texture of "
            "each lineage's voice.", h_body))
        story.append(Spacer(1, 8))
        try:
            max_w = (PAGE_W - 2 * MARGIN)
            max_h = (PAGE_H - 2 * MARGIN - 120)
            story.append(Image(str(sound_png),
                                width=max_w, height=max_h,
                                kind="proportional"))
        except Exception as exc:
            print(f"sound-tree Image embed failed: {exc}")
            story.append(Paragraph(
                f"<i>Could not embed sound-kinship tree: {exc}</i>",
                h_caption))
        story.append(PageBreak())

    # ---- Page 3: blurb + about + footprint + license ----
    story.append(Paragraph(title_text, h_sec))
    blurb = _tree_blurb(tree_name)
    if blurb:
        # Replace newlines with paragraph breaks
        for para in blurb.split("\n\n"):
            story.append(Paragraph(para.replace("\n", "<br/>"), h_body))
            story.append(Spacer(1, 6))
    else:
        story.append(Paragraph(
            "A tree of the kin in this gathering, drawn on the deep-time "
            "scaffold of the NCBI taxonomy and the dated nodes from "
            "TimeTree of Life.", h_body))

    story.append(Spacer(1, 14))
    story.append(Paragraph("About {r}Evolving Kinship", h_sec))
    story.append(Paragraph(
        "{r}Evolving Kinship is a participatory ecological art piece by "
        "Maya, of Shared Rivers. Visitors name a species they feel kin "
        "to; the piece places that species in the tree of life, redraws "
        "the tree with the visitor's kin inside it, and sounds the "
        "deep-time distances back as a microtonal chord. Each finished "
        "tree carries a photo, a short profile, and the species' actual "
        "recorded voice, so the kinship is felt across every sense the "
        "gallery has.", h_body))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Shared Rivers is the global confluence lab Maya works through, "
        "gathering artists and ecologists and educators around the idea "
        "that waterways are not borders or resources but living "
        "connectors. The lab convenes events that braid art, ecology, "
        "music, gastronomy, and education into one room.", h_body))

    fp = _footprint_lines(tree_name)
    if fp:
        story.append(Spacer(1, 10))
        story.append(Paragraph("Footprint of this build", h_sec))
        for line in fp:
            story.append(Paragraph("• " + line, h_body))

    story.append(Spacer(1, 12))
    story.append(Paragraph("License + support", h_sec))
    story.append(Paragraph(
        'This pipeline and its outputs are released under '
        '<a href="https://creativecommons.org/licenses/by-sa/4.0/">'
        '<font color="#a85a1f">CC BY-SA 4.0</font></a>. '
        'More about Shared Rivers at '
        '<a href="https://shared-rivers.org">'
        '<font color="#a85a1f">shared-rivers.org</font></a>. Support our '
        'work via <a href="https://buymeacoffee.com/shared.rivers">'
        '<font color="#a85a1f">buy me a coffee</font></a> or a '
        'tax-deductible donation at '
        '<a href="https://fundraising.fracturedatlas.org/shared-rivers-confluences">'
        '<font color="#a85a1f">Fractured Atlas</font></a>.', h_body))
    story.append(PageBreak())

    # ---- Page 3+: listening cards (one species per row, ~3-4 per page) ----
    records = _species_records(tree_name)
    if records:
        story.append(Paragraph("Listening cards", h_sec))
        story.append(Paragraph(
            "One row per species. Photo and audio credits ride along with "
            "every recording — every image and every sound has the "
            "contributor and license preserved.", h_caption))
        story.append(Spacer(1, 10))
        for rec in records:
            block = []
            # Heading
            head = (f"{rec['common']} " if rec['common']
                    else "")
            block.append(Paragraph(head or rec['scientific'],
                                     h_species_name))
            block.append(Paragraph(
                f"<i>{rec['scientific']}</i>", h_sci_name))
            # Two-column: photo on left, summary + attribution on right.
            left_cell = ""
            if rec.get("image_path") and Path(rec["image_path"]).exists():
                try:
                    left_cell = Image(rec["image_path"], width=1.4*inch,
                                        height=1.4*inch, kind="proportional")
                except Exception:
                    left_cell = ""
            summ = rec.get("summary") or "(no summary on file)"
            if len(summ) > 600:
                summ = summ[:600] + "…"
            right_bits = [Paragraph(summ, h_body)]
            if rec.get("image_attribution"):
                right_bits.append(Spacer(1, 4))
                right_bits.append(Paragraph(
                    f"Photo: {rec['image_attribution'][:120]}", h_caption))
            if rec.get("audio_attribution"):
                right_bits.append(Paragraph(
                    f"Audio: {rec['audio_attribution'][:120]}", h_caption))
            links = []
            if rec.get("wikipedia"):
                links.append(
                    f'<a href="{rec["wikipedia"]}">Wikipedia</a>')
            if rec.get("inaturalist"):
                links.append(
                    f'<a href="{rec["inaturalist"]}">iNaturalist</a>')
            if links:
                right_bits.append(Paragraph(" · ".join(links), h_caption))
            tbl = Table(
                [[left_cell or "", right_bits]],
                colWidths=[1.5*inch, (PAGE_W - 2*MARGIN) - 1.5*inch - 8],
            )
            tbl.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            block.append(tbl)
            block.append(Spacer(1, 10))
            story.append(KeepTogether(block))

    doc = SimpleDocTemplate(
        str(out_path), pagesize=letter,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
        title=f"{tree_settings.PROJECT_MARK} — {title_text}",
        author="Maya (Shared Rivers)",
        subject="Press kit",
    )
    doc.build(story)
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m src.press_pdf '<tree name>'")
        sys.exit(1)
    p = build_press_pdf(sys.argv[1])
    print(f"wrote {p}")
