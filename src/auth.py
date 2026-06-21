"""
Authentication, roles, and permissions for {r}Evolving Kinship.

Three classes of visitor:

  - **admin** — Maya (and anyone she promotes). Can edit anything.
  - **editor** — trusted signed-in user. Can edit anyone's contributions
    except admin-owned trees.
  - **visitor** / signed-in users — can add to community datapoints and edit
    their own trees + contributions. Includes both registered accounts and
    named guests (no account, just a name).

Persistent login uses streamlit-authenticator's signed-cookie JWT, so
returning visitors stay logged in across browser sessions for 30 days.

Maya's admin password is read from the ADMIN_PASSWORD env var (Streamlit
Cloud secret); on first run the auth module hashes it into the `maya`
contributor row, so there's no plaintext anywhere on disk or in code.
"""

from __future__ import annotations

import os

import bcrypt
import streamlit as st
import streamlit_authenticator as stauth

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
# Bootstrap Maya admin password from env (one-time, on first import)
# ---------------------------------------------------------------------------
def seed_admin_password_if_needed() -> None:
    """If maya exists in contributor but has no password_hash, set it from
    the ADMIN_PASSWORD env var. Runs at most once per Streamlit session
    so we don't pay a DB read on every script rerun."""
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
    if not user:
        return
    if user.get("password_hash"):
        return
    hashed = hash_password(admin_pw)
    db.set_user_password(user["contributor_id"], hashed)


# ---------------------------------------------------------------------------
# streamlit-authenticator wiring
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60, show_spinner=False)
def _build_credentials_dict() -> dict:
    """Pull all signed-in users from the contributor table into the format
    streamlit-authenticator expects. Cached 60s so we don't hit the DB
    every script rerun."""
    try:
        users = db.list_signed_in_users()
    except Exception:
        users = None

    creds: dict = {"usernames": {}}
    if users is None or users.empty:
        return creds
    for _, row in users.iterrows():
        username = row.get("username")
        pw_hash = row.get("password_hash")
        if not username or not pw_hash:
            continue
        creds["usernames"][username] = {
            "name": row.get("display_name") or username,
            "password": pw_hash,
            "email": row.get("email") or "",
            "failed_login_attempts": 0,
            "logged_in": False,
        }
    return creds


def _get_authenticator() -> stauth.Authenticate:
    """Build the streamlit-authenticator instance. Cached per session so the
    same cookie state is reused across reruns within a session."""
    if "_authenticator" in st.session_state:
        return st.session_state["_authenticator"]
    # JWT signing key for the auth cookie. Prefer the explicit COOKIE_KEY env
    # var. Fall back to a key derived from ADMIN_PASSWORD so existing
    # deployments keep working. As a last resort, use a clearly-labeled
    # default and warn — production should override.
    cookie_key = os.environ.get("COOKIE_KEY")
    if not cookie_key:
        admin_pw = os.environ.get("ADMIN_PASSWORD", "").strip()
        if admin_pw:
            cookie_key = admin_pw + "-kinship-cookie"
        else:
            cookie_key = "kinship-please-set-COOKIE_KEY-in-secrets-1f9a"
    auth = stauth.Authenticate(
        _build_credentials_dict(),
        cookie_name="kinship_auth",
        cookie_key=cookie_key,
        cookie_expiry_days=30,
        # We store our own bcrypt hashes; tell the library not to re-hash
        # them. Without this, 0.3.x will try to bcrypt the bcrypt string on
        # every rerun, breaking login.
        auto_hash=False,
    )
    st.session_state["_authenticator"] = auth
    return auth


# ---------------------------------------------------------------------------
# Current user (session_state shape we agree on across the app)
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
    """The active user. Always returns a dict, with None fields when nobody
    has named themselves yet."""
    return st.session_state.get("user", dict(_GUEST_USER))


def _set_session_user_from_db(username: str) -> None:
    """Load a full user row from contributor and store it in session_state.
    Updates last_login_at AND starts a server-side session (writes the
    remember-me cookie) so the next browser refresh stays signed in."""
    user_row = db.get_user_by_username(username)
    if not user_row:
        return
    st.session_state["user"] = {
        "username": user_row["username"],
        "name": user_row.get("display_name") or username,
        "role": user_row.get("role") or "visitor",
        "contributor_id": user_row["contributor_id"],
        "bio": user_row.get("bio"),
        "avatar_url": user_row.get("avatar_url"),
    }
    st.session_state["is_admin"] = (
        st.session_state["user"]["role"] == "admin"
    )
    try:
        db.update_last_login(user_row["contributor_id"])
    except Exception:
        pass
    # Persist the session in our own table + cookie so refresh = stay in.
    try:
        _start_remembered_session(user_row["contributor_id"])
    except Exception:
        pass


def clear_session_user() -> None:
    # Clear both the in-memory session AND the server-side row + cookie
    # so the next page load doesn't auto-restore the user we just signed
    # out.
    try:
        _end_remembered_session()
    except Exception:
        pass
    st.session_state.pop("user", None)
    st.session_state["is_admin"] = False


def set_guest_user(name: str) -> tuple[bool, str]:
    """Named-guest path: no password, just a display name. Returns
    (success, message). Refuses if `name` belongs to a registered user, so
    a guest can't impersonate Maya/an editor."""
    if not name or not name.strip():
        return (False, "Give yourself a name first.")
    name = name.strip()
    contributor_id, is_registered = db.get_or_create_guest_contributor(name)
    if is_registered:
        return (False,
                f"\"{name}\" is a registered account. Sign in with your "
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
# Role + permission helpers
# ---------------------------------------------------------------------------
def role() -> str | None:
    return current_user().get("role")


def is_admin() -> bool:
    return role() == "admin"


def is_editor_or_admin() -> bool:
    return role() in ("editor", "admin")


def is_signed_in() -> bool:
    """True for username/password accounts (not named guests)."""
    return bool(current_user().get("username"))


def is_named() -> bool:
    """True once the user has either signed in or given a guest name."""
    return bool(current_user().get("name"))


def can_edit_tree(tree_row: dict | None) -> bool:
    """
    tree_row is a dict with at least owner_id + owner_role.
    Rules:
      - admin: can edit anything
      - signed-in user / editor / visitor: can edit their own trees
      - if tree's owner is admin: only admins can edit (locked)
      - editor (not own tree, not admin-owned): can edit
    """
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
    """
    Rules:
      - admin / editor: can edit anyone's contribution
      - contributor: can edit their own
      - everyone else: no
    """
    u = current_user()
    if u.get("role") in ("admin", "editor"):
        return True
    if (u.get("contributor_id")
            and u["contributor_id"] == contribution_contributor_id):
        return True
    return False




# --- Cookie-backed remember-me ----------------------------------------------
# We replaced streamlit-authenticator's built-in cookie (which doesn't
# persist reliably across refreshes on Streamlit Cloud, because the app
# runs in an iframe and SameSite/Secure attributes aren't always set) with
# a server-side session token. The browser cookie holds only an opaque
# UUID; the auth_session table maps it to a contributor_id.

_COOKIE_NAME = "kinship_session"


def _get_cookie_manager():
    """One CookieManager per Streamlit session. The library caches its own
    component-key state internally, so creating multiple managers will
    fight over keys and corrupt the cookie dict. We stash one in
    session_state and reuse it for every read/write."""
    if "_cookie_manager" in st.session_state:
        return st.session_state["_cookie_manager"]
    try:
        import extra_streamlit_components as stx
        cm = stx.CookieManager(key="kinship_cookie_mgr_init")
    except Exception as exc:
        print(f"CookieManager init failed: {exc}")
        cm = None
    st.session_state["_cookie_manager"] = cm
    return cm


def _read_session_cookie() -> str | None:
    """Read our session cookie from the CookieManager. On the very first
    script run after a fresh page load, the manager's internal dict is
    still {} because the JS iframe hasn't synced yet — it returns None.
    Streamlit auto-reruns when the component sends real data; on that
    rerun we get the real value. No retry loop needed here, just don't
    crash on the empty case."""
    cm = _get_cookie_manager()
    if cm is None:
        return None
    try:
        v = cm.get(cookie=_COOKIE_NAME)
        return v if v else None
    except Exception:
        return None


def _write_session_cookie(session_id: str) -> None:
    """Write the session_id cookie. The two attributes that matter for
    Streamlit Cloud + iframe contexts:
      - same_site='none' lets the cookie ride along even when the component
        iframe is a cross-site context (which it always is)
      - secure=True is required by browsers whenever same_site='none'

    Default of the library is same_site='strict' which silently discards
    the cookie in iframe contexts — that was the bug all along."""
    cm = _get_cookie_manager()
    if cm is None:
        return
    from datetime import datetime, timedelta
    try:
        cm.set(
            _COOKIE_NAME, session_id,
            expires_at=datetime.now() + timedelta(days=30),
            key=f"kinship_cookie_set_{session_id[:8]}",
            same_site="none",
            secure=True,
            path="/",
        )
    except Exception as exc:
        print(f"cookie write failed: {exc}")


def _clear_session_cookie() -> None:
    """Delete the session cookie. We also overwrite with an expired one
    using the same SameSite settings, because some browsers only honor
    delete-by-overwrite (not the Set-Cookie header's delete attribute)
    when the original cookie was SameSite=none."""
    cm = _get_cookie_manager()
    if cm is None:
        return
    from datetime import datetime, timedelta
    try:
        cm.delete(_COOKIE_NAME, key="kinship_cookie_clear")
    except Exception:
        pass
    try:
        cm.set(_COOKIE_NAME, "",
               expires_at=datetime.now() - timedelta(days=1),
               key="kinship_cookie_overwrite",
               same_site="none", secure=True, path="/")
    except Exception:
        pass


def _try_cookie_restore() -> bool:
    """Read the browser cookie. If it points at a valid auth_session row,
    sign the user in silently. Runs on every page load so a returning
    visitor is restored before any UI gate checks is_named().

    Returns True if the user is named after the call."""
    # Probabilistic GC: ~1% of page loads sweep expired auth_session rows.
    # Cheap and self-healing without needing a separate cron.
    import secrets as _s
    if _s.randbelow(100) == 0:
        try:
            db.cleanup_expired_sessions()
        except Exception:
            pass
    if is_named():
        return True
    session_id = _read_session_cookie()
    if not session_id:
        return False
    cid = db.lookup_auth_session(session_id)
    if not cid:
        # Stale or unknown cookie. Clear it so the browser doesn't keep
        # sending a token we don't recognize.
        _clear_session_cookie()
        return False
    user = db.get_user_by_id(cid)
    if not user or not user.get("username"):
        _clear_session_cookie()
        return False
    # Found a valid signed-in session — populate session_state directly.
    st.session_state["user"] = {
        "username": user["username"],
        "name": user.get("display_name") or user["username"],
        "role": user.get("role") or "visitor",
        "contributor_id": user["contributor_id"],
        "bio": user.get("bio"),
        "avatar_url": user.get("avatar_url"),
    }
    st.session_state["is_admin"] = (user.get("role") == "admin")
    # Optional housekeeping
    try:
        db.touch_auth_session(session_id)
    except Exception:
        pass
    return True


def _start_remembered_session(contributor_id: str) -> None:
    """Called right after a successful sign-in. Creates the server-side
    session row + writes the cookie so the next page load restores
    automatically."""
    if not contributor_id:
        return
    session_id = db.create_auth_session(contributor_id)
    if session_id:
        _write_session_cookie(session_id)


def _end_remembered_session() -> None:
    """Called on explicit sign-out. Deletes the server-side row + clears
    the cookie. The browser will stop offering the token going forward."""
    session_id = _read_session_cookie()
    if session_id:
        try:
            db.delete_auth_session(session_id)
        except Exception:
            pass
    _clear_session_cookie()


# ---------------------------------------------------------------------------
# UI: landing-page gate (main panel — mobile friendly)
# ---------------------------------------------------------------------------
def render_main_gate() -> None:
    """A wider, friendlier version of the sign-in / sign-up / guest forms
    that sits in the main panel. Used by the landing screen when the
    visitor has not yet named themselves, so phone users do not have to
    discover the collapsed sidebar. Tries the cookie first so returning
    users don't see the gate at all."""
    seed_admin_password_if_needed()
    _try_cookie_restore()
    auth_obj = _get_authenticator()

    st.markdown(
        '<div style="max-width:540px;margin:18px auto;">',
        unsafe_allow_html=True,
    )
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
        try:
            auth_obj.login(location="main", key="main_login_widget")
        except Exception:
            pass
        status = st.session_state.get("authentication_status")
        if status:
            username = st.session_state.get("username")
            if username:
                _set_session_user_from_db(username)
                st.rerun()
        elif status is False:
            st.error("Username or password is incorrect.")
        with st.expander("Forgot your password?", expanded=False):
            _render_forgot_password_form(form_key="forgot_main")

    elif mode == "Make an account":
        with st.form("main_signup_form"):
            new_user = st.text_input("Username", help="No spaces.")
            new_name = st.text_input("Display name")
            new_email = st.text_input("Email (optional)")
            new_pw = st.text_input("Password", type="password")
            new_pw2 = st.text_input("Confirm password", type="password")
            if st.form_submit_button("Create account", type="primary",
                                     use_container_width=True):
                _handle_signup(new_user, new_name, new_email,
                               new_pw, new_pw2)

    else:  # Just a name
        with st.form("main_guest_form"):
            st.caption(
                "We use your name so contributions stay attributable. "
                "You can sign up later to keep a profile and revisit "
                "your trees.")
            guest_name = st.text_input(
                "Your name",
                placeholder="Maya, Yui, Ade, ...",
            )
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
    st.markdown("</div>", unsafe_allow_html=True)


def render_sidebar_identity() -> None:
    """Compact identity card for the sidebar once the user is named.
    Shows display name with a role glyph (shield for admin, writing hand for
    editor, leaf for visitor), optional bio, sign-out button."""
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
        auth_obj = _get_authenticator()
        if is_signed_in():
            try:
                auth_obj.logout("Sign out", "sidebar", key="auth_logout")
            except Exception:
                if st.button("Sign out", key="auth_logout_fallback",
                             use_container_width=True):
                    clear_session_user()
                    st.rerun()
            if (st.session_state.get("authentication_status") is None
                    and is_signed_in()):
                clear_session_user()
                st.rerun()
        else:
            if st.button("Leave guest mode", key="leave_guest",
                         use_container_width=True):
                clear_session_user()
                st.rerun()


# ---------------------------------------------------------------------------
# UI: the sidebar gate (kept for desktop fallback — collapses into the
# identity card when the user is named)
# ---------------------------------------------------------------------------
def render_sidebar_gate() -> None:
    """Render the auth widget in the sidebar. Replaces the old admin password
    gate. Once the user is signed in or named, the sidebar shows their info
    plus a sign-out button. Tries to restore a previous session's cookie
    first so returning users don't see the sign-in form again."""

    # Make sure the maya admin row has a password hash on first run.
    seed_admin_password_if_needed()
    # Restore session from the auth cookie if one is still valid (30 days).
    _try_cookie_restore()

    auth_obj = _get_authenticator()

    with st.sidebar:
        if is_named():
            # Hand off to the dedicated identity card so we don't duplicate
            # the markup. This is the only path the station uses now.
            pass
        else:
            pass
    if is_named():
        render_sidebar_identity()
        return

        # Not yet logged in or named. Three doors.
        st.markdown("### Welcome")
        st.caption(
            "Sign in, make an account, or give a name and visit as a guest.")
        mode = st.radio(
            "Choose how to enter",
            ["Sign in", "Create an account", "Continue as guest"],
            key="auth_mode",
            label_visibility="collapsed")

        if mode == "Sign in":
            try:
                auth_obj.login(location="sidebar", key="login_widget")
            except Exception:
                pass
            status = st.session_state.get("authentication_status")
            if status:
                username = st.session_state.get("username")
                if username:
                    _set_session_user_from_db(username)
                    st.rerun()
            elif status is False:
                st.error("Username or password is incorrect.")
            with st.expander("Forgot your password?", expanded=False):
                _render_forgot_password_form(form_key="forgot_sidebar")

        elif mode == "Create an account":
            with st.form("signup_form"):
                new_user = st.text_input("Username", help="No spaces.")
                new_name = st.text_input("Display name")
                new_email = st.text_input("Email (optional)")
                new_pw = st.text_input("Password", type="password")
                new_pw2 = st.text_input("Confirm password", type="password")
                if st.form_submit_button("Create account", type="primary"):
                    _handle_signup(new_user, new_name, new_email,
                                   new_pw, new_pw2)

        else:  # Continue as guest
            with st.form("guest_form"):
                guest_name = st.text_input(
                    "Your name",
                    help="So we know who's contributing. You can sign up "
                         "later to keep a profile.")
                if st.form_submit_button("Enter as guest", type="primary"):
                    if guest_name.strip():
                        ok, msg = set_guest_user(guest_name)
                        if ok:
                            st.rerun()
                        else:
                            st.warning(msg)
                    else:
                        st.warning("Give yourself a name first.")


def _handle_signup(username: str, display_name: str, email: str,
                   pw: str, pw_confirm: str) -> None:
    username = (username or "").strip()
    display_name = (display_name or "").strip()
    email = (email or "").strip() or None
    pw = pw or ""
    if not username or not display_name or not pw:
        st.warning("Username, display name, and password are required.")
        return
    if " " in username:
        st.warning("Username can't contain spaces.")
        return
    if pw != pw_confirm:
        st.error("Passwords don't match.")
        return
    if len(pw) < 6:
        st.warning("Password must be at least 6 characters.")
        return
    try:
        if db.get_user_by_username(username):
            st.warning("That username is taken.")
            return
        db.create_signed_in_user(
            username=username,
            password_hash=hash_password(pw),
            display_name=display_name,
            email=email,
            role="visitor",
        )
        st.success(
            f"Account created for {display_name}. Switch to **Sign in** "
            "to enter.")
    except Exception as exc:
        st.error(f"Sign up failed: {exc}")


# ---------------------------------------------------------------------------
# Convenience: get the active contributor_id for any write path
# ---------------------------------------------------------------------------
def active_contributor_id() -> str | None:
    return current_user().get("contributor_id")

# ---------------------------------------------------------------------------
# Forgot-password support
# ---------------------------------------------------------------------------
import secrets as _secrets
import string as _string


def _generate_temp_password() -> str:
    """Pleasant-to-type temp password: three short words + 3 digits."""
    words = ["river", "leaf", "moss", "stone", "willow", "heron",
             "fern", "otter", "tide", "kelp", "ember", "loam", "reed"]
    return "-".join([
        _secrets.choice(words),
        _secrets.choice(words),
        "".join(_secrets.choice(_string.digits) for _ in range(3)),
    ])


def handle_forgot_password(username: str, email: str) -> tuple[bool, str]:
    """Run a password reset. Returns (success, message_or_temp_password).
    On success, the message IS the temp password — caller should display it
    to the user. We don't differentiate the failure cases (wrong username,
    wrong email, no email on file) so we don't leak whether a username
    exists in the system."""
    user = db.request_password_reset(username, email)
    if not user:
        return (False, "No account matches that username and email.")
    temp_pw = _generate_temp_password()
    db.complete_password_reset(user["contributor_id"], hash_password(temp_pw))
    return (True, temp_pw)


def must_change_password() -> bool:
    """True when the current user got a temp password and hasn't replaced
    it with one of their own. Tolerates the case where the
    forgot_password_migration hasn't been applied (returns False)."""
    u = current_user()
    cid = u.get("contributor_id")
    if not cid:
        return False
    return db.get_user_must_change_password(cid)


def change_my_password(new_password: str,
                        current_password: str | None = None) -> tuple[bool, str]:
    """Self-service: signed-in user replaces their own password. If
    current_password is provided, verify it first (used by the regular
    'change my password' card; the forgot-password reset path skips this
    because the user just typed a temp password to sign in)."""
    u = current_user()
    cid = u.get("contributor_id")
    if not cid or not u.get("username"):
        return (False, "You are not signed in with an account.")
    if not new_password or len(new_password) < 6:
        return (False, "Password must be at least 6 characters.")
    if current_password is not None:
        # Pull the current hash and verify before replacing.
        user_row = db.get_user_by_id(cid)
        if not user_row or not user_row.get("password_hash"):
            return (False, "Could not verify current password.")
        if not verify_password(current_password,
                                user_row["password_hash"]):
            return (False, "Current password is wrong.")
    db.set_user_password(cid, hash_password(new_password))
    db.clear_must_change_password(cid)
    return (True, "Password updated.")

def _render_forgot_password_form(form_key: str) -> None:
    """Inline form used by both the main and sidebar sign-in tiles.

    User supplies username + email. If they match, we generate a one-time
    temp password and show it right here on the page (they're sitting at
    the device that asked). They sign in with it, then the Profile tab
    forces them to set a new one."""
    with st.form(f"{form_key}_form"):
        st.caption(
            "Type your username and the email you signed up with. If they "
            "match, you'll see a one-time temporary password to sign in "
            "with. Change it from your Profile tab right after.")
        fp_user = st.text_input("Username", key=f"{form_key}_user")
        fp_email = st.text_input("Email", key=f"{form_key}_email")
        submit = st.form_submit_button("Send reset", type="primary",
                                        use_container_width=True)
    if submit:
        ok, msg = handle_forgot_password(fp_user.strip(), fp_email.strip())
        if not ok:
            st.warning(msg)
        else:
            st.success("Reset done. Your one-time temporary password is:")
            st.code(msg, language=None)
            st.caption("Sign in above with this password, then change it "
                       "right away from your Profile tab.")

