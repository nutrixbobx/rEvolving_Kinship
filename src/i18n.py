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


# ---------------------------------------------------------------------------
# Region picker: macro-region → country/sub-region (ISO 3166 codes)
# ---------------------------------------------------------------------------
REGIONS_BY_MACRO: dict[str, list[tuple[str, str]]] = {
    "South Asia": [
        ("IN",    "India"),
        ("PK",    "Pakistan"),
        ("BD",    "Bangladesh"),
        ("LK",    "Sri Lanka"),
        ("NP",    "Nepal"),
        ("BT",    "Bhutan"),
        ("MV",    "Maldives"),
        ("AF",    "Afghanistan"),
    ],
    "Southeast Asia": [
        ("ID",    "Indonesia"),
        ("PH",    "Philippines"),
        ("VN",    "Vietnam"),
        ("TH",    "Thailand"),
        ("MM",    "Myanmar"),
        ("MY",    "Malaysia"),
        ("SG",    "Singapore"),
        ("KH",    "Cambodia"),
        ("LA",    "Laos"),
        ("TL",    "Timor-Leste"),
        ("BN",    "Brunei"),
    ],
    "East Asia": [
        ("CN",    "China"),
        ("JP",    "Japan"),
        ("KR",    "South Korea"),
        ("KP",    "North Korea"),
        ("TW",    "Taiwan"),
        ("HK",    "Hong Kong"),
        ("MO",    "Macau"),
        ("MN",    "Mongolia"),
    ],
    "West Asia": [
        ("TR",    "Turkey"),
        ("SY",    "Syria"),
        ("LB",    "Lebanon"),
        ("IL",    "Israel"),
        ("PS",    "Palestine"),
        ("JO",    "Jordan"),
        ("IQ",    "Iraq"),
        ("IR",    "Iran"),
        ("SA",    "Saudi Arabia"),
        ("YE",    "Yemen"),
        ("OM",    "Oman"),
        ("AE",    "UAE"),
        ("QA",    "Qatar"),
        ("BH",    "Bahrain"),
        ("KW",    "Kuwait"),
        ("AM",    "Armenia"),
        ("AZ",    "Azerbaijan"),
        ("GE",    "Georgia"),
        ("CY",    "Cyprus"),
    ],
    "Central Asia": [
        ("KZ",    "Kazakhstan"),
        ("UZ",    "Uzbekistan"),
        ("TM",    "Turkmenistan"),
        ("KG",    "Kyrgyzstan"),
        ("TJ",    "Tajikistan"),
    ],
    "North Africa": [
        ("EG",    "Egypt"),
        ("LY",    "Libya"),
        ("TN",    "Tunisia"),
        ("DZ",    "Algeria"),
        ("MA",    "Morocco"),
        ("SD",    "Sudan"),
        ("SS",    "South Sudan"),
    ],
    "West Africa": [
        ("NG",    "Nigeria"),
        ("GH",    "Ghana"),
        ("SN",    "Senegal"),
        ("CI",    "Côte d'Ivoire"),
        ("ML",    "Mali"),
        ("BF",    "Burkina Faso"),
        ("NE",    "Niger"),
        ("GM",    "Gambia"),
        ("GN",    "Guinea"),
        ("LR",    "Liberia"),
        ("SL",    "Sierra Leone"),
        ("BJ",    "Benin"),
        ("TG",    "Togo"),
        ("MR",    "Mauritania"),
        ("CV",    "Cape Verde"),
        ("GW",    "Guinea-Bissau"),
    ],
    "East Africa": [
        ("KE",    "Kenya"),
        ("ET",    "Ethiopia"),
        ("TZ",    "Tanzania"),
        ("UG",    "Uganda"),
        ("RW",    "Rwanda"),
        ("BI",    "Burundi"),
        ("ER",    "Eritrea"),
        ("SO",    "Somalia"),
        ("DJ",    "Djibouti"),
        ("MG",    "Madagascar"),
        ("MU",    "Mauritius"),
        ("SC",    "Seychelles"),
        ("KM",    "Comoros"),
    ],
    "Central Africa": [
        ("CD",    "DR Congo"),
        ("CG",    "Republic of Congo"),
        ("AO",    "Angola"),
        ("CM",    "Cameroon"),
        ("CF",    "Central African Republic"),
        ("TD",    "Chad"),
        ("GQ",    "Equatorial Guinea"),
        ("GA",    "Gabon"),
        ("ST",    "São Tomé and Príncipe"),
    ],
    "Southern Africa": [
        ("ZA",    "South Africa"),
        ("NA",    "Namibia"),
        ("BW",    "Botswana"),
        ("ZW",    "Zimbabwe"),
        ("ZM",    "Zambia"),
        ("MW",    "Malawi"),
        ("MZ",    "Mozambique"),
        ("LS",    "Lesotho"),
        ("SZ",    "Eswatini"),
    ],
    "Western Europe": [
        ("FR",    "France"),
        ("DE",    "Germany"),
        ("ES",    "Spain"),
        ("PT",    "Portugal"),
        ("IT",    "Italy"),
        ("NL",    "Netherlands"),
        ("BE",    "Belgium"),
        ("CH",    "Switzerland"),
        ("AT",    "Austria"),
        ("LU",    "Luxembourg"),
        ("IE",    "Ireland"),
        ("GB",    "United Kingdom"),
        ("IS",    "Iceland"),
    ],
    "Northern Europe": [
        ("SE",    "Sweden"),
        ("NO",    "Norway"),
        ("DK",    "Denmark"),
        ("FI",    "Finland"),
        ("EE",    "Estonia"),
        ("LV",    "Latvia"),
        ("LT",    "Lithuania"),
    ],
    "Eastern Europe": [
        ("PL",    "Poland"),
        ("CZ",    "Czechia"),
        ("SK",    "Slovakia"),
        ("HU",    "Hungary"),
        ("RO",    "Romania"),
        ("BG",    "Bulgaria"),
        ("UA",    "Ukraine"),
        ("BY",    "Belarus"),
        ("RU",    "Russia"),
        ("MD",    "Moldova"),
        ("HR",    "Croatia"),
        ("SI",    "Slovenia"),
        ("RS",    "Serbia"),
        ("BA",    "Bosnia and Herzegovina"),
        ("ME",    "Montenegro"),
        ("MK",    "North Macedonia"),
        ("AL",    "Albania"),
        ("GR",    "Greece"),
        ("XK",    "Kosovo"),
    ],
    "North America": [
        ("US",    "United States"),
        ("CA",    "Canada"),
        ("MX",    "Mexico"),
    ],
    "Mesoamerica": [
        ("MX",    "Mexico"),
        ("GT",    "Guatemala"),
        ("BZ",    "Belize"),
        ("HN",    "Honduras"),
        ("SV",    "El Salvador"),
        ("NI",    "Nicaragua"),
        ("CR",    "Costa Rica"),
        ("PA",    "Panama"),
    ],
    "Caribbean": [
        ("CU",    "Cuba"),
        ("DO",    "Dominican Republic"),
        ("HT",    "Haiti"),
        ("JM",    "Jamaica"),
        ("PR",    "Puerto Rico"),
        ("TT",    "Trinidad and Tobago"),
        ("BS",    "Bahamas"),
        ("BB",    "Barbados"),
    ],
    "South America": [
        ("BR",    "Brazil"),
        ("AR",    "Argentina"),
        ("CO",    "Colombia"),
        ("PE",    "Peru"),
        ("VE",    "Venezuela"),
        ("CL",    "Chile"),
        ("EC",    "Ecuador"),
        ("BO",    "Bolivia"),
        ("PY",    "Paraguay"),
        ("UY",    "Uruguay"),
        ("GY",    "Guyana"),
        ("SR",    "Suriname"),
    ],
    "Oceania": [
        ("AU",    "Australia"),
        ("NZ",    "New Zealand"),
        ("PG",    "Papua New Guinea"),
        ("FJ",    "Fiji"),
        ("SB",    "Solomon Islands"),
        ("VU",    "Vanuatu"),
        ("WS",    "Samoa"),
        ("TO",    "Tonga"),
        ("KI",    "Kiribati"),
        ("PW",    "Palau"),
        ("MH",    "Marshall Islands"),
        ("FM",    "Micronesia"),
        ("NR",    "Nauru"),
        ("TV",    "Tuvalu"),
    ],
    "Indigenous North America": [
        ("US-CHR", "Cherokee Nation"),
        ("US-NAV", "Navajo Nation"),
        ("US-LKT", "Lakota / Dakota"),
        ("US-OJI", "Ojibwe / Anishinaabe"),
        ("US-HAW", "Hawai'i"),
        ("CA-IND", "Canadian First Nations"),
    ],
}


def region_dropdown_choices() -> list[str]:
    """Single flattened list with macro-region prefix so the user can scan."""
    out: list[str] = ["(none)"]
    for macro, items in REGIONS_BY_MACRO.items():
        for code, name in items:
            out.append(f"[{macro}] {code} — {name}")
    out.append(OTHER_LABEL)
    return out


def render_region_picker(label: str, key: str,
                          initial_code: str | None = None) -> str | None:
    """Two-step region picker: macro-region first, then country within it.
    Returns the ISO 3166 code (or 'US-CHR'-style indigenous code), or None
    for the 'none' option, or whatever the user types when they pick Other."""
    import streamlit as st
    initial_macro = "(none)"
    initial_country = None
    if initial_code:
        for macro, items in REGIONS_BY_MACRO.items():
            for code, _name in items:
                if code == initial_code:
                    initial_macro = macro
                    initial_country = code
                    break
            if initial_country:
                break

    macro_choices = ["(none)"] + list(REGIONS_BY_MACRO.keys()) + [OTHER_LABEL]
    macro_idx = (macro_choices.index(initial_macro)
                  if initial_macro in macro_choices else 0)
    macro = st.selectbox(label, macro_choices, index=macro_idx,
                          key=f"{key}_macro")
    if macro == "(none)":
        return None
    if macro == OTHER_LABEL:
        custom = st.text_input(
            "Region code", value=initial_code or "",
            key=f"{key}_other",
            help="Any ISO 3166 code (US-GA, AM, MX) or a custom prefix.")
        return (custom or "").strip().upper() or None

    items = REGIONS_BY_MACRO[macro]
    country_labels = [f"{code} — {name}" for code, name in items]
    initial_country_idx = 0
    if initial_country:
        for i, (code, _) in enumerate(items):
            if code == initial_country:
                initial_country_idx = i
                break
    country_label = st.selectbox(
        "Country or sub-region", country_labels,
        index=initial_country_idx, key=f"{key}_country")
    return country_label.split(" — ", 1)[0].strip()


# ---------------------------------------------------------------------------
# Script picker (basic click-to-compose keyboard for non-Latin scripts)
# ---------------------------------------------------------------------------
# Each script: a list of rows (each row is a string of characters). The
# UI lays them out as buttons; clicking appends to the buffer that the
# user can copy into the Name field.
SCRIPTS = {
    "Devanagari (Hindi, Sanskrit, Marathi)": [
        "अआइईउऊऋॠऌॡएऐओऔ",
        "कखगघङचछजझञ",
        "टठडढणतथदधन",
        "पफबभमयरलवशषसह",
        "ािीुूृॄेैोौंः्",
    ],
    "Gurmukhi (Panjabi)": [
        "ਅਆਇਈਉਊਏਐਓਔ",
        "ਕਖਗਘਙਚਛਜਝਞ",
        "ਟਠਡਢਣਤਥਦਧਨ",
        "ਪਫਬਭਮਯਰਲਵਸਹ",
        "ਾਿੀੁੂੇੈੋੌਂੰ੍",
    ],
    "Bengali": [
        "অআইঈউঊঋএঐওঔ",
        "কখগঘঙচছজঝঞ",
        "টঠডঢণতথদধন",
        "পফবভমযরলশষসহ",
        "ািীুূেৈোৌংঃ্",
    ],
    "Tamil": [
        "அஆஇஈஉஊஎஏஐஒஓஔ",
        "கசஞடணதநபமயரலவ",
        "ழளறனஜஶஷஸஹ",
        "ாிீுூெேைொோௌஂ்",
    ],
    "Armenian": [
        "ԱԲԳԴԵԶԷԸԹԺԻԼԽԾԿՀՁՂՃՄ",
        "ՅՆՇՈՉՊՋՌՍՎՏՐՑՒՓՔՕՖ",
        "աբգդեզէըթժիլխծկհձղճմ",
        "յնշոչպջռսվտրցւփքօֆ",
    ],
    "Arabic": [
        "ابتثجحخدذر",
        "زسشصضطظعغف",
        "قكلمنهوي",
        "ءأإآؤئىة",
        "ًٌٍَُِّْـ",
    ],
    "Hebrew": [
        "אבגדהוזחטיכלמ",
        "נסעפצקרשת",
        "ךםןףץ",
        "ְֱֲֳִֵֶַָֹֻּ",
    ],
    "Cyrillic (Russian, Ukrainian, etc.)": [
        "АБВГДЕЁЖЗИЙКЛМНО",
        "ПРСТУФХЦЧШЩЪЫЬЭЮЯ",
        "абвгдеёжзийклмно",
        "прстуфхцчшщъыьэюя",
    ],
    "Greek": [
        "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ",
        "αβγδεζηθικλμνξοπρστυφχψω",
    ],
    "Hiragana (Japanese)": [
        "あいうえお",
        "かきくけこ",
        "さしすせそ",
        "たちつてと",
        "なにぬねの",
        "はひふへほ",
        "まみむめも",
        "やゆよ",
        "らりるれろ",
        "わをん",
    ],
    "Katakana (Japanese)": [
        "アイウエオ",
        "カキクケコ",
        "サシスセソ",
        "タチツテト",
        "ナニヌネノ",
        "ハヒフヘホ",
        "マミムメモ",
        "ヤユヨ",
        "ラリルレロ",
        "ワヲン",
    ],
}


def render_script_keyboard(target_key: str) -> str:
    """Inline 'compose in another script' helper. The current composition
    lives in st.session_state[f'{target_key}_script_buf']; clicking any
    character button appends to it; a 'Clear' button resets it. The caller
    is responsible for inserting the buffer into the Name field (typically
    by setting a default value or asking the user to paste). Returns the
    current buffer string."""
    import streamlit as st
    buf_key = f"{target_key}_script_buf"
    if buf_key not in st.session_state:
        st.session_state[buf_key] = ""
    script = st.selectbox(
        "Script", list(SCRIPTS.keys()),
        key=f"{target_key}_script_pick")
    st.caption("Click letters to compose. Copy the result into the Name "
                "field above when done.")
    rows = SCRIPTS.get(script, [])
    for ridx, row in enumerate(rows):
        cols = st.columns(len(row))
        for cidx, ch in enumerate(row):
            with cols[cidx]:
                if st.button(ch, key=f"{target_key}_btn_{ridx}_{cidx}_{ch}"):
                    st.session_state[buf_key] += ch
                    st.rerun()
    bcol1, bcol2 = st.columns([5, 1])
    with bcol1:
        st.text_input("Composed text", value=st.session_state[buf_key],
                       key=f"{buf_key}_display",
                       disabled=True)
    with bcol2:
        if st.button("Clear", key=f"{target_key}_clear_buf"):
            st.session_state[buf_key] = ""
            st.rerun()
    return st.session_state[buf_key]

