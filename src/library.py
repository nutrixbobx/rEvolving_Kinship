"""
The kinship Library tab.

Two halves: a public browse of every community knowledge surface (species,
trees, names, stories, dishes, pantheons, cultural connections), and an
admin-only entry panel for adding new rows from the dashboard.

Reads are cached per session with @st.cache_data so opening the tab doesn't
refetch every dataframe on every Streamlit rerun. Cache is cleared
automatically after any successful admin write so visitors see new entries
immediately. Each expander shows a row count in its title so visitors know
what's inside before clicking.
"""

from __future__ import annotations

import streamlit as st

from src import db
from src import i18n


# ---------------------------------------------------------------------------
# Cached read wrappers
# ---------------------------------------------------------------------------
# 90-second TTL: short enough that cross-user changes propagate quickly,
# long enough that interaction-driven reruns are free.
_TTL = 90


@st.cache_data(ttl=_TTL, show_spinner=False)
def _cached_species_overview():
    return db.list_species_overview()


@st.cache_data(ttl=_TTL, show_spinner=False)
def _cached_trees():
    return db.list_trees()


@st.cache_data(ttl=_TTL, show_spinner=False)
def _cached_names():
    return db.list_all_names()


@st.cache_data(ttl=_TTL, show_spinner=False)
def _cached_stories():
    return db.list_stories()


@st.cache_data(ttl=_TTL, show_spinner=False)
def _cached_dishes():
    return db.list_dishes()


@st.cache_data(ttl=_TTL, show_spinner=False)
def _cached_dish_ingredients():
    return db.list_dish_ingredients()


@st.cache_data(ttl=_TTL, show_spinner=False)
def _cached_pantheons():
    try:
        return db.list_pantheons()
    except Exception:
        import pandas as _pd
        return _pd.DataFrame()


@st.cache_data(ttl=_TTL, show_spinner=False)
def _cached_species_deities():
    return db.list_species_deities()


@st.cache_data(ttl=_TTL, show_spinner=False)
def _cached_cultural():
    try:
        return db.list_cultural_connections()
    except Exception:
        import pandas as _pd
        return _pd.DataFrame()


@st.cache_data(ttl=_TTL, show_spinner=False)
def _cached_species_picker():
    return db.list_species_for_picker()


@st.cache_data(ttl=_TTL, show_spinner=False)
def _cached_my_stories(cid):
    return db.list_user_stories(cid)


@st.cache_data(ttl=_TTL, show_spinner=False)
def _cached_my_dishes(cid):
    return db.list_user_dishes(cid)


@st.cache_data(ttl=_TTL, show_spinner=False)
def _cached_my_names(cid):
    return db.list_user_names(cid)


@st.cache_data(ttl=_TTL, show_spinner=False)
def _cached_my_cultural(cid):
    return db.list_user_cultural(cid)


@st.cache_data(ttl=30, show_spinner=False)
def _cached_recent_contribs_lib(limit):
    return db.recent_contributions(limit=limit)


def _invalidate_all_caches() -> None:
    """Clear every cached read in this module so the next page render
    reflects fresh data after a write."""
    for fn in (_cached_species_overview, _cached_trees, _cached_names,
               _cached_stories, _cached_dishes, _cached_dish_ingredients,
               _cached_pantheons, _cached_species_deities,
               _cached_cultural, _cached_species_picker,
               _cached_my_stories, _cached_my_dishes, _cached_my_names,
               _cached_my_cultural, _cached_recent_contribs_lib):
        try:
            fn.clear()
        except Exception:
            pass


def _csv_download(df, name: str, key: str) -> None:
    """Compact CSV download button under each dataframe."""
    if df.empty:
        return
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        f"Download {name}.csv  ·  {len(df)} rows",
        csv, file_name=f"{name}.csv", mime="text/csv",
        key=f"dl_{key}",
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def render(is_admin: bool, can_edit_contribution=None, current_contributor_id: str | None = None) -> None:
    from src import theme, auth as _auth
    theme.section_heading("The kinship library", kicker="Community knowledge")
    st.markdown(
        "Every name a species answers to, every story it appears in, every "
        "dish it ends up in, every deity it stands beside. The library is "
        "where the cultural layer lives. New entries show up the moment "
        "you save them; reads are cached for about ninety seconds."
    )

    can_write = _auth.can_write()
    is_editor_or_admin = _auth.is_editor_or_admin()
    is_guest = _auth.is_guest()

    if is_editor_or_admin:
        browse, add, manage = st.tabs(["Browse", "Add", "Manage"])
    elif can_write:
        browse, add = st.tabs(["Browse", "Add"])
        manage = None
    else:
        # Guests + not-yet-named: no Add tab surfaces at all.
        browse, = st.tabs(["Browse"])
        add = None
        manage = None

    with browse:
        if current_contributor_id:
            _render_my_contributions(current_contributor_id,
                                     can_edit_contribution,
                                     is_editor_or_admin)
        _render_browse()
    if add is not None:
        with add:
            _render_admin_entry(is_editor_or_admin=is_editor_or_admin)
    else:
        # No Add tab — offer the upgrade path instead.
        if is_guest:
            st.info("Guests can browse the library but can't add "
                     "entries. Head to your Profile to upgrade with "
                     "an access code, then come back here to add.")
        else:
            st.info("Give yourself a name in the sidebar, then sign "
                     "up with an access code to add to the library.")
    if manage is not None:
        with manage:
            _render_manage()


# ---------------------------------------------------------------------------
# Browse: read-only views of every domain, each with row count + CSV export
# ---------------------------------------------------------------------------
def _render_browse() -> None:
    # Species overview is the natural lead — one row per real species with
    # rolled-up counts across every other surface.
    df_sp = _cached_species_overview()
    with st.expander(
            f"Species  ·  {len(df_sp)} canonical species", expanded=True):
        if df_sp.empty:
            st.caption("No species yet. The Request station tab is where "
                       "everything starts.")
        else:
            st.dataframe(df_sp, use_container_width=True, hide_index=True)
            _csv_download(df_sp, "species_overview", "species_csv")

    df_tr = _cached_trees()
    with st.expander(
            f"Trees  ·  {len(df_tr)} kinship trees", expanded=False):
        if df_tr.empty:
            st.caption("No trees yet.")
        else:
            st.dataframe(df_tr, use_container_width=True, hide_index=True)
            _csv_download(df_tr, "trees", "trees_csv")

    df_nm = _cached_names()
    n_langs = df_nm["language"].nunique() if not df_nm.empty else 0
    with st.expander(
            f"Multilingual names  ·  {len(df_nm)} names "
            f"in {n_langs} languages", expanded=False):
        if df_nm.empty:
            st.caption("No names recorded yet beyond what NCBI gave us. "
                       "Add your first one in the Add tab.")
        else:
            st.dataframe(df_nm, use_container_width=True, hide_index=True)
            _csv_download(df_nm, "names", "names_csv")

    df_st = _cached_stories()
    with st.expander(
            f"Stories  ·  {len(df_st)} stories", expanded=False):
        if df_st.empty:
            st.caption("No stories yet. The Add tab is where they begin.")
        else:
            st.dataframe(df_st, use_container_width=True, hide_index=True)
            _csv_download(df_st, "stories", "stories_csv")

    df_di = _cached_dishes()
    with st.expander(
            f"Dishes and recipes  ·  {len(df_di)} dishes", expanded=False):
        if df_di.empty:
            st.caption("No dishes yet. The Armenian Dolma tree was the "
                       "seed; the Library is where the kitchen lives.")
        else:
            st.dataframe(df_di, use_container_width=True, hide_index=True)
            _csv_download(df_di, "dishes", "dishes_csv")
            df_ing = _cached_dish_ingredients()
            if not df_ing.empty:
                st.markdown(
                    f"**Ingredients across all dishes**  ·  {len(df_ing)} links")
                st.dataframe(df_ing, use_container_width=True,
                             hide_index=True)
                _csv_download(df_ing, "dish_ingredients", "ingredients_csv")

    df_pa = _cached_pantheons()
    df_sd = _cached_species_deities()
    with st.expander(
            f"Pantheons and deities  ·  {len(df_pa)} pantheons, "
            f"{len(df_sd)} species links", expanded=False):
        if df_pa.empty:
            st.caption("No pantheons yet. Any tradition is welcome: Greek, Mayan, Yoruba, Hindu, Cherokee, Armenian, anything held by anyone in your community.")
        else:
            st.dataframe(df_pa, use_container_width=True, hide_index=True)
            _csv_download(df_pa, "pantheons", "pantheons_csv")
            if not df_sd.empty:
                st.markdown("**Species linked to deities**")
                st.dataframe(df_sd, use_container_width=True,
                             hide_index=True)
                _csv_download(df_sd, "species_deities", "species_deities_csv")

    df_cc = _cached_cultural()
    with st.expander(
            f"Cultural connections  ·  {len(df_cc)} connections",
            expanded=False):
        if df_cc.empty:
            st.caption("Nothing here yet. Cultural connections hold the looser ties: a species as totem, as medicine, as ceremony, or as the heart of a foodway.")
        else:
            st.dataframe(df_cc, use_container_width=True, hide_index=True)
            _csv_download(df_cc, "cultural_connections", "cultural_csv")


# ---------------------------------------------------------------------------
# Admin entry forms (write paths)
# ---------------------------------------------------------------------------
def _species_picker(label: str, key: str,
                    allow_none: bool = False,
                    help: str | None = None) -> str | None:
    df = _cached_species_picker()
    if df.empty:
        st.warning("No species in the database yet. Add some via the "
                   "Request station tab first.")
        return None
    options = list(df["species_id"])
    if allow_none:
        options = [""] + options

    def fmt(sid):
        if not sid:
            return "(none, tree-level)"
        row = df[df["species_id"] == sid].iloc[0]
        if row["common_name"]:
            return (f"{row['common_name']}  "
                    f"({row['canonical_scientific_name']})")
        return row["canonical_scientific_name"]

    return st.selectbox(label, options, format_func=fmt, key=key,
                        help=help) or None


def _tree_picker(label: str, key: str,
                 allow_none: bool = True) -> str | None:
    trees = _cached_trees()
    if trees.empty:
        return None
    options = [""] if allow_none else []
    name_to_id = {}
    for name in trees["tree_name"].tolist():
        tid = db.get_tree_id(name)
        if tid:
            options.append(tid)
            name_to_id[tid] = name

    def fmt(tid):
        if not tid:
            return "(none, species-level)"
        return name_to_id.get(tid, tid)

    return st.selectbox(label, options, format_func=fmt, key=key) or None


def _saved(message: str) -> None:
    """Common post-write step: clear caches, flash success, rerun."""
    _invalidate_all_caches()
    st.success(message)
    st.rerun()


def _render_admin_entry(is_editor_or_admin: bool = False) -> None:
    from src import auth as _auth
    me = _auth.current_user()
    contributor_id = me.get("contributor_id")
    if not contributor_id:
        st.info("Sign in or give a guest name in the sidebar to attribute "
                "your contributions.")
        return
    st.caption(
        f"Adding as **{me.get('name')}** "
        f"({(me.get('role') or 'guest').upper()}). "
        "Everything you save is attributed to you and visible the moment "
        "you save it.")

    # ---------- Multilingual name ----------
    with st.expander("Add a name in another language or category",
                     expanded=False):
        # Pickers OUTSIDE the form so their interactive widgets (selectbox
        # branches, character keyboard buttons) actually fire on each
        # click. Forms only submit when the submit button is pressed —
        # interactive widgets inside them don't trigger reruns.
        sp_id = _species_picker("Species", key="addname_sp")
        lang = i18n.render_language_picker(
            "Language", key="addname_lang", initial_code="ENG")
        region = i18n.render_region_picker(
            "Region (optional)", key="addname_region")
        non_latin = st.checkbox(
            "Script (non-Latin)",
            key="addname_script_flag",
            help="Tick if this name is written in a script other than "
                 "Latin (Devanagari, Armenian, Han, etc.). A character "
                 "keyboard appears below to compose it.")
        script_name = None
        if non_latin:
            composed = i18n.render_script_keyboard("addname_kbd")
            script_name = st.session_state.get("addname_kbd_script_pick")
            if composed:
                st.caption(
                    f"Composed: **{composed}** — paste into Name below.")

        # The form holds just the fields that don't need live interactivity.
        with st.form("add_name_form"):
            name_text = st.text_input(
                "Name", help="The name as written in its language.")
            cat = st.selectbox(
                "Category",
                ["common", "folk", "ceremonial", "scientific", "synonym"])
            is_pref = st.checkbox(
                "Make this the preferred name for this species + language",
                value=False)
            name_notes = st.text_area(
                "Notes (optional)",
                placeholder="Where this name comes from, what it "
                             "means, when it is used...",
                height=68)
            if st.form_submit_button("Save name", type="primary"):
                if sp_id and (name_text or "").strip():
                    db.add_species_name(
                        sp_id, name_text.strip(),
                        language=lang or "ENG",
                        category=cat, source="community",
                        is_preferred=is_pref,
                        contributor_id=contributor_id,
                        region_code=region,
                        script=script_name if non_latin else None,
                        notes=(name_notes or "").strip() or None)
                    _saved(f"Saved {name_text!r} ({lang}/{cat}).")
                else:
                    st.warning("Need a species and a non-empty name.")

    # ---------- Story ----------
    with st.expander("Add a story", expanded=False):
        # Pickers outside the form (interactive)
        sp_id = _species_picker(
            "Species (optional if linked to a tree instead)",
            key="addstory_sp", allow_none=True)
        tr_id = _tree_picker(
            "Tree (optional if linked to a species instead)",
            key="addstory_tr")
        # Language picker outside the form (interactive)
        story_lang = i18n.render_language_picker(
            "Language", key="addstory_lang", initial_code="ENG")
        with st.form("add_story_form"):
            title = st.text_input(
                "Title (optional)",
                help="Leave blank for a short note without a heading.")
            body = st.text_area(
                "Story body", height=180,
                help="Plain text; line breaks render as paragraphs.")
            region = st.text_input(
                "Region (optional)", key="addstory_region")
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
                            language=story_lang or "ENG",
                            region=region.strip() or None,
                            contributor_id=contributor_id)
                        _saved("Saved.")
                    except Exception as exc:
                        st.error(f"Save failed: {exc}")

    # ---------- Dish + ingredients ----------
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
            st.markdown("**Ingredients**. Pick a species per row, add roles "
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
                        _saved(
                            f"Saved dish {d_name!r} with {linked} ingredient(s).")
                    except Exception as exc:
                        st.error(f"Save failed: {exc}")

    # ---------- Pantheon + deity ----------
    if is_editor_or_admin:
      with st.expander("Add a pantheon and a deity within it",
                     expanded=False):
        with st.form("add_pantheon_form"):
            existing_p = _cached_pantheons()
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
                        _saved(f"Saved deity {d_name!r}.")
                    except Exception as exc:
                        st.error(f"Save failed: {exc}")

    # ---------- Link species to deity ----------
    with st.expander("Link a species to a deity", expanded=False):
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
                            _saved("Linked.")
                        except Exception as exc:
                            st.error(f"Save failed: {exc}")
                    else:
                        st.warning("Pick a species and a deity.")

    # ---------- Cultural connection ----------
    if not is_editor_or_admin:
        st.caption("Adding a new pantheon or deity is editor/admin only "
                   "since they're structural. To suggest a new pantheon, "
                   "leave it in a story and an editor will lift it up.")
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
                        _saved("Saved.")
                    except Exception as exc:
                        st.error(f"Save failed: {exc}")


# ---------------------------------------------------------------------------
# Per-user "Your contributions" section (Library → Browse top)
# ---------------------------------------------------------------------------
def _render_my_contributions(contributor_id: str,
                              can_edit_contribution,
                              is_editor_or_admin: bool) -> None:
    """A compact expander that lists the current user's contributions across
    stories, dishes, names, and cultural connections, with a delete button
    on every row. Editors and admins additionally get a 'Recent community
    additions' panel for moderation."""

    my_stories = _cached_my_stories(contributor_id)
    my_dishes = _cached_my_dishes(contributor_id)
    my_names = _cached_my_names(contributor_id)
    my_cc = _cached_my_cultural(contributor_id)

    total = len(my_stories) + len(my_dishes) + len(my_names) + len(my_cc)
    title = (f"Your contributions  ·  {total} items"
             if total else "Your contributions")

    with st.expander(title, expanded=False):
        if total == 0:
            st.caption("Nothing yet. Add a story, a dish, a multilingual "
                       "name, or a cultural connection from the Add tab.")
            return

        if not my_stories.empty:
            st.markdown("**Stories**")
            for _, r in my_stories.iterrows():
                _delete_row(
                    label=r.get("title") or "(untitled)",
                    sub=(f"for {r['species']}"
                         if r.get("species") else None),
                    when=r.get("contributed_at"),
                    key=f"lib_mc_story_{r['story_id']}",
                    on_delete=lambda sid=r["story_id"]:
                        db.delete_story(sid),
                    edit_kind="story", edit_id=r["story_id"])

        if not my_dishes.empty:
            st.markdown("**Dishes**")
            for _, r in my_dishes.iterrows():
                _delete_row(
                    label=r.get("name") or "(unnamed)",
                    sub=r.get("cuisine"),
                    when=r.get("contributed_at"),
                    key=f"lib_mc_dish_{r['dish_id']}",
                    on_delete=lambda did=r["dish_id"]:
                        db.delete_dish(did),
                    edit_kind="dish", edit_id=r["dish_id"])

        if not my_names.empty:
            st.markdown("**Multilingual names**")
            for _, r in my_names.iterrows():
                _delete_row(
                    label=f"{r['name_text']} ({r.get('language')})",
                    sub=(f"for {r['species']}"
                         if r.get("species") else None),
                    when=r.get("contributed_at"),
                    key=f"lib_mc_name_{r['name_id']}",
                    on_delete=lambda nid=r["name_id"]:
                        db.delete_species_name(nid))

        if not my_cc.empty:
            st.markdown("**Cultural connections**")
            for _, r in my_cc.iterrows():
                _delete_row(
                    label=f"{r.get('culture','')} / "
                          f"{r.get('significance_type','tie')}",
                    sub=(f"for {r['species']}"
                         if r.get("species") else None),
                    when=r.get("contributed_at"),
                    key=f"lib_mc_cc_{r['connection_id']}",
                    on_delete=lambda cid=r["connection_id"]:
                        db.delete_cultural_connection(cid),
                    edit_kind="cultural_connection",
                    edit_id=r["connection_id"])

    if is_editor_or_admin:
        with st.expander("Community review (recent additions, any author)",
                          expanded=False):
            df = _cached_recent_contribs_lib(50)
            if df.empty:
                st.caption("Nothing recent.")
                return
            for _, r in df.iterrows():
                kind = r.get("kind", "?")
                row_id = r.get("row_id")
                # Clickable byline above each row
                _contributor_link(
                    r.get("contributor"),
                    r.get("contributor_id"),
                    key=f"libcrev_byline_{kind}_{row_id}",
                )
                # Only the three rich kinds are inline-editable.
                _editable_kinds = {"story", "dish", "cultural_connection"}
                _delete_row(
                    label=(r.get("title") or "(untitled)") + f"  · {kind}",
                    sub=None,
                    when=r.get("contributed_at"),
                    key=f"lib_review_{kind}_{row_id}",
                    on_delete=lambda k=kind, i=row_id:
                        _delete_by_kind(k, i),
                    edit_kind=(kind if kind in _editable_kinds else None),
                    edit_id=(row_id if kind in _editable_kinds else None))


def _delete_by_kind(kind: str, row_id: str):
    if kind == "story":
        return db.delete_story(row_id)
    if kind == "dish":
        return db.delete_dish(row_id)
    if kind == "name":
        return db.delete_species_name(row_id)
    if kind == "cultural_connection":
        return db.delete_cultural_connection(row_id)
    return None


def _fmt_when_short(when) -> str:
    if when is None:
        return ""
    if isinstance(when, str):
        return when[:10]
    try:
        return when.strftime("%Y-%m-%d")
    except Exception:
        return str(when)[:10]


def _delete_row(label: str, sub: str | None, when,
                 key: str, on_delete,
                 edit_kind: str | None = None,
                 edit_id: str | None = None) -> None:
    """Render one row with Delete (always) and Edit (when edit_kind/edit_id
    are supplied AND we know how to edit that kind). The edit form expands
    inline beneath the row when toggled."""
    has_edit = edit_kind in ("story", "dish", "cultural_connection",
                            "name", "pantheon", "deity",
                            "species_deity") and bool(edit_id)
    cols = (st.columns([5, 1, 1]) if has_edit else st.columns([6, 2]))
    with cols[0]:
        when_str = _fmt_when_short(when)
        sub_html = (f' <span style="color:#7a8d86;font-size:11px">· {sub}</span>'
                    if sub else "")
        when_html = (f' <span style="color:#9ab3ab;font-size:11px">'
                     f'· {when_str}</span>'
                     if when_str else "")
        st.markdown(
            f'<div style="padding:6px 0;border-bottom:1px solid #1c2e2b;'
            f'color:#e8f3ef">{label}{sub_html}{when_html}</div>',
            unsafe_allow_html=True,
        )
    if has_edit:
        with cols[1]:
            edit_flag = f"_edit_open_{edit_kind}_{edit_id}"
            if st.button("Edit", key=f"{key}_edit",
                         use_container_width=True):
                st.session_state[edit_flag] = not st.session_state.get(
                    edit_flag, False)
                st.rerun()
        with cols[2]:
            _delete_button(key, on_delete)
    else:
        with cols[1]:
            _delete_button(key, on_delete)

    # If the edit toggle is on, render the inline form below the row.
    if has_edit and st.session_state.get(f"_edit_open_{edit_kind}_{edit_id}"):
        _render_edit_form_inline(edit_kind, edit_id, key_prefix=key)


def _delete_button(key: str, on_delete) -> None:
    if st.button("Delete", key=key, use_container_width=True):
        try:
            on_delete()
            _invalidate_all_caches()
            try:
                from src import profile as _p
                _p._invalidate_profile_caches()
            except Exception:
                pass
            st.success("Deleted.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


def _render_edit_form_inline(kind: str, row_id: str,
                              key_prefix: str) -> None:
    """Pull the current row, render a small form, and PATCH on save."""
    engine = db.get_engine()
    from sqlalchemy import text as _sa_text

    if kind == "story":
        with engine.connect() as c:
            row = c.execute(_sa_text(
                "SELECT title, body_text, language_code, region_code "
                "FROM story WHERE story_id = :i"), {"i": row_id}).fetchone()
        if not row:
            st.warning("Row not found — refresh.")
            return
        with st.form(f"{key_prefix}_story_form"):
            t = st.text_input("Title", value=row[0] or "")
            body = st.text_area("Story", value=row[1] or "", height=140)
            lcols = st.columns(2)
            with lcols[0]:
                # Plain text input inside the form (selectbox + conditional
                # reveal doesn't work in forms; user types 3-letter ISO 639-3)
                lang = st.text_input(
                    "Language (3-letter ISO 639-3)",
                    value=row[2] or "ENG",
                    key=f"{key_prefix}_story_lang",
                    max_chars=5)
            with lcols[1]:
                region = st.text_input("Region (optional)", value=row[3] or "")
            save = st.form_submit_button("Save changes", type="primary",
                                          use_container_width=True)
            cancel = st.form_submit_button("Cancel",
                                            use_container_width=True)
        if cancel:
            st.session_state.pop(f"_edit_open_story_{row_id}", None)
            st.rerun()
        if save:
            db.update_story(row_id, {
                "title": (t or "").strip() or None,
                "body_text": (body or "").strip() or None,
                "language_code": lang or "ENG",
                "region_code": (region or "").strip() or None,
            })
            _invalidate_all_caches()
            try:
                from src import profile as _p
                _p._invalidate_profile_caches()
            except Exception:
                pass
            st.session_state.pop(f"_edit_open_story_{row_id}", None)
            st.success("Saved.")
            st.rerun()
        return

    if kind == "dish":
        with engine.connect() as c:
            row = c.execute(_sa_text(
                "SELECT name, cuisine, origin_region, description "
                "FROM dish WHERE dish_id = :i"), {"i": row_id}).fetchone()
        if not row:
            st.warning("Row not found — refresh.")
            return
        with st.form(f"{key_prefix}_dish_form"):
            name = st.text_input("Name", value=row[0] or "")
            c1, c2 = st.columns(2)
            with c1:
                cuisine = st.text_input("Cuisine", value=row[1] or "")
            with c2:
                origin = st.text_input("Origin region", value=row[2] or "")
            desc = st.text_area("Description", value=row[3] or "", height=110)
            save = st.form_submit_button("Save changes", type="primary",
                                          use_container_width=True)
            cancel = st.form_submit_button("Cancel",
                                            use_container_width=True)
        if cancel:
            st.session_state.pop(f"_edit_open_dish_{row_id}", None)
            st.rerun()
        if save:
            db.update_dish(row_id, {
                "name": (name or "").strip() or row[0],
                "cuisine": (cuisine or "").strip() or None,
                "origin_region": (origin or "").strip() or None,
                "description": (desc or "").strip() or None,
            })
            _invalidate_all_caches()
            try:
                from src import profile as _p
                _p._invalidate_profile_caches()
            except Exception:
                pass
            st.session_state.pop(f"_edit_open_dish_{row_id}", None)
            st.success("Saved.")
            st.rerun()
        return

    if kind == "cultural_connection":
        with engine.connect() as c:
            row = c.execute(_sa_text(
                "SELECT culture, significance_type, description, source "
                "FROM cultural_connection WHERE connection_id = :i"),
                {"i": row_id}).fetchone()
        if not row:
            st.warning("Row not found — refresh.")
            return
        with st.form(f"{key_prefix}_cc_form"):
            culture = st.text_input("Culture", value=row[0] or "")
            sig = st.text_input("Significance type",
                                value=row[1] or "")
            desc = st.text_area("Description", value=row[2] or "",
                                height=110)
            src = st.text_input("Source (optional)", value=row[3] or "")
            save = st.form_submit_button("Save changes", type="primary",
                                          use_container_width=True)
            cancel = st.form_submit_button("Cancel",
                                            use_container_width=True)
        if cancel:
            st.session_state.pop(
                f"_edit_open_cultural_connection_{row_id}", None)
            st.rerun()
        if save:
            db.update_cultural_connection(row_id, {
                "culture": (culture or "").strip() or row[0],
                "significance_type": (sig or "").strip() or None,
                "description": (desc or "").strip() or None,
                "source": (src or "").strip() or None,
            })
            _invalidate_all_caches()
            try:
                from src import profile as _p
                _p._invalidate_profile_caches()
            except Exception:
                pass
            st.session_state.pop(
                f"_edit_open_cultural_connection_{row_id}", None)
            st.success("Saved.")
            st.rerun()
        return

    if kind == "name":
        with engine.connect() as c:
            row = c.execute(_sa_text(
                "SELECT name_text, language_code, name_category, "
                "       region_code, is_preferred "
                "FROM species_name WHERE name_id = :i"),
                {"i": row_id}).fetchone()
        if not row:
            st.warning("Row not found — refresh.")
            return
        with st.form(f"{key_prefix}_name_form"):
            n = st.text_input("Name", value=row[0] or "")
            lang = st.text_input(
                "Language (3-letter ISO 639-3)",
                value=row[1] or "ENG",
                key=f"{key_prefix}_name_lang",
                max_chars=5)
            c1, c2 = st.columns(2)
            with c1:
                cats = ["common","folk","ceremonial","scientific","synonym"]
                cat = st.selectbox(
                    "Category", cats,
                    index=cats.index(row[2] or "common"))
            with c2:
                region = st.text_input("Region (optional)",
                                       value=row[3] or "")
            pref = st.checkbox("Preferred name for this "
                                "(species, language, category)",
                                value=bool(row[4]))
            save = st.form_submit_button("Save changes", type="primary",
                                          use_container_width=True)
            cancel = st.form_submit_button("Cancel",
                                            use_container_width=True)
        if cancel:
            st.session_state.pop(f"_edit_open_name_{row_id}", None)
            st.rerun()
        if save:
            db.update_species_name(row_id, {
                "name_text": (n or "").strip() or row[0],
                "language_code": lang or "ENG",
                "name_category": cat,
                "region_code": (region or "").strip() or None,
                "is_preferred": bool(pref),
            })
            _invalidate_all_caches()
            try:
                from src import profile as _p
                _p._invalidate_profile_caches()
            except Exception:
                pass
            st.session_state.pop(f"_edit_open_name_{row_id}", None)
            st.success("Saved.")
            st.rerun()
        return

    if kind == "pantheon":
        with engine.connect() as c:
            row = c.execute(_sa_text(
                "SELECT name, region, tradition_type "
                "FROM pantheon WHERE pantheon_id = :i"),
                {"i": row_id}).fetchone()
        if not row:
            st.warning("Row not found — refresh.")
            return
        with st.form(f"{key_prefix}_pantheon_form"):
            name = st.text_input("Name", value=row[0] or "")
            c1, c2 = st.columns(2)
            with c1:
                region = st.text_input("Region", value=row[1] or "")
            with c2:
                trads = ["religious","mythological","folk","animist"]
                tradition = st.selectbox(
                    "Tradition", trads,
                    index=trads.index(row[2] or "mythological"))
            save = st.form_submit_button("Save changes", type="primary",
                                          use_container_width=True)
            cancel = st.form_submit_button("Cancel",
                                            use_container_width=True)
        if cancel:
            st.session_state.pop(f"_edit_open_pantheon_{row_id}", None)
            st.rerun()
        if save:
            db.update_pantheon(row_id, {
                "name": (name or "").strip() or row[0],
                "region": (region or "").strip() or None,
                "tradition_type": tradition,
            })
            _invalidate_all_caches()
            st.session_state.pop(f"_edit_open_pantheon_{row_id}", None)
            st.success("Saved.")
            st.rerun()
        return

    if kind == "deity":
        with engine.connect() as c:
            row = c.execute(_sa_text(
                "SELECT name, domain, aliases "
                "FROM deity WHERE deity_id = :i"),
                {"i": row_id}).fetchone()
        if not row:
            st.warning("Row not found — refresh.")
            return
        aliases_str = ", ".join(row[2]) if row[2] else ""
        with st.form(f"{key_prefix}_deity_form"):
            name = st.text_input("Name", value=row[0] or "")
            domain = st.text_input("Domain", value=row[1] or "",
                                    help="water, hunt, fertility, death...")
            aliases = st.text_input(
                "Alternate names (comma-separated)", value=aliases_str)
            save = st.form_submit_button("Save changes", type="primary",
                                          use_container_width=True)
            cancel = st.form_submit_button("Cancel",
                                            use_container_width=True)
        if cancel:
            st.session_state.pop(f"_edit_open_deity_{row_id}", None)
            st.rerun()
        if save:
            db.update_deity(row_id, {
                "name": (name or "").strip() or row[0],
                "domain": (domain or "").strip() or None,
                "aliases": aliases,
            })
            _invalidate_all_caches()
            st.session_state.pop(f"_edit_open_deity_{row_id}", None)
            st.success("Saved.")
            st.rerun()
        return

    if kind == "species_deity":
        parts = (row_id or "").split("||")
        if len(parts) != 3:
            st.warning("Edit key shape unexpected — refresh.")
            return
        sp_id, de_id, rel = parts
        with engine.connect() as c:
            row = c.execute(_sa_text(
                "SELECT note FROM species_deity "
                "WHERE species_id = :s AND deity_id = :d "
                "  AND relationship = :r"),
                {"s": sp_id, "d": de_id, "r": rel}).fetchone()
        if not row:
            st.warning("Row not found — refresh.")
            return
        with st.form(f"{key_prefix}_sd_form"):
            st.caption(f"Editing the note. To change the relationship "
                        f"type ({rel}), delete this link and add it back "
                        "with the new type.")
            note = st.text_area("Note", value=row[0] or "", height=80)
            save = st.form_submit_button("Save changes", type="primary",
                                          use_container_width=True)
            cancel = st.form_submit_button("Cancel",
                                            use_container_width=True)
        if cancel:
            st.session_state.pop(f"_edit_open_species_deity_{row_id}",
                                  None)
            st.rerun()
        if save:
            db.update_species_deity_note(sp_id, de_id, rel,
                                          (note or "").strip() or None)
            _invalidate_all_caches()
            st.session_state.pop(f"_edit_open_species_deity_{row_id}",
                                  None)
            st.success("Saved.")
            st.rerun()
        return


def _contributor_link(name: str | None,
                       contributor_id: str | None,
                       key: str) -> None:
    """Render a contributor name as a small button that, when clicked, sets
    session_state['viewing_profile_of'] so the Profile tab shows them.
    Falls back to plain text when there's no contributor_id."""
    label = name or "anonymous"
    if contributor_id:
        if st.button(f"by {label}", key=key,
                     help=f"View {label}'s profile"):
            st.session_state["viewing_profile_of"] = str(contributor_id)
            st.success(f"Opened {label}'s profile in the Profile tab.")
    else:
        st.markdown(
            f'<span style="color:#9ab3ab;font-size:11px">by {label}</span>',
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Manage tab (editor/admin only). One sub-tab per kind, each listing every
# row with Edit (where supported) and Delete buttons.
# ---------------------------------------------------------------------------
def _render_manage() -> None:
    from src import theme as _theme
    _theme.section_heading("Manage the library",
                            kicker="Editor / admin")
    st.caption("Every row across the community layer, with Edit (where it "
                "makes sense) and Delete. Changes invalidate caches "
                "automatically, so Browse reflects them right away.")

    tabs = st.tabs([
        "Stories", "Dishes", "Names", "Cultural", "Pantheons & deities",
        "Trees", "Clade dates",
    ])

    with tabs[0]:
        df = _cached_stories()
        if df.empty:
            st.caption("No stories yet.")
        else:
            _bulk_delete_bar("mng_stories",
                              delete_one=lambda i: db.delete_story(i),
                              label="stories")
            for _, r in df.iterrows():
                _bulk_checkbox("mng_stories", str(r["story_id"]))
                sub = (f"for {r['species']}" if r.get("species")
                       else (f"in {r['tree']}" if r.get("tree") else None))
                _delete_row(
                    label=r.get("title") or "(untitled)",
                    sub=sub,
                    when=r.get("contributed_at"),
                    key=f"mng_story_{r['story_id']}",
                    on_delete=lambda sid=r["story_id"]:
                        db.delete_story(sid),
                    edit_kind="story", edit_id=r["story_id"])

    with tabs[1]:
        df = _cached_dishes()
        if df.empty:
            st.caption("No dishes yet.")
        else:
            _bulk_delete_bar("mng_dishes",
                              delete_one=lambda i: db.delete_dish(i),
                              label="dishes")
            for _, r in df.iterrows():
                _bulk_checkbox("mng_dishes", str(r["dish_id"]))
                sub_bits = []
                if r.get("cuisine"): sub_bits.append(r["cuisine"])
                if r.get("ingredient_count"):
                    sub_bits.append(f"{int(r['ingredient_count'])} ingredient(s)")
                _delete_row(
                    label=r.get("name") or "(unnamed)",
                    sub=" · ".join(sub_bits) if sub_bits else None,
                    when=r.get("contributed_at"),
                    key=f"mng_dish_{r['dish_id']}",
                    on_delete=lambda did=r["dish_id"]:
                        db.delete_dish(did),
                    edit_kind="dish", edit_id=r["dish_id"])

    with tabs[2]:
        df = _cached_names()
        if df.empty:
            st.caption("No multilingual names yet.")
        else:
            # Names are tiny — no inline edit. Just delete + add fresh.
            for _, r in df.iterrows():
                label = (f"{r['name_text']} "
                         f"({r.get('language')}/{r.get('category')})")
                if r.get("is_preferred"):
                    label += " ★"
                # `_cached_names()` doesn't currently return name_id (it's
                # the species view). We need the row id, so call the
                # per-row picker by name_id via db.list_user_names equivalent.
                # Simpler: pull names with ids in a manage-only view.
                pass
            # Fall back to a dataframe + bulk delete for now.
            st.dataframe(df, use_container_width=True, hide_index=True)
            _render_manage_names_table()

    with tabs[3]:
        df = _cached_cultural()
        if df.empty:
            st.caption("No cultural connections yet.")
        else:
            _bulk_delete_bar("mng_cultural",
                              delete_one=lambda i:
                                  db.delete_cultural_connection(i),
                              label="cultural connections")
            for _, r in df.iterrows():
                _bulk_checkbox("mng_cultural", str(r["connection_id"]))
                _delete_row(
                    label=f"{r.get('culture','')} / "
                          f"{r.get('significance_type','tie')}",
                    sub=(f"for {r['species']}"
                         if r.get("species") else None),
                    when=None,
                    key=f"mng_cc_{r['connection_id']}",
                    on_delete=lambda cid=r["connection_id"]:
                        db.delete_cultural_connection(cid),
                    edit_kind="cultural_connection",
                    edit_id=r["connection_id"])

    with tabs[4]:
        # Pantheons + deities. Editor/admin only (already gated by being
        # inside Manage). Delete pantheon cascades to deities, deity cascades
        # to species_deity links.
        df_p = _cached_pantheons()
        if df_p.empty:
            st.caption("No pantheons yet.")
        else:
            st.markdown("**Pantheons** (deleting a pantheon removes all its "
                         "deities)")
            _bulk_delete_bar("mng_pantheons",
                              delete_one=lambda i: db.delete_pantheon(i),
                              label="pantheons")
            for _, r in df_p.iterrows():
                _bulk_checkbox("mng_pantheons", str(r["pantheon_id"]))
                _delete_row(
                    label=r.get("name") or "(unnamed)",
                    sub=(f"{r.get('region','')} "
                          f"({int(r.get('deities_count',0))} deities, "
                          f"{int(r.get('species_count',0))} species)"),
                    when=None,
                    key=f"mng_pan_{r['pantheon_id']}",
                    on_delete=lambda pid=r["pantheon_id"]:
                        db.delete_pantheon(pid),
                    edit_kind="pantheon",
                    edit_id=str(r["pantheon_id"]))

            # Deities themselves
            from sqlalchemy import text as _sa_text2
            with db.get_engine().connect() as _c:
                _deity_rows = _c.execute(_sa_text2("""
                    SELECT d.deity_id::text, d.name, d.domain,
                           p.name AS pantheon
                    FROM deity d
                    JOIN pantheon p ON p.pantheon_id = d.pantheon_id
                    ORDER BY p.name, d.name
                """)).fetchall()
            if _deity_rows:
                st.markdown("**Deities** (deleting cascades to species links)")
                for _drow in _deity_rows:
                    _did, _dname, _ddom, _dpan = _drow
                    _delete_row(
                        label=_dname,
                        sub=f"{_dpan}" + (f" · {_ddom}" if _ddom else ""),
                        when=None,
                        key=f"mng_deity_{_did}",
                        on_delete=lambda di=_did: db.delete_deity(di),
                        edit_kind="deity", edit_id=_did)

        # Species-deity links (the joining table)
        # Pull species_deity with id columns so we can edit + delete by id.
        from sqlalchemy import text as _sa_text
        with db.get_engine().connect() as _c:
            _sd_rows = _c.execute(_sa_text("""
                SELECT sd.species_id::text, sd.deity_id::text,
                       sd.relationship,
                       s.canonical_scientific_name AS species,
                       (SELECT sn.name_text FROM species_name sn
                          WHERE sn.species_id = s.species_id
                            AND sn.language_code = 'en'
                            AND sn.name_category = 'common'
                            AND sn.is_preferred = true LIMIT 1) AS common_name,
                       d.name AS deity,
                       p.name AS pantheon
                FROM species_deity sd
                JOIN species s ON s.species_id = sd.species_id
                JOIN deity d ON d.deity_id = sd.deity_id
                JOIN pantheon p ON p.pantheon_id = d.pantheon_id
                ORDER BY s.canonical_scientific_name, p.name, d.name
            """)).fetchall()
        if _sd_rows:
            st.markdown("**Species ↔ deity links** (deleting unlinks; keeps "
                         "both species and deity)")
            for _row in _sd_rows:
                _sp, _de, _rel, _sci, _comm, _dname, _pname = _row
                _composite = f"{_sp}||{_de}||{_rel}"
                _delete_row(
                    label=f"{_comm or _sci} ↔ {_dname}",
                    sub=f"{_pname} · {_rel}",
                    when=None,
                    key=f"mng_sd_{_sp[:8]}_{_de[:8]}_{_rel[:12]}",
                    on_delete=lambda s=_sp, d=_de, r=_rel:
                        db.delete_species_deity_link(s, d, r),
                    edit_kind="species_deity",
                    edit_id=_composite)

    with tabs[5]:
        df_tr = _cached_trees()
        if df_tr.empty:
            st.caption("No trees yet.")
        else:
            st.caption("Deleting a tree removes its species links but leaves "
                        "the species themselves. Renaming + ownership transfer "
                        "live in the Dashboard tab.")
            _bulk_delete_bar("mng_trees",
                              delete_one=lambda n: db.delete_tree(n),
                              label="trees")
            for _, r in df_tr.iterrows():
                _bulk_checkbox("mng_trees", str(r["tree_name"]))
                _delete_row(
                    label=r.get("tree_name") or "(unnamed tree)",
                    sub=f"{int(r.get('species_count', 0))} species",
                    when=r.get("created_at"),
                    key=f"mng_tree_{r['tree_name'][:32]}",
                    on_delete=lambda tn=r["tree_name"]:
                        db.delete_tree(tn))

    with tabs[6]:
        _render_clade_dating()


def _render_manage_names_table() -> None:
    """Names section uses a per-row id picker because list_all_names()
    rolls up rows for browsing. Pull species_name with name_id and offer
    delete one at a time."""
    from sqlalchemy import text as _sa_text
    engine = db.get_engine()
    with engine.connect() as c:
        rows = c.execute(_sa_text("""
            SELECT sn.name_id, sn.name_text, sn.language_code,
                   sn.name_category, sn.is_preferred,
                   s.canonical_scientific_name AS species,
                   co.display_name AS contributor,
                   co.contributor_id AS contributor_id
            FROM species_name sn
            JOIN species s ON s.species_id = sn.species_id
            LEFT JOIN contributor co ON co.contributor_id = sn.contributed_by
            ORDER BY s.canonical_scientific_name, sn.language_code,
                     sn.is_preferred DESC, sn.name_text
            LIMIT 300
        """)).fetchall()
    if not rows:
        return
    with st.expander(f"Delete individual names ({len(rows)} shown)",
                      expanded=False):
        _bulk_delete_bar("mng_names",
                          delete_one=lambda i: db.delete_species_name(i),
                          label="names")
        for row in rows:
            (name_id, name_text, lang, cat, pref, species, contributor,
             contributor_id) = row
            _bulk_checkbox("mng_names", str(name_id))
            label = f"{name_text} ({lang}/{cat})"
            if pref:
                label += " ★"
            _delete_row(
                label=label,
                sub=f"for {species}" if species else None,
                when=None,
                key=f"mng_name_{name_id}",
                on_delete=lambda nid=name_id:
                    db.delete_species_name(nid),
                edit_kind="name", edit_id=str(name_id))


def _delete_species_deity_by_names(species_name: str, deity_name: str,
                                     relationship: str) -> None:
    """Resolve names → ids and unlink. Used by the Manage Pantheons sub-tab
    which gets joined rows from list_species_deities (no surrogate ids)."""
    from sqlalchemy import text as _sa_text
    engine = db.get_engine()
    with engine.connect() as c:
        row = c.execute(_sa_text("""
            SELECT sd.species_id, sd.deity_id
            FROM species_deity sd
            JOIN species s ON s.species_id = sd.species_id
            JOIN deity   d ON d.deity_id   = sd.deity_id
            WHERE s.canonical_scientific_name = :sn
              AND d.name = :dn
              AND sd.relationship = :rel
            LIMIT 1
        """), {"sn": species_name, "dn": deity_name,
               "rel": relationship}).fetchone()
    if not row:
        return None
    return db.delete_species_deity_link(str(row[0]), str(row[1]),
                                          relationship)


# ---------------------------------------------------------------------------
# Batch-delete helpers (used by Manage sub-tabs + Profile activity)
# ---------------------------------------------------------------------------
def _bulk_mode_on(section_key: str) -> bool:
    """True when this section is in bulk-select mode."""
    return bool(st.session_state.get(f"_bulk_mode_{section_key}", False))


def _bulk_selected_ids(section_key: str) -> list[str]:
    """Return the row_ids currently checked in this section."""
    prefix = f"_bulk_sel_{section_key}_"
    return [k[len(prefix):]
            for k, v in st.session_state.items()
            if k.startswith(prefix) and v]


def _bulk_clear(section_key: str) -> None:
    prefix = f"_bulk_sel_{section_key}_"
    for k in list(st.session_state.keys()):
        if k.startswith(prefix):
            st.session_state.pop(k, None)


def _bulk_delete_bar(section_key: str,
                      delete_one: "callable[[str], object]",
                      label: str = "row(s)") -> None:
    """Render the 'Bulk mode' toggle and the 'Delete N selected' button at
    the top of a section. `delete_one(id)` is called once per selected id."""
    cols = st.columns([2, 5])
    with cols[0]:
        cur = _bulk_mode_on(section_key)
        new = st.checkbox("Bulk mode", value=cur,
                          key=f"_bulk_mode_chk_{section_key}",
                          help="Show checkboxes next to each row so you "
                               "can delete many at once.")
        if new != cur:
            st.session_state[f"_bulk_mode_{section_key}"] = new
            if not new:
                _bulk_clear(section_key)
            st.rerun()
    with cols[1]:
        if _bulk_mode_on(section_key):
            selected = _bulk_selected_ids(section_key)
            n = len(selected)
            disabled = (n == 0)
            if st.button(f"Delete {n} selected {label}",
                         key=f"_bulk_delete_btn_{section_key}",
                         disabled=disabled,
                         type="primary",
                         use_container_width=True):
                failed = 0
                for rid in selected:
                    try:
                        delete_one(rid)
                    except Exception:
                        failed += 1
                _bulk_clear(section_key)
                _invalidate_all_caches()
                try:
                    from src import profile as _p
                    _p._invalidate_profile_caches()
                except Exception:
                    pass
                msg = f"Deleted {n - failed} {label}."
                if failed:
                    msg += f" {failed} failed."
                st.success(msg)
                st.rerun()


def _bulk_checkbox(section_key: str, row_id: str) -> None:
    """Render a single-row checkbox when bulk mode is on."""
    if not _bulk_mode_on(section_key):
        return
    st.checkbox(
        " ",
        key=f"_bulk_sel_{section_key}_{row_id}",
        label_visibility="collapsed",
    )


def _render_clade_dating() -> None:
    """Library → Manage → Clade dates.

    Editors/admins set divergence_mya (millions of years since last
    common ancestor) on any clade. Undated clades render as teal dots
    on every tree until someone sets a date here.

    Sourcing tip in the help: TimeTree of Life (timetree.org) is the
    standard reference, but any peer-reviewed dated tree works."""
    from src import theme as _theme
    _theme.section_heading("Clade dates", kicker="Admin / editor")
    st.caption(
        "Set the last-common-ancestor age (in millions of years) for "
        "any clade in the system. Undated clades show as teal dots; "
        "once you set an age, they turn amber on every tree.")
    try:
        df = db.list_clades_for_dating()
    except Exception as exc:
        st.error(f"Couldn't load clades: {exc}")
        return
    if df.empty:
        st.caption("No clades in the database yet. Build a tree first.")
        return
    undated = int(df["mya"].isna().sum())
    st.markdown(
        f"**{len(df)} clades** total, **{undated}** still undated.")

    # Filter toggle
    only_undated = st.checkbox(
        "Show only undated clades", value=True, key="clade_only_undated")
    view = df[df["mya"].isna()] if only_undated else df

    for _, r in view.iterrows():
        cols = st.columns([3, 1, 1, 1])
        with cols[0]:
            cn = r.get("clade_name") or "(unnamed)"
            from src.render import _format_clade_name
            current = r.get("mya")
            label = f"**{_format_clade_name(cn)}**"
            if r.get("species_count"):
                label += (f"  <span style='color:#9ab3ab;font-size:11px'>"
                          f"· {int(r['species_count'])} sp.</span>")
            st.markdown(label, unsafe_allow_html=True)
        with cols[1]:
            try:
                cur_val = float(current) if current is not None else 0.0
            except (TypeError, ValueError):
                cur_val = 0.0
            new_val = st.number_input(
                "mya",
                min_value=0.0, max_value=5000.0, step=1.0,
                value=cur_val,
                key=f"mya_input_{r['clade_id']}",
                label_visibility="collapsed",
            )
        with cols[2]:
            if st.button("Save", key=f"mya_save_{r['clade_id']}",
                          use_container_width=True):
                v = float(new_val) if new_val > 0 else None
                try:
                    db.set_clade_divergence_mya(r["clade_id"], v)
                    _invalidate_all_caches()
                    st.success("Saved. Rebuild the tree to see "
                                "the amber dot.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        with cols[3]:
            if current is not None:
                if st.button("Clear", key=f"mya_clear_{r['clade_id']}",
                              use_container_width=True):
                    try:
                        db.set_clade_divergence_mya(r["clade_id"], None)
                        _invalidate_all_caches()
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))

