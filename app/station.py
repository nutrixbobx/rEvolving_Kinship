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

import sys
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
from src import db  # noqa: E402
from src import render as render_mod  # noqa: E402
from src import taxonomy_search as ts  # noqa: E402

st.set_page_config(page_title="{r}Evolving Kinship", layout="wide")
db.init_db()


def _stem(name: str) -> str:
    return name.strip().replace(" ", "_").lower()


def _label(hit: dict) -> str:
    if hit["common_name"]:
        return f"{hit['common_name']} ({hit['scientific_name']}) [{hit['rank']}]"
    return f"{hit['scientific_name']} [{hit['rank']}]"


st.title("{r}Evolving Kinship")
station_tab, dash_tab = st.tabs(["Request station", "Dashboard"])

# ---------------------------------------------------------------------------
# Request station (the kiosk)
# ---------------------------------------------------------------------------
with station_tab:
    st.subheader("Name a species you feel kin to")

    trees = db.list_trees()
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
            "The NCBI database is not built yet, so live search and validation "
            "are off. Build it once with a pipeline run, or "
            "`python -m src.build_taxonomy`. You can still add names below and "
            "they will resolve on the next run."
        )

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
            )
            label = pick["common_name"] or pick["scientific_name"]
            if is_new:
                st.success(f"{label} joined {tree_name}.")
            else:
                st.info(f"{pick['scientific_name']} is already in {tree_name}.")

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
with dash_tab:
    trees = db.list_trees()
    if trees.empty:
        st.info("No species yet. Add some on the request station tab, or run "
                "`make load` to import the sample data.")
    else:
        st.subheader("Trees in the warehouse")
        st.dataframe(trees, use_container_width=True, hide_index=True)

        pick_tree = st.selectbox("Look at a tree", trees["tree_name"].tolist())
        df = db.read_tree(pick_tree)
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
                    show_scientific=show_sci,
                )
                components.html(html, height=880, scrolling=True)
            else:
                st.caption("This tree has not been built yet. Use the button "
                           "below.")

            if nwk.exists() and meta:
                with st.expander("Listen to each species", expanded=False):
                    from src import species_player
                    players = species_player.players_for_tree(pick_tree, meta)
                    if not players:
                        st.caption("No recordings found for any species yet. "
                                   "Build the chorus first to fetch them.")
                    for html, h in players:
                        components.html(html, height=h, scrolling=False)

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
        with rename_col:
            new_name = st.text_input("Rename this tree", value=pick_tree,
                                     key=f"rename_{pick_tree}")
            if st.button("Save tree name"):
                try:
                    n = db.rename_tree(pick_tree, new_name)
                    st.success(f"Renamed {n} row(s). Rebuild so the output "
                               "files match the new name.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

        # ------- Edit a species ---------------------------------------------
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
