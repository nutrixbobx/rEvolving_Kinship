"""
Visual identity for {r}Evolving Kinship.

One palette, one CSS payload, one footer. Every screen pulls from here so the
kiosk, dashboard, range map, and library feel like the same room. The palette
matches the GBIF range-map page so the app stays of-a-piece even when you
switch tabs.

Mobile rules baked in:
  - Columns wrap and stack under ~640px wide so two-up layouts don't squish.
  - Buttons inside columns fill the width on small screens.
  - The tab bar scrolls horizontally rather than collapsing.
  - Expanders, forms, and dataframes get tighter padding on phones.

Usage:
    from src import theme
    theme.inject_css()
    ...
    theme.render_footer(slogan="...")
"""

from __future__ import annotations

import streamlit as st

# Earth-dark palette. Same six anchor colors used across the GBIF map, the
# tree renders, and now the chrome.
PALETTE = {
    "bg":         "#3a0124",  # crimson violet, deeper than the anchor so the
                              # bigger anchor (#700143) reads as a highlight
    "bg_alt":     "#4a0030",  # sidebar / cards — slightly lifted from bg
    "ink":        "#f4ecdc",  # warm cream for body text on the violet bg
    "muted":      "#c9a5b6",  # dusty rose for secondary text
    "rule":       "#5a1c40",  # dividers, borders — soft violet line
    "accent":     "#cfd78c",  # PALE AMBER — links, focus, highlights
    "warm":       "#cfd78c",  # primary buttons share the amber for cohesion
    "primary":    "#9bc77b",  # leaf green (success, primary actions)
    "danger":     "#e08a4a",  # warm coral against the violet
    "donate":     "#ffd97a",  # bright donate links pop without clashing
}

_CSS_INJECTED_KEY = "_theme_css_injected"


def inject_css() -> None:
    """Apply the theme CSS once per session. Safe to call multiple times; the
    second call is a no-op."""
    if st.session_state.get(_CSS_INJECTED_KEY):
        return
    st.session_state[_CSS_INJECTED_KEY] = True
    st.markdown(_CSS, unsafe_allow_html=True)


def render_footer(slogan: str = "") -> None:
    """Site-wide footer. CC license, byline, support links."""
    slogan_html = (
        f'<div class="footer-slogan">{slogan}</div>' if slogan else ""
    )
    st.markdown(
        f"""
<div class="kinship-footer">
  <div class="footer-title">{{r}}Evolving Kinship</div>
  {slogan_html}
  <div class="footer-row">
    <a href="https://shared-rivers.org" target="_blank">Shared Rivers</a>
    <span class="dot"></span>
    <a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank">CC BY-SA 4.0</a>
    <span class="dot"></span>
    <span>Maya Nutria</span>
  </div>
  <div class="footer-row support-row">
    <span class="muted">Support our work</span>
    <a class="support" href="https://buymeacoffee.com/shared.rivers" target="_blank">buy me a coffee</a>
    <span class="muted">or contribute a</span>
    <a class="support" href="https://fundraising.fracturedatlas.org/shared-rivers-confluences" target="_blank">tax-deductible donation</a>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def section_heading(text: str, kicker: str | None = None) -> None:
    """A consistent two-line heading: a small kicker label and a larger title.
    Use in place of st.subheader where the page has more than one section."""
    if kicker:
        st.markdown(
            f'<div class="kicker">{kicker}</div>'
            f'<div class="section-title">{text}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="section-title">{text}</div>',
            unsafe_allow_html=True,
        )


def soft_card(html: str) -> None:
    """Wrap a small block of HTML in a card with the theme padding + border."""
    st.markdown(f'<div class="soft-card">{html}</div>', unsafe_allow_html=True)


def app_header(title: str, slogan: str | None = None) -> None:
    """The big top-of-page identity. Used by the landing screen and the main
    app shell."""
    sl = (f'<div class="app-slogan">{slogan}</div>'
          if slogan else "")
    st.markdown(
        f"""
<div class="app-header">
  <div class="app-title">{title}</div>
  {sl}
</div>
""",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# The CSS
# ---------------------------------------------------------------------------
_CSS = f"""
<style>
:root {{
  --kn-bg:       {PALETTE['bg']};
  --kn-bg-alt:   {PALETTE['bg_alt']};
  --kn-ink:      {PALETTE['ink']};
  --kn-muted:    {PALETTE['muted']};
  --kn-rule:     {PALETTE['rule']};
  --kn-accent:   {PALETTE['accent']};
  --kn-warm:     {PALETTE['warm']};
  --kn-primary:  {PALETTE['primary']};
  --kn-danger:   {PALETTE['danger']};
  --kn-donate:   {PALETTE['donate']};
}}

/* Page chrome */
[data-testid="stAppViewContainer"],
[data-testid="stHeader"],
.stApp {{
  background: var(--kn-bg) !important;
}}
[data-testid="stHeader"] {{ background: rgba(58,1,36,0.92)!important; }}
.block-container {{
  padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1200px;
}}
body, .stApp, .stMarkdown, [data-testid="stMarkdownContainer"] {{
  color: var(--kn-ink);
}}
h1, h2, h3, h4 {{ color: var(--kn-ink); letter-spacing: -0.01em; }}
h1 {{ font-weight: 600; }}
hr, .stDivider {{ border-color: var(--kn-rule) !important; }}

/* Sidebar */
[data-testid="stSidebar"] {{
  background: var(--kn-bg-alt) !important;
  border-right: 1px solid var(--kn-rule);
}}
[data-testid="stSidebar"] * {{ color: var(--kn-ink); }}
[data-testid="stSidebar"] .stMarkdown a {{ color: var(--kn-accent); }}

/* Links */
a {{ color: var(--kn-accent); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}

/* Inputs */
input, textarea, select,
.stTextInput input, .stTextArea textarea, .stNumberInput input,
.stDateInput input, .stTimeInput input {{
  background: var(--kn-bg-alt) !important;
  color: var(--kn-ink) !important;
  border: 1px solid var(--kn-rule) !important;
  border-radius: 8px !important;
}}
input:focus, textarea:focus, select:focus {{
  border-color: var(--kn-accent) !important;
  box-shadow: 0 0 0 2px rgba(207,215,140,0.22) !important;
}}
[data-testid="stTextInput"] label,
[data-testid="stTextArea"] label,
[data-testid="stSelectbox"] label,
[data-testid="stMultiSelect"] label,
[data-testid="stRadio"] label,
[data-testid="stCheckbox"] label {{
  color: var(--kn-muted) !important;
  font-size: 12px !important;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}}

/* Selectbox dropdown */
[data-baseweb="select"] > div {{
  background: var(--kn-bg-alt) !important;
  border: 1px solid var(--kn-rule) !important;
  border-radius: 8px !important;
  color: var(--kn-ink) !important;
}}

/* Buttons */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {{
  background: var(--kn-bg-alt);
  color: var(--kn-ink);
  border: 1px solid var(--kn-rule);
  border-radius: 8px;
  padding: 8px 16px;
  font-weight: 500;
  transition: border-color .15s, background .15s, transform .05s;
}}
.stButton > button:hover, .stDownloadButton > button:hover,
.stFormSubmitButton > button:hover {{
  border-color: var(--kn-accent);
  background: rgba(207,215,140,0.10);
}}
.stButton > button:active {{ transform: translateY(1px); }}
/* Primary button: warm accent for build CTAs */
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {{
  background: var(--kn-warm);
  color: #3a0124;  /* deep crimson on amber for readability */
  border-color: var(--kn-warm);
  font-weight: 600;
}}
.stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primary"]:hover {{
  background: #dde29d;
  border-color: #dde29d;
}}
.stButton > button:disabled {{
  opacity: 0.55; cursor: not-allowed;
}}

/* Tabs — make them scrollable on narrow viewports */
[data-baseweb="tab-list"] {{
  background: transparent !important;
  border-bottom: 1px solid var(--kn-rule);
  gap: 4px;
  overflow-x: auto;
  scrollbar-width: thin;
}}
[data-baseweb="tab-list"]::-webkit-scrollbar {{ height: 4px; }}
[data-baseweb="tab-list"]::-webkit-scrollbar-thumb {{
  background: var(--kn-rule);
}}
[data-baseweb="tab"] {{
  color: var(--kn-muted) !important;
  background: transparent !important;
  border-radius: 8px 8px 0 0 !important;
  padding: 10px 14px !important;
  white-space: nowrap;
}}
[data-baseweb="tab"][aria-selected="true"] {{
  color: var(--kn-accent) !important;
  background: rgba(207,215,140,0.10) !important;
}}
[data-baseweb="tab-highlight"] {{ background: var(--kn-accent) !important; }}

/* Expanders */
[data-testid="stExpander"] details {{
  background: var(--kn-bg-alt);
  border: 1px solid var(--kn-rule);
  border-radius: 10px;
  margin-bottom: 10px;
}}
[data-testid="stExpander"] summary {{
  padding: 12px 14px;
  color: var(--kn-ink);
  font-weight: 500;
}}
[data-testid="stExpander"] summary:hover {{ color: var(--kn-accent); }}

/* Dataframes — horizontally scrollable instead of squishing on phones */
[data-testid="stDataFrame"] {{
  background: var(--kn-bg-alt);
  border: 1px solid var(--kn-rule);
  border-radius: 10px;
}}

/* Captions & helper text */
.stCaption, [data-testid="stCaptionContainer"], small {{
  color: var(--kn-muted) !important;
}}

/* Info / success / warning / error pills */
[data-testid="stAlert"] {{
  background: var(--kn-bg-alt) !important;
  border-left: 3px solid var(--kn-accent) !important;
  border-radius: 6px !important;
  color: var(--kn-ink) !important;
}}
[data-testid="stAlert"][data-baseweb="notification"] [data-testid="stMarkdownContainer"] * {{
  color: var(--kn-ink) !important;
}}

/* Custom helpers used by section_heading + soft_card + app_header + footer */
.kicker {{
  color: var(--kn-muted);
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-size: 11px;
  margin-bottom: 4px;
}}
.section-title {{
  font-size: 22px;
  font-weight: 500;
  color: var(--kn-ink);
  margin: 0 0 14px 0;
}}
.soft-card {{
  background: var(--kn-bg-alt);
  border: 1px solid var(--kn-rule);
  border-radius: 12px;
  padding: 16px;
  margin: 12px 0;
}}
.app-header {{
  padding: 0 0 8px 0;
}}
.app-title {{
  font-size: 38px;
  font-weight: 700;
  letter-spacing: -0.025em;
  color: var(--kn-ink);
  line-height: 1.05;
}}
.app-slogan {{
  color: var(--kn-muted);
  font-style: italic;
  font-size: 14px;
  font-weight: 400;
  margin-top: 6px;
  margin-bottom: 20px;
  max-width: 760px;
  line-height: 1.45;
}}

/* Footer */
.kinship-footer {{
  margin-top: 56px;
  padding: 22px 0 16px 0;
  border-top: 1px solid var(--kn-rule);
  text-align: center;
  color: var(--kn-muted);
  font-size: 12px;
  line-height: 1.85;
}}
.footer-title {{
  color: var(--kn-ink);
  font-weight: 700;
  letter-spacing: 0.03em;
  font-size: 16px;
}}
.footer-slogan {{
  color: var(--kn-muted);
  font-style: italic;
  font-size: 12px;
  margin-top: 4px;
  max-width: 640px;
  margin-left: auto;
  margin-right: auto;
  line-height: 1.5;
}}
.footer-row {{
  margin-top: 10px;
}}
.footer-row .dot {{
  display: inline-block;
  width: 3px;
  height: 3px;
  background: var(--kn-rule);
  border-radius: 50%;
  margin: 0 10px;
  vertical-align: middle;
}}
.footer-row a {{ color: var(--kn-muted); }}
.footer-row a:hover {{ color: var(--kn-accent); }}
.support-row {{
  display: inline-flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: center;
  gap: 8px;
}}
.support-row > * {{ margin: 0 !important; }}
.support-row .support {{ color: var(--kn-donate) !important; font-weight: 500; }}
.support-row .support:hover {{ color: var(--kn-accent) !important; }}
.footer-row .muted {{ color: var(--kn-muted); margin-right: 6px; }}

/* Role badges (sidebar identity chip) */
.role-badge {{
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 10px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  font-weight: 600;
}}
.role-admin {{ background: rgba(207,215,140,0.18); color: var(--kn-accent); }}
.role-editor {{ background: rgba(155,199,123,0.16); color: var(--kn-primary); }}
.role-visitor {{ background: rgba(201,165,182,0.14); color: var(--kn-muted); }}

/* Identity card in sidebar */
.identity-card {{
  background: var(--kn-bg);
  border: 1px solid var(--kn-rule);
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: 10px;
}}
.identity-name {{ color: var(--kn-ink); font-weight: 500; font-size: 14px; }}
.identity-bio {{ color: var(--kn-muted); font-size: 12px; margin-top: 4px; }}

/* ============ MOBILE — under 640px ================================= */
@media (max-width: 640px) {{
  .block-container {{
    padding-top: 0.8rem;
    padding-left: 0.7rem;
    padding-right: 0.7rem;
  }}
  .app-title {{ font-size: 30px; font-weight: 700; line-height: 1.1; }}
  .app-slogan {{ font-size: 13px; margin-bottom: 16px; }}
  .footer-title {{ font-size: 15px; }}
  .footer-slogan {{ font-size: 11px; }}

  /* Horizontal blocks (st.columns) wrap and full-width on mobile */
  [data-testid="stHorizontalBlock"] {{
    flex-wrap: wrap !important;
    gap: 12px !important;
  }}
  [data-testid="stHorizontalBlock"] > div[data-testid="column"] {{
    min-width: 100% !important;
    width: 100% !important;
    flex: 1 1 100% !important;
  }}

  /* Buttons fill the column on mobile */
  .stButton > button, .stDownloadButton > button,
  .stFormSubmitButton > button {{
    width: 100%;
    padding: 12px 16px;
    font-size: 15px;
  }}

  /* Tighter expanders */
  [data-testid="stExpander"] summary {{
    padding: 10px 12px;
    font-size: 14px;
  }}

  /* Inputs grow comfortable for thumbs */
  input, textarea, select,
  .stTextInput input, .stTextArea textarea {{
    font-size: 16px !important; /* prevents iOS auto-zoom */
    padding: 10px 12px !important;
  }}

  /* Sidebar slides over content; widen it a touch */
  [data-testid="stSidebar"] {{
    min-width: 80vw !important;
  }}
}}

/* ============ Small visual flourishes for landing screen =========== */
.welcome-card {{
  max-width: 540px;
  margin: 18px auto;
  background: var(--kn-bg-alt);
  border: 1px solid var(--kn-rule);
  border-radius: 14px;
  padding: 22px 22px 18px 22px;
}}
.welcome-card h3 {{ margin: 0 0 6px 0; font-size: 18px; }}
.welcome-card .muted {{ color: var(--kn-muted); font-size: 13px; line-height: 1.55; }}
</style>
"""

# ---------------------------------------------------------------------------
# Role glyph — Maya prefers a shield for admin instead of the ADMIN text.
# Returns ready-to-render HTML so callers can drop it inline.
# ---------------------------------------------------------------------------
_ROLE_GLYPHS = {
    "admin":   ("\U0001F6E1",  "var(--kn-accent)"),  # shield
    "editor":  ("\u270D",      "var(--kn-primary)"),  # writing hand
    "visitor": ("\U0001F33F",  "var(--kn-muted)"),    # herb leaf
}


def role_glyph(role: str | None, size_px: int = 16) -> str:
    glyph, color = _ROLE_GLYPHS.get(role or "visitor", _ROLE_GLYPHS["visitor"])
    return (
        f'<span title="{(role or "guest").capitalize()}" '
        f'style="display:inline-block;color:{color};font-size:{size_px}px;'
        f'vertical-align:middle;margin-left:6px;line-height:1">{glyph}</span>'
    )

def avatar_html(url_or_data: str | None, size_px: int = 44) -> str:
    """Tiny circular avatar. Used by the sidebar identity card so the
    sidebar shows your face, not just your name. Falls back to a soft
    placeholder when no avatar is set."""
    if url_or_data:
        return (
            f'<span style="display:inline-block;width:{size_px}px;'
            f'height:{size_px}px;border-radius:50%;overflow:hidden;'
            f'border:1px solid var(--kn-rule);background:var(--kn-bg);'
            f'vertical-align:middle">'
            f'<img src="{url_or_data}" '
            f'style="width:100%;height:100%;object-fit:cover" alt=""></span>'
        )
    return (
        f'<span style="display:inline-flex;width:{size_px}px;'
        f'height:{size_px}px;border-radius:50%;background:var(--kn-bg);'
        f'border:1px solid var(--kn-rule);align-items:center;'
        f'justify-content:center;color:var(--kn-muted);'
        f'font-size:{int(size_px/2)}px;vertical-align:middle">·</span>'
    )

