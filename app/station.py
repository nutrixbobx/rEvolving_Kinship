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

# Apply the unified theme on every load.
theme.inject_css()

# Pre-init cookie manager + try restore before anything else renders.
# CookieManager's component reads from the browser asynchronously, so the
# very first script run after a page load gets an empty cookie dict.
# Streamlit auto-reruns when the component sends real data; on that rerun
# the cookie is available and the user is signed in silently. By calling
# _try_cookie_restore here, we make sure the restore happens BEFORE the
# auth gate decides whether to show the sign-in form.
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


def _fav_toggle_for_tree(tree_name: str) -> None:
    """Render a ⭐/☆ favorite toggle for the currently-picked tree. Visible
    to any named user. No-op when not named."""
    cid = auth.active_contributor_id()
    if not cid:
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
station_tab, dash_tab, map_tab, library_tab, profile_tab = st.tabs(["Request station", "Dashboard", "Range map", "Library", "Profile"])

# ---------------------------------------------------------------------------
# Request station (the kiosk)
# ---------------------------------------------------------------------------
with station_tab:
    with st.expander("How this works (read me first)", expanded=False):
        st.markdown(
            "**1.** Name one or more species you feel kin to. Search by common name "
            "(coyote) or scientific name (Canis latrans), pick the match, and hit "
            "**Add to the tree**.\n\n"
            "**2.** Open the **Dashboard** tab, pick your tree, and click "
            "**Build / rebuild**. The tree draws itself, the chord rings, the photos "
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

    ready = ts.is_ready()
    if not ready:
        st.warning(
            "The NCBI taxonomy database is not built on this server yet, so "
            "live search and validation are off. Build it once below "
            "(takes about five minutes; after that, kiosk autocomplete "
            "works instantly). You can also add names without validation "
            "and they will resolve on the next run."
        )
        with st.expander("Build NCBI taxonomy on this server", expanded=False):
            st.caption(
                "This downloads about 80 MB from NCBI and builds the local "
                "taxonomy SQLite (~600 MB). One-time setup. On Streamlit "
                "Cloud the build persists until the container restarts.")
            if st.button("Start NCBI build", type="primary",
                         key="build_ncbi"):
                # Step 1: if NCBI_TAXA_URL is set (e.g. Supabase Storage),
                # try the fast URL download first (~30 seconds).
                from src import setup_ncbi
                ncbi_url = os.environ.get("NCBI_TAXA_URL")
                if ncbi_url:
                    with st.spinner(
                            f"Downloading NCBI taxonomy from your bucket. "
                            f"This takes about 30 seconds."):
                        if setup_ncbi.ensure_taxonomy_from_url():
                            st.success(
                                "NCBI taxonomy downloaded from your bucket. "
                                "Reload the page to activate autocomplete.")
                            st.stop()
                        else:
                            st.warning(
                                "Bucket download failed. Trying full NCBI "
                                "build as a fallback (about five minutes).")
                # Step 2: full ete3 build from NCBI FTP (slow path).
                with st.spinner(
                        "Building the NCBI taxonomy from scratch. Do not "
                        "close this tab. This takes about five minutes."):
                    try:
                        from ete3 import NCBITaxa
                        NCBITaxa()
                        st.success(
                            "NCBI taxonomy built. Reload the page to "
                            "activate kiosk autocomplete.")
                    except Exception as exc:
                        st.error(f"Build failed: {exc}")
                        st.info(
                            "Upload taxdump.tar.gz or a pre-built "
                            "taxa.sqlite.gz to your Supabase Storage and set "
                            "NCBI_TAXA_URL in your Streamlit secrets to "
                            "point at it. See DEPLOYMENT.md for the steps.")

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

    if st.button("Add to the tree", type="primary"):
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
with dash_tab:
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
                "Pick a tree below, then click **Build / rebuild** on the right to "
                "compute its topology, draw it, sound the chord, fetch the photos, and "
                "write a short note. The first build takes a minute or two. "
                "After that, every other section comes alive: hover the tips, listen to "
                "each species, download the press files, mix a meditation track."
            )
        pick_tree = st.selectbox("Pick a tree",
                                 trees["tree_name"].tolist())
        _fav_toggle_for_tree(pick_tree)
        try:
            df = _cached_read_tree(pick_tree)
        except Exception as _exc:
            st.error(f"Could not load this tree from the database. "
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
            if st.button(f"Build / rebuild  “{pick_tree}”",
                         type="primary",
                         key=f"build_top_{pick_tree}",
                         use_container_width=True):
                with st.spinner("Resolving taxonomy, building the tree, "
                                "rendering, and sonifying. The first ever run "
                                "also downloads the NCBI taxonomy, which takes "
                                "a few minutes."):
                    try:
                        from src import pipeline
                        pipeline.run(pick_tree)
                        st.success("Built. Reloading.")
                        st.rerun()
                    except SystemExit as exc:
                        st.error(str(exc))
                    except Exception as exc:
                        st.error(f"Build failed: {exc}")
            st.markdown("&nbsp;")
            layout_name = st.radio("Layout", list(render_mod.LAYOUTS.keys()))
            show_sci = st.checkbox("Show scientific names", value=True)
            st.markdown(
                f"""<div style="font-size:13px;line-height:1.9">
<span style="display:inline-block;width:11px;height:11px;border-radius:50%;
background:{render_mod.LEAF_COLOR}"></span> species (leaf)<br>
<span style="display:inline-block;width:13px;height:13px;border-radius:50%;
background:{render_mod.DATED_NODE_COLOR}"></span> clade with a divergence age<br>
<span style="display:inline-block;width:11px;height:11px;border-radius:50%;
background:{render_mod.PLAIN_NODE_COLOR}"></span> clade, no age yet</div>""",
                unsafe_allow_html=True,
            )
            st.caption(f"{len(df)} species, {n_dated} dated node(s). "
                       "Hover any node for its details.")
            if wav.exists():
                st.markdown("**Hear the ecosystem chord**")
                st.audio(wav.read_bytes(), format="audio/wav")
            if mid.exists():
                st.download_button("Download chord (.mid)", mid.read_bytes(),
                                   file_name=mid.name, mime="audio/midi")
            if nwk.exists():
                st.download_button("Download tree (.nwk)", nwk.read_bytes(),
                                   file_name=nwk.name, mime="text/plain")

            st.markdown("**Meditation track**")
            med_min = st.radio("Length", [1, 2, 5],
                               format_func=lambda m: f"{m} min",
                               horizontal=True, key=f"med_min_{pick_tree}")
            med_secs = med_min * 60
            med_path = config.OUTPUT_DIR / f"{stem}_meditation_{med_secs}s.wav"
            if med_path.exists():
                st.audio(med_path.read_bytes(), format="audio/wav")
                st.download_button(f"Download {med_min} min meditation",
                                   med_path.read_bytes(),
                                   file_name=med_path.name,
                                   mime="audio/wav",
                                   key=f"med_dl_{pick_tree}_{med_secs}")
            if st.button(f"Build {med_min} min meditation",
                         key=f"med_build_{pick_tree}_{med_secs}"):
                with st.spinner(f"Blending the chord and the chorus into a "
                                f"{med_min} minute track."):
                    try:
                        from src import meditation
                        res = meditation.build_meditation(pick_tree, med_secs)
                        if res is None:
                            st.info("Need a dated clade (the chord) to build a "
                                    "meditation track. Rebuild this tree first.")
                        else:
                            st.success(f"Built {med_min} min meditation "
                                       f"({'with chorus' if res['has_chorus'] else 'chord only, no chorus yet'}).")
                            st.rerun()
                    except Exception as exc:
                        st.error(f"Build failed: {exc}")
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
                            st.caption(_sp_profile["image_attribution"][:80])
                    if _sp_profile:
                        st.markdown(f"**{row.get('common_name') or ql}**  "
                                    f"*{ql}*")
                        st.write((_sp_profile.get("summary") or "")[:500])
                        link_bits = []
                        for lab, key in (("Wikipedia", "wikipedia_url"),
                                         ("iNaturalist", "inaturalist_url"),
                                         ("GBIF", "gbif_url")):
                            if _sp_profile.get(key):
                                link_bits.append(f"[{lab}]({_sp_profile[key]})")
                        if link_bits:
                            st.markdown(" · ".join(link_bits))

            if st.button("Export species list for TimeTree"):
                from src import timetree
                p = timetree.export_species_list(pick_tree)
                st.success(f"Wrote {p.name}. Upload it at timetree.org, save the "
                           f"result as data/{stem}_timetree.nwk, then rebuild.")

            chorus = config.OUTPUT_DIR / f"{stem}_chorus.wav"
            sound_tree = config.OUTPUT_DIR / f"{stem}_sound_tree.png"
            st.markdown("---")
            st.markdown("**Animal chorus**")
            if chorus.exists():
                st.audio(chorus.read_bytes(), format="audio/wav")
            if st.button("Build / refresh chorus", key=f"chorus_{pick_tree}"):
                with st.spinner("Fetching recordings from Xeno-Canto + Wikipedia, and "
                                "blending them. First run for new species "
                                "downloads; later runs use the cache."):
                    try:
                        from src import audio_blend
                        res = audio_blend.build_chorus(pick_tree)
                        if res is None:
                            st.info("No recordings found for any species "
                                    "in this tree.")
                        else:
                            st.success(f"Built chorus with {len(res['voices'])} voice(s).")
                            st.rerun()
                    except Exception as exc:
                        st.error(f"Chorus build failed: {exc}")
            st.markdown("**Sound kinship tree**")
            if sound_tree.exists():
                st.image(sound_tree.read_bytes())
            if st.button("Build / refresh sound tree",
                         key=f"sound_tree_{pick_tree}"):
                with st.spinner("Drawing the tree and rendering a "
                                "spectrogram at each tip."):
                    try:
                        from src import spectrogram_tree
                        spectrogram_tree.build_sound_tree(pick_tree)
                        st.success("Built sound kinship tree.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Sound tree build failed: {exc}")
        with view:
            if nwk.exists() and meta:
                html = render_mod.render_html(
                    nwk, meta, layout=render_mod.LAYOUTS[layout_name],
                    show_scientific=show_sci, tree_name=pick_tree,
                )
                components.html(html, height=880, scrolling=True)
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
        build_col, rename_col = st.columns([1, 2])
        with build_col:
            if st.button(f"Build / rebuild  “{pick_tree}”", type="primary"):
                with st.spinner("Resolving taxonomy, building the tree, "
                                "rendering, and sonifying. The first ever run "
                                "also downloads the NCBI taxonomy, which takes "
                                "a few minutes."):
                    try:
                        from src import pipeline
                        pipeline.run(pick_tree)
                        st.success("Built. Reloading.")
                        st.rerun()
                    except SystemExit as exc:
                        st.error(str(exc))
                    except Exception as exc:
                        st.error(f"Build failed: {exc}")

            st.markdown("---")
            st.markdown("**Photo tree**")
            photo_tree = config.OUTPUT_DIR / f"{stem}_photo_tree.png"
            if photo_tree.exists():
                st.image(photo_tree.read_bytes())
            if st.button("Build / refresh photo tree",
                         key=f"phototree_{pick_tree}"):
                with st.spinner("Fetching photos and composing the tree."):
                    try:
                        from src import image_tree
                        image_tree.build_image_tree(pick_tree)
                        st.success("Built.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Photo tree build failed: {exc}")
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

            # Admin-only ownership transfer (e.g. lock Maya's seed trees).
            if auth.is_admin() and auth.active_contributor_id():
                cur_owner_id = (_owner_info or {}).get("owner_id")
                me = auth.active_contributor_id()
                if cur_owner_id != me:
                    if st.button("Transfer ownership to me",
                                 key=f"transfer_{pick_tree}",
                                 help="Lock this tree as admin-owned so only "
                                      "admins can rename, delete, or modify it."):
                        db.set_tree_owner(pick_tree, me)
                        _invalidate_dashboard_caches()
                        st.success("Ownership transferred to you.")
                        st.rerun()

        if auth.is_admin():
            with st.expander("Tree personalization (admin)"):
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
                st.caption(f"Will render as: "
                           f"“{tree_settings.title_for(pick_tree)}”")

        # ------- Edit a species (admin only) --------------------------------
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

        # ------- Add a name (any signed-in user / guest) --------------------
        if auth.is_named() and label_by_sci:
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
                _region = i18n.render_region_picker(
                    "Region (optional)",
                    key=f"dash_addname_region_{pick_tree}")
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
                                    script=_script_name if _non_latin else None)
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

        # ------- Per-tree common-name picker --------------------------------
        if _can_edit_this_tree:
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
                                st.success(f"Saved. Rebuild the tree so the "
                                            f"label updates in the render.")
                                st.rerun()

        if _can_edit_this_tree:
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
            confirm = st.checkbox(f"Yes, permanently delete the whole "
                                  f"'{pick_tree}' tree")
            if st.button("Delete entire tree", disabled=not confirm):
                removed = db.delete_tree(pick_tree)
                st.success(f"Deleted {removed} rows from {pick_tree}.")
                st.rerun()

        # ------- Energy + offset invitation -------------------------------
        st.divider()
        totals = usage_log.get_totals()
        tree_wh = usage_log.tree_total(pick_tree)
        last = usage_log.last_event_summary()
        st.markdown(f"#### Approximate footprint of *{pick_tree}*")
        if tree_wh > 0:
            st.markdown(
                f"This tree has used about **{tree_wh} Wh** of electricity "
                f"({usage_log.relatable(tree_wh)}) and "
                f"**{usage_log.wh_to_water_ml(tree_wh):.0f} mL of water** "
                f"({usage_log.water_relatable(tree_wh)}) for data-center cooling.")
        else:
            st.caption("This tree has not been built yet, so no measurable "
                       "electricity or water has been used for it.")
        if last and last.get("tree") == pick_tree:
            st.caption(
                f"Last build event · {last['type']} · {last['wh']} Wh "
                f"({last['relatable']})")
        st.markdown(usage_log.invitation(pick_tree))
        st.markdown(
            f'<div style="color:#9ab3ab;font-size:11px;margin-top:8px">'
            f'Across the whole app: {totals["events"]} builds, '
            f'about {totals["total_wh"]} Wh '
            f'(~{totals["total_co2_g"]:.1f} g CO₂eq, '
            f'{usage_log.wh_to_water_ml(totals["total_wh"]):.0f} mL of water).'
            f'</div>',
            unsafe_allow_html=True)

        # ------- Listen to each species (lazy: opt-in to load) ------
        st.divider()
        st.markdown("### Listen to each species")
        # The per-species profile + audio + player_html lookups are the
        # slowest part of the Dashboard, so we hide them behind a checkbox.
        # Users who actually want to listen flip it on; the page renders
        # instantly otherwise.
        _listen_open = st.checkbox(
            "Load the listening cards",
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
                                        _sp_profile["image_attribution"][:90])
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


# ---------------------------------------------------------------------------
# Range map tab. Interactive species range map via GBIF.
# ---------------------------------------------------------------------------
with map_tab:
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
with library_tab:
    library.render(
        is_admin=auth.is_admin(),
        can_edit_contribution=auth.can_edit_contribution,
        current_contributor_id=auth.active_contributor_id(),
    )


with profile_tab:
    profile.render()


# Site footer (license, byline, support links).
theme.render_footer(tree_settings.PROJECT_SLOGAN)
