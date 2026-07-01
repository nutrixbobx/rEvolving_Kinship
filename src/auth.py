"""
Authentication, roles, and remember-me for {r}Evolving Kinship.

Three classes of visitor:

  - **admin** (Maya, and anyone she promotes): can edit anything.
  - **editor**: signed-in user trusted to moderate. Can edit anyone's
    contributions except admin-owned trees.
  - **visitor**: signed-in user OR named guest. Can add to community
    datapoints + edit their own trees and contributions.

Remember-me mechanism:

  After successful sign-in we create an auth_session row in Postgres and
  put its session_id into the URL as `?s=<token>`. On every page load we
  read the token from the URL, look it up in Postgres, and silently
  restore the user. The URL is the source of truth because cookies
  proved unreliable on Streamlit Cloud (iframe + third-party blocking).

  Trade-off: anyone with a copy of the URL can sign in as that user.
  For a single-curator art app this is acceptable; the user rotates
  their token by signing out + back in.

No streamlit-authenticator dependency. Just bcrypt + auth_session table
+ st.query_params.
"""

from __future__ import annotations

import os

import bcrypt
import streamlit as st

from src import db


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")


def verify_password(password: str, stored_hash: str) -> bool:
    if not password or not stored_hash:
        return False
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"), stored_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Admin password bootstrap (one-time per session)
# ---------------------------------------------------------------------------
def seed_admin_password_if_needed() -> None:
    """If Maya's contributor row has no password_hash, set it from the
    ADMIN_PASSWORD env var. Runs at most once per session."""
    if st.session_state.get("_admin_pw_seeded"):
        return
    st.session_state["_admin_pw_seeded"] = True
    admin_pw = os.environ.get("ADMIN_PASSWORD")
    if not admin_pw:
        return
    try:
        user = db.get_user_by_username("maya")
    except Exception:
        return
    if not user or user.get("password_hash"):
        return
    db.set_user_password(user["contributor_id"], hash_password(admin_pw))


# ---------------------------------------------------------------------------
# Session state shape
# ---------------------------------------------------------------------------
_GUEST_USER = {
    "username": None,
    "name": None,
    "role": None,
    "contributor_id": None,
    "bio": None,
    "avatar_url": None,
}


def current_user() -> dict:
    return st.session_state.get("user", dict(_GUEST_USER))


def role() -> str | None:
    return current_user().get("role")


def is_admin() -> bool:
    return role() == "admin"


def is_editor_or_admin() -> bool:
    return role() in ("editor", "admin")


def is_signed_in() -> bool:
    return bool(current_user().get("username"))


def is_named() -> bool:
    return bool(current_user().get("name"))


def active_contributor_id() -> str | None:
    return current_user().get("contributor_id")


def can_edit_tree(tree_row: dict | None) -> bool:
    """admin: anything. owner: their own. editor: anything not admin-owned."""
    if tree_row is None:
        return False
    u = current_user()
    if u.get("role") == "admin":
        return True
    if u.get("contributor_id") and u["contributor_id"] == tree_row.get("owner_id"):
        return True
    if tree_row.get("owner_role") == "admin":
        return False
    return u.get("role") == "editor"


def can_edit_contribution(contribution_contributor_id: str | None) -> bool:
    """admin / editor: anyone's. otherwise: their own only."""
    u = current_user()
    if u.get("role") in ("admin", "editor"):
        return True
    if (u.get("contributor_id")
            and u["contributor_id"] == contribution_contributor_id):
        return True
    return False


# ---------------------------------------------------------------------------
# URL query-param remember-me
# ---------------------------------------------------------------------------
_SESSION_PARAM = "s"


def _read_session_token() -> str | None:
    try:
        v = st.query_params.get(_SESSION_PARAM)
    except Exception:
        return None
    if not v:
        return None
    if isinstance(v, list):
        v = v[0] if v else None
    return str(v) if v else None


def _write_session_token(token: str) -> None:
    if not token:
        return
    try:
        st.query_params[_SESSION_PARAM] = token
    except Exception:
        pass


def _clear_session_token() -> None:
    try:
        if _SESSION_PARAM in st.query_params:
            del st.query_params[_SESSION_PARAM]
    except Exception:
        pass


def _set_session_user(user_row: dict) -> None:
    """Populate session_state["user"] from a contributor row."""
    st.session_state["user"] = {
        "username": user_row.get("username"),
        "name": user_row.get("display_name") or user_row.get("username"),
        "role": user_row.get("role") or "visitor",
        "contributor_id": user_row.get("contributor_id"),
        "bio": user_row.get("bio"),
        "avatar_url": user_row.get("avatar_url"),
    }
    st.session_state["is_admin"] = (user_row.get("role") == "admin")
    # Cache the user's theme pick so inject_css can apply it on
    # subsequent reruns without another DB hit.
    cid = user_row.get("contributor_id")
    if cid:
        try:
            st.session_state["user_theme"] = db.get_user_theme(cid)
        except Exception:
            st.session_state["user_theme"] = None


def _start_remembered_session(contributor_id: str) -> None:
    """Create auth_session row + write the token to URL."""
    if not contributor_id:
        return
    token = db.create_auth_session(contributor_id)
    if token:
        _write_session_token(token)


def _end_remembered_session() -> None:
    """Delete the auth_session row + clear the URL token."""
    token = _read_session_token()
    if token:
        try:
            db.delete_auth_session(token)
        except Exception:
            pass
    _clear_session_token()


def clear_session_user() -> None:
    """Sign out: clear session_state + URL token + auth_session row."""
    try:
        _end_remembered_session()
    except Exception:
        pass
    st.session_state.pop("user", None)
    st.session_state["is_admin"] = False


def _try_cookie_restore() -> bool:
    """Read the URL session token. If valid, sign the user in silently.

    Function name retained for backward compatibility with callers in
    station.py; the actual mechanism is URL query params, not cookies.
    Returns True if the user is named after the call."""
    # Probabilistic GC: 1% of page loads sweep expired auth_session rows.
    import secrets as _s
    if _s.randbelow(100) == 0:
        try:
            db.cleanup_expired_sessions()
        except Exception:
            pass
    if is_named():
        return True
    token = _read_session_token()
    if not token:
        return False
    cid = db.lookup_auth_session(token)
    if not cid:
        _clear_session_token()
        return False
    user = db.get_user_by_id(cid)
    if not user or not user.get("username"):
        _clear_session_token()
        return False
    _set_session_user(user)
    try:
        db.touch_auth_session(token)
        db.update_last_login(cid)
    except Exception:
        pass
    return True


def should_show_restoring_placeholder() -> bool:
    """Kept as a public symbol for backward compat. Query params are
    synchronous, so no placeholder is ever needed."""
    return False


# ---------------------------------------------------------------------------
# Guest entry
# ---------------------------------------------------------------------------
def set_guest_user(name: str) -> tuple[bool, str]:
    """Guest path: no password, just a display name. Refuses if `name`
    belongs to a registered user (so a guest can't impersonate Maya).
    Returns (success, error_msg_if_any)."""
    if not name or not name.strip():
        return (False, "Give yourself a name first.")
    name = name.strip()
    contributor_id, is_registered = db.get_or_create_guest_contributor(name)
    if is_registered:
        return (False,
                f'"{name}" is a registered account. Sign in with your '
                "password, or use a different name as a guest.")
    if not contributor_id:
        return (False, "Could not create a guest profile. Try again.")
    st.session_state["user"] = {
        "username": None,
        "name": name,
        "role": "visitor",
        "contributor_id": contributor_id,
        "bio": None,
        "avatar_url": None,
    }
    st.session_state["is_admin"] = False
    return (True, "")


# ---------------------------------------------------------------------------
# Sign-in / sign-up (no streamlit-authenticator)
# ---------------------------------------------------------------------------
def _do_signin(username: str, password: str,
                remember: bool = True) -> tuple[bool, str]:
    """Validate credentials against the contributor table.
    Returns (success, error_msg). On success populates session_state.
    remember=True writes a URL token so the session survives page
    refreshes and tab restores for 30 days. remember=False keeps the
    user signed in only for this browser session."""
    if not username or not password:
        return (False, "Username and password required.")
    user = db.get_user_by_username(username.strip())
    if not user or not user.get("password_hash"):
        return (False, "Username or password is incorrect.")
    if not verify_password(password, user["password_hash"]):
        return (False, "Username or password is incorrect.")
    _set_session_user(user)
    if remember:
        try:
            _start_remembered_session(user["contributor_id"])
        except Exception:
            pass
    return (True, "")


def _do_signup(username: str, display_name: str, email: str,
                password: str, password_confirm: str) -> tuple[bool, str]:
    username = (username or "").strip()
    display_name = (display_name or "").strip()
    email = (email or "").strip() or None
    if not username or not display_name or not password:
        return (False, "Username, display name, and password are required.")
    if " " in username:
        return (False, "Username can't contain spaces.")
    if password != password_confirm:
        return (False, "Passwords don't match.")
    if len(password) < 6:
        return (False, "Password must be at least 6 characters.")
    try:
        if db.get_user_by_username(username):
            return (False, "That username is taken.")
        db.create_signed_in_user(
            username=username,
            password_hash=hash_password(password),
            display_name=display_name,
            email=email,
            role="visitor",
        )
        return (True, "")
    except Exception as exc:
        return (False, f"Sign up failed: {exc}")


def handle_forgot_password(username: str, email: str) -> tuple[bool, str]:
    """Forgot-password flow — generate a one-time temp password.
    Returns (success, temp_password_or_error_message)."""
    user = db.request_password_reset(username, email)
    if not user:
        return (False, "No account matches that username and email.")
    import secrets as _secrets
    import string as _string
    words = ["river", "leaf", "moss", "stone", "willow", "heron",
             "fern", "otter", "tide", "kelp", "ember", "loam", "reed"]
    temp_pw = "-".join([
        _secrets.choice(words),
        _secrets.choice(words),
        "".join(_secrets.choice(_string.digits) for _ in range(3)),
    ])
    db.complete_password_reset(user["contributor_id"], hash_password(temp_pw))
    return (True, temp_pw)


def must_change_password() -> bool:
    """True when the current user signed in with a temp password and
    hasn't replaced it. Tolerates missing forgot_password migration."""
    cid = active_contributor_id()
    if not cid:
        return False
    return db.get_user_must_change_password(cid)


def change_my_password(new_password: str,
                        current_password: str | None = None) -> tuple[bool, str]:
    u = current_user()
    cid = u.get("contributor_id")
    if not cid or not u.get("username"):
        return (False, "You are not signed in with an account.")
    if not new_password or len(new_password) < 6:
        return (False, "Password must be at least 6 characters.")
    if current_password is not None:
        user_row = db.get_user_by_id(cid)
        if not user_row or not user_row.get("password_hash"):
            return (False, "Could not verify current password.")
        if not verify_password(current_password, user_row["password_hash"]):
            return (False, "Current password is wrong.")
    db.set_user_password(cid, hash_password(new_password))
    db.clear_must_change_password(cid)
    return (True, "Password updated.")


# ---------------------------------------------------------------------------
# UI: identity card (sidebar, when signed in)
# ---------------------------------------------------------------------------
def render_sidebar_identity() -> None:
    """Compact identity card with avatar, name, role glyph, sign-out button.
    Rendered in the sidebar once the user is named."""
    from src import theme as _theme
    u = current_user()
    bio_html = (f'<div class="identity-bio">{u["bio"]}</div>'
                if u.get("bio") else "")
    avatar = _theme.avatar_html(u.get("avatar_url"), size_px=44)
    with st.sidebar:
        st.markdown(
            f'<div class="identity-card" '
            f'style="display:flex;align-items:center;gap:12px">'
            f'  {avatar}'
            f'  <div style="flex:1;min-width:0">'
            f'    <div class="identity-name">{u.get("name")}'
            f'{_theme.role_glyph(u.get("role"), size_px=15)}'
            f'    </div>'
            f'    {bio_html}'
            f'  </div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if is_signed_in():
            if st.button("Sign out", key="signout_btn",
                          use_container_width=True):
                clear_session_user()
                st.rerun()
        else:
            if st.button("Leave guest mode", key="leave_guest",
                          use_container_width=True):
                clear_session_user()
                st.rerun()


# ---------------------------------------------------------------------------
# UI: main-panel gate (landing screen)
# ---------------------------------------------------------------------------
def render_main_gate() -> None:
    """Three-door entry on the landing screen: sign in / sign up / guest.
    Used when not is_named() on mobile (sidebar collapsed by default)."""
    seed_admin_password_if_needed()
    st.markdown(
        '<div class="welcome-card">'
        '<h3>Step into the river</h3>'
        '<div class="muted">'
        "Every species in our tree is held by a real person. Pick how you "
        "want to enter: sign in, make a quick account, or just leave us "
        "your first name."
        "</div></div>",
        unsafe_allow_html=True,
    )
    mode = st.radio(
        "How would you like to enter?",
        ["I have an account", "Make an account", "Just a name"],
        key="auth_main_mode",
        horizontal=True,
        label_visibility="collapsed",
    )
    if mode == "I have an account":
        _render_signin_form("main")
    elif mode == "Make an account":
        _render_signup_form("main")
    else:
        _render_guest_form("main")


def render_sidebar_gate() -> None:
    """Slim version of the gate for the sidebar. Used on desktop where the
    sidebar is the natural place to live. Once the user is named, the
    sidebar shows the identity card instead via render_sidebar_identity."""
    seed_admin_password_if_needed()
    if is_named():
        render_sidebar_identity()
        return
    with st.sidebar:
        st.markdown("### Welcome")
        st.caption("Sign in, make an account, or give a name as a guest.")
        mode = st.radio(
            "Choose how to enter",
            ["Sign in", "Create an account", "Continue as guest"],
            key="auth_sidebar_mode",
            label_visibility="collapsed",
        )
        if mode == "Sign in":
            _render_signin_form("sidebar")
        elif mode == "Create an account":
            _render_signup_form("sidebar")
        else:
            _render_guest_form("sidebar")


def _render_signin_form(scope: str) -> None:
    """Custom sign-in form (replaces streamlit-authenticator's login widget).
    On success: populates session_state, writes URL token (only if Stay
    signed in is checked), st.rerun()s."""
    with st.form(f"signin_form_{scope}"):
        u = st.text_input("Username", key=f"signin_user_{scope}")
        p = st.text_input("Password", type="password",
                            key=f"signin_pw_{scope}")
        remember = st.checkbox(
            "Stay signed in for 30 days",
            value=True,
            key=f"signin_remember_{scope}",
            help="Off = sign-out when you close the browser. "
                 "On = a URL token keeps you signed in until you "
                 "explicitly sign out.")
        if st.form_submit_button("Sign in", type="primary",
                                   use_container_width=True):
            ok, msg = _do_signin(u, p, remember=remember)
            if ok:
                st.rerun()
            else:
                st.error(msg)
    with st.expander("Forgot your password?", expanded=False):
        with st.form(f"forgot_pw_form_{scope}"):
            st.caption(
                "Type your username and the email you signed up with. "
                "If they match, you'll see a one-time temporary password "
                "to sign in with. Change it from your Profile tab after.")
            fp_user = st.text_input("Username", key=f"fp_user_{scope}")
            fp_email = st.text_input("Email", key=f"fp_email_{scope}")
            if st.form_submit_button("Send reset", type="primary",
                                       use_container_width=True):
                ok, msg = handle_forgot_password(fp_user.strip(),
                                                  fp_email.strip())
                if not ok:
                    st.warning(msg)
                else:
                    st.success("Reset done. Your one-time temporary "
                                "password is:")
                    st.code(msg, language=None)


def _render_signup_form(scope: str) -> None:
    """Invite-only: public sign-up is disabled. Admin creates accounts
    from Profile → Team. Anyone can still enter as a named guest via
    the third door on the gate."""
    st.info(
        "Accounts are invite-only. To get a signed-in profile with "
        "avatar, bio, and follow/favorite features, ask Maya to add "
        "you (maya@shared-rivers.org). In the meantime you can enter "
        "as a **guest** using the third option above — your name "
        "still attributes any contributions.")


def _render_guest_form(scope: str) -> None:
    with st.form(f"guest_form_{scope}"):
        st.caption(
            "We use your name so contributions stay attributable. "
            "You can sign up later to keep a profile.")
        guest_name = st.text_input("Your name", key=f"guest_name_{scope}")
        if st.form_submit_button("Enter as guest", type="primary",
                                   use_container_width=True):
            if guest_name.strip():
                ok, msg = set_guest_user(guest_name)
                if ok:
                    st.rerun()
                else:
                    st.warning(msg)
            else:
                st.warning("Give yourself a name first.")


# ---------------------------------------------------------------------------
# Diagnostic panel (admin-visible, helps debug auth issues)
# ---------------------------------------------------------------------------
def render_auth_diagnostic() -> None:
    """Render a debug panel showing URL query params, session state user,
    and the auth_session lookup result. Admin can use this to verify the
    remember-me chain is working end-to-end."""
    if not is_admin():
        return
    with st.expander("Auth diagnostic (admin)", expanded=False):
        st.markdown("**URL query params:**")
        try:
            params = dict(st.query_params)
            st.json(params)
        except Exception as exc:
            st.error(f"st.query_params unavailable: {exc}")
        st.markdown("**Current session_state['user']:**")
        # Redact bulky / sensitive fields so the panel stays scannable
        _u = dict(current_user())
        if _u.get("avatar_url"):
            v = _u["avatar_url"]
            _u["avatar_url"] = (f"<base64 image, {len(v)} bytes>"
                                  if v.startswith("data:") else v)
        st.json(_u)
        st.markdown("**Token lookup result:**")
        token = _read_session_token()
        if not token:
            st.warning("No URL session token present. Refresh = sign-out.")
        else:
            cid = db.lookup_auth_session(token)
            if cid:
                st.success(
                    f"Token resolves to contributor_id={cid}. "
                    "Refresh should keep you signed in.")
            else:
                st.error(
                    f"Token {token[:8]}… does NOT resolve in "
                    "auth_session. Either it expired, was deleted, or "
                    "the auth_session_migration.sql has not been "
                    "applied to this Supabase project.")
