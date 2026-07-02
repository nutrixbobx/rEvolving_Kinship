"""
Request station and dashboard, in one small Streamlit app.

  - "Request station" is the kiosk. A visitor searches by common or scientific
    name, picks a real match, and it joins the tree with its NCBI TaxID, group,
    and clade ranks filled. A short note can ride along.
  - "Dashboard" shows the warehouse, the tree (switch between rectangular,
    circular, unrooted), the chord, lets you edit any species' fields and
    rename or rebuild a tree.

Run it with:
    streamlit run app/station.py
"""

from __future__ import annotations

import os
import traceback
import sys
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

# === Streamlit Cloud bridge: copy st.secrets to os.environ so the rest of the
# code (which reads from os.environ everywhere) works whether you are running
# locally with a .env file or on Streamlit Cloud with secrets.toml.
try:
    if hasattr(st, "secrets"):
        for _k in ("DATABASE_URL", "ADMIN_PASSWORD",
                   "XENO_CANTO_API_KEY", "GROQ_API_KEY", "HF_TOKEN",
                   "NCBI_TAXA_DB"):
            if _k in st.secrets and not os.environ.get(_k):
                os.environ[_k] = str(st.secrets[_k])
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
from src import db  # noqa: E402
from src import render as render_mod  # noqa: E402
from src import taxonomy_search as ts  # noqa: E402
from src import theme  # noqa: E402
from src import species_profile  # noqa: E402
from src import species_player  # noqa: E402
from src import tree_settings  # noqa: E402
from src import library  # noqa: E402
from src import i18n  # noqa: E402
from src import auth  # noqa: E402
from src.credits import format_credit  # noqa: E402
from src import profile  # noqa: E402
from src import ai_blurb  # noqa: E402
from src import usage_log  # noqa: E402

st.set_page_config(
    page_title="{r}Evolving Kinship",
    page_icon="🌿",  # herb leaf — matches the river/earth theme
    layout="wide",
    initial_sidebar_state="auto",
    menu_items={
        "Get help": "https://shared-rivers.org",
        "Report a bug": "mailto:maya@shared-rivers.org",
        "About": ("{r}Evolving Kinship is a participatory "
                  "ecological art piece by Shared Rivers. "
                  "shared-rivers.org"),
    },
)


@st.cache_resource(show_spinner=False)
def _verified_db_init():
    """Run the v2 schema verification once per session, not every rerun."""
    db.init_db()
    return True


_verified_db_init()

# Apply the unified theme on every load. If the signed-in user has
# a saved theme pick (loaded further down after auth), we override
# the palette variables — see the second inject_css call at the top
# of Dashboard / Library / Profile blocks.
theme.inject_css(st.session_state.get("user_theme"))

# One-time NCBI taxonomy download. If it isn't on disk yet, this
# takes over the whole page with a fun-fact loading card and reruns
# every few seconds until the file is there.
from src import loading  # noqa: E402
if loading.render_loading_gate_if_needed():
    st.stop()

# Pre-init cookie manager + try restore before anything else renders.
# CookieManager's component reads from the browser asynchronously, so the
# very first script run after a page load gets an empty cookie dict.
# Streamlit auto-reruns when the component sends real data; on that rerun
# the cookie is available and the user is signed in silently. By calling
# _try_cookie_restore here, we make sure the restore happens BEFORE the
# auth gate decides whether to show the sign-in form.
# Read the URL session token (if any) and sign the user in silently.
# Synchronous — no async iframe / cookie sync race. Either the token in
# the URL is valid and we're signed in, or it isn't and we show the gate.
auth._try_cookie_restore()


def _stem(name: str) -> str:
    """Tree-name slug used for output filenames. Delegates to tree._safe so
    rename and rebuild share one canonical definition of safety."""
    from src.tree import _safe as _tree_safe
    return _tree_safe(name).lower()


def _label(hit: dict) -> str:
    if hit["common_name"]:
        return f"{hit['common_name']} ({hit['scientific_name']}) [{hit['rank']}]"
    return f"{hit['scientific_name']} [{hit['rank']}]"




# Light Python-level memoization. Streamlit's @st.cache_data had reliability
# issues with the large HTML payloads (and the previous wrappers contained a
# self-recursing bug). The underlying functions already disk-cache, so this
# in-memory dict is enough for a session.
_PROFILE_CACHE: dict = {}
_AUDIO_CACHE: dict = {}
_PLAYER_CACHE: dict = {}


def _cached_profile(sci, common):
    key = (sci, common)
    if key in _PROFILE_CACHE:
        return _PROFILE_CACHE[key]
    try:
        v = species_profile.find_profile(sci, common)
    except Exception:
        v = None
    _PROFILE_CACHE[key] = v
    return v


def _cached_audio(sci, common):
    key = (sci, common)
    if key in _AUDIO_CACHE:
        return _AUDIO_CACHE[key]
    try:
        from src import species_audio as _sa
        rec = _sa.find_recording(sci, common)
    except Exception:
        rec = None
    out = (None if not rec
           else {"path": str(rec["path"]),
                 "attribution": rec.get("attribution", ""),
                 "source": rec.get("source", "")})
    _AUDIO_CACHE[key] = out
    return out


@st.cache_data(ttl=300, show_spinner=False)
def _cached_list_trees_for_dashboard():
    """Cache the trees-in-warehouse list for 60s so the picker doesn't
    refetch on every interaction. Invalidated implicitly by TTL when admins
    add/remove via the dashboard."""
    return db.list_trees()


@st.cache_data(ttl=300, show_spinner=False)
def _cached_read_tree(tree_name):
    """Cache one tree's species DataFrame for 60s. Invalidated by TTL after
    the kiosk adds a species; admin edits call .clear() to refresh now."""
    return db.read_tree(tree_name)


@st.cache_data(ttl=300, show_spinner=False)
def _cached_tree_species_picker(tree_name):
    """Cache the per-tree name picker. The query is a 1-shot scan of
    tree_species + species_name; caching it 60s removes a noticeable hit
    on every Dashboard interaction."""
    return db.list_tree_species_with_names(tree_name)


@st.cache_data(ttl=600, show_spinner=False)
def _clade_browser_lookup(tree_name: str, nwk_path: str,
                           clade_name: str) -> dict:
    """Resolve a clade in the tree to (rep photo, rep species, species
    list). Cached per (tree_name, clade_name) for 10 minutes so
    switching between clades is instant on the second visit."""
    from pathlib import Path as _P
    import json as _json
    from ete3 import Tree as _Tree
    from src import species_profile
    p = _P(nwk_path)
    if not p.exists():
        return {}
    t = _Tree(p.read_text(), format=1)
    nodes = t.search_nodes(name=clade_name)
    if not nodes:
        return {}
    meta_path = p.parent / p.name.replace(
        "_named_tree.nwk", "_nodes.json").replace(
        "_scaled_tree.nwk", "_nodes.json")
    meta = _json.loads(meta_path.read_text()) if meta_path.exists() else {}
    rep_photo_url = None
    rep_common = None
    rep_sci = None
    species_under: list[str] = []
    for lf in nodes[0].get_leaves():
        lm = meta.get(lf.name, {})
        sci = lm.get("scientific_name")
        if not sci:
            continue
        species_under.append(lm.get("common_name") or sci)
        if rep_photo_url is None:
            try:
                prof = species_profile.find_profile(sci, lm.get("common_name"))
            except Exception:
                prof = None
            if prof and prof.get("image_url"):
                rep_photo_url = prof["image_url"]
                rep_common = lm.get("common_name")
                rep_sci = sci
    return {
        "photo_url": rep_photo_url,
        "rep_common": rep_common,
        "rep_sci": rep_sci,
        "species_under": species_under,
    }


def _fav_toggle_for_tree(tree_name: str) -> None:
    """Render a ⭐/☆ favorite toggle for the currently-picked tree. Visible
    to any named user. No-op when not named."""
    cid = auth.active_contributor_id()
    if not cid or auth.is_guest():
        return
    tree_id = db.get_tree_id(tree_name)
    if not tree_id:
        return
    is_fav = db.is_tree_favorited(cid, tree_id)
    label = "★ Favorited" if is_fav else "☆ Favorite this tree"
    if st.button(label, key=f"fav_{tree_name}",
                  use_container_width=True,
                  type=("secondary" if is_fav else "primary")):
        if is_fav:
            db.unfavorite_tree(cid, tree_id)
        else:
            db.favorite_tree(cid, tree_id)
        # Profile favorites cache lives in profile.py — clear it so the
        # 'Favorites' tab reflects the change.
        try:
            from src import profile as _p
            _p._cached_favorites.clear()
            _p._cached_follow_counts.clear()
        except Exception:
            pass
        st.rerun()


def _safe_url(url: str | None) -> str:
    """URL-encode unsafe characters so a markdown link [text](url)
    doesn't break on spaces, parens, etc. Wikipedia URLs from iNat
    sometimes come back with raw spaces in the species path."""
    if not url:
        return ""
    # Keep already-encoded sequences but quote spaces + parens
    import urllib.parse as _u
    # Split into prefix + path so we don't double-encode the scheme
    if "://" in url:
        scheme, rest = url.split("://", 1)
        # quote everything except already-encoded %XX sequences
        rest = _u.quote(rest, safe="/:?#=&%")
        return f"{scheme}://{rest}"
    return _u.quote(url, safe="/:?#=&%")


def _invalidate_dashboard_caches():
    _cached_list_trees_for_dashboard.clear()
    _cached_read_tree.clear()
    _cached_tree_species_picker.clear()


def _cached_player_html(common, sci, path_str, attribution):
    key = (common, sci, path_str, attribution)
    if key in _PLAYER_CACHE:
        return _PLAYER_CACHE[key]
    from pathlib import Path
    out = species_player.player_html(common, sci, Path(path_str), attribution)
    _PLAYER_CACHE[key] = out
    return out

# --- Auth gate ------------------------------------------------------
# Sidebar holds the identity card once named. The landing screen below
# carries the sign-in / sign-up / guest forms so phone visitors do not
# have to discover the collapsed sidebar.
auth.render_sidebar_gate()

if not auth.is_named():
    theme.app_header("{r}Evolving Kinship", tree_settings.PROJECT_SLOGAN)
    auth.render_main_gate()
    theme.render_footer(tree_settings.PROJECT_SLOGAN)
    st.stop()

theme.app_header("{r}Evolving Kinship", tree_settings.PROJECT_SLOGAN)
# Custom tab navigation: a radio backed by session_state. st.tabs()
# resets to the first tab on every st.rerun() (a known Streamlit
# behaviour) which kept booting users off the Dashboard whenever they
# built a tree. Radios DO preserve their value via session_state, so we
# use one and conditionally render the body of each "tab".
_TAB_NAMES = ["Request station", "Dashboard", "Range map", "Library", "Profile"]
active_tab = st.radio(
    "Section", _TAB_NAMES, key="active_tab", horizontal=True,
    label_visibility="collapsed")

# ---------------------------------------------------------------------------
# Request station (the kiosk)
# ---------------------------------------------------------------------------
if active_tab == "Request station":
    with st.expander("About the technology", expanded=False):
        st.markdown(
            "**Where the data comes from**\n\n"
            "- **Species names and the tree topology** come from the "
            "[NCBI Taxonomy](https://www.ncbi.nlm.nih.gov/taxonomy), "
            "the same database biologists rely on daily. When you type "
            "*coyote*, the search hits a local copy of NCBI's tree.\n"
            "- **Divergence ages** (the numbers on the amber clade "
            "nodes) come from [TimeTree of Life]"
            "(https://timetree.org), a curated chronology of when "
            "lineages split.\n"
            "- **Species photos** come from "
            "[iNaturalist](https://www.inaturalist.org), filtered to "
            "Creative Commons licenses only.\n"
            "- **Species recordings** come from "
            "[Xeno-canto](https://xeno-canto.org) (all CC-licensed by "
            "platform policy) and "
            "[Wikimedia Commons](https://commons.wikimedia.org).\n"
            "- **Range maps** come from "
            "[GBIF](https://www.gbif.org) occurrence density tiles.\n\n"
            "**What runs the app**\n\n"
            "- Python + [Streamlit](https://streamlit.io) for the "
            "browser interface.\n"
            "- [Supabase](https://supabase.com) Postgres for the "
            "community database (contributions, accounts, ownership).\n"
            "- The kinship tree drawing uses "
            "[toytree](https://toytree.readthedocs.io) and "
            "matplotlib.\n"
            "- The kinship chord + audio blending use "
            "[librosa](https://librosa.org) + SciPy.\n\n"
            "**Everything is open**. The pipeline is released under "
            "CC BY-SA. Take it, remix it, stand up your own waterway "
            "or foodway or ecology piece.")

    with st.expander("How this works (read me first)", expanded=False):
        st.markdown(
            "**1.** Name one or more species you feel kin to. Search by common name "
            "(coyote) or scientific name (Canis latrans), pick the match, and hit "
            "**Add to the tree**.\n\n"
            "**2.** Open the **Dashboard** tab, pick your tree, and click "
            "**Build / refresh**. The tree draws itself, the chord rings, the photos "
            "fetch, and a short note appears under it.\n\n"
            "**3.** Hover the tree to read the tips, listen to each species, build a "
            "meditation track, or download the press files. The raw Newick is in "
            "there too, in case you want to take this tree elsewhere."
        )
    theme.section_heading("Name a species you feel kin to",
                          kicker="Request station")

    trees = _cached_list_trees_for_dashboard()
    existing = trees["tree_name"].tolist() if not trees.empty else []
    choice = st.selectbox(
        "Which tree are you adding to?", existing + ["+ start a new tree"]
    )
    tree_name = (
        st.text_input("Name the new tree", "")
        if choice == "+ start a new tree"
        else choice
    )

    # NCBI taxonomy is guaranteed to be ready here (loading gate at
    # the top of the file blocks the app until taxa.sqlite lands),
    # so `ready` is effectively always True. Keeping the variable for
    # the downstream `if ready and len(query) >= 2` search path.
    ready = ts.is_ready()

    st.markdown("**Search** a common or scientific name")
    query = st.text_input(
        "search", label_visibility="collapsed",
        placeholder="coyote, white oak, Canis latrans ...",
        help="Type a few letters of a common name (coyote) or a scientific name "
             "(Canis latrans), then pick from the matches. Choosing one fills "
             "the NCBI TaxID, the group, and the clades automatically.",
    )

    pick = None
    if ready and len(query.strip()) >= 2:
        results = ts.search_species(query, limit=12)
        if results:
            idx = st.selectbox(
                "Matches", range(len(results)),
                format_func=lambda i: _label(results[i]),
            )
            pick = results[idx]
        else:
            st.caption("No matches yet. Keep typing the common or scientific name.")

    notes = st.text_area(
        "Notes (optional)", "",
        height=68,
        help="Any extra context to keep with this species: a grocery equivalent, "
             "a memory, where it was spotted, anything.",
    )

    _guest_lock = not auth.can_write()
    if _guest_lock:
        st.info("Guests can search + browse but can't add species to a "
                 "tree. Head to your Profile to upgrade with an access "
                 "code, then come back here.")
    if st.button("Add to the tree", type="primary", disabled=_guest_lock):
        if not tree_name.strip():
            st.warning("Name the tree first.")
        elif not pick:
            st.warning("Search for a species and pick a match first.")
        else:
            lineage = None
            try:
                lineage = ts.lineage_for_taxid(pick["taxid"])
            except Exception:
                pass
            is_new = db.insert_request(
                tree_name=tree_name.strip(),
                scientific_name=pick["scientific_name"],
                common_name=pick["common_name"] or None,
                ncbi_taxid=pick["taxid"],
                domain=(lineage or {}).get("domain"),
                lineage=lineage,
                notes=notes.strip() or None,
                submitted_by=auth.current_user().get("name") or None,
                contributor_id=auth.active_contributor_id(),
            )
            label = pick["common_name"] or pick["scientific_name"]
            if is_new:
                _invalidate_dashboard_caches()
                st.success(f"{label} joined {tree_name}.")
            else:
                st.info(f"{pick['scientific_name']} is already in {tree_name}.")

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
if active_tab == "Dashboard":
    # Admin: force re-download taxa.sqlite when corruption is suspected
    # (the build-images error "database disk image is malformed" comes
    # from a half-downloaded or stale taxa.sqlite on the Cloud container.)
    if auth.is_admin():
        with st.expander("Rebuild taxonomy file (admin)",
                          expanded=False):
            st.caption(
                "If you see 'database disk image is malformed' when "
                "building photos or running the pipeline, the cached "
                "taxa.sqlite on this Streamlit Cloud container is "
                "corrupt. Click below to delete + re-download the "
                "fresh copy from your NCBI_TAXA_URL release "
                "(~30 seconds).")
            if st.button("Force re-download taxa.sqlite",
                          key="force_taxa_redl",
                          type="primary"):
                from src import setup_ncbi
                with st.spinner("Deleting + re-downloading "
                                  "taxa.sqlite..."):
                    ok = setup_ncbi.force_redownload()
                if ok:
                    st.success("Done. Rebuild your tree to try again.")
                else:
                    st.error("Re-download failed. Check that "
                              "NCBI_TAXA_URL is set in Streamlit "
                              "secrets and points at a valid file.")

    trees = _cached_list_trees_for_dashboard()
    if trees.empty:
        st.info("No species yet. Add some on the request station tab, or run "
                "`make load` to import the sample data.")
    else:
        with st.expander("How to build your tree (read me first)", expanded=False):
            st.markdown(
                "Pick a tree below, then click **Build / refresh** on the right to "
                "compute its topology, draw it, sound the chord, fetch the photos, and "
                "write a short note. The first build takes a minute or two. "
                "After that, every other section comes alive: hover the tips, listen to "
                "each species, download the press files, mix a meditation track."
            )
        pick_tree = st.selectbox("Pick a tree",
                                 trees["tree_name"].tolist())
        _fav_toggle_for_tree(pick_tree)

        # Tree personalization right under T0 (the picker) so the
        # admin-customization fields are co-located with the tree they
        # apply to instead of buried way down the page.
        if auth.is_admin():
            with st.expander("Tree personalization (admin)",
                              expanded=False):
                cur = tree_settings.get_tree_settings(pick_tree)
                owner_in = st.text_input(
                    "Owner name",
                    value=cur.get("owner", ""),
                    key=f"owner_{pick_tree}",
                    help="Used in the header of generated graphics.")
                tmpl_in = st.text_input(
                    "Title template",
                    value=cur.get(
                        "title_template",
                        tree_settings.DEFAULT_TEMPLATE),
                    key=f"tmpl_{pick_tree}",
                    help="Use {owner} as the placeholder.")
                if st.button("Save personalization",
                             key=f"save_owner_{pick_tree}"):
                    tree_settings.set_tree_settings(
                        pick_tree, owner=owner_in.strip(),
                        title_template=tmpl_in.strip())
                    st.success("Saved.")
                    st.rerun()
                st.caption("Will render as: "
                            f"“{tree_settings.title_for(pick_tree)}”")

        try:
            df = _cached_read_tree(pick_tree)
        except Exception as _exc:
            st.error("Could not load this tree from the database. "
                      f"Try again, or contact Maya. ({_exc})")
            st.stop()
        headers = {
            "common_name": "Common", "scientific_name": "Scientific",
            "genus": "Genus", "family": "Family", "order_": "Order",
            "class_": "Class", "phylum": "Phylum", "kingdom": "Kingdom",
            "domain": "Group", "ncbi_taxid": "TaxID", "notes": "Notes",
        }
        present = [c for c in headers if c in df.columns]
        st.dataframe(
            df[present].rename(columns=headers),
            use_container_width=True, hide_index=True,
        )

        stem = _stem(pick_tree)
        nwk = config.OUTPUT_DIR / f"{stem}_named_tree.nwk"
        meta_path = config.OUTPUT_DIR / f"{stem}_nodes.json"
        mid = config.OUTPUT_DIR / f"{stem}_chord.mid"
        wav = config.OUTPUT_DIR / f"{stem}_chord.wav"
        meta = render_mod.load_meta(meta_path) if meta_path.exists() else {}
        n_dated = sum(1 for v in meta.values()
                      if not v.get("is_leaf") and v.get("mya") is not None)

        view, side = st.columns([3, 1])
        with side:
            # Visible build button up here so mobile users don't have to scroll
            # past the whole page to find it.
            # Row 1: Build + Download nwk side by side (Maya wants these
            # near each other since they're related actions)
            top_cols = st.columns([2, 1])
            with top_cols[0]:
                if st.button(f"Build / refresh  “{pick_tree}”",
                             type="primary",
                             key=f"build_top_{pick_tree}",
                             use_container_width=True):
                    with loading.spinner_with_tip("Resolving taxonomy, building the tree, "
                                    "rendering, and sonifying. The first "
                                    "ever run also downloads the NCBI "
                                    "taxonomy (~5 min)."):
                        try:
                            from src import pipeline
                            pipeline.run(pick_tree)
                            st.success("Built. Reloading.")
                            st.rerun()
                        except SystemExit as exc:
                            st.error(str(exc))
                        except Exception as exc:
                            st.error(f"Build failed: {exc}")
            with top_cols[1]:
                if nwk.exists():
                    st.download_button(".nwk", nwk.read_bytes(),
                                       file_name=nwk.name,
                                       mime="text/plain",
                                       use_container_width=True,
                                       key=f"nwk_top_{pick_tree}")
            layout_name = st.radio("Layout", list(render_mod.LAYOUTS.keys()))
            show_sci = st.checkbox("Show scientific names", value=True)
            zoom_pct = st.slider(
                "Zoom", min_value=50, max_value=130, value=85, step=5,
                key=f"zoom_{pick_tree}",
                help="100% = native; lower = fits more in view; "
                     "higher = closer detail.",
                format="%d%%")
            st.caption(f"{len(df)} species, {n_dated} dated node(s). "
                       "Legend + 'mya' explanation are inside every "
                       "exported tree. Hover any node for its details.")

            with st.expander("Quick look at a species", expanded=False):
                sci_names = sorted(df["scientific_name"].dropna().unique().tolist())
                ql = st.selectbox("Pick", [""] + sci_names,
                                  format_func=lambda x: x or "(none)",
                                  key=f"ql_{pick_tree}")
                if ql:
                    row = df[df["scientific_name"] == ql].iloc[0]
                    try:
                        _sp_profile = _cached_profile(ql, row.get("common_name"))
                    except Exception:
                        _sp_profile = None
                    if _sp_profile and _sp_profile.get("image_path"):
                        st.image(_sp_profile["image_path"], use_container_width=True)
                        if _sp_profile.get("image_attribution"):
                            st.caption(format_credit(_sp_profile["image_attribution"]))
                    if _sp_profile:
                        st.markdown(f"**{row.get('common_name') or ql}**  "
                                    f"*{ql}*")
                        st.write((_sp_profile.get("summary") or "")[:500])
                        link_bits = []
                        for lab, key in (("Wikipedia", "wikipedia_url"),
                                         ("iNaturalist", "inaturalist_url"),
                                         ("GBIF", "gbif_url")):
                            if _sp_profile.get(key):
                                link_bits.append(f"[{lab}]({_safe_url(_sp_profile[key])})")
                        if link_bits:
                            st.markdown(" · ".join(link_bits))

            if st.button("Export species list for TimeTree"):
                from src import timetree
                p = timetree.export_species_list(pick_tree)
                st.success(f"Wrote {p.name}. Upload it at timetree.org, save the "
                           f"result as data/{stem}_timetree.nwk, then rebuild.")

            # ━━━ Kinship Sonification ━━━
            st.markdown("---")
            st.markdown("### Kinship Sonification")
            chorus = config.OUTPUT_DIR / f"{stem}_chorus.wav"

            # 1. Kinship chord (ecosystem chord)
            st.markdown("**Kinship chord**")
            if wav.exists():
                st.audio(wav.read_bytes(), format="audio/wav")
            if mid.exists():
                st.download_button("Download chord (.mid)",
                                    mid.read_bytes(),
                                    file_name=mid.name,
                                    mime="audio/midi",
                                    key=f"chord_dl_{pick_tree}")

            # 2. Animal chorus
            st.markdown("**Animal chorus**")
            if chorus.exists():
                st.audio(chorus.read_bytes(), format="audio/wav")
            if st.button("Build / refresh chorus",
                         key=f"chorus_{pick_tree}"):
                with st.spinner("Fetching recordings from Xeno-Canto + "
                                  "Wikipedia and blending."):
                    try:
                        from src import audio_blend
                        res = audio_blend.build_chorus(pick_tree)
                        if res is None:
                            st.info("No recordings found.")
                        else:
                            st.success(
                                f"Built chorus with "
                                f"{len(res['voices'])} voice(s).")
                            st.rerun()
                    except Exception as exc:
                        st.error(f"Chorus build failed: {exc}")

            # 3. Meditation track
            st.markdown("**Meditation track**")
            med_min = st.radio("Length", [1, 2, 5],
                               format_func=lambda m: f"{m} min",
                               horizontal=True,
                               key=f"med_min_{pick_tree}")
            med_secs = med_min * 60
            med_path = config.OUTPUT_DIR / f"{stem}_meditation_{med_secs}s.wav"
            if med_path.exists():
                st.audio(med_path.read_bytes(), format="audio/wav")
                st.download_button(
                    f"Download {med_min} min meditation",
                    med_path.read_bytes(), file_name=med_path.name,
                    mime="audio/wav",
                    key=f"med_dl_{pick_tree}_{med_secs}")
            if st.button(f"Build {med_min} min meditation",
                         key=f"med_build_{pick_tree}_{med_secs}"):
                with st.spinner(f"Blending the chord and the chorus into "
                                  f"a {med_min} min track."):
                    try:
                        from src import meditation
                        res = meditation.build_meditation(pick_tree,
                                                            med_secs)
                        if res is None:
                            st.info("Need a dated clade (the chord) to "
                                    "build a meditation track.")
                        else:
                            st.success(
                                f"Built {med_min} min meditation "
                                f"({'with chorus' if res['has_chorus'] else 'chord only'}).")
                            st.rerun()
                    except Exception as exc:
                        st.error(f"Build failed: {exc}")
        with view:
            if nwk.exists() and meta:
                html = render_mod.render_html(
                    nwk, meta, layout=render_mod.LAYOUTS[layout_name],
                    show_scientific=show_sci, tree_name=pick_tree,
                    zoom=zoom_pct / 100.0,
                )
                components.html(html, height=740, scrolling=True)

                # Download the current layout (SVG + PNG)
                dl_cols = st.columns(2)
                with dl_cols[0]:
                    if st.button(f"Build {layout_name} SVG / PNG",
                                 key=f"dl_build_{pick_tree}_{layout_name}"):
                        layout_code = render_mod.LAYOUTS[layout_name]
                        out = render_mod.render_files(
                            nwk, meta,
                            f"{stem}_tree_{layout_name.lower()}",
                            layout=layout_code, tree_name=pick_tree)
                        usage_log.log_event("render_tree", pick_tree)
                        st.success("Files ready below.")
                        st.rerun()
                with dl_cols[1]:
                    svg_p = config.OUTPUT_DIR / f"{stem}_tree_{layout_name.lower()}.svg"
                    png_p = config.OUTPUT_DIR / f"{stem}_tree_{layout_name.lower()}.png"
                    if svg_p.exists():
                        st.download_button(
                            f"SVG ({layout_name})", svg_p.read_bytes(),
                            file_name=svg_p.name, mime="image/svg+xml",
                            key=f"dl_svg_{pick_tree}_{layout_name}")
                    if png_p.exists():
                        st.download_button(
                            f"PNG ({layout_name})", png_p.read_bytes(),
                            file_name=png_p.name, mime="image/png",
                            key=f"dl_png_{pick_tree}_{layout_name}")
                # Short note under the tree, generated or LLM-written
                try:
                    b = ai_blurb.blurb_for_tree(pick_tree)
                    usage_log.log_event(
                        "blurb_template" if b.get("source") == "template"
                        else "blurb_remote", pick_tree)
                    st.markdown("&nbsp;")
                    body = b["text"].replace("\n\n", "  \n\n")
                    st.markdown(body)
                    src_lbl = {
                        "template": "generated from this tree’s structure",
                        "groq": "written by an LLM via Groq",
                        "hugging-face": "written by an LLM via Hugging Face",
                    }.get(b.get("source", ""), b.get("source", ""))
                    cached_tag = " (cached)" if b.get("cached") else ""
                    st.caption(f"{src_lbl}{cached_tag}")
                    if st.button("Refresh this note",
                                 key=f"blurb_refresh_{pick_tree}"):
                        ai_blurb.blurb_for_tree(pick_tree,
                                                force_refresh=True)
                        st.rerun()
                except Exception as exc:
                    st.warning(f"note unavailable: {exc}")
            else:
                st.caption("This tree has not been built yet. Use the button "
                           "below.")

        st.divider()

        # Sub-nav for the sections below the tree. Keeps the scroll
        # short and lets users focus on one cluster at a time.
        # Radio (not st.tabs) so the choice persists via session_state
        # across reruns.
        _DASH_SUB = ["Outputs", "Customize", "Listen", "Footprint"]
        _sub = st.radio(
            "Dashboard section", _DASH_SUB,
            key=f"dash_sub_tab_{pick_tree}",
            horizontal=True, label_visibility="collapsed")

        # Bottom action row: rename + photo trees + PDF (build button is
        # at the top of the side column, no need to duplicate here).
        # Artifacts take 3/4 width; rename fits in 1/4 on the right.
        build_col, rename_col = st.columns([3, 1])
        with build_col:
            if _sub != "Outputs":
                st.empty()  # placeholder — Outputs section is gated below
            # ═══════════════════════════════════════════════════════════
            # Generated artifacts (gated by sub-nav)
            # ═══════════════════════════════════════════════════════════
            if _sub == "Outputs":
              st.markdown("---")
              # ─── Personalized kinship report (TOP) ───────────────────
              st.markdown("### Personalized kinship report (PDF)")
              st.caption("Five-page report: hero unrooted-with-photos, "
                         "project info + license + footprint, photo-"
                         "spectral tree, spectrogram blend + range map, "
                         "credits, kin cards.")
              press_pdf_path = config.OUTPUT_DIR / f"{stem}_kinship_report.pdf"
              _rep_cols = st.columns([1, 1])
              with _rep_cols[0]:
                  if st.button("Build / refresh kinship report",
                               key=f"presspdf_{pick_tree}",
                               type="primary",
                               use_container_width=True):
                      with loading.spinner_with_tip("Composing the kinship report. "
                                        "This can take a minute if photos "
                                        "are being fetched for the first "
                                        "time."):
                          try:
                              from src import press_pdf
                              press_pdf.build_press_pdf(pick_tree)
                              st.success("Built. Download below.")
                              st.rerun()
                          except Exception as exc:
                              st.error(f"PDF build failed: {exc}")
              with _rep_cols[1]:
                  if press_pdf_path.exists():
                      st.download_button(
                          "Download kinship report (.pdf)",
                          press_pdf_path.read_bytes(),
                          file_name=press_pdf_path.name,
                          mime="application/pdf",
                          use_container_width=True,
                          key=f"presspdf_dl_{pick_tree}")

              # ─── T1 + T2 side-by-side ─────────────────────────────────
              st.markdown("---")
              st.markdown("### Tree variants")
              _tree_cols = st.columns(2)
              with _tree_cols[0]:
                  st.markdown("**T1 — Photo-Spectral Tree** (rectangular)")
                  photo_audio = config.OUTPUT_DIR / f"{stem}_photo_audio.png"
                  if photo_audio.exists():
                      st.image(photo_audio.read_bytes())
                      st.download_button(
                          "Download (.png)", photo_audio.read_bytes(),
                          file_name=photo_audio.name, mime="image/png",
                          use_container_width=True,
                          key=f"photoaudio_dl_{pick_tree}")
                  if st.button("Build / refresh T1",
                               key=f"photoaudio_{pick_tree}",
                               use_container_width=True):
                      with st.spinner("Fetching photos + audio, rendering "
                                        "spectrograms, composing tree."):
                          try:
                              from src import photo_audio_tree
                              photo_audio_tree.build_photo_audio_tree(
                                  pick_tree)
                              st.success("Built.")
                              st.rerun()
                          except Exception as exc:
                              st.error(f"T1 build failed: {exc}")
              with _tree_cols[1]:
                  st.markdown("**T2 — Unrooted Tree with Photos**")
                  photo_tips = config.OUTPUT_DIR / f"{stem}_photo_tips.png"
                  if photo_tips.exists():
                      st.image(photo_tips.read_bytes())
                      st.download_button(
                          "Download (.png)", photo_tips.read_bytes(),
                          file_name=photo_tips.name, mime="image/png",
                          use_container_width=True,
                          key=f"phototips_dl_{pick_tree}")
                  if st.button("Build / refresh T2",
                               key=f"phototips_{pick_tree}",
                               use_container_width=True):
                      with st.spinner("Fetching photos + drawing "
                                        "tip thumbnails."):
                          try:
                              from src import photo_tip_tree
                              photo_tip_tree.build_photo_tip_tree(pick_tree)
                              st.success("Built.")
                              st.rerun()
                          except Exception as exc:
                              st.error(f"T2 build failed: {exc}")

              # ─── Spectrogram Blend + Range map side-by-side ───────────
              st.markdown("---")
              st.markdown("### Composites")
              _comp_cols = st.columns(2)
              with _comp_cols[0]:
                  st.markdown("**Spectrogram Blend**")
                  blend_png = config.OUTPUT_DIR / f"{stem}_spectrogram_blend.png"
                  if blend_png.exists():
                      st.image(blend_png.read_bytes())
                      st.download_button(
                          "Download (.png)", blend_png.read_bytes(),
                          file_name=blend_png.name, mime="image/png",
                          use_container_width=True,
                          key=f"specblend_dl_{pick_tree}")
                  if st.button("Build / refresh blend",
                               key=f"specblend_{pick_tree}",
                               use_container_width=True):
                      with st.spinner("Overlaying every spectrogram..."):
                          try:
                              from src import spectrogram_blend
                              spectrogram_blend.build_spectrogram_blend(
                                  pick_tree)
                              st.success("Built.")
                              st.rerun()
                          except Exception as exc:
                              st.error(f"Blend build failed: {exc}")
              with _comp_cols[1]:
                  st.markdown("**Range map (static)**")
                  range_png = config.OUTPUT_DIR / f"{stem}_range_map.png"
                  if range_png.exists():
                      st.image(range_png.read_bytes())
                      st.download_button(
                          "Download (.png)", range_png.read_bytes(),
                          file_name=range_png.name, mime="image/png",
                          use_container_width=True,
                          key=f"rangemap_dl_{pick_tree}")
                  if st.button("Build / refresh range map",
                               key=f"rangemap_{pick_tree}",
                               use_container_width=True):
                      with loading.spinner_with_tip("Fetching CARTO basemap + GBIF "
                                        "density per species. ~30s."):
                          try:
                              from src import range_map_static
                              range_map_static.build_range_map(pick_tree)
                              st.success("Built.")
                              st.rerun()
                          except Exception as exc:
                              st.error(f"Range map build failed: {exc}")

              # ─── Credits at bottom ────────────────────────────────────
              st.markdown("---")
              st.markdown("### All credits (.txt)")
              st.caption("Every species' photo + audio attribution, with "
                         "license links.")
              credits_txt = config.OUTPUT_DIR / f"{stem}_credits.txt"
              _cred_cols = st.columns([1, 1])
              with _cred_cols[0]:
                  if st.button("Build / refresh credits",
                               key=f"credits_build_{pick_tree}",
                               use_container_width=True):
                      with st.spinner("Aggregating credits..."):
                          try:
                              from src.credits import write_credits_txt
                              write_credits_txt(pick_tree, credits_txt)
                              st.success("Built.")
                              st.rerun()
                          except Exception as exc:
                              st.error(f"Credits build failed: {exc}")
              with _cred_cols[1]:
                  if credits_txt.exists():
                      st.download_button(
                          "Download credits (.txt)",
                          credits_txt.read_bytes(),
                          file_name=credits_txt.name,
                          mime="text/plain",
                          use_container_width=True,
                          key=f"credits_dl_{pick_tree}")

        with rename_col:
            new_name = st.text_input("Rename this tree", value=pick_tree,
                                     key=f"rename_{pick_tree}")
            # Lock down rename to people who own this tree (or admins).
            _owner_info = db.get_tree_owner_info(pick_tree) or {}
            _can_edit_this_tree = auth.can_edit_tree(_owner_info)
            if st.button("Save tree name", disabled=not _can_edit_this_tree):
                try:
                    n = db.rename_tree(pick_tree, new_name)
                    st.success(f"Renamed {n} row(s). Rebuild so the output "
                               "files match the new name.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
            if not _can_edit_this_tree:
                _owner_label = _owner_info.get("owner_display_name") or "an admin"
                st.caption(f"This tree is curated by {_owner_label}. "
                           "Sign in as the owner to rename.")

            # Ownership transfer. Owners can hand off to any signed-in
            # user; admins can transfer any tree (including grabbing it
            # to themselves for moderation / seeding).
            _me_cid = auth.active_contributor_id()
            cur_owner_id = (_owner_info or {}).get("owner_id")
            _can_transfer = (auth.is_admin()
                              or (_me_cid and _me_cid == cur_owner_id))
            if _can_transfer and _me_cid:
                with st.expander("Transfer ownership", expanded=False):
                    # Transfer to self (handy for admins grabbing a tree)
                    if cur_owner_id != _me_cid:
                        if st.button("Transfer to me",
                                     key=f"transfer_self_{pick_tree}",
                                     use_container_width=True):
                            db.set_tree_owner(pick_tree, _me_cid)
                            _invalidate_dashboard_caches()
                            st.success("Ownership transferred to you.")
                            st.rerun()
                    # Transfer to any other signed-in user
                    try:
                        _users = db.list_signed_in_users()
                    except Exception:
                        _users = None
                    if _users is not None and not _users.empty:
                        # Drop self from the dropdown — there's a
                        # separate button for that.
                        _others = _users[
                            _users["contributor_id"].astype(str)
                            != str(_me_cid)
                        ]
                        if not _others.empty:
                            _opts = list(_others["contributor_id"]
                                          .astype(str))
                            _names = {
                                str(r["contributor_id"]):
                                    (f"{r['display_name']} "
                                     f"(@{r['username']})")
                                for _, r in _others.iterrows()
                            }
                            _pick = st.selectbox(
                                "Transfer to another signed-in user",
                                _opts,
                                format_func=lambda i, _n=_names:
                                    _n.get(i, i),
                                key=f"transfer_pick_{pick_tree}",
                            )
                            if st.button("Transfer",
                                          key=f"transfer_other_{pick_tree}",
                                          use_container_width=True):
                                db.set_tree_owner(pick_tree, _pick)
                                _invalidate_dashboard_caches()
                                st.success(
                                    f"Ownership transferred to "
                                    f"{_names.get(_pick, _pick)}.")
                                st.rerun()
                        else:
                            st.caption("No other signed-in users yet "
                                        "to transfer to.")
                    else:
                        st.caption("No signed-in users available to "
                                    "transfer to.")

        # ------- Customize block (gated by sub-nav) ------------------------
        if _sub == "Customize":
         # ------- Edit a species (admin only) -------------------------------
         if _can_edit_this_tree:
          with st.expander("Edit a species in this tree"):
            label_by_sci = {
                r["scientific_name"]: (
                    f"{r['common_name']} ({r['scientific_name']})"
                    if r.get("common_name") else r["scientific_name"]
                )
                for _, r in df.iterrows() if r.get("scientific_name")
            }
            if not label_by_sci:
                st.caption("No species to edit yet.")
            else:
                pick_sci = st.selectbox(
                    "Species", list(label_by_sci.keys()),
                    format_func=lambda s: label_by_sci.get(s, s),
                    key=f"edit_pick_{pick_tree}",
                )
                row = df[df["scientific_name"] == pick_sci].iloc[0].to_dict()
                with st.form(f"edit_form_{pick_tree}_{pick_sci}"):
                    new_vals = {}
                    new_vals["common_name"] = st.text_input(
                        "Common name", value=row.get("common_name") or "")
                    grid_l, grid_r = st.columns(2)
                    with grid_l:
                        new_vals["domain"] = st.text_input(
                            "Group (Animal/Plant/Fungi/Human/Insect/Other)",
                            value=row.get("domain") or "")
                        new_vals["kingdom"] = st.text_input(
                            "Kingdom", value=row.get("kingdom") or "")
                        new_vals["phylum"] = st.text_input(
                            "Phylum", value=row.get("phylum") or "")
                        new_vals["class_"] = st.text_input(
                            "Class", value=row.get("class_") or "")
                    with grid_r:
                        new_vals["order_"] = st.text_input(
                            "Order", value=row.get("order_") or "")
                        new_vals["family"] = st.text_input(
                            "Family", value=row.get("family") or "")
                        new_vals["genus"] = st.text_input(
                            "Genus", value=row.get("genus") or "")
                        new_vals["ncbi_taxid"] = st.text_input(
                            "NCBI TaxID",
                            value=str(int(row["ncbi_taxid"]))
                            if row.get("ncbi_taxid") not in (None, "") else "")
                    new_vals["notes"] = st.text_area(
                        "Notes", value=row.get("notes") or "")
                    new_vals["story"] = st.text_area(
                        "Story", value=row.get("story") or "")
                    new_vals["submitted_by"] = st.text_input(
                        "Submitted by", value=row.get("submitted_by") or "")
                    saved = st.form_submit_button("Save changes",
                                                  type="primary")
                if saved:
                    cleaned = {}
                    for k, v in new_vals.items():
                        if k == "ncbi_taxid":
                            cleaned[k] = int(v) if str(v).strip() else None
                        else:
                            cleaned[k] = v.strip() if isinstance(v, str) else v
                            if cleaned[k] == "":
                                cleaned[k] = None
                    n = db.update_fields(pick_tree, pick_sci, cleaned)
                    st.success(f"Updated {n} row(s).")
                    st.rerun()

        # ------- Add a name (gated by sub-nav) -----------------------------
        if _sub == "Customize" and auth.can_write() and label_by_sci:
            with st.expander("Add a name in another language"):
                st.caption("Save a name in another language or category "
                            "for any species in this tree. Same effect as "
                            "Library → Add → Multilingual name, kept here "
                            "for speed.")
                _pick_sci = st.selectbox(
                    "Species", list(label_by_sci.keys()),
                    format_func=lambda s: label_by_sci.get(s, s),
                    key=f"dash_addname_pick_{pick_tree}",
                )
                # Out-of-form: pickers + script keyboard (interactive)
                _lang = i18n.render_language_picker(
                    "Language",
                    key=f"dash_addname_lang_{pick_tree}",
                    initial_code="ENG")
                _region = i18n.region_codes_to_str(
                    i18n.render_region_multi_picker(
                        "Region tags (optional, multiple)",
                        key=f"dash_addname_region_{pick_tree}"))
                _non_latin = st.checkbox(
                    "Script (non-Latin)",
                    key=f"dash_addname_script_flag_{pick_tree}",
                    help="Tick if the name is written in Devanagari, "
                         "Armenian, Han, etc. A character keyboard appears "
                         "below to compose it.")
                _script_name = None
                if _non_latin:
                    _composed = i18n.render_script_keyboard(
                        f"dash_addname_kbd_{pick_tree}")
                    _script_name = st.session_state.get(
                        f"dash_addname_kbd_{pick_tree}_script_pick")
                    if _composed:
                        st.caption(
                            f"Composed: **{_composed}** — paste into "
                            "Name below.")
                with st.form(f"dash_addname_form_{pick_tree}"):
                    _name_text = st.text_input(
                        "Name",
                        key=f"dash_addname_text_{pick_tree}",
                        help="The name as written in its language.")
                    _cat = st.selectbox(
                        "Category",
                        ["common","folk","ceremonial",
                         "scientific","synonym"],
                        key=f"dash_addname_cat_{pick_tree}")
                    _pref = st.checkbox(
                        "Make this the preferred name for this "
                        "(species, language, category)",
                        value=False,
                        key=f"dash_addname_pref_{pick_tree}")
                    _name_notes = st.text_area(
                        "Notes (optional)",
                        placeholder="Where this name comes from, "
                                     "what it means, when it is used...",
                        height=68,
                        key=f"dash_addname_notes_{pick_tree}")
                    if st.form_submit_button("Save name", type="primary",
                                              use_container_width=True):
                        if not (_name_text or "").strip():
                            st.warning("Name can't be empty.")
                        else:
                            # Resolve species_id from scientific_name
                            _row = df[df["scientific_name"] == _pick_sci]
                            _row = _row.iloc[0] if not _row.empty else None
                            if _row is None:
                                st.warning("Couldn't find that species.")
                            else:
                                _sp_id = db.get_or_create_species(
                                    int(_row["ncbi_taxid"]), _pick_sci)
                                db.add_species_name(
                                    _sp_id,
                                    _name_text.strip(),
                                    language=_lang or "ENG",
                                    category=_cat,
                                    source="community",
                                    is_preferred=bool(_pref),
                                    contributor_id=
                                        auth.active_contributor_id(),
                                    region_code=_region,
                                    script=(_script_name
                                             if _non_latin else None),
                                    notes=(_name_notes or "").strip() or None)
                                _invalidate_dashboard_caches()
                                try:
                                    from src import library as _lib
                                    _lib._invalidate_all_caches()
                                except Exception:
                                    pass
                                st.success(
                                    f"Saved {_name_text!r} "
                                    f"({_lang}/{_cat}). Rebuild the tree so "
                                    "the labels show the new name if you "
                                    "made it preferred.")
                                st.rerun()

        # ------- Per-tree common-name picker (gated by sub-nav) ------------
        if _sub == "Customize" and _can_edit_this_tree:
            with st.expander("Choose how each species is named in this tree"):
                st.caption(
                    "Pick a different name for any species in this tree "
                    "(another language, a folk name, a ceremonial name). "
                    "Only this tree changes — other trees keep their own "
                    "picks. Rebuild after saving so the rendered labels "
                    "match.")
                _picker_rows = _cached_tree_species_picker(pick_tree)
                if not _picker_rows:
                    st.caption("No species in this tree yet.")
                else:
                    for _pr in _picker_rows:
                        _sp_id = _pr["species_id"]
                        _sci   = _pr["scientific_name"]
                        _choices = _pr["choices"]
                        _ids = [c[0] for c in _choices]
                        _labels = {c[0]: c[1] for c in _choices}
                        _current_idx = (_ids.index(_pr["current_name_id"])
                                          if _pr["current_name_id"] in _ids
                                          else 0)
                        _picked = st.selectbox(
                            _sci, _ids,
                            index=_current_idx,
                            format_func=lambda i, _l=_labels: _l.get(i, "(default)"),
                            key=f"name_pick_{pick_tree}_{_sp_id}",
                        )
                        if _picked != _pr["current_name_id"]:
                            if st.button(
                                f"Save name for {_sci}",
                                key=f"name_save_{pick_tree}_{_sp_id}",
                            ):
                                db.set_tree_species_display_name(
                                    pick_tree, _sp_id, _picked)
                                _invalidate_dashboard_caches()
                                st.success("Saved. Rebuild the tree so the "
                                            "label updates in the render.")
                                st.rerun()

        # ------- Clade Browser + notes (gated by sub-nav) ----------------
        # Pick a clade in this tree, see its representative species photo,
        # its divergence age, and its species. Signed-in users can leave
        # a note attached to the clade (surfaces here and in the Library).
        if _sub == "Customize" and meta:
            with st.expander("Clade browser — photo, age, notes"):
                _clades = sorted(
                    (n for n, v in meta.items()
                     if not v.get("is_leaf") and n),
                    key=lambda n: (
                        # dated clades first (with age), then alphabetical
                        0 if meta[n].get("mya") is not None else 1,
                        (meta[n].get("mya") or 1e9),
                        n))
                if not _clades:
                    st.caption("No named clades in this tree yet.")
                else:
                    _pick_clade = st.selectbox(
                        "Clade",
                        _clades,
                        format_func=lambda n: (
                            f"{n} — {meta[n].get('mya')} MYA"
                            if meta[n].get("mya") is not None
                            else n),
                        key=f"clade_browser_pick_{pick_tree}")
                    _cinfo = meta.get(_pick_clade, {})
                    _cage = _cinfo.get("mya")
                    st.caption(
                        f"Divergence: "
                        f"{f'{_cage} MYA' if _cage is not None else 'age not set'}")

                    # Editors/admins can fill in a missing divergence
                    # age here, without going into SQL. Writes to the
                    # clade table so this contribution helps every
                    # tree, not just this one.
                    if auth.is_editor_or_admin():
                        _clade_db_id = db.get_clade_id_by_name(_pick_clade)
                        if _clade_db_id:
                            with st.form(
                                    key=f"mya_form_{pick_tree}_{_pick_clade}"):
                                _new_mya = st.number_input(
                                    "Set divergence age (MYA). Blank/0 to "
                                    "clear.",
                                    min_value=0.0, max_value=5000.0,
                                    value=float(_cage) if _cage else 0.0,
                                    step=0.5,
                                    key=f"mya_input_{pick_tree}_{_pick_clade}")
                                if st.form_submit_button("Save age",
                                                           type="primary"):
                                    to_save = (
                                        _new_mya if _new_mya > 0 else None)
                                    db.set_clade_divergence_mya(
                                        _clade_db_id, to_save)
                                    st.success(
                                        "Saved. Rebuild the tree so "
                                        "branches rescale to the new age.")
                                    st.rerun()
                        else:
                            st.caption("(This clade isn't in the "
                                        "database yet; it lives only in "
                                        "the tree render. Rebuild the "
                                        "tree once to seed it.)")

                    # Find representative species: first leaf descendant
                    # in the newick that has a scientific_name. Cached
                    # by (tree_name, clade_name, file mtime) so repeated
                    # picks don't re-parse ete3 + re-fetch iNat.
                    _rep_photo_url = None
                    _rep_common = None
                    _rep_sci = None
                    _species_under: list[str] = []
                    try:
                        _rep = _clade_browser_lookup(
                            pick_tree, str(nwk), _pick_clade)
                        _rep_photo_url = _rep.get("photo_url")
                        _rep_common = _rep.get("rep_common")
                        _rep_sci = _rep.get("rep_sci")
                        _species_under = _rep.get("species_under") or []
                    except Exception as _exc:
                        st.caption(f"Couldn't read tree file: {_exc}")

                    _photo_col, _species_col = st.columns([1, 2])
                    with _photo_col:
                        if _rep_photo_url:
                            st.image(_rep_photo_url, width=180)
                            _cap = (f"{_rep_common} ({_rep_sci})"
                                    if _rep_common else _rep_sci)
                            st.caption(f"Representative: {_cap}")
                        else:
                            st.caption("No representative photo available.")
                    with _species_col:
                        st.caption(f"{len(_species_under)} species under "
                                    f"this clade:")
                        st.markdown(
                            "\n".join(f"- {s}"
                                        for s in _species_under[:20])
                            or "_(none)_")
                        if len(_species_under) > 20:
                            st.caption(f"...and {len(_species_under)-20} more.")

                    # Notes: list existing + add form
                    st.markdown("---")
                    st.markdown("**Notes**")
                    _notes = db.list_clade_notes(_pick_clade,
                                                  tree_name=pick_tree)
                    if not _notes:
                        st.caption("No notes yet. Add one below.")
                    for _n in _notes[:12]:
                        _who = _n.get("display_name") or _n.get(
                            "username") or "Someone"
                        _when = _n.get("created_at")
                        _when_s = _when.strftime("%Y-%m-%d") if _when else ""
                        _scope = ("this tree" if _n.get("tree_name")
                                  else "global")
                        st.markdown(f"> {_n['body']}")
                        _cap_line = f"— {_who}, {_when_s} · {_scope}"
                        _del_col = st.columns([5, 1])
                        _del_col[0].caption(_cap_line)
                        _own_id = _n.get("contributor_id")
                        _me_id = auth.active_contributor_id()
                        if (_me_id and (_me_id == _own_id
                                         or auth.is_admin())):
                            if _del_col[1].button(
                                    "delete",
                                    key=f"cnote_del_{_n['clade_note_id']}"):
                                db.delete_clade_note(
                                    _n["clade_note_id"], _me_id,
                                    is_admin=auth.is_admin())
                                st.rerun()

                    if auth.can_write():
                        with st.form(
                                key=f"cnote_form_{pick_tree}_{_pick_clade}",
                                clear_on_submit=True):
                            _body = st.text_area(
                                "Your note about this clade",
                                placeholder="A memory, a story, a name, "
                                             "why this clade matters to you...",
                                height=80)
                            _scope_pick = st.radio(
                                "Where does this note belong?",
                                ["This tree only", "All trees (global)"],
                                horizontal=True, index=0,
                                key=f"cnote_scope_{pick_tree}_{_pick_clade}")
                            if st.form_submit_button("Save note",
                                                       type="primary"):
                                _tn = (pick_tree
                                        if _scope_pick.startswith("This")
                                        else None)
                                _nid = db.add_clade_note(
                                    _pick_clade, _body,
                                    auth.active_contributor_id(),
                                    tree_name=_tn)
                                if _nid:
                                    st.success("Note saved.")
                                    st.rerun()
                                else:
                                    st.warning(
                                        "Couldn't save — the clade_note "
                                        "table may not be provisioned yet. "
                                        "See db/clade_note_migration.sql.")

        if _sub == "Customize" and _can_edit_this_tree:
          with st.expander("Remove species, or delete this tree"):
            to_remove = st.multiselect(
                "Species to remove from this tree",
                list(label_by_sci.keys()) if label_by_sci else [],
                format_func=lambda s: label_by_sci.get(s, s) if label_by_sci else s,
            )
            if st.button("Remove selected species", disabled=not to_remove):
                removed = sum(db.delete_species(pick_tree, s) for s in to_remove)
                st.success(f"Removed {removed} species. Rebuild to refresh the "
                           "tree, chord, and files.")
                st.rerun()
            st.caption("Removing is permanent. Rebuild afterward so the tree "
                       "and chord match the data.")
            st.divider()
            confirm = st.checkbox("Yes, permanently delete the whole "
                                  f"'{pick_tree}' tree")
            if st.button("Delete entire tree", disabled=not confirm):
                removed = db.delete_tree(pick_tree)
                st.success(f"Deleted {removed} rows from {pick_tree}.")
                st.rerun()

        # ------- Energy + offset invitation -------------------------------
        st.divider()
        # ------- Listen to each species (gated by sub-nav) --------
        if _sub == "Listen":
          st.divider()
          st.markdown("### Listen to each species")
        # The per-species profile + audio + player_html lookups are the
        # slowest part of the Dashboard, so we hide them behind a checkbox.
        # Users who actually want to listen flip it on; the page renders
        # instantly otherwise.
        _listen_open = st.checkbox(
            "Load the kin cards",
            key=f"listen_open_{pick_tree}",
            value=False,
            help="Off by default so the Dashboard stays fast. Switch on "
                 "to fetch photos, summaries, and play audio for each "
                 "species in this tree.")
        try:
            if _listen_open and nwk.exists() and meta:
                with st.expander("Listen to each species", expanded=True):
                    admin = auth.is_admin()
                    tip_rows = [(n, i) for n, i in meta.items()
                                if i.get("is_leaf")]
                    if not tip_rows:
                        st.caption("Build the tree first.")
                    for tip_name, info in tip_rows:
                        sci = (info.get("scientific_name")
                               or tip_name.replace("_", " "))
                        common = info.get("common_name")
                        try:
                            _sp_profile = _cached_profile(sci, common)
                        except Exception as exc:
                            _sp_profile = None
                            if admin:
                                st.warning(f"_sp_profile {sci}: {exc}")
                        try:
                            rec = _cached_audio(sci, common)
                        except Exception as exc:
                            rec = None
                            if admin:
                                st.warning(f"audio {sci}: {exc}")
    
                        st.divider()
                        c_img, c_text = st.columns([1, 3])
                        with c_img:
                            if _sp_profile and _sp_profile.get("image_path"):
                                st.image(_sp_profile["image_path"],
                                         use_container_width=True)
                                if _sp_profile.get("image_attribution"):
                                    st.caption(
                                        format_credit(_sp_profile["image_attribution"]))
                            else:
                                st.caption("(no photo)")
                        with c_text:
                            head = f"**{common or sci}**"
                            if common:
                                head += f"  *({sci})*"
                            st.markdown(head)
                            summ = (_sp_profile or {}).get("summary") or ""
                            if summ:
                                trim = summ[:700]
                                if len(summ) > 700:
                                    trim += "…"
                                st.write(trim)
                            links = []
                            for lab, k in (("Wikipedia", "wikipedia_url"),
                                           ("iNaturalist", "inaturalist_url"),
                                           ("GBIF", "gbif_url")):
                                if (_sp_profile or {}).get(k):
                                    links.append(f"[{lab}]({_sp_profile[k]})")
                            if links:
                                st.markdown(" · ".join(links))
                            anc = (_sp_profile or {}).get("ancestors") or []
                            if anc:
                                chips = " › ".join(
                                    a["name"] for a in anc[-7:])
                                st.caption(chips)
                            if rec:
                                try:
                                    html = _cached_player_html(
                                        common, sci, str(rec["path"]),
                                        rec.get("attribution",""))
                                    components.html(
                                        html, height=290, scrolling=False)
                                except Exception as exc:
                                    st.warning(f"player {sci}: {exc}")
                                    if admin:
                                        st.code(traceback.format_exc())
                            else:
                                st.caption("(no open recording found)")
                            if admin:
                                with st.expander("Edit profile (admin)"):
                                    cur = species_profile.list_overrides().get(
                                        sci, {})
                                    img_url = st.text_input(
                                        "Custom image URL",
                                        value=cur.get("image_url", ""),
                                        key=f"oi_{sci}")
                                    summ_in = st.text_area(
                                        "Custom summary",
                                        value=cur.get("summary", ""),
                                        key=f"os_{sci}")
                                    cs, cc = st.columns(2)
                                    with cs:
                                        if st.button("Save",
                                                     key=f"sov_{sci}"):
                                            species_profile.save_override(
                                                sci, image_url=img_url,
                                                summary=summ_in)
                                            st.success("Saved.")
                                            st.rerun()
                                    with cc:
                                        if st.button("Clear",
                                                     key=f"cov_{sci}"):
                                            species_profile.clear_override(sci)
                                            st.success("Cleared.")
                                            st.rerun()
        except Exception as _listen_exc:
            st.warning(f"Listen section failed: {_listen_exc}")
            if auth.is_admin():
                st.code(traceback.format_exc(), language="python")

        # ------- Footprint (gated by sub-nav) ------------------------------
        if _sub == "Footprint":
            totals = usage_log.get_totals()
            tree_wh = usage_log.tree_total(pick_tree)
            last = usage_log.last_event_summary()
            st.markdown(f"#### Approximate footprint of *{pick_tree}*")
            if tree_wh > 0:
                st.markdown(
                    f"This tree has used about **{tree_wh} Wh** of "
                    f"electricity ({usage_log.relatable(tree_wh)}) and "
                    f"**{usage_log.wh_to_water_ml(tree_wh):.0f} mL of "
                    f"water** ({usage_log.water_relatable(tree_wh)}) "
                    f"for data-center cooling.")
            else:
                st.caption("This tree has not been built yet, so no "
                            "measurable electricity or water has been "
                            "used for it.")
            if last and last.get("tree") == pick_tree:
                st.caption(
                    f"Last build event · {last['type']} · "
                    f"{last['wh']} Wh ({last['relatable']})")
            st.markdown(usage_log.invitation(pick_tree))
            st.markdown(
                f'<div style="color:#9ab3ab;font-size:11px;margin-top:8px">'
                f'Across the whole app: {totals["events"]} builds, '
                f'about {totals["total_wh"]} Wh '
                f'(~{totals["total_co2_g"]:.1f} g CO₂eq, '
                f'{usage_log.wh_to_water_ml(totals["total_wh"]):.0f} mL of water).'
                f'</div>',
                unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Range map tab. Interactive species range map via GBIF.
# ---------------------------------------------------------------------------
if active_tab == "Range map":
    # Quick-look: if the URL has ?species=..., show a species card at
    # the top of the Range map tab. Users land here by clicking a
    # species name in the map's layer control.
    _picked_species_qp = st.query_params.get("species")
    if _picked_species_qp:
        _sci = (
            _picked_species_qp[0]
            if isinstance(_picked_species_qp, list)
            else _picked_species_qp)
        try:
            from src import species_profile as _sp
            _prof = _sp.find_profile(_sci, None)
        except Exception:
            _prof = None
        if _prof:
            _card_cols = st.columns([1, 3])
            with _card_cols[0]:
                if _prof.get("image_url"):
                    st.image(_prof["image_url"])
            with _card_cols[1]:
                _cn = _prof.get("common_name")
                st.markdown(
                    f"### {_cn} *({_sci})*" if _cn else f"### *{_sci}*")
                _summ = _prof.get("summary") or ""
                if _summ:
                    st.write(_summ[:600] + ("..." if len(_summ) > 600 else ""))
                _links = []
                if _prof.get("wikipedia_url"):
                    _links.append(f"[Wikipedia]({_prof['wikipedia_url']})")
                if _prof.get("inaturalist_url"):
                    _links.append(
                        f"[iNaturalist]({_prof['inaturalist_url']})")
                if _links:
                    st.caption(" · ".join(_links))
                if st.button("Back to the map",
                              key="clear_species_qp"):
                    del st.query_params["species"]
                    st.rerun()
            st.markdown("---")
        else:
            st.caption(f"No profile found for {_sci}.")

    theme.section_heading("Where these kin live", kicker="Range map")
    st.markdown(
        "Occurrence density for each species in your tree, drawn from "
        "[GBIF](https://www.gbif.org/) onto one map. You can see where the "
        "ranges overlap and where they don't. Drag to pan, scroll to zoom, "
        "and toggle species on or off in the top-right panel."
    )

    map_trees = _cached_list_trees_for_dashboard()
    if map_trees.empty:
        st.info("Add species in the Request station tab first, then build a "
                "tree. Once a tree exists, its range map shows up here.")
    else:
        map_pick = st.selectbox("Pick a tree",
                                map_trees["tree_name"].tolist(),
                                key="map_tree_pick")
        from src import gbif_map
        try:
            species_for_map = gbif_map.species_for_tree(map_pick)
        except Exception as _exc:
            st.error(f"Could not load the species list for the map. ({_exc})")
            species_for_map = []

        if not species_for_map:
            st.caption("This tree has no species yet.")
        else:
            with st.spinner(
                    f"Resolving {len(species_for_map)} species in GBIF "
                    "(cached after the first lookup)..."):
                mapped, unmapped = gbif_map.resolve_species(species_for_map)

            if not mapped:
                st.warning(
                    "None of these species have GBIF occurrence records yet. "
                    "Common for very recently described species or for "
                    "uncommon synonyms.")
            else:
                html = gbif_map.build_map_html(species_for_map, height=620)
                components.html(html, height=640)
                st.caption(
                    "Map data © OpenStreetMap, © CARTO. Occurrence data © "
                    "GBIF and its contributing institutions. Coverage is "
                    "uneven globally; blank does not mean absent, it means "
                    "undocumented in GBIF's records.")

            if unmapped:
                with st.expander(
                        f"{len(unmapped)} species without GBIF records"):
                    for sp in unmapped:
                        st.caption(
                            f"- {sp.get('common_name') or sp.get('scientific_name')}"
                            f"  *({sp.get('scientific_name')})*")
                    st.caption(
                        "These species are either too recently described to "
                        "be in GBIF, or the scientific name we have is a "
                        "synonym GBIF doesn't recognize directly. "
                        "Tip: editing the scientific name in the dashboard "
                        "(admin only) to the canonical GBIF name resolves "
                        "most of these.")


# ---------------------------------------------------------------------------
# Library tab. Community knowledge: names, stories, dishes, pantheons,
# cultural connections) with admin entry forms.
# ---------------------------------------------------------------------------
if active_tab == "Library":
    library.render(
        is_admin=auth.is_admin(),
        can_edit_contribution=auth.can_edit_contribution,
        current_contributor_id=auth.active_contributor_id(),
    )


if active_tab == "Profile":
    profile.render()


# Admin-only diagnostic panel (collapsed by default; tucked above the
# footer so it doesn't crowd the main UI but is one click away when
# debugging an auth issue).
if auth.is_admin():
    auth.render_auth_diagnostic()

# Site footer (license, byline, support links).
theme.render_footer(tree_settings.PROJECT_SLOGAN)
