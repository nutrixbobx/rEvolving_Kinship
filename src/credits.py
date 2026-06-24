"""
Standardized credit formatting for images + audio.

Raw attribution strings from iNaturalist + Xeno-canto come in many shapes:

  iNat photos:   "(c) Nuno Verissimo P., some rights reserved (CC BY-NC-SA), uploaded by …"
  iNat (CC0):    "(c) Foo Bar, no rights reserved, …"
  Xeno-canto:    "Xeno-canto XC995887 - Tommy Kaae - https://creativecommons.org/licenses/by-nc-sa/4.0/"

We collapse each to one compact form: "(c) Name, CC BY-NC-SA 4.0"
with the license code as a hyperlink to the relevant creativecommons.org
page. The verbose source-platform language is dropped.
"""

from __future__ import annotations
import re

# Map raw license codes / phrases to (canonical_label, url)
_LICENSE_MAP = [
    ("cc0",            "CC0 1.0",       "https://creativecommons.org/publicdomain/zero/1.0/"),
    ("public domain",  "Public Domain", "https://creativecommons.org/publicdomain/mark/1.0/"),
    ("cc by-nc-sa",    "CC BY-NC-SA 4.0", "https://creativecommons.org/licenses/by-nc-sa/4.0/"),
    ("cc by-nc-nd",    "CC BY-NC-ND 4.0", "https://creativecommons.org/licenses/by-nc-nd/4.0/"),
    ("cc by-sa",       "CC BY-SA 4.0",   "https://creativecommons.org/licenses/by-sa/4.0/"),
    ("cc by-nc",       "CC BY-NC 4.0",   "https://creativecommons.org/licenses/by-nc/4.0/"),
    ("cc by-nd",       "CC BY-ND 4.0",   "https://creativecommons.org/licenses/by-nd/4.0/"),
    ("cc by",          "CC BY 4.0",      "https://creativecommons.org/licenses/by/4.0/"),
]


def _detect_license(raw: str) -> tuple[str, str] | None:
    """Return (label, url) for the first known license code found in raw,
    or None if nothing matches."""
    if not raw:
        return None
    low = raw.lower()
    # First, look for a creativecommons.org/licenses/<code>/ URL — that's
    # how Xeno-canto attributions express their license.
    m = re.search(
        r"creativecommons\.org/(?:licenses|publicdomain)/"
        r"([a-z0-9\-]+)/?",
        low)
    if m:
        slug = m.group(1)
        slug_key = "cc " + slug if slug not in ("zero", "mark") else "cc0"
        for key, label, url in _LICENSE_MAP:
            if slug_key.startswith(key) or key.endswith(slug_key.lstrip("cc ")):
                return (label, url)
        # Direct construction from the slug if we don't have it in the map
        if slug.startswith("by"):
            return (f"CC {slug.upper()} 4.0",
                    f"https://creativecommons.org/licenses/{slug}/4.0/")
    # iNat's "no rights reserved" === CC0
    if "no rights reserved" in low:
        return ("CC0 1.0", "https://creativecommons.org/publicdomain/zero/1.0/")
    for key, label, url in _LICENSE_MAP:
        if key in low:
            return (label, url)
    return None


def _extract_name(raw: str) -> str:
    """Pull the contributor name out of typical iNat / XC attribution
    strings. Best-effort; returns 'Unknown' when nothing parses."""
    if not raw:
        return "Unknown"
    s = raw.strip()
    # iNat shape: "(c) Name, some rights reserved (CC BY-...)"
    m = re.match(r"\(c\)\s*([^,]+),", s)
    if m:
        return m.group(1).strip()
    # Xeno-canto shape: "Xeno-canto XCxxxxx - Name - https://..."
    m = re.match(r"^Xeno-canto\s+XC\d+\s*-\s*([^-]+?)\s*-\s*http", s)
    if m:
        return m.group(1).strip()
    # Wikimedia / "by Name" shape
    m = re.search(r"\bby\s+([A-Z][^,\.]+)", s)
    if m:
        return m.group(1).strip()
    # Fall back to first comma-bounded chunk
    return s.split(",")[0].strip() or "Unknown"


def format_credit(raw: str | None,
                  *, markdown: bool = True) -> str:
    """Standardized one-line credit: '(c) Name, CC BY-NC-SA 4.0' with the
    license as a hyperlink to creativecommons.org.

    markdown=True returns Markdown link syntax (for st.markdown / PDF
    Paragraphs). markdown=False returns plain "(c) Name, CC BY-NC-SA 4.0"
    with no hyperlink — for SVG <text> elements where rich links don't
    render."""
    if not raw:
        return "(c) Unknown"
    name = _extract_name(raw)
    detected = _detect_license(raw)
    if not detected:
        return f"(c) {name}"
    label, url = detected
    if markdown:
        return f"(c) {name}, [{label}]({url})"
    return f"(c) {name}, {label}"


def format_credit_html(raw: str | None) -> str:
    """For ReportLab Paragraph / HTML contexts where we need an explicit
    <a href> tag instead of markdown syntax."""
    if not raw:
        return "(c) Unknown"
    name = _extract_name(raw)
    detected = _detect_license(raw)
    if not detected:
        return f"(c) {name}"
    label, url = detected
    return f'(c) {name}, <a href="{url}">{label}</a>'
