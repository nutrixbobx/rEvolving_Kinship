"""
The kinship Library tab.

Two halves: a public browse of every community knowledge surface (names,
stories, dishes, pantheons, cultural connections), and an admin-only entry
panel for adding new rows directly from the dashboard.

Browse uses st.dataframe per domain so any visitor can scroll through what
the community has gathered. Admin forms write to Supabase via the helpers
in db.py.
"""

from __future__ import annotations

import streamlit as st

from src import db


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def render(is_admin: bool) -> None:
    st.subheader("The kinship library")
    st.markdown(
        "Everything the community has woven around these species: the names "
        "they're called across languages, the stories they appear in, the "
        "dishes they're cooked into, the pantheons they show up in, and the "
        "cultural connections we want to keep."
    )
    browse, add = st.tabs(["Browse", "Add (admin only)"])

    with browse:
        _render_browse()
    with add:
        if is_admin:
            _render_admin_entry()
        else:
            st.info(
                "Sign in as admin in the sidebar to add stories, dishes, "
                "pantheons, deities, multilingual names, and cultural "
                "connections.")


# ---------------------------------------------------------------------------
# Browse: read-only views of every domain
# ---------------------------------------------------------------------------
def _render_browse() -> None:
    st.markdown("&nbsp;")

    with st.expander("Multilingual names",
                     expanded=False):
        df = db.list_all_names()
        if df.empty:
            st.caption("No names recorded yet beyond what NCBI gave us. Add "
                       "your first one in the admin tab.")
        else:
            st.caption(
                f"{len(df)} names across "
                f"{df['language'].nunique()} languages.")
            st.dataframe(df, use_container_width=True, hide_index=True)

    with st.expander("Stories", expanded=True):
        df = db.list_stories()
        if df.empty:
            st.caption("No stories yet. The Add tab is where they begin.")
        else:
            st.caption(f"{len(df)} stories.")
            st.dataframe(df, use_container_width=True, hide_index=True)

    with st.expander("Dishes and recipes", expanded=False):
        dishes = db.list_dishes()
        if dishes.empty:
            st.caption("No dishes yet. The Armenian Dolma tree was the seed; "
                       "the Library is where the kitchen lives.")
        else:
            st.caption(f"{len(dishes)} dishes.")
            st.dataframe(dishes, use_container_width=True, hide_index=True)
            ingredients = db.list_dish_ingredients()
            if not ingredients.empty:
                st.markdown("**Ingredients across all dishes**")
                st.dataframe(ingredients, use_container_width=True,
                             hide_index=True)

    with st.expander("Pantheons and deities", expanded=False):
        pantheons = db.list_pantheons()
        if pantheons.empty:
            st.caption("No pantheons yet. Greek, Mayan, Yoruba, Hindu, "
                       "Cherokee, Armenian — any tradition is welcome.")
        else:
            st.caption(f"{len(pantheons)} pantheons.")
            st.dataframe(pantheons, use_container_width=True,
                         hide_index=True)
            species_deities = db.list_species_deities()
            if not species_deities.empty:
                st.markdown("**Species linked to deities**")
                st.dataframe(species_deities, use_container_width=True,
                             hide_index=True)

    with st.expander("Cultural connections", expanded=False):
        df = db.list_cultural_connections()
        if df.empty:
            st.caption("Nothing here yet. Cultural connections capture the "
                       "looser ties: a species as totem, as medicinal, as "
                       "ceremonial, as foundational to a foodway.")
        else:
            st.caption(f"{len(df)} cultural connections.")
            st.dataframe(df, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Admin entry forms
# ---------------------------------------------------------------------------
def _species_picker(label: str, key: str,
                    allow_none: bool = False,
                    help: str | None = None) -> str | None:
    """Dropdown of every species in the warehouse. Returns species_id."""
    df = db.list_species_for_picker()
    if df.empty:
        st.warning("No species in the database yet. Add some via the "
                   "Request station tab first.")
        return None
    options = list(df["species_id"])
    if allow_none:
        options = [""] + options

    def fmt(sid):
        if not sid:
            return "(none — tree-level)"
        row = df[df["species_id"] == sid].iloc[0]
        if row["common_name"]:
            return (f"{row['common_name']}  "
                    f"({row['canonical_scientific_name']})")
        return row["canonical_scientific_name"]

    picked = st.selectbox(label, options, format_func=fmt, key=key,
                          help=help)
    return picked or None


def _tree_picker(label: str, key: str,
                 allow_none: bool = True) -> str | None:
    """Dropdown of every tree. Returns tree_id."""
    trees = db.list_trees()
    if trees.empty:
        return None
    # We need tree_id, not name. Fetch via get_tree_id per row.
    options = [""] if allow_none else []
    name_to_id = {}
    for name in trees["tree_name"].tolist():
        tid = db.get_tree_id(name)
        if tid:
            options.append(tid)
            name_to_id[tid] = name

    def fmt(tid):
        if not tid:
            return "(none — species-level)"
        return name_to_id.get(tid, tid)

    picked = st.selectbox(label, options, format_func=fmt, key=key)
    return picked or None


def _render_admin_entry() -> None:
    st.caption("All entries are attributed; visitors can see who contributed "
               "what in the Browse tab.")
    contrib_name = st.text_input(
        "Your contributor name (for attribution)",
        value="maya",
        key="lib_contrib_name",
        help="Reused across submissions in this session. New names create a "
             "new contributor row in the database.")
    contributor_id = db.get_or_create_contributor(contrib_name)

    # ---------- Add a multilingual name ----------
    with st.expander("Add a name in another language or category",
                     expanded=False):
        with st.form("add_name_form"):
            sp_id = _species_picker("Species", key="addname_sp")
            name_text = st.text_input(
                "Name", help="The name as written in its language.")
            cols = st.columns(3)
            with cols[0]:
                lang = st.text_input(
                    "Language code", value="en",
                    help="ISO 639-1 (en, hy, es, fr, ja, sw, ...).")
            with cols[1]:
                cat = st.selectbox(
                    "Category",
                    ["common", "folk", "ceremonial", "scientific", "synonym"])
            with cols[2]:
                region = st.text_input(
                    "Region (optional)",
                    help="ISO 3166 (US-GA, AM, MX, ...).")
            is_pref = st.checkbox(
                "Make this the preferred name for this species + language",
                value=False)
            if st.form_submit_button("Save name", type="primary"):
                if sp_id and name_text.strip():
                    db.add_species_name(
                        sp_id, name_text.strip(),
                        language=lang.strip() or "en",
                        category=cat, source="community",
                        is_preferred=is_pref,
                        contributor_id=contributor_id)
                    st.success(
                        f"Saved {name_text!r} ({lang}/{cat}).")
                    st.rerun()
                else:
                    st.warning("Need a species and a non-empty name.")

    # ---------- Add a story ----------
    with st.expander("Add a story", expanded=False):
        with st.form("add_story_form"):
            sp_id = _species_picker(
                "Species (optional if linked to a tree instead)",
                key="addstory_sp", allow_none=True)
            tr_id = _tree_picker(
                "Tree (optional if linked to a species instead)",
                key="addstory_tr")
            title = st.text_input(
                "Title (optional)",
                help="Leave blank for a short note without a heading.")
            body = st.text_area(
                "Story body", height=180,
                help="Plain text; line breaks render as paragraphs.")
            cols = st.columns(2)
            with cols[0]:
                lang = st.text_input("Language code", value="en")
            with cols[1]:
                region = st.text_input("Region (optional)")
            if st.form_submit_button("Save story", type="primary"):
                if not body.strip():
                    st.warning("Story body cannot be empty.")
                elif not sp_id and not tr_id:
                    st.warning("Link the story to a species or a tree.")
                else:
                    try:
                        db.add_story(
                            body, species_id=sp_id, tree_id=tr_id,
                            title=title.strip() or None,
                            language=lang.strip() or "en",
                            region=region.strip() or None,
                            contributor_id=contributor_id)
                        st.success("Saved.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Save failed: {exc}")

    # ---------- Add a dish + its ingredients ----------
    with st.expander("Add a dish and link species as ingredients",
                     expanded=False):
        with st.form("add_dish_form"):
            d_name = st.text_input("Dish name")
            cols = st.columns(2)
            with cols[0]:
                cuisine = st.text_input(
                    "Cuisine", help="Armenian, Lowcountry, Mayan, ...")
            with cols[1]:
                origin = st.text_input("Origin region (city / country)")
            description = st.text_area(
                "Description (optional)", height=80)
            st.markdown("**Ingredients** — pick a species per row, add roles "
                        "and quantities, leave unused rows blank.")
            n_rows = 6
            ing_inputs = []
            for i in range(n_rows):
                cols = st.columns([3, 1, 2])
                with cols[0]:
                    sp = _species_picker(
                        f"Species {i + 1}",
                        key=f"adddish_sp_{i}", allow_none=True)
                with cols[1]:
                    role = st.selectbox(
                        f"Role {i + 1}",
                        ["ingredient", "main", "protein", "wrapping",
                         "flavoring", "herb", "garnish"],
                        key=f"adddish_role_{i}")
                with cols[2]:
                    qty = st.text_input(
                        f"Quantity note {i + 1}",
                        key=f"adddish_qty_{i}",
                        help="Free text: 'two cups', 'a pinch', etc.")
                ing_inputs.append((sp, role, qty))
            if st.form_submit_button("Save dish", type="primary"):
                if not d_name.strip():
                    st.warning("Dish name is required.")
                else:
                    try:
                        dish_id = db.add_dish(
                            d_name.strip(),
                            origin_region=origin.strip() or None,
                            cuisine=cuisine.strip() or None,
                            description=description.strip() or None,
                            contributor_id=contributor_id)
                        linked = 0
                        for sp, role, qty in ing_inputs:
                            if sp:
                                db.link_dish_species(
                                    dish_id, sp, role=role,
                                    quantity_note=qty.strip() or None)
                                linked += 1
                        st.success(
                            f"Saved dish {d_name!r} with {linked} ingredient(s).")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Save failed: {exc}")

    # ---------- Add a pantheon + deity ----------
    with st.expander("Add a pantheon and a deity within it",
                     expanded=False):
        with st.form("add_pantheon_form"):
            existing_p = db.list_pantheons()
            pantheon_options = ["+ create new pantheon"] + (
                existing_p["name"].tolist() if not existing_p.empty else [])
            picked_p_name = st.selectbox(
                "Pantheon", pantheon_options,
                help="Pick an existing pantheon or create a new one.")
            if picked_p_name == "+ create new pantheon":
                new_p_name = st.text_input(
                    "New pantheon name",
                    help="Greek, Hindu, Yoruba, Cherokee, ...")
                cols = st.columns(2)
                with cols[0]:
                    p_region = st.text_input("Region")
                with cols[1]:
                    p_tradition = st.selectbox(
                        "Tradition type",
                        ["mythological", "religious", "folk", "animist"])
            else:
                new_p_name, p_region, p_tradition = "", "", ""

            st.markdown("**Deity** within that pantheon (required):")
            d_name = st.text_input("Deity name")
            cols = st.columns(2)
            with cols[0]:
                d_aliases = st.text_input(
                    "Aliases (comma separated)",
                    help="Alternative names this deity is known by.")
            with cols[1]:
                d_domain = st.text_input(
                    "Domain",
                    help="water, hunt, fertility, sun, ...")

            if st.form_submit_button("Save pantheon + deity", type="primary"):
                if not d_name.strip():
                    st.warning("Deity name is required.")
                else:
                    try:
                        if picked_p_name == "+ create new pantheon":
                            if not new_p_name.strip():
                                st.warning("New pantheon name required.")
                                st.stop()
                            pantheon_id = db.add_pantheon(
                                new_p_name.strip(),
                                region=p_region.strip() or None,
                                tradition_type=p_tradition)
                        else:
                            pantheon_id = str(existing_p[
                                existing_p["name"] == picked_p_name
                            ].iloc[0]["pantheon_id"])

                        aliases = ([a.strip() for a in d_aliases.split(",")
                                    if a.strip()]
                                   if d_aliases.strip() else None)
                        db.add_deity(
                            pantheon_id, d_name.strip(),
                            aliases=aliases,
                            domain=d_domain.strip() or None)
                        st.success(f"Saved deity {d_name!r}.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Save failed: {exc}")

    # ---------- Link a species to a deity ----------
    with st.expander("Link a species to a deity", expanded=False):
        deities = db.list_deities() if hasattr(db, "list_deities") else None
        # Build deities list inline (function may not be in db.py)
        import pandas as _pd
        from sqlalchemy import text as _text
        deities = _pd.read_sql(_text("""
            SELECT de.deity_id, de.name AS deity, p.name AS pantheon
            FROM deity de JOIN pantheon p ON p.pantheon_id = de.pantheon_id
            ORDER BY p.name, de.name
        """), db.get_engine())
        if deities.empty:
            st.caption("Add a pantheon and deity first, above.")
        else:
            with st.form("link_species_deity_form"):
                sp_id = _species_picker("Species", key="linksd_sp")
                deity_ids = deities["deity_id"].tolist()

                def fmt_d(did):
                    row = deities[deities["deity_id"] == did].iloc[0]
                    return f"{row['deity']} ({row['pantheon']})"

                deity_pick = st.selectbox(
                    "Deity", deity_ids, format_func=fmt_d)
                relationship = st.selectbox(
                    "Relationship",
                    ["sacred_to", "avatar_of", "offering", "companion",
                     "symbol_of"])
                note = st.text_area("Note (optional)", height=68)
                if st.form_submit_button("Save link", type="primary"):
                    if sp_id and deity_pick:
                        try:
                            db.link_species_deity(
                                sp_id, str(deity_pick),
                                relationship=relationship,
                                note=note.strip() or None,
                                contributor_id=contributor_id)
                            st.success("Linked.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Save failed: {exc}")
                    else:
                        st.warning("Pick a species and a deity.")

    # ---------- Add a cultural connection ----------
    with st.expander("Add a cultural connection", expanded=False):
        with st.form("add_cultural_form"):
            sp_id = _species_picker("Species", key="addcc_sp")
            culture = st.text_input(
                "Culture",
                help="Cherokee, Armenian, Yoruba, Mayan, ...")
            sig = st.selectbox(
                "Significance type",
                ["totem", "medicinal", "ceremonial", "foundational",
                 "symbolic", "agricultural", "musical", "other"])
            description = st.text_area(
                "Description", height=120,
                help="What does this species mean to this culture?")
            source = st.text_input(
                "Source (optional)",
                help="A citation or URL where this connection is documented.")
            if st.form_submit_button(
                    "Save cultural connection", type="primary"):
                if not sp_id or not culture.strip():
                    st.warning("Species and culture are both required.")
                else:
                    try:
                        db.add_cultural_connection(
                            sp_id, culture.strip(),
                            significance_type=sig,
                            description=description.strip() or None,
                            source=source.strip() or None,
                            contributor_id=contributor_id)
                        st.success("Saved.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Save failed: {exc}")
