"""
Language helpers — ISO 639-3 (three-letter) codes for the kinship library.

Why 639-3 not 639-1: 639-3 covers everything 639-1 does plus many indigenous
and minority languages 639-1 doesn't (Cherokee=CHR, Quechua family, dozens
of Mayan languages, etc.). For a kinship project that wants to record names
in languages 639-1 ignores, this is the right register.

LANGUAGES below is the curated short-list shown in dropdowns. Any code can
still be entered through the "Other" option, which opens a free-text field
the user can fill with any valid ISO 639-3 code.
"""

from __future__ import annotations

# Curated list — the most common languages we'd expect contributors to use,
# plus ones Maya has specifically mentioned (Armenian, Mayan, Cherokee).
# Order is roughly: lingua francas first, then major regional languages,
# then indigenous languages of the Americas + Africa.
LANGUAGES = [
    ("ENG", "English"),
    ("SPA", "Spanish"),
    ("FRA", "French"),
    ("POR", "Portuguese"),
    ("DEU", "German"),
    ("ITA", "Italian"),
    ("RUS", "Russian"),
    ("ARA", "Arabic"),
    ("ZHO", "Chinese"),
    ("JPN", "Japanese"),
    ("KOR", "Korean"),
    ("HIN", "Hindi"),
    ("BEN", "Bengali"),
    ("URD", "Urdu"),
    ("PAN", "Panjabi"),
    ("TAM", "Tamil"),
    ("TUR", "Turkish"),
    ("FAS", "Persian"),
    ("HEB", "Hebrew"),
    ("HYE", "Armenian"),
    ("KAT", "Georgian"),
    ("ELL", "Greek"),
    ("POL", "Polish"),
    ("UKR", "Ukrainian"),
    ("NLD", "Dutch"),
    ("SWE", "Swedish"),
    ("NOR", "Norwegian"),
    ("FIN", "Finnish"),
    ("VIE", "Vietnamese"),
    ("THA", "Thai"),
    ("IND", "Indonesian"),
    ("FIL", "Filipino"),
    ("SWA", "Swahili"),
    ("YOR", "Yoruba"),
    ("IBO", "Igbo"),
    ("HAU", "Hausa"),
    ("AMH", "Amharic"),
    ("ZUL", "Zulu"),
    ("XHO", "Xhosa"),
    ("SOM", "Somali"),
    ("QUE", "Quechua"),
    ("AYM", "Aymara"),
    ("GRN", "Guarani"),
    ("NAH", "Nahuatl"),
    ("MAY", "Mayan languages"),
    ("YUA", "Yucatec Maya"),
    ("QUC", "K'iche'"),
    ("CHR", "Cherokee"),
    ("OJI", "Ojibwe"),
    ("LKT", "Lakota"),
    ("NAV", "Navajo"),
    ("HAW", "Hawaiian"),
    ("MRI", "Maori"),
    ("LAT", "Latin"),
    ("SAN", "Sanskrit"),
    ("MIS", "Other / uncoded"),
]

CODE_BY_NAME = {name: code for code, name in LANGUAGES}
NAME_BY_CODE = {code: name for code, name in LANGUAGES}

# Best-effort 2-letter (639-1) → 3-letter (639-3) mapping for the migration.
# Includes the codes we know already exist in the DB from earlier defaults.
TWO_TO_THREE = {
    "en": "ENG", "es": "SPA", "fr": "FRA", "pt": "POR", "de": "DEU",
    "it": "ITA", "ru": "RUS", "ar": "ARA", "zh": "ZHO", "ja": "JPN",
    "ko": "KOR", "hi": "HIN", "bn": "BEN", "ur": "URD", "pa": "PAN",
    "ta": "TAM", "tr": "TUR", "fa": "FAS", "he": "HEB", "hy": "HYE",
    "ka": "KAT", "el": "ELL", "pl": "POL", "uk": "UKR", "nl": "NLD",
    "sv": "SWE", "no": "NOR", "fi": "FIN", "vi": "VIE", "th": "THA",
    "id": "IND", "tl": "FIL", "sw": "SWA", "yo": "YOR", "ig": "IBO",
    "ha": "HAU", "am": "AMH", "zu": "ZUL", "xh": "XHO", "so": "SOM",
    "qu": "QUE", "ay": "AYM", "gn": "GRN",
    "nah": "NAH", "may": "MAY", "yua": "YUA", "quc": "QUC", "chr": "CHR",
    "oj": "OJI", "lkt": "LKT", "nav": "NAV", "haw": "HAW", "mi": "MRI",
    "la": "LAT", "sa": "SAN",
}

OTHER_LABEL = "Other (type a code)"


def normalize_language_code(raw: str | None) -> str:
    """Take whatever's stored in the DB or typed by a user and return a
    canonical three-letter code (uppercased). Falls back to MIS for blanks
    or unparseable input."""
    if not raw:
        return "MIS"
    s = str(raw).strip().lower()
    if not s:
        return "MIS"
    if s in TWO_TO_THREE:
        return TWO_TO_THREE[s]
    upper = s.upper()
    if upper in NAME_BY_CODE:
        return upper
    return upper[:3] if len(upper) >= 3 else "MIS"


def language_dropdown_choices() -> list[str]:
    """Display labels for the dropdown, in order. Each label is "ENG —
    English"; the codes are extracted from the label when reading the
    selection back."""
    return [f"{code} — {name}" for code, name in LANGUAGES] + [OTHER_LABEL]


def code_from_choice(label: str) -> str:
    """Reverse of language_dropdown_choices: read the code back out of a
    selected label. Returns "" for the Other label (caller then reads the
    free-text field)."""
    if not label or label == OTHER_LABEL:
        return ""
    return label.split(" — ", 1)[0].strip().upper()


def render_language_picker(label: str, key: str,
                            initial_code: str | None = "ENG") -> str:
    """Streamlit widget: dropdown + (conditional) Other text field.
    Returns the chosen three-letter code, always uppercased, MIS for blank.
    Stays self-contained (caches nothing; widgets manage their own state)."""
    import streamlit as st
    initial_code = normalize_language_code(initial_code or "ENG")
    choices = language_dropdown_choices()
    if initial_code in NAME_BY_CODE:
        initial_label = f"{initial_code} — {NAME_BY_CODE[initial_code]}"
        initial_idx = choices.index(initial_label)
    else:
        # Code we don't have in the curated list — open with "Other".
        initial_idx = len(choices) - 1
    picked = st.selectbox(label, choices, index=initial_idx, key=key)
    code = code_from_choice(picked)
    if not code:
        custom = st.text_input(
            "Language code (3-letter ISO 639-3)",
            value=(initial_code if initial_code not in NAME_BY_CODE
                   else ""),
            key=f"{key}_other",
            max_chars=5,
            help="Any valid ISO 639-3 code. Look up: iso639-3.sil.org",
        )
        code = normalize_language_code(custom)
    return code
