"""
Profile tab for {r}Evolving Kinship.

What it does:

  - Shows the current user's avatar, name, role, bio, last-login.
  - Lets them edit display name, bio, email, and avatar.
  - Avatars are stored as base64 data URIs in contributor.avatar_url so we
    don't need an external storage bucket. PIL resizes to 256x256 first so
    no row grows beyond a few KB.
  - Counts tile: trees owned, stories, dishes, names, cultural ties.
  - Tabbed activity feed of everything the user has contributed.
  - When admin: a "Team" section to promote / demote signed-in users.

Designed to fit cleanly inside a Streamlit tab (so app/station.py just
calls profile.render() inside its tab).
"""

from __future__ import annotations

import base64
import io

import pandas as pd
import streamlit as st

from src import auth
from src import db
from src import theme


# ---------------------------------------------------------------------------
# Avatar handling — base64 data URI in the avatar_url column
# ---------------------------------------------------------------------------
_AVATAR_MAX_SIDE = 256
_AVATAR_FORMAT = "JPEG"   # JPEG keeps things small; PNG works fine too
_AVATAR_QUALITY = 82


def _resize_to_data_uri(uploaded_bytes: bytes) -> str | None:
    """Take raw uploaded image bytes and return a base64 data URI sized so
    it fits comfortably in a TEXT column. Returns None on failure."""
    try:
        from PIL import Image
    except Exception:
        st.warning(
            "Pillow is not installed on the server. Avatar uploads need it; "
            "paste a URL instead.")
        return None
    try:
        im = Image.open(io.BytesIO(uploaded_bytes)).convert("RGB")
    except Exception as exc:
        st.error(f"Couldn't read that image: {exc}")
        return None
    im.thumbnail((_AVATAR_MAX_SIDE, _AVATAR_MAX_SIDE))
    buf = io.BytesIO()
    im.save(buf, format=_AVATAR_FORMAT, quality=_AVATAR_QUALITY,
            optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _avatar_html(url_or_data: str | None, size_px: int = 88) -> str:
    """Render an avatar image (with a placeholder if none). Returns HTML
    suitable for st.markdown(unsafe_allow_html=True)."""
    if url_or_data:
        src = url_or_data
    else:
        # Tiny placeholder — a soft circle with the theme's bg-alt color
        src = ""
    if src:
        return (
            f'<div style="width:{size_px}px;height:{size_px}px;'
            f'border-radius:50%;overflow:hidden;border:2px solid #1c2e2b;'
            f'background:#13211f;display:inline-block">'
            f'<img src="{src}" style="width:100%;height:100%;'
            f'object-fit:cover" alt="avatar"></div>'
        )
    return (
        f'<div style="width:{size_px}px;height:{size_px}px;border-radius:50%;'
        f'background:#13211f;border:2px solid #1c2e2b;display:inline-flex;'
        f'align-items:center;justify-content:center;color:#9ab3ab;'
        f'font-size:{size_px // 2}px">·</div>'
    )


# ---------------------------------------------------------------------------
# Cached reads
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60, show_spinner=False)
def _cached_counts(cid: str) -> dict:
    return db.user_activity_counts(cid)


@st.cache_data(ttl=60, show_spinner=False)
def _cached_user_trees(cid: str) -> pd.DataFrame:
    return db.list_user_trees(cid)


@st.cache_data(ttl=60, show_spinner=False)
def _cached_user_stories(cid: str) -> pd.DataFrame:
    return db.list_user_stories(cid)


@st.cache_data(ttl=60, show_spinner=False)
def _cached_user_dishes(cid: str) -> pd.DataFrame:
    return db.list_user_dishes(cid)


@st.cache_data(ttl=60, show_spinner=False)
def _cached_user_names(cid: str) -> pd.DataFrame:
    return db.list_user_names(cid)


@st.cache_data(ttl=60, show_spinner=False)
def _cached_user_cultural(cid: str) -> pd.DataFrame:
    return db.list_user_cultural(cid)


@st.cache_data(ttl=30, show_spinner=False)
def _cached_user_by_id(cid: str) -> dict | None:
    return db.get_user_by_id(cid)


@st.cache_data(ttl=30, show_spinner=False)
def _cached_all_users() -> pd.DataFrame:
    return db.list_all_users_for_admin()


@st.cache_data(ttl=30, show_spinner=False)
def _cached_recent_contribs(limit: int) -> pd.DataFrame:
    return db.recent_contributions(limit=limit)


def _invalidate_profile_caches() -> None:
    for fn in (_cached_counts, _cached_user_trees, _cached_user_stories,
               _cached_user_dishes, _cached_user_names, _cached_user_cultural,
               _cached_all_users, _cached_recent_contribs,
               _cached_user_by_id):
        try:
            fn.clear()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Public entry — call from app/station.py inside the Profile tab
# ---------------------------------------------------------------------------
def render() -> None:
    # If a contributor name was clicked in Library, render a public view
    # of that user instead of the current user's editable profile.
    viewing_id = st.session_state.get("viewing_profile_of")
    if viewing_id:
        _render_public_profile(viewing_id)
        return

    if not auth.is_named():
        st.info("Sign in or give a guest name in the sidebar to see your "
                "profile.")
        return

    u = auth.current_user()
    cid = u.get("contributor_id")
    if not cid:
        st.warning("Your account is missing a contributor row. Try signing "
                   "out and back in.")
        return

    # Refresh user details from DB so the profile reflects the latest
    # display_name / bio / avatar even after edits in another session.
    try:
        fresh = _cached_user_by_id(cid)
    except Exception as exc:
        st.warning(
            "Couldn't refresh your profile from the database "
            f"({exc}). Showing the cached version. If you just deployed "
            "and it's a missing-column error, run the latest migration "
            "in db/ via the Supabase SQL editor.")
        fresh = None
    if fresh:
        u = {**u, **{
            "name": fresh.get("display_name") or u.get("name"),
            "bio": fresh.get("bio"),
            "avatar_url": fresh.get("avatar_url"),
            "role": fresh.get("role") or u.get("role"),
        }}
        # Keep session_state in sync so the sidebar identity card matches.
        st.session_state["user"].update({
            "name": u["name"], "bio": u["bio"],
            "avatar_url": u["avatar_url"], "role": u["role"],
        })

    theme.section_heading(u.get("name") or "Your profile",
                          kicker="Profile")

    _render_header(u)

    # If we just did a forgot-password reset, force the user to set a new
    # password before anything else on the page is touched.
    if auth.must_change_password():
        st.divider()
        st.warning("You're on a temporary password. Set a new one to keep "
                   "your account safe.")
        _render_change_password_card(force=True)
        return

    st.divider()
    _render_change_password_card(force=False)
    st.divider()
    _render_edit_form(u, cid)
    st.divider()
    _render_activity(cid)

    if auth.is_admin():
        st.divider()
        _render_admin_team()
        st.divider()
        _render_admin_pending_resets()
        st.divider()
        _render_admin_review_feed()


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------
def _render_header(u: dict) -> None:
    counts = _cached_counts(u["contributor_id"])
    role_glyph_html = theme.role_glyph(u.get("role"), size_px=18)
    bio_html = (
        f'<div style="color:#9ab3ab;margin-top:6px;font-size:13px">'
        f'{u["bio"]}</div>'
        if u.get("bio") else
        '<div style="color:#5e6f6a;margin-top:6px;font-size:12px;'
        'font-style:italic">No bio yet. Tell people what brought you to '
        'these rivers.</div>'
    )
    if not u.get("username"):
        username_hint = (
            '<div style="color:#9ab3ab;font-size:11px;margin-top:4px">'
            'Guest. Make an account from the sidebar to keep this profile '
            'across sessions.</div>'
        )
    else:
        username_hint = (
            f'<div style="color:#7a8d86;font-size:11px;margin-top:4px">'
            f'@{u["username"]}</div>'
        )

    st.markdown(
        f'<div style="display:flex;gap:18px;align-items:flex-start;'
        f'flex-wrap:wrap;margin-bottom:12px">'
        f'  <div>{_avatar_html(u.get("avatar_url"), size_px=96)}</div>'
        f'  <div style="flex:1;min-width:240px">'
        f'    <div style="font-size:20px;font-weight:500">{u.get("name") or ""}'
        f'      {role_glyph_html}'
        f'    </div>'
        f'    {username_hint}'
        f'    {bio_html}'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Count tiles
    tile_html = (
        '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:8px">'
        + "".join(
            f'<div style="flex:1;min-width:96px;background:#13211f;'
            f'border:1px solid #1c2e2b;border-radius:10px;padding:10px 12px">'
            f'<div style="color:#9ab3ab;font-size:10px;text-transform:uppercase;'
            f'letter-spacing:0.08em">{label}</div>'
            f'<div style="color:#e8f3ef;font-size:22px;font-weight:500;'
            f'margin-top:2px">{count}</div>'
            f'</div>'
            for label, count in (
                ("Trees",     counts.get("trees", 0)),
                ("Stories",   counts.get("stories", 0)),
                ("Dishes",    counts.get("dishes", 0)),
                ("Names",     counts.get("names", 0)),
                ("Cultural",  counts.get("cultural", 0)),
                ("Deities",   counts.get("deities", 0)),
            )
        )
        + '</div>'
    )
    st.markdown(tile_html, unsafe_allow_html=True)


def _render_edit_form(u: dict, cid: str) -> None:
    with st.expander("Edit your profile", expanded=False):
        with st.form("profile_edit_form"):
            new_name = st.text_input(
                "Display name", value=u.get("name") or "")
            new_email = st.text_input(
                "Email (optional, kept private)",
                value=(u.get("email") if isinstance(u.get("email"), str)
                       else "") or "")
            new_bio = st.text_area(
                "Bio",
                value=u.get("bio") or "",
                height=110,
                placeholder=(
                    "Where you live, what you study, the river you're closest "
                    "to, anything you want people seeing your contributions "
                    "to know."),
            )

            st.markdown("**Avatar**")
            colA, colB = st.columns([1, 2])
            with colA:
                st.markdown(_avatar_html(u.get("avatar_url"), 88),
                            unsafe_allow_html=True)
            with colB:
                avatar_url_in = st.text_input(
                    "Image URL",
                    value=(u.get("avatar_url") or "")
                    if not (u.get("avatar_url") or "").startswith("data:")
                    else "",
                    help="Paste a link to your avatar (Gravatar, social, "
                         "anywhere). Or upload below.",
                )
                avatar_upload = st.file_uploader(
                    "Or upload an image",
                    type=["png", "jpg", "jpeg", "webp"],
                    key="profile_avatar_upload",
                    label_visibility="visible",
                    help="Resized to 256px and stored inline. Replaces any "
                         "URL set above.",
                )
                clear_avatar = st.checkbox(
                    "Remove my avatar", value=False)

            cols_btn = st.columns([1, 1])
            with cols_btn[0]:
                saved = st.form_submit_button(
                    "Save changes", type="primary",
                    use_container_width=True)
            with cols_btn[1]:
                cancel = st.form_submit_button(
                    "Cancel", use_container_width=True)

        if cancel:
            st.rerun()
        if saved:
            patch: dict = {}
            if (new_name or "").strip() != (u.get("name") or ""):
                patch["display_name"] = (new_name or "").strip() or u.get("name")
            if (new_bio or "").strip() != (u.get("bio") or ""):
                patch["bio"] = (new_bio or "").strip() or None
            if (new_email or "").strip() != (u.get("email") or ""):
                patch["email"] = (new_email or "").strip() or None

            new_avatar_value: str | None = None
            if clear_avatar:
                new_avatar_value = None
                patch["avatar_url"] = None
            elif avatar_upload is not None:
                data_uri = _resize_to_data_uri(avatar_upload.getvalue())
                if data_uri:
                    new_avatar_value = data_uri
                    patch["avatar_url"] = data_uri
            elif (avatar_url_in or "").strip():
                cleaned = (avatar_url_in or "").strip()
                if cleaned != (u.get("avatar_url") or ""):
                    new_avatar_value = cleaned
                    patch["avatar_url"] = cleaned

            if not patch:
                st.info("Nothing to change.")
                return
            try:
                db.update_user_profile(cid, **patch)
                _invalidate_profile_caches()
                # Refresh session_state user with new values
                for k, v in patch.items():
                    if k == "display_name":
                        st.session_state["user"]["name"] = v
                    elif k == "avatar_url":
                        st.session_state["user"]["avatar_url"] = v
                    elif k == "bio":
                        st.session_state["user"]["bio"] = v
                    elif k == "email":
                        st.session_state["user"]["email"] = v
                st.success("Saved.")
                st.rerun()
            except Exception as exc:
                st.error(f"Save failed: {exc}")


def _render_activity(cid: str) -> None:
    st.markdown("### Your activity")
    tabs = st.tabs(["Trees", "Stories", "Dishes", "Names", "Cultural",
                    "Following", "Favorites"])

    with tabs[0]:
        df = _cached_user_trees(cid)
        if df.empty:
            st.caption("You haven't started a tree yet. The Request station "
                       "tab is where they begin.")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)

    with tabs[1]:
        df = _cached_user_stories(cid)
        if df.empty:
            st.caption("No stories yet. Stories live in the Library tab.")
        else:
            _prof_bulk_delete_bar("act_stories",
                                   lambda i: db.delete_story(i),
                                   "stories")
            for _, row in df.iterrows():
                _prof_bulk_checkbox("act_stories", str(row["story_id"]))
                _row_with_delete(
                    title=row.get("title") or "(untitled)",
                    sub=(f"about {row['species']}"
                         if row.get("species") else None),
                    when=row.get("contributed_at"),
                    delete_label="Delete this story",
                    delete_key=f"prof_del_story_{row['story_id']}",
                    on_delete=lambda sid=row["story_id"]:
                        db.delete_story(sid),
                )

    with tabs[2]:
        df = _cached_user_dishes(cid)
        if df.empty:
            st.caption("No dishes yet.")
        else:
            _prof_bulk_delete_bar("act_dishes",
                                   lambda i: db.delete_dish(i),
                                   "dishes")
            for _, row in df.iterrows():
                _prof_bulk_checkbox("act_dishes", str(row["dish_id"]))
                _row_with_delete(
                    title=row.get("name") or "(unnamed)",
                    sub=row.get("cuisine"),
                    when=row.get("contributed_at"),
                    delete_label="Delete this dish",
                    delete_key=f"prof_del_dish_{row['dish_id']}",
                    on_delete=lambda did=row["dish_id"]:
                        db.delete_dish(did),
                )

    with tabs[3]:
        df = _cached_user_names(cid)
        if df.empty:
            st.caption("No multilingual names contributed yet.")
        else:
            _prof_bulk_delete_bar("act_names",
                                   lambda i: db.delete_species_name(i),
                                   "names")
            for _, row in df.iterrows():
                _prof_bulk_checkbox("act_names", str(row["name_id"]))
                _row_with_delete(
                    title=f"{row['name_text']}  ({row.get('language')})",
                    sub=(f"for {row['species']}"
                         if row.get("species") else None),
                    when=row.get("contributed_at"),
                    delete_label="Delete this name",
                    delete_key=f"prof_del_name_{row['name_id']}",
                    on_delete=lambda nid=row["name_id"]:
                        db.delete_species_name(nid),
                )

    with tabs[4]:
        df = _cached_user_cultural(cid)
        if df.empty:
            st.caption("No cultural connections yet.")
        else:
            _prof_bulk_delete_bar("act_cultural",
                                   lambda i: db.delete_cultural_connection(i),
                                   "cultural ties")
            for _, row in df.iterrows():
                _prof_bulk_checkbox("act_cultural", str(row["connection_id"]))
                _row_with_delete(
                    title=f"{row.get('culture','')}: "
                          f"{row.get('significance_type','tie')}",
                    sub=(f"for {row['species']}"
                         if row.get("species") else None),
                    when=row.get("contributed_at"),
                    delete_label="Delete this connection",
                    delete_key=f"prof_del_cc_{row['connection_id']}",
                    on_delete=lambda cnid=row["connection_id"]:
                        db.delete_cultural_connection(cnid),
                )

    with tabs[5]:
        _render_following_tab(cid)

    with tabs[6]:
        _render_favorites_tab(cid)


def _row_with_delete(title: str, sub: str | None, when,
                     delete_label: str, delete_key: str,
                     on_delete) -> None:
    """Render one community row with a delete button. The delete callback
    runs and the page reruns."""
    cols = st.columns([6, 2])
    with cols[0]:
        when_str = _fmt_when(when)
        sub_html = (f' <span style="color:#7a8d86">· {sub}</span>'
                    if sub else "")
        when_html = (f'<div style="color:#9ab3ab;font-size:11px">{when_str}</div>'
                     if when_str else "")
        st.markdown(
            f'<div style="padding:8px 0;border-bottom:1px solid #1c2e2b">'
            f'<div style="color:#e8f3ef">{title}{sub_html}</div>'
            f'{when_html}</div>',
            unsafe_allow_html=True,
        )
    with cols[1]:
        if st.button(delete_label, key=delete_key,
                     use_container_width=True):
            try:
                owner = on_delete()
                # owner is the contributor_id that originally added it (or None).
                # We don't re-check here because the UI only ever offers the
                # button on rows the user can delete.
                _invalidate_profile_caches()
                # Library caches live in src/library.py — clear them too.
                try:
                    from src import library
                    library._invalidate_all_caches()
                except Exception:
                    pass
                st.success("Deleted.")
                st.rerun()
            except Exception as exc:
                st.error(f"Delete failed: {exc}")


def _fmt_when(when) -> str:
    if when is None:
        return ""
    if isinstance(when, str):
        return when[:10]
    try:
        return when.strftime("%Y-%m-%d")
    except Exception:
        return str(when)[:10]


# ---------------------------------------------------------------------------
# Admin: team / role management
# ---------------------------------------------------------------------------
def _render_admin_team() -> None:
    theme.section_heading("Team", kicker="Admin")
    st.caption(
        "Promote a signed-in user to editor (can edit anyone's contributions, "
        "but can't touch admin-owned trees) or admin (full access). Guests "
        "without accounts don't show up here.")
    try:
        df = _cached_all_users()
    except Exception as _exc:
        st.warning(f"Could not load the team list ({_exc}). The "
                    "auth_migration.sql may need to run.")
        return
    if df.empty:
        st.caption("No users yet.")
        return

    # Only show signed-in users (need a username to change role meaningfully).
    df = df[df["username"].notna()].reset_index(drop=True)
    if df.empty:
        st.caption("No signed-in users yet, just guests.")
        return

    for _, row in df.iterrows():
        cols = st.columns([3, 2, 2])
        with cols[0]:
            stat = (f"{row['display_name']}  "
                    f"<span style='color:#7a8d86'>(@{row['username']})</span>")
            sub_bits = []
            if row.get("trees_owned"):
                sub_bits.append(f"{int(row['trees_owned'])} trees")
            if row.get("stories"):
                sub_bits.append(f"{int(row['stories'])} stories")
            if row.get("dishes"):
                sub_bits.append(f"{int(row['dishes'])} dishes")
            sub = " · ".join(sub_bits) if sub_bits else "no contributions yet"
            st.markdown(
                f'<div style="padding:8px 0;border-bottom:1px solid #1c2e2b">'
                f'<div>{stat}</div>'
                f'<div style="color:#9ab3ab;font-size:11px">{sub}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with cols[1]:
            current = row.get("role") or "visitor"
            new_role = st.selectbox(
                "Role",
                ["visitor", "editor", "admin"],
                index=["visitor", "editor", "admin"].index(current),
                key=f"role_pick_{row['contributor_id']}",
                label_visibility="collapsed",
            )
        with cols[2]:
            disabled = (new_role == current)
            if st.button("Update", key=f"role_save_{row['contributor_id']}",
                         disabled=disabled,
                         use_container_width=True):
                try:
                    db.set_user_role(row["contributor_id"], new_role)
                    _cached_all_users.clear()
                    st.success(f"{row['display_name']} is now {new_role}.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))


def _render_admin_review_feed() -> None:
    theme.section_heading("Recent community additions",
                          kicker="Editor review")
    df = _cached_recent_contribs(50)
    if df.empty:
        st.caption("Nothing yet.")
        return
    st.caption("Most recent 50 additions across stories, dishes, names, and "
               "cultural connections. Delete any.")
    # Bulk delete bar: works on the visible composite ids (kind:id).
    def _delete_composite(composite_id: str) -> None:
        try:
            kind, rid = composite_id.split(":", 1)
        except ValueError:
            return
        if kind == "story":               db.delete_story(rid)
        elif kind == "dish":              db.delete_dish(rid)
        elif kind == "name":              db.delete_species_name(rid)
        elif kind == "cultural_connection":
            db.delete_cultural_connection(rid)
    _prof_bulk_delete_bar("admin_review", _delete_composite,
                           "additions")
    for _, row in df.iterrows():
        kind = row.get("kind", "?")
        row_id = row.get("row_id")
        title = row.get("title") or "(untitled)"
        by = row.get("contributor") or "anonymous"
        when_str = _fmt_when(row.get("contributed_at"))
        _prof_bulk_checkbox("admin_review", f"{kind}:{row_id}")
        cols = st.columns([6, 2])
        with cols[0]:
            st.markdown(
                f'<div style="padding:8px 0;border-bottom:1px solid #1c2e2b">'
                f'<div style="color:#e8f3ef">{title} '
                f'<span style="color:#7a8d86">· {kind}</span></div>'
                f'<div style="color:#9ab3ab;font-size:11px">{by} · {when_str}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with cols[1]:
            if st.button("Delete", key=f"rev_del_{kind}_{row_id}",
                         use_container_width=True):
                try:
                    if kind == "story":
                        db.delete_story(row_id)
                    elif kind == "dish":
                        db.delete_dish(row_id)
                    elif kind == "name":
                        db.delete_species_name(row_id)
                    elif kind == "cultural_connection":
                        db.delete_cultural_connection(row_id)
                    _invalidate_profile_caches()
                    try:
                        from src import library
                        library._invalidate_all_caches()
                    except Exception:
                        pass
                    st.success("Deleted.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))


# ---------------------------------------------------------------------------
# Public profile view (when someone clicks a contributor's name in Library)
# ---------------------------------------------------------------------------
def _render_public_profile(contributor_id: str) -> None:
    pub = db.get_public_profile(contributor_id)
    if not pub:
        st.warning("This contributor isn't in the system anymore.")
        if st.button("Back", key="back_from_missing"):
            st.session_state.pop("viewing_profile_of", None)
            st.rerun()
        return

    # Header row: back button + breadcrumb
    cols = st.columns([2, 6])
    with cols[0]:
        if st.button("← Back to my profile",
                     key="back_from_public",
                     use_container_width=True):
            st.session_state.pop("viewing_profile_of", None)
            st.rerun()
    with cols[1]:
        st.markdown(
            '<div class="kicker">Public profile</div>',
            unsafe_allow_html=True,
        )

    glyph_html = theme.role_glyph(pub.get("role"), size_px=18)
    if pub.get("bio"):
        bio_html = (f'<div style="color:#9ab3ab;margin-top:6px;'
                    f'font-size:13px">{pub["bio"]}</div>')
    else:
        bio_html = ('<div style="color:#5e6f6a;margin-top:6px;'
                    'font-size:12px;font-style:italic">'
                    'This contributor hasn\'t written a bio yet.</div>')

    sub_bits = []
    if pub.get("username"):
        sub_bits.append(f"@{pub['username']}")
    elif pub.get("role") == "visitor" and not pub.get("username"):
        sub_bits.append("guest")
    sub_str = " · ".join(sub_bits)
    sub_html = (
        f'<div style="color:#7a8d86;font-size:11px;margin-top:4px">'
        f'{sub_str}</div>' if sub_str else "")

    st.markdown(
        f'<div style="display:flex;gap:18px;align-items:flex-start;'
        f'flex-wrap:wrap;margin:12px 0">'
        f'  <div>{_avatar_html(pub.get("avatar_url"), size_px=96)}</div>'
        f'  <div style="flex:1;min-width:240px">'
        f'    <div style="font-size:20px;font-weight:500">'
        f'      {pub.get("display_name") or "(unnamed)"}{glyph_html}'
        f'    </div>'
        f'    {sub_html}{bio_html}'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    # Follow/Unfollow button (no-op when viewing your own profile)
    _follow_cols = st.columns([2, 4])
    with _follow_cols[0]:
        _render_follow_button(pub["contributor_id"])
    with _follow_cols[1]:
        _fcounts = _cached_follow_counts(pub["contributor_id"])
        st.markdown(
            f'<div style="color:#9ab3ab;font-size:12px;'
            f'padding-top:6px;line-height:1.7">'
            f'<b>{_fcounts.get("followers", 0)}</b> followers · '
            f'<b>{_fcounts.get("following", 0)}</b> following · '
            f'<b>{_fcounts.get("favorites", 0)}</b> favorites'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Count tiles (same shape as own profile)
    counts = {
        "Trees":     pub["trees"],
        "Stories":   pub["stories"],
        "Dishes":    pub["dishes"],
        "Names":     pub["names"],
        "Cultural":  pub["cultural"],
        "Deities":   pub["deities"],
    }
    tile_html = (
        '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:8px">'
        + "".join(
            f'<div style="flex:1;min-width:96px;background:#13211f;'
            f'border:1px solid #1c2e2b;border-radius:10px;padding:10px 12px">'
            f'<div style="color:#9ab3ab;font-size:10px;text-transform:uppercase;'
            f'letter-spacing:0.08em">{label}</div>'
            f'<div style="color:#e8f3ef;font-size:22px;font-weight:500;'
            f'margin-top:2px">{count}</div>'
            f'</div>'
            for label, count in counts.items()
        )
        + '</div>'
    )
    st.markdown(tile_html, unsafe_allow_html=True)

    # Public activity feed (no delete buttons here)
    st.markdown("### Their activity")
    tabs = st.tabs(["Trees", "Stories", "Dishes", "Names", "Cultural"])
    cid = pub["contributor_id"]
    with tabs[0]:
        df = db.list_user_trees(cid)
        if df.empty: st.caption("No trees yet.")
        else: st.dataframe(df, use_container_width=True, hide_index=True)
    with tabs[1]:
        df = db.list_user_stories(cid)
        if df.empty: st.caption("No stories yet.")
        else: st.dataframe(df, use_container_width=True, hide_index=True)
    with tabs[2]:
        df = db.list_user_dishes(cid)
        if df.empty: st.caption("No dishes yet.")
        else: st.dataframe(df, use_container_width=True, hide_index=True)
    with tabs[3]:
        df = db.list_user_names(cid)
        if df.empty: st.caption("No multilingual names yet.")
        else: st.dataframe(df, use_container_width=True, hide_index=True)
    with tabs[4]:
        df = db.list_user_cultural(cid)
        if df.empty: st.caption("No cultural connections yet.")
        else: st.dataframe(df, use_container_width=True, hide_index=True)


def _render_change_password_card(force: bool = False) -> None:
    """Self-service password change. Always available to signed-in users;
    automatically expanded when force=True (after a temp-password reset)."""
    if not auth.is_signed_in():
        return
    with st.expander("Change your password",
                     expanded=force):
        with st.form("change_pw_form"):
            if not force:
                # Normal change: ask for current password first.
                # On force=True (post-reset) we skip this since the user
                # just typed the temp password to sign in.
                current_pw = st.text_input(
                    "Current password", type="password",
                    help="Required to confirm it's really you.")
            else:
                current_pw = None
            new_pw = st.text_input("New password", type="password",
                                   help="Six characters minimum.")
            new_pw2 = st.text_input("Confirm new password", type="password")
            saved = st.form_submit_button("Update password", type="primary",
                                           use_container_width=True)
        if saved:
            if not new_pw or new_pw != new_pw2:
                st.error("Passwords don't match.")
                return
            ok, msg = auth.change_my_password(new_pw,
                                               current_password=current_pw)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)


def _render_admin_pending_resets() -> None:
    theme.section_heading("Password resets (last 30 days)",
                          kicker="Admin")
    try:
        df = db.list_pending_resets()
    except Exception as exc:
        st.caption(f"(pending-resets table not present yet: {exc})")
        return
    if df is None or df.empty:
        st.caption("No reset requests in the last 30 days.")
        return
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption("Each reset surfaces a one-time temp password on the user's "
                "own screen. This panel just records that they asked.")


# ---------------------------------------------------------------------------
# Batch-delete helpers (Profile activity + admin Review feed)
# ---------------------------------------------------------------------------
def _prof_bulk_mode_on(section_key: str) -> bool:
    return bool(st.session_state.get(f"_prof_bulk_mode_{section_key}", False))


def _prof_bulk_selected(section_key: str) -> list[str]:
    prefix = f"_prof_bulk_sel_{section_key}_"
    return [k[len(prefix):]
            for k, v in st.session_state.items()
            if k.startswith(prefix) and v]


def _prof_bulk_clear(section_key: str) -> None:
    prefix = f"_prof_bulk_sel_{section_key}_"
    for k in list(st.session_state.keys()):
        if k.startswith(prefix):
            st.session_state.pop(k, None)


def _prof_bulk_delete_bar(section_key: str, delete_one, label: str) -> None:
    cols = st.columns([2, 5])
    with cols[0]:
        cur = _prof_bulk_mode_on(section_key)
        new = st.checkbox("Bulk mode", value=cur,
                          key=f"_prof_bulk_mode_chk_{section_key}",
                          help="Show checkboxes next to each row.")
        if new != cur:
            st.session_state[f"_prof_bulk_mode_{section_key}"] = new
            if not new:
                _prof_bulk_clear(section_key)
            st.rerun()
    with cols[1]:
        if _prof_bulk_mode_on(section_key):
            sel = _prof_bulk_selected(section_key)
            n = len(sel)
            if st.button(f"Delete {n} selected {label}",
                         key=f"_prof_bulk_del_btn_{section_key}",
                         disabled=(n == 0),
                         type="primary",
                         use_container_width=True):
                failed = 0
                for rid in sel:
                    try:
                        delete_one(rid)
                    except Exception:
                        failed += 1
                _prof_bulk_clear(section_key)
                _invalidate_profile_caches()
                try:
                    from src import library
                    library._invalidate_all_caches()
                except Exception:
                    pass
                msg = f"Deleted {n - failed} {label}."
                if failed:
                    msg += f" {failed} failed."
                st.success(msg)
                st.rerun()


def _prof_bulk_checkbox(section_key: str, row_id: str) -> None:
    if not _prof_bulk_mode_on(section_key):
        return
    st.checkbox(
        " ", key=f"_prof_bulk_sel_{section_key}_{row_id}",
        label_visibility="collapsed",
    )


# ---------------------------------------------------------------------------
# Follow / favorite helpers used by the public profile view
# ---------------------------------------------------------------------------
def _render_follow_button(target_contributor_id: str) -> None:
    """Follow / Unfollow toggle. Visible on someone else's public profile.
    No-op when you're looking at your own profile or you haven't named
    yourself."""
    me_cid = auth.active_contributor_id()
    if not me_cid or me_cid == target_contributor_id:
        return
    following = db.is_following(me_cid, target_contributor_id)
    label = "Unfollow" if following else "Follow"
    if st.button(label, key=f"follow_btn_{target_contributor_id}",
                  type=("secondary" if following else "primary"),
                  use_container_width=True):
        if following:
            db.unfollow_user(me_cid, target_contributor_id)
        else:
            db.follow_user(me_cid, target_contributor_id)
        try:
            _cached_following.clear()
            _cached_followers.clear()
            _cached_follow_counts.clear()
        except Exception:
            pass
        st.rerun()


@st.cache_data(ttl=60, show_spinner=False)
def _cached_following(cid: str):
    return db.list_following(cid)


@st.cache_data(ttl=60, show_spinner=False)
def _cached_followers(cid: str):
    return db.list_followers(cid)


@st.cache_data(ttl=60, show_spinner=False)
def _cached_favorites(cid: str):
    return db.list_favorite_trees(cid)


@st.cache_data(ttl=60, show_spinner=False)
def _cached_follow_counts(cid: str):
    return db.follow_counts(cid)


def _render_following_tab(cid: str) -> None:
    df = _cached_following(cid)
    if df.empty:
        st.caption("You're not following anyone yet. Click a contributor "
                   "byline in Library to land on their profile, then hit "
                   "Follow.")
        return
    for _, r in df.iterrows():
        cols = st.columns([1, 5, 2])
        with cols[0]:
            st.markdown(
                _avatar_html(r.get("avatar_url"), size_px=40),
                unsafe_allow_html=True)
        with cols[1]:
            name = r.get("display_name") or "(unnamed)"
            user_handle = (f" <span style='color:#7a8d86;font-size:11px'>"
                           f"@{r['username']}</span>"
                           if r.get("username") else "")
            sub = (f"{int(r.get('trees',0))} trees · "
                   f"{int(r.get('stories',0))} stories")
            st.markdown(
                f'<div style="padding:6px 0">'
                f'<div style="color:#e8f3ef">{name}{user_handle}</div>'
                f'<div style="color:#9ab3ab;font-size:11px">{sub}</div>'
                f'</div>',
                unsafe_allow_html=True)
        with cols[2]:
            if st.button("Open profile",
                          key=f"view_following_{r['contributor_id']}",
                          use_container_width=True):
                st.session_state["viewing_profile_of"] = r["contributor_id"]
                st.rerun()


def _render_favorites_tab(cid: str) -> None:
    df = _cached_favorites(cid)
    if df.empty:
        st.caption("No favorite trees yet. Open the Dashboard, pick a "
                   "tree, and hit the ☆ to favorite it.")
        return
    for _, r in df.iterrows():
        cols = st.columns([5, 2])
        with cols[0]:
            owner = (f" <span style='color:#7a8d86;font-size:11px'>by "
                     f"{r['owner']}</span>" if r.get("owner") else "")
            st.markdown(
                f'<div style="padding:6px 0;border-bottom:1px solid #1c2e2b">'
                f'<div style="color:#e8f3ef">{r["tree_name"]}{owner}</div>'
                f'<div style="color:#9ab3ab;font-size:11px">'
                f'{int(r.get("species_count",0))} species · '
                f'favorited {_fmt_when(r.get("favorited_at"))}</div>'
                f'</div>',
                unsafe_allow_html=True)
        with cols[1]:
            if st.button("Remove",
                          key=f"unfav_{r['tree_id']}",
                          use_container_width=True):
                db.unfavorite_tree(cid, r["tree_id"])
                try:
                    _cached_favorites.clear()
                    _cached_follow_counts.clear()
                except Exception:
                    pass
                st.rerun()

