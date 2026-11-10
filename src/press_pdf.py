"""
Personalized kinship report (PDF) for a single tree.

Layout (US Letter, portrait):

  Page 1 — unrooted kinship layout (full-page tree image)
  Page 2 — short blurb about THIS tree (template or LLM-generated)
            + the About box for {r}Evolving Kinship + Shared Rivers
            + CC license, donation links, water/energy footprint
  Page 3+ — one species "kin card" per page (or two per page when
            they're compact): photo on the left, common+scientific name,
            short profile summary, audio attribution if a recording exists.

Built on ReportLab. The PNG of the unrooted layout is rendered fresh by
render.render_files if it's not on disk yet, so the PDF is always current
with the latest tree data.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
from src.credits import format_credit_html, aggregate_tree_credits

# Letter page dims (points)
PAGE_W, PAGE_H = 612, 792
MARGIN = 36

ACCENT = "#a85a1f"
INK = "#243b34"
MUTED = "#5e6f68"




# ---------------------------------------------------------------------------
# Multi-font Unicode handling
# ---------------------------------------------------------------------------
# System font directories, kept because a self-hosted run may well have
# them. They are no longer relied on: packages.txt installs nothing now.
_NOTO_DIR = "/usr/share/fonts/truetype/noto"
_NOTO_CJK_DIR = "/usr/share/fonts/opentype/noto"
_DEJAVU_DIR = "/usr/share/fonts/truetype/dejavu"

# Where to look for fonts, best first. The bundled folder leads because
# it is the only one guaranteed to exist: packages.txt no longer apt-installs
# anything, so on Streamlit Cloud /usr/share/fonts/.../noto is mostly empty
# and the old hardcoded paths all missed. A miss used to leave the base font
# as Helvetica, which is why even a Latin name like "kasturi" with macrons
# came out as boxes.
_BUNDLED_FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
_FONT_SEARCH_DIRS = [
    _BUNDLED_FONT_DIR,
    Path(_NOTO_DIR),
    Path(_NOTO_CJK_DIR),
    Path("/usr/share/fonts/truetype/noto"),
    Path("/usr/share/fonts/opentype/noto"),
    Path(_DEJAVU_DIR),
    Path("/usr/share/fonts/truetype/google-fonts"),
]
# Fonts that cover a lot but draw badly as body text, or that we only ever
# want as a last resort for a script nothing else has.
_FONT_SKIP = ("Mono", "Emoji", "Symbols", "Bold", "Italic", "Oblique")


def _font_coverage(path: Path) -> set:
    """The set of code points a font file actually draws, read from its
    cmap. Replaces guessing by Unicode block: a font either has the glyph
    or it doesn't, and that is a question the file can answer."""
    try:
        from fontTools.ttLib import TTFont as _FTFont, TTCollection
        covered: set = set()
        if path.suffix.lower() == ".ttc":
            coll = TTCollection(str(path), lazy=True)
            faces = list(coll.fonts)[:1]
        else:
            faces = [_FTFont(str(path), lazy=True, fontNumber=0)]
        for face in faces:
            for table in face["cmap"].tables:
                covered |= set(table.cmap.keys())
            face.close()
        return covered
    except Exception as exc:
        print(f"font coverage {path.name}: {exc}")
        return set()


@lru_cache(maxsize=1)
def _discover_fonts() -> list:
    """Every usable font on this machine, as (name, path, covered_cps),
    ordered so the preferred body font comes first. Cached: reading cmaps
    costs a few hundred milliseconds and the answer never changes within
    a run."""
    found = []
    seen_names = set()
    for d in _FONT_SEARCH_DIRS:
        try:
            if not d.is_dir():
                continue
            files = sorted(list(d.glob("*.ttf")) + list(d.glob("*.otf"))
                           + list(d.glob("*.ttc")))
        except Exception:
            continue
        for p in files:
            if any(s in p.stem for s in _FONT_SKIP):
                continue
            if p.stem in seen_names:
                continue
            cov = _font_coverage(p)
            if not cov:
                continue
            seen_names.add(p.stem)
            found.append((f"Kin-{p.stem}", p, cov))
    # NotoSans first when present: it is the house face and covers Latin,
    # Greek and Cyrillic, so most text stays in one font.
    found.sort(key=lambda t: (0 if t[1].stem == "NotoSans-Regular"
                              else 1 if t[1].stem.startswith("NotoSans")
                              else 2, t[1].stem))
    return found


@lru_cache(maxsize=1)
def _register_unicode_fonts() -> tuple[dict, str, str]:
    """Register every font we found with ReportLab. Returns:
      ({code_point: registered_font_name}, base_font, italic_font)
    The map is built per code point from real glyph coverage, so a script
    is handled the moment a font covering it lands in assets/fonts, with
    no range table to update."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    fonts = _discover_fonts()
    registered: dict = {}
    base = "Helvetica"
    italic = "Helvetica-Oblique"
    live = []
    for font_name, path, cov in fonts:
        try:
            if path.suffix.lower() == ".ttc":
                pdfmetrics.registerFont(
                    TTFont(font_name, str(path), subfontIndex=0))
            else:
                pdfmetrics.registerFont(TTFont(font_name, str(path)))
        except Exception as exc:
            # ReportLab cannot embed CFF/PostScript outlines, which is what
            # the Noto CJK .ttc collections use. Expected, not a fault.
            if "postscript outlines" not in str(exc).lower():
                print(f"register {font_name} from {path}: {exc}")
            continue
        live.append((font_name, path, cov))
        # First registered font that draws plain ASCII becomes the body
        # face, with its italic cut if the file is next to it.
        if base == "Helvetica" and ord("A") in cov and ord("ū") in cov:
            base = font_name
            ital_p = path.with_name(
                path.name.replace("-Regular", "-Italic"))
            if ital_p.exists() and ital_p != path:
                try:
                    pdfmetrics.registerFont(
                        TTFont(f"{font_name}-Italic", str(ital_p)))
                    italic = f"{font_name}-Italic"
                except Exception:
                    italic = font_name
            else:
                italic = font_name
    # Flatten to code point -> font, first font winning, so the body face
    # keeps everything it can draw and the rest fills the gaps.
    for font_name, _path, cov in live:
        for cp in cov:
            if cp not in registered:
                registered[cp] = font_name
    if not live:
        print("press_pdf: no TrueType font found, falling back to "
              "Helvetica (non-Latin text will not draw)")
    return registered, base, italic


def missing_script_report(text: str) -> list:
    """Characters in `text` that no installed font can draw, so a caller
    can say which script needs a font file instead of shipping boxes
    silently."""
    registered, _b, _i = _register_unicode_fonts()
    gaps = []
    for ch in dict.fromkeys(text or ""):
        if ch.isspace():
            continue
        if ord(ch) not in registered:
            gaps.append(ch)
    return gaps


def _font_for_codepoint(cp: int, registered: dict) -> str | None:
    """Pick the registered font that covers this code point."""
    return registered.get(cp)


def _tag_runs(text: str, registered: dict, default_font: str) -> str:
    """Wrap runs of characters in <font name="..."> tags so ReportLab
    uses the right script font for each block. ReportLab's Paragraph
    interprets <font> tags inside the text."""
    if not text or not registered:
        return text or ""
    out = []
    current = default_font
    buf = []
    for ch in text:
        cp = ord(ch)
        font = _font_for_codepoint(cp, registered) or default_font
        if font != current:
            if buf:
                if current == default_font:
                    out.append("".join(buf))
                else:
                    out.append(
                        f'<font name="{current}">{"".join(buf)}</font>')
                buf = []
            current = font
        buf.append(ch)
    if buf:
        if current == default_font:
            out.append("".join(buf))
        else:
            out.append(f'<font name="{current}">{"".join(buf)}</font>')
    return "".join(out)




def _safe_pdf_url(url: str | None) -> str:
    """URL-encode unsafe chars before embedding the url in a Paragraph's
    <a href="..."> tag. ReportLab is tolerant but spaces are still
    spaces."""
    if not url:
        return ""
    import urllib.parse as _u
    if "://" in url:
        scheme, rest = url.split("://", 1)
        rest = _u.quote(rest, safe="/:?#=&%")
        return f"{scheme}://{rest}"
    return _u.quote(url, safe="/:?#=&%")


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
    if png_path.exists():
        return png_path
    # The SVG rasterizers can be unavailable on a given host (cairosvg
    # needs system cairo). Rather than hand ReportLab a path to a file
    # that was never written, draw the tree with matplotlib instead.
    print("  unrooted PNG missing after render_files; "
          "falling back to the matplotlib tree")
    from src import image_tree
    return image_tree.build_plain_tree_png(tree_name)


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
    """Per-species data for the kin cards: name, photo path, summary,
    audio attribution. Fetches profiles + audio in parallel via a thread
    pool so a 10-species tree finishes in ~3s instead of ~15s cold."""
    from src import db
    from concurrent.futures import ThreadPoolExecutor, as_completed
    df = db.read_tree(tree_name)
    if df.empty:
        return []
    try:
        from src import species_profile
    except Exception:
        species_profile = None
    try:
        from src import species_audio
    except Exception:
        species_audio = None

    tasks = []
    for _, row in df.iterrows():
        sci = row.get("scientific_name")
        if not isinstance(sci, str) or not sci.strip():
            continue
        common = row.get("common_name") if isinstance(
            row.get("common_name"), str) else None
        tasks.append((sci.strip(), common))

    def _one(sci: str, common: str | None) -> dict:
        profile = None
        if species_profile:
            try:
                profile = species_profile.find_profile(sci, common)
            except Exception:
                profile = None
        rec = {
            "scientific": sci,
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
                    rec["audio_path"] = str(rec_audio.get("path") or "")
            except Exception:
                pass
        return rec

    records: list[dict] = []
    # 6 workers is friendly to iNat + XenoCanto rate limits.
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(_one, sci, common): (sci, common)
                    for sci, common in tasks}
        by_sci: dict[str, dict] = {}
        for fut in as_completed(futures):
            try:
                r = fut.result()
                by_sci[r["scientific"]] = r
            except Exception:
                pass
    # Preserve the original tree order
    for sci, _ in tasks:
        if sci in by_sci:
            records.append(by_sci[sci])
    return records




def _render_spectrogram_thumb(audio_path: str) -> Path | None:
    """Render a small matplotlib spectrogram PNG (cached by audio path)
    and return its disk path. None if anything fails. Cached under
    outputs/_spec_cache/."""
    if not audio_path:
        return None
    src = Path(audio_path)
    if not src.exists():
        return None
    cache_dir = config.OUTPUT_DIR / "_spec_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    import hashlib
    key = hashlib.sha1(str(src.resolve()).encode()).hexdigest()[:16]
    out = cache_dir / f"{key}.png"
    if out.exists() and out.stat().st_size > 0:
        return out
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import librosa
        import numpy as np
        y, sr = librosa.load(str(src), sr=None, mono=True, duration=8.0)
        if len(y) == 0:
            return None
        S = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=64,
                                              fmax=sr // 2)
        S_db = librosa.power_to_db(S, ref=np.max)
        fig, ax = plt.subplots(figsize=(3.0, 1.1), dpi=120,
                                  facecolor="#0e1b1a")
        ax.imshow(S_db, aspect="auto", origin="lower", cmap="magma")
        ax.axis("off")
        fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
        fig.savefig(out, dpi=120, facecolor="#0e1b1a",
                     bbox_inches="tight", pad_inches=0.02)
        plt.close(fig)
        return out
    except Exception as exc:
        print(f"  spec failed for {src.name}: {exc}")
        return None



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
    # Register every Noto Sans script font we can find so the PDF
    # renders Devanagari, CJK, Arabic, Hebrew, Tamil, Thai, Armenian,
    # etc. without rendering as boxes. Falls back to Helvetica only
    # if no Unicode font is on the filesystem.
    _SCRIPT_FONTS, _BASE_FONT, _ITALIC_FONT = _register_unicode_fonts()
    _BODY_FONT = _BASE_FONT

    out_dir = out_dir or config.OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = _stem(tree_name)
    out_path = out_dir / f"{stem}_kinship_report.pdf"

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

    # ---- Kick off all sub-builds in parallel ----
    # T2 (photo-tips), T1 (photo-audio), spec blend, and range map
    # each write to their own output file. Running them in a thread
    # pool cuts cold-build time by ~30 seconds vs sequential.
    _sub_stems = {
        "photo_tip": f"{stem}_photo_tips.png",
        "photo_audio": f"{stem}_photo_audio.png",
        "spec_blend": f"{stem}_spectrogram_blend.png",
        "range_map": f"{stem}_range_map.png",
    }
    _missing = {k: config.OUTPUT_DIR / v
                for k, v in _sub_stems.items()
                if not (config.OUTPUT_DIR / v).exists()}
    if _missing:
        from concurrent.futures import ThreadPoolExecutor
        def _build_photo_tip():
            from src import photo_tip_tree
            photo_tip_tree.build_photo_tip_tree(tree_name)
        def _build_photo_audio():
            from src import photo_audio_tree
            photo_audio_tree.build_photo_audio_tree(tree_name)
        def _build_spec_blend():
            from src import spectrogram_blend
            spectrogram_blend.build_spectrogram_blend(tree_name)
        def _build_range_map():
            from src import range_map_static
            range_map_static.build_range_map(tree_name)
        _job_map = {
            "photo_tip": _build_photo_tip,
            "photo_audio": _build_photo_audio,
            "spec_blend": _build_spec_blend,
            "range_map": _build_range_map,
        }
        with ThreadPoolExecutor(max_workers=4) as _ex:
            _futs = {name: _ex.submit(_job_map[name]) for name in _missing}
            for name, fut in _futs.items():
                try:
                    fut.result()
                except Exception as exc:
                    print(f"parallel {name} sub-build failed: {exc}")

    # ---- Page 1: title + the unrooted tree image ----
    from src import tree_settings
    title_text = tree_settings.title_for(tree_name)
    story.append(Paragraph(tree_settings.PROJECT_MARK, h_title))
    story.append(Paragraph(tree_settings.PROJECT_SLOGAN, h_slogan))
    story.append(Paragraph(title_text, h_sec))
    try:
        # Prefer the photo-tip tree (the prettier output Maya uses for
        # the report's hero page). Build it if missing.
        photo_tip_png = config.OUTPUT_DIR / f"{stem}_photo_tips.png"
        if not photo_tip_png.exists():
            try:
                from src import photo_tip_tree
                photo_tip_tree.build_photo_tip_tree(tree_name)
            except Exception as exc:
                print(f"photo_tip build for PDF failed: {exc}")
        if photo_tip_png.exists():
            png_path = photo_tip_png
        else:
            png_path = _ensure_tree_png(tree_name)
        max_w = (PAGE_W - 2 * MARGIN)
        max_h = (PAGE_H - 2 * MARGIN - 100)
        img = Image(str(png_path), width=max_w, height=max_h,
                     kind="proportional")
        story.append(img)
    except Exception as exc:
        story.append(Paragraph(
            f"<i>Tree image unavailable: {exc}</i>", h_caption))
    story.append(PageBreak())

    # ---- Page 3: combined photo + audio square tree ----
    # Build it if missing — pulls every species' photo + spectrogram and
    # composites them as a single image.
    combined_png = config.OUTPUT_DIR / f"{stem}_photo_audio.png"
    if not combined_png.exists():
        try:
            from src import photo_audio_tree
            photo_audio_tree.build_photo_audio_tree(tree_name)
        except Exception as exc:
            print(f"photo_audio build during PDF failed: {exc}")
    if combined_png.exists() and combined_png.stat().st_size > 0:
        story.append(Paragraph(
            f"{title_text}: kin in image + voice", h_sec))
        story.append(Paragraph(
            "Each species along the square tree, with its photo and a "
            "spectrogram of its actual recorded voice. Image and audio "
            "attributions ride along on the right column.", h_body))
        story.append(Spacer(1, 8))
        try:
            max_w = (PAGE_W - 2 * MARGIN)
            max_h = (PAGE_H - 2 * MARGIN - 120)
            story.append(Image(str(combined_png),
                                width=max_w, height=max_h,
                                kind="proportional"))
        except Exception as exc:
            print(f"combined-tree Image embed failed: {exc}")
            story.append(Paragraph(
                f"<i>Could not embed combined tree: {exc}</i>",
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
        "{r}Evolving Kinship is a participatory ecological art piece "
        "hosted by Shared Rivers. Visitors name a species they feel "
        "kin to; the piece places that species in the tree of life, "
        "redraws the tree with the visitor's kin inside it, and sounds "
        "the deep-time distances back as a microtonal chord. Each "
        "finished tree carries a photo, a short profile, and the "
        "species' actual recorded voice, so the kinship is felt "
        "across every sense the room has.", h_body))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Shared Rivers is the global confluence lab that runs this "
        "piece and others alongside it. The lab gathers artists, "
        "ecologists, and educators around the idea that waterways are "
        "not borders or resources but living connectors. It convenes "
        "events that braid art, ecology, music, gastronomy, and "
        "education into one room. This piece has traveled to several "
        "venues.", h_body))

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

    # ---- Page 4 (optional): Spectrogram Blend ----
    blend_png = config.OUTPUT_DIR / f"{stem}_spectrogram_blend.png"
    if not blend_png.exists():
        try:
            from src import spectrogram_blend
            spectrogram_blend.build_spectrogram_blend(tree_name)
        except Exception as exc:
            print(f"spectrogram_blend build during PDF failed: {exc}")
    if blend_png.exists() and blend_png.stat().st_size > 0:
        story.append(Paragraph(
            f"{title_text}: spectrogram blend", h_sec))
        story.append(Paragraph(
            "Every species' voice averaged into one image: the "
            "ecosystem's collective spectrogram.", h_body))
        story.append(Spacer(1, 8))
        try:
            max_w = (PAGE_W - 2 * MARGIN)
            max_h = (PAGE_H - 2 * MARGIN - 100)
            story.append(Image(str(blend_png),
                                width=max_w, height=max_h,
                                kind="proportional"))
        except Exception as exc:
            print(f"blend embed failed: {exc}")

    # ---- Range map (its own page after the spec blend) ----
    try:
        from src import range_map_static
        range_png = config.OUTPUT_DIR / f"{stem}_range_map.png"
        if not range_png.exists():
            try:
                range_map_static.build_range_map(tree_name)
            except Exception as exc:
                print(f"range_map build during PDF failed: {exc}")
        if range_png.exists() and range_png.stat().st_size > 0:
            story.append(PageBreak())
            story.append(Paragraph(
                f"{title_text}, range map", h_sec))
            story.append(Paragraph(
                "Every species' GBIF occurrence density on the same "
                "basemap the interactive tab uses. Colors match the "
                "legend, and the whole thing sits above cropped "
                "Antarctica so the visual weight goes to the actual "
                "ranges.", h_body))
            story.append(Spacer(1, 8))
            try:
                rw = (PAGE_W - 2 * MARGIN)
                rh = rw * 0.9    # crop-aware aspect (world + legend)
                story.append(Image(str(range_png),
                                     width=rw, height=rh,
                                     kind="proportional"))
            except Exception as exc:
                print(f"range_map embed failed: {exc}")
            story.append(PageBreak())
    except Exception as exc:
        print(f"range_map page failed: {exc}")

    # ---- Kin cards (one species per row, 3-4 per page) ----
    records = _species_records(tree_name)
    if records:
        story.append(Paragraph("Kin cards", h_sec))
        story.append(Spacer(1, 8))
        for rec in records:
            block = []
            # Heading — tag runs so non-Latin scripts pick the right font
            head_raw = (rec['common'] or rec['scientific']) or ''
            head = _tag_runs(head_raw, _SCRIPT_FONTS, _BODY_FONT)
            sci = _tag_runs(rec['scientific'] or '',
                             _SCRIPT_FONTS, _ITALIC_FONT)
            block.append(Paragraph(head, h_species_name))
            block.append(Paragraph(f"<i>{sci}</i>", h_sci_name))
            # Two-column: photo on left, summary + attribution on right.
            # LEFT column: photo + its credit underneath it
            left_bits = []
            if rec.get("image_path") and Path(rec["image_path"]).exists():
                try:
                    left_bits.append(Image(
                        rec["image_path"], width=1.4*inch, height=1.4*inch,
                        kind="proportional"))
                except Exception:
                    pass
            if rec.get("image_attribution") and left_bits:
                ia = _tag_runs(format_credit_html(rec["image_attribution"]),
                                _SCRIPT_FONTS, _BODY_FONT)
                left_bits.append(Spacer(1, 2))
                left_bits.append(Paragraph(ia, h_caption))
            left_cell = left_bits or ""

            # RIGHT column: summary → links → spectrogram → audio credit
            summ = rec.get("summary") or "(no summary on file)"
            if len(summ) > 600:
                summ = summ[:600] + "…"
            summ = _tag_runs(summ, _SCRIPT_FONTS, _BODY_FONT)
            right_bits = [Paragraph(summ, h_body)]

            # Links row — moved ABOVE the spectrogram per Maya
            links = []
            if rec.get("wikipedia"):
                links.append(
                    f'<a href="{_safe_pdf_url(rec["wikipedia"])}">Wikipedia</a>')
            if rec.get("inaturalist"):
                links.append(
                    f'<a href="{_safe_pdf_url(rec["inaturalist"])}">iNaturalist</a>')
            if links:
                right_bits.append(Spacer(1, 4))
                right_bits.append(Paragraph(" · ".join(links), h_caption))

            # Spectrogram thumbnail
            spec_embedded = False
            if rec.get("audio_path"):
                spec_png = _render_spectrogram_thumb(rec["audio_path"])
                if spec_png and spec_png.exists():
                    try:
                        right_bits.append(Spacer(1, 6))
                        right_bits.append(Image(
                            str(spec_png), width=2.6*inch, height=0.9*inch,
                            kind="proportional"))
                        spec_embedded = True
                    except Exception as _exc:
                        print(f"spec embed failed: {_exc}")

            # Audio credit BELOW the spectrogram
            if rec.get("audio_attribution"):
                aa = _tag_runs(format_credit_html(rec["audio_attribution"]),
                                _SCRIPT_FONTS, _BODY_FONT)
                right_bits.append(Spacer(1, 2 if spec_embedded else 4))
                right_bits.append(Paragraph(aa, h_caption))
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
        title=f"{tree_settings.PROJECT_MARK}: {title_text}",
        author="Maya (Shared Rivers)",
        subject="Personalized kinship report",
    )
    # ---- Credits page — LAST page of the PDF (Maya's ask). Every
    # photo + audio attribution consolidated with hyperlinked license.
    try:
        cred_rows = aggregate_tree_credits(tree_name)
    except Exception as exc:
        print(f"aggregate_tree_credits failed: {exc}")
        cred_rows = []
    if cred_rows:
        story.append(PageBreak())
        story.append(Paragraph("Credits", h_sec))
        story.append(Paragraph(
            "Photo and audio per species. License code links to the "
            "Creative Commons page that defines it.", h_caption))
        story.append(Spacer(1, 8))
        for r in cred_rows:
            head = r["common"] or r["species"]
            sub = f" <i>({r['species']})</i>" if r["common"] else ""
            story.append(Paragraph(
                _tag_runs(f"<b>{head}</b>{sub}",
                           _SCRIPT_FONTS, _BODY_FONT),
                h_body))
            if r["photo_credit_html"]:
                story.append(Paragraph(
                    _tag_runs(
                        f"photo: {r['photo_credit_html']}",
                        _SCRIPT_FONTS, _BODY_FONT),
                    h_caption))
            if r["audio_credit_html"]:
                story.append(Paragraph(
                    _tag_runs(
                        f"audio: {r['audio_credit_html']}",
                        _SCRIPT_FONTS, _BODY_FONT),
                    h_caption))
            sub_links = []
            if r.get("wikipedia_url"):
                sub_links.append(
                    f'<a href="{_safe_pdf_url(r["wikipedia_url"])}">'
                    'Wikipedia</a>')
            if r.get("inaturalist_url"):
                sub_links.append(
                    f'<a href="{_safe_pdf_url(r["inaturalist_url"])}">'
                    'iNaturalist</a>')
            if sub_links:
                story.append(Paragraph(
                    " · ".join(sub_links), h_caption))
            story.append(Spacer(1, 6))


    doc.build(story)
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m src.press_pdf '<tree name>'")
        sys.exit(1)
    p = build_press_pdf(sys.argv[1])
    print(f"wrote {p}")
