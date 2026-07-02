"""
Warehouse layer (v2 — 4NF+ schema on Supabase Postgres).

The public API is intentionally the same as v1 (init_db, read_tree,
list_trees, insert_request, rename_tree, delete_species, delete_tree,
update_fields, append_dedup) so consumers (tree.py, pipeline.py, station.py,
etl.py) keep working without changes. Internally the calls translate between
the old flat row shape and the new normalized tables:

    contributor                                 — anyone who writes data
    species              (PK species_id)        — one row per real species
    clade                (PK clade_id)          — taxonomic ancestry, shared
    species_clade        (M2M)                  — species → clades
    species_name         (PK name_id)           — multilingual / multicultural
    tree                 (PK tree_id)           — first-class trees with slug
    tree_species         (PK tree_id, species_id) — m2m + per-tree note

NCBI taxonomy stays where it was (taxa.sqlite via ete3, file-based).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

_engine: Engine | None = None

# Column names the v1 code expects on a read_tree() DataFrame. The
# v_legacy_species_rows view in schema_v2.sql produces all but `domain` and
# `story` which we add on the read path below.
WRITE_COLUMNS = [
    "tree_name", "common_name", "scientific_name", "ncbi_taxid",
    "domain", "kingdom", "phylum", "class_", "order_", "family", "genus",
    "story", "submitted_by", "notes",
]

EDITABLE_COLUMNS = [c for c in WRITE_COLUMNS
                    if c not in ("tree_name", "scientific_name")]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(config.DATABASE_URL, future=True,
                                pool_pre_ping=True)
    return _engine


def is_postgres() -> bool:
    return get_engine().dialect.name == "postgresql"


# ---------------------------------------------------------------------------
# Slug + safe-name helpers (kept here so the DB layer can guarantee uniqueness)
# ---------------------------------------------------------------------------
_SLUG_UNSAFE = re.compile(r'[\s/\\:*?"<>|#%&{}\(\),;]+')


def _safe_slug(name: str) -> str:
    if not isinstance(name, str):
        return "tree"
    s = name.strip().lower()
    s = _SLUG_UNSAFE.sub("_", s)
    s = re.sub(r"[^a-z0-9_\-]+", "", s)
    s = re.sub(r"_+", "_", s).strip("_-")
    return s or "tree"


# ---------------------------------------------------------------------------
# init_db — verify the v2 schema is present in Supabase
# ---------------------------------------------------------------------------
def init_db() -> None:
    """Verify the v2 schema is applied. wipe_and_init.sql + schema_v2.sql must
    be run in the Supabase SQL editor before the app starts."""
    engine = get_engine()
    with engine.connect() as conn:
        n = conn.execute(text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'public' "
            "AND table_name IN ('tree','species','species_name',"
            "'tree_species','clade','contributor')"
        )).scalar() or 0
    if int(n) < 6:
        raise RuntimeError(
            "v2 schema missing. Run db/wipe_and_init.sql then "
            "db/schema_v2.sql in the Supabase SQL editor.")
    where = "Postgres/Supabase" if is_postgres() else "SQLite"
    print(f"warehouse ready ({where}, schema v2): "
          f"{config.DATABASE_URL.split('@')[-1]}")


# ---------------------------------------------------------------------------
# Contributors
# ---------------------------------------------------------------------------
def get_or_create_contributor(display_name: str | None) -> str | None:
    """Return contributor_id (UUID string) or None if no name supplied."""
    if not display_name:
        return None
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT contributor_id FROM contributor "
                 "WHERE display_name = :n LIMIT 1"),
            {"n": display_name},
        ).fetchone()
        if row:
            return str(row[0])
        new = conn.execute(
            text("INSERT INTO contributor (display_name, role) "
                 "VALUES (:n, 'visitor') RETURNING contributor_id"),
            {"n": display_name},
        ).fetchone()
        return str(new[0])


# ---------------------------------------------------------------------------
# Auth / user management (after db/auth_migration.sql)
# ---------------------------------------------------------------------------
_USER_COLS = ("contributor_id, display_name, username, password_hash, "
              "role, email, bio, avatar_url, last_login_at")


def _row_to_user_dict(row) -> dict | None:
    if not row:
        return None
    return {
        "contributor_id": str(row[0]),
        "display_name": row[1],
        "username": row[2],
        "password_hash": row[3],
        "role": row[4],
        "email": row[5],
        "bio": row[6],
        "avatar_url": row[7],
        "last_login_at": row[8],
    }


def get_user_by_username(username: str) -> dict | None:
    """Look up a signed-in user by username (case-insensitive)."""
    if not username:
        return None
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT {_USER_COLS} FROM contributor "
                 "WHERE lower(username) = lower(:u) LIMIT 1"),
            {"u": username},
        ).fetchone()
    return _row_to_user_dict(row)


def get_user_by_id(contributor_id: str) -> dict | None:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT {_USER_COLS} FROM contributor "
                 "WHERE contributor_id = :i LIMIT 1"),
            {"i": contributor_id},
        ).fetchone()
    return _row_to_user_dict(row)


def list_signed_in_users() -> pd.DataFrame:
    """All contributor rows with a username + password_hash. Used by the auth
    module to feed streamlit-authenticator on every script rerun."""
    return pd.read_sql(text(
        "SELECT contributor_id, display_name, username, password_hash, "
        "role, email, bio, avatar_url, last_login_at "
        "FROM contributor "
        "WHERE username IS NOT NULL AND password_hash IS NOT NULL "
        "ORDER BY lower(username)"
    ), get_engine())


def list_all_users_for_admin() -> pd.DataFrame:
    """Admin view: every contributor row, signed-in or not. Used by the admin
    role-management UI."""
    return pd.read_sql(text(
        "SELECT c.contributor_id, c.display_name, c.username, c.role, "
        "c.email, c.bio, c.last_login_at, "
        "(SELECT count(*) FROM tree t WHERE t.owner_id = c.contributor_id) "
        "  AS trees_owned, "
        "(SELECT count(*) FROM story s WHERE s.contributed_by = c.contributor_id) "
        "  AS stories, "
        "(SELECT count(*) FROM dish d WHERE d.contributed_by = c.contributor_id) "
        "  AS dishes "
        "FROM contributor c "
        "ORDER BY (c.role = 'admin') DESC, (c.role = 'editor') DESC, "
        "         lower(coalesce(c.username, c.display_name))"
    ), get_engine())


def create_signed_in_user(username: str, password_hash: str,
                          display_name: str, email: str | None = None,
                          role: str = "visitor") -> str:
    """Create a new contributor with a username + password_hash. If a
    contributor with this display_name already exists (e.g. they used the
    app as a named guest first), upgrade that row instead of inserting a
    duplicate. Returns contributor_id."""
    engine = get_engine()
    with engine.begin() as conn:
        # Upgrade a guest row of the same display name, if any.
        existing = conn.execute(
            text("SELECT contributor_id FROM contributor "
                 "WHERE display_name = :n AND username IS NULL LIMIT 1"),
            {"n": display_name},
        ).fetchone()
        if existing:
            cid = str(existing[0])
            conn.execute(
                text("UPDATE contributor SET username = :u, "
                     "password_hash = :p, email = :e, role = :r "
                     "WHERE contributor_id = :i"),
                {"u": username, "p": password_hash, "e": email,
                 "r": role, "i": cid},
            )
            return cid
        new = conn.execute(
            text("INSERT INTO contributor "
                 "  (display_name, username, password_hash, email, role) "
                 "VALUES (:n, :u, :p, :e, :r) RETURNING contributor_id"),
            {"n": display_name, "u": username, "p": password_hash,
             "e": email, "r": role},
        ).fetchone()
        return str(new[0])


def set_user_password(contributor_id: str, password_hash: str) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE contributor SET password_hash = :p "
                 "WHERE contributor_id = :i"),
            {"p": password_hash, "i": contributor_id},
        )


def set_user_role(contributor_id: str, role: str) -> None:
    """Promote or demote a user. Allowed roles: visitor, editor, admin."""
    if role not in ("visitor", "editor", "admin"):
        raise ValueError(f"Invalid role: {role}")
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE contributor SET role = :r "
                 "WHERE contributor_id = :i"),
            {"r": role, "i": contributor_id},
        )


def set_user_theme(contributor_id: str, theme: str | None) -> None:
    """Save the user's theme choice. Silently no-ops if the theme
    column doesn't exist yet (migration not applied)."""
    engine = get_engine()
    try:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE contributor SET theme = :t "
                     "WHERE contributor_id = :i"),
                {"t": theme, "i": contributor_id},
            )
    except Exception as exc:
        # UndefinedColumn if migration hasn't run — safe to swallow
        if "theme" in str(exc).lower():
            return
        raise


def add_clade_note(clade_name: str, body: str,
                   contributor_id: str | None,
                   tree_name: str | None = None) -> str | None:
    """Save a note attached to a clade. Returns the new id, or None if
    the table isn't provisioned yet."""
    if not clade_name or not body or not body.strip():
        return None
    engine = get_engine()
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text("INSERT INTO clade_note "
                     "(clade_name, body, contributor_id, tree_name) "
                     "VALUES (:c, :b, :u, :t) "
                     "RETURNING clade_note_id"),
                {"c": clade_name.strip(),
                 "b": body.strip(),
                 "u": contributor_id,
                 "t": tree_name},
            ).fetchone()
        return str(row[0]) if row else None
    except Exception as exc:
        if "clade_note" in str(exc).lower():
            return None
        raise


def list_clade_notes(clade_name: str,
                     tree_name: str | None = None) -> list[dict]:
    """Notes for a clade. If tree_name given, include tree-specific AND
    global notes; otherwise only globals."""
    engine = get_engine()
    try:
        with engine.begin() as conn:
            if tree_name:
                q = ("SELECT n.clade_note_id, n.body, n.tree_name, "
                     "       n.created_at, c.display_name, c.username, "
                     "       c.contributor_id "
                     "FROM clade_note n "
                     "LEFT JOIN contributor c "
                     "  ON c.contributor_id = n.contributor_id "
                     "WHERE n.clade_name = :cn "
                     "  AND (n.tree_name IS NULL OR n.tree_name = :tn) "
                     "ORDER BY n.created_at DESC")
                params = {"cn": clade_name, "tn": tree_name}
            else:
                q = ("SELECT n.clade_note_id, n.body, n.tree_name, "
                     "       n.created_at, c.display_name, c.username, "
                     "       c.contributor_id "
                     "FROM clade_note n "
                     "LEFT JOIN contributor c "
                     "  ON c.contributor_id = n.contributor_id "
                     "WHERE n.clade_name = :cn "
                     "ORDER BY n.created_at DESC")
                params = {"cn": clade_name}
            rows = conn.execute(text(q), params).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception:
        return []


def delete_clade_note(clade_note_id: str,
                      by_contributor_id: str,
                      is_admin: bool = False) -> bool:
    """Delete a note. Owner or admin only. Returns True on success."""
    engine = get_engine()
    try:
        with engine.begin() as conn:
            if is_admin:
                r = conn.execute(
                    text("DELETE FROM clade_note "
                         "WHERE clade_note_id = :i RETURNING 1"),
                    {"i": clade_note_id}).fetchone()
            else:
                r = conn.execute(
                    text("DELETE FROM clade_note "
                         "WHERE clade_note_id = :i "
                         "  AND contributor_id = :u RETURNING 1"),
                    {"i": clade_note_id, "u": by_contributor_id}
                ).fetchone()
        return bool(r)
    except Exception:
        return False


def get_user_theme(contributor_id: str) -> str | None:
    """Read the user's theme choice. Returns None if column missing
    or user has no preference."""
    engine = get_engine()
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text("SELECT theme FROM contributor "
                     "WHERE contributor_id = :i"),
                {"i": contributor_id},
            ).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def update_user_profile(contributor_id: str,
                        display_name: str | None = None,
                        bio: str | None = None,
                        avatar_url: str | None = None,
                        email: str | None = None) -> None:
    """Patch the profile fields the user can edit themselves. Each arg is
    only applied when not None, so callers can pass just the ones that
    changed."""
    sets, params = [], {"i": contributor_id}
    if display_name is not None:
        sets.append("display_name = :n")
        params["n"] = display_name
    if bio is not None:
        sets.append("bio = :b")
        params["b"] = bio
    if avatar_url is not None:
        sets.append("avatar_url = :a")
        params["a"] = avatar_url
    if email is not None:
        sets.append("email = :e")
        params["e"] = email
    if not sets:
        return
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(f"UPDATE contributor SET {', '.join(sets)} "
                 "WHERE contributor_id = :i"),
            params,
        )


def update_last_login(contributor_id: str) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE contributor SET last_login_at = now() "
                 "WHERE contributor_id = :i"),
            {"i": contributor_id},
        )


def get_tree_owner_info(tree_name: str) -> dict | None:
    """Return {owner_id, owner_role, owner_display_name} for permission
    checks. None if tree or owner is missing."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT t.owner_id, c.role, c.display_name
            FROM tree t
            LEFT JOIN contributor c ON c.contributor_id = t.owner_id
            WHERE t.name = :n LIMIT 1
        """), {"n": tree_name}).fetchone()
    if not row:
        return None
    return {
        "owner_id": str(row[0]) if row[0] is not None else None,
        "owner_role": row[1],
        "owner_display_name": row[2],
    }


def set_tree_owner(tree_name: str, owner_contributor_id: str) -> int:
    """Transfer ownership of a tree. Used by admin's 'lock this tree to me'
    UI."""
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("UPDATE tree SET owner_id = :o WHERE name = :n"),
            {"o": owner_contributor_id, "n": tree_name},
        )
        return int(result.rowcount or 0)


# ---------------------------------------------------------------------------
# Trees
# ---------------------------------------------------------------------------
def get_tree_id(tree_name: str) -> str | None:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT tree_id FROM tree WHERE name = :n LIMIT 1"),
            {"n": tree_name.strip()},
        ).fetchone()
    return str(row[0]) if row else None


def get_or_create_tree(tree_name: str,
                       owner_display_name: str | None = None) -> str:
    name = tree_name.strip()
    existing = get_tree_id(name)
    if existing:
        return existing
    slug = _safe_slug(name)
    owner_id = get_or_create_contributor(owner_display_name) if owner_display_name else None
    # If the slug collides (different display name, same slug) append a suffix.
    engine = get_engine()
    with engine.begin() as conn:
        attempt = slug
        for i in range(1, 50):
            row = conn.execute(
                text("SELECT 1 FROM tree WHERE slug = :s"),
                {"s": attempt},
            ).fetchone()
            if not row:
                break
            attempt = f"{slug}-{i}"
        new = conn.execute(
            text("INSERT INTO tree (name, slug, owner_id) "
                 "VALUES (:n, :s, :o) RETURNING tree_id"),
            {"n": name, "s": attempt, "o": owner_id},
        ).fetchone()
        return str(new[0])


def rename_tree(old: str, new: str) -> int:
    """Rename a tree by string-old / string-new for back-compat with the kiosk.
    Returns 1 on success, 0 if no such tree."""
    old, new = old.strip(), new.strip()
    if not new:
        raise ValueError("New tree name is empty.")
    if old == new:
        return 0
    engine = get_engine()
    with engine.begin() as conn:
        # Collision check
        col = conn.execute(
            text("SELECT count(*) FROM tree WHERE name = :n"),
            {"n": new},
        ).scalar()
        if col:
            raise ValueError(f"A tree named '{new}' already exists.")
        # Update both name and slug
        new_slug = _safe_slug(new)
        attempt = new_slug
        for i in range(1, 50):
            row = conn.execute(
                text("SELECT 1 FROM tree WHERE slug = :s AND name <> :o"),
                {"s": attempt, "o": old},
            ).fetchone()
            if not row:
                break
            attempt = f"{new_slug}-{i}"
        result = conn.execute(
            text("UPDATE tree SET name = :n, slug = :s WHERE name = :o"),
            {"n": new, "s": attempt, "o": old},
        )
        return int(result.rowcount or 0)


def delete_tree(tree_name: str) -> int:
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM tree WHERE name = :n"),
            {"n": tree_name},
        )
        return int(result.rowcount or 0)


# ---------------------------------------------------------------------------
# Species
# ---------------------------------------------------------------------------
def get_or_create_species(ncbi_taxid: int, scientific_name: str,
                          rank: str | None = None) -> str:
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT species_id FROM species WHERE ncbi_taxid = :t"),
            {"t": int(ncbi_taxid)},
        ).fetchone()
        if row:
            return str(row[0])
        new = conn.execute(
            text("INSERT INTO species (ncbi_taxid, canonical_scientific_name, rank) "
                 "VALUES (:t, :n, :r) RETURNING species_id"),
            {"t": int(ncbi_taxid), "n": scientific_name, "r": rank},
        ).fetchone()
        return str(new[0])


def add_species_name(species_id: str, name_text: str,
                     language: str = "ENG",
                     category: str = "common",
                     source: str = "community",
                     is_preferred: bool = False,
                     contributor_id: str | None = None,
                     region_code: str | None = None,
                     script: str | None = None) -> None:
    if not name_text or not name_text.strip():
        return
    name_text = name_text.strip()
    engine = get_engine()
    with engine.begin() as conn:
        # If marking this as preferred, demote any others first so there is
        # only one preferred name per (species, language, category).
        if is_preferred:
            conn.execute(
                text("""
                    UPDATE species_name
                    SET is_preferred = false
                    WHERE species_id = :s
                      AND language_code = :l
                      AND name_category = :c
                      AND lower(name_text) <> lower(:n)
                """),
                {"s": species_id, "l": language, "c": category, "n": name_text},
            )
        # Try the insert with script first; if the column hasn't been
        # migrated yet, fall back to the legacy insert.
        try:
            conn.execute(text("""
                INSERT INTO species_name
                    (species_id, name_text, language_code, name_category,
                     region_code, source, is_preferred, contributed_by, script)
                VALUES (:s, :n, :l, :c, :r, :src, :p, :by, :sc)
                ON CONFLICT (species_id, name_text, language_code, name_category)
                DO UPDATE SET is_preferred = EXCLUDED.is_preferred,
                              region_code  = COALESCE(EXCLUDED.region_code,
                                                       species_name.region_code),
                              script       = COALESCE(EXCLUDED.script,
                                                       species_name.script)
            """), {"s": species_id, "n": name_text, "l": language,
                   "c": category, "r": region_code, "src": source,
                   "p": is_preferred, "by": contributor_id, "sc": script})
        except Exception:
            conn.execute(text("""
                INSERT INTO species_name
                    (species_id, name_text, language_code, name_category,
                     region_code, source, is_preferred, contributed_by)
                VALUES (:s, :n, :l, :c, :r, :src, :p, :by)
                ON CONFLICT (species_id, name_text, language_code, name_category)
                DO UPDATE SET is_preferred = EXCLUDED.is_preferred,
                              region_code  = COALESCE(EXCLUDED.region_code,
                                                       species_name.region_code)
            """), {"s": species_id, "n": name_text, "l": language,
                   "c": category, "r": region_code, "src": source,
                   "p": is_preferred, "by": contributor_id})


# ---------------------------------------------------------------------------
# tree_species (the actual link rows)
# ---------------------------------------------------------------------------
def add_species_to_tree(tree_id: str, species_id: str,
                        note: str | None = None,
                        added_by: str | None = None) -> bool:
    engine = get_engine()
    with engine.begin() as conn:
        # Check existing
        row = conn.execute(
            text("SELECT 1 FROM tree_species "
                 "WHERE tree_id = :t AND species_id = :s"),
            {"t": tree_id, "s": species_id},
        ).fetchone()
        if row:
            return False
        conn.execute(
            text("INSERT INTO tree_species (tree_id, species_id, note, added_by) "
                 "VALUES (:t, :s, :n, :a)"),
            {"t": tree_id, "s": species_id, "n": note, "a": added_by},
        )
        return True


def link_species_to_clades(species_id: str,
                            clade_chain: list[dict]) -> int:
    """Given an ordered chain of clade dicts (root -> species), upsert each
    clade and link species_clade. Sets clade.parent_clade_id to the previous
    surviving clade so the in-table tree reflects ancestry filtered to the
    ranks we store. Returns the number of clades linked. Idempotent."""
    if not clade_chain:
        return 0
    n = 0
    parent_id: str | None = None
    engine = get_engine()
    with engine.begin() as conn:
        for cl in clade_chain:
            taxid_int = int(cl["taxid"])
            existing = conn.execute(
                text("SELECT clade_id FROM clade WHERE ncbi_taxid = :t"),
                {"t": taxid_int},
            ).fetchone()
            if existing:
                clade_id = str(existing[0])
                # Backfill mya/parent if missing
                conn.execute(
                    text("""
                        UPDATE clade
                        SET parent_clade_id = COALESCE(parent_clade_id, :p),
                            divergence_mya  = COALESCE(divergence_mya, :m)
                        WHERE clade_id = :c
                    """),
                    {"p": parent_id, "m": cl.get("mya"), "c": clade_id},
                )
            else:
                row = conn.execute(
                    text("""
                        INSERT INTO clade
                          (ncbi_taxid, name, rank, parent_clade_id,
                           divergence_mya)
                        VALUES (:t, :n, :r, :p, :m)
                        ON CONFLICT (ncbi_taxid) DO NOTHING
                        RETURNING clade_id
                    """),
                    {"t": taxid_int, "n": cl["name"], "r": cl.get("rank"),
                     "p": parent_id, "m": cl.get("mya")},
                ).fetchone()
                if row:
                    clade_id = str(row[0])
                else:
                    # Race: someone else inserted between our SELECT and INSERT.
                    re_row = conn.execute(
                        text("SELECT clade_id FROM clade WHERE ncbi_taxid = :t"),
                        {"t": taxid_int},
                    ).fetchone()
                    clade_id = str(re_row[0])
            # Link species_clade (no-op if already there)
            conn.execute(
                text("""
                    INSERT INTO species_clade (species_id, clade_id)
                    VALUES (:s, :c)
                    ON CONFLICT DO NOTHING
                """),
                {"s": species_id, "c": clade_id},
            )
            parent_id = clade_id
            n += 1
    return n


def _link_clades_for_taxid(species_id: str, ncbi_taxid: int) -> int:
    """Resolve the NCBI lineage for a taxid and link the filtered clade chain
    to one species. Used by insert_request and backfill_clades. Best-effort:
    if NCBI lookup fails, returns 0 without raising."""
    try:
        from src import taxonomy_search as ts
        lin = ts.lineage_clades_for_taxid(int(ncbi_taxid))
    except Exception as exc:
        print(f"  clade lookup failed for taxid {ncbi_taxid}: {exc}")
        return 0
    if not lin or not lin.get("clades"):
        return 0
    return link_species_to_clades(species_id, lin["clades"])


def delete_species(tree_name: str, scientific_name: str) -> int:
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                DELETE FROM tree_species ts
                USING tree t, species s
                WHERE ts.tree_id = t.tree_id
                  AND ts.species_id = s.species_id
                  AND t.name = :tn
                  AND lower(s.canonical_scientific_name) = lower(:sn)
            """),
            {"tn": tree_name, "sn": scientific_name.strip()},
        )
        return int(result.rowcount or 0)


# ---------------------------------------------------------------------------
# The "back-compat insert" path used by the kiosk and the dashboard editor.
# ---------------------------------------------------------------------------
def insert_request(
    tree_name: str,
    scientific_name: str,
    common_name: str | None = None,
    ncbi_taxid: int | None = None,
    domain: str | None = None,        # ignored in v2 (lives in cultural layer)
    story: str | None = None,         # routed into the story table
    submitted_by: str | None = None,
    lineage: dict | None = None,      # ignored in v2 for now (TODO: upsert clade)
    notes: str | None = None,
    contributor_id: str | None = None,  # if supplied, used directly
) -> bool:
    """Add a species to a tree. Same signature as v1 so the kiosk's
    add-to-tree path keeps working without a rewrite. Returns True if a new
    tree_species row was created, False if the species was already in the tree.

    The taxid + scientific name path is required (we can't dedup without
    a taxid). If you don't have one, raise.
    """
    if ncbi_taxid is None:
        raise ValueError(
            "v2 requires an NCBI TaxID for every species. The kiosk's "
            "species search returns one; the manual-name path is no "
            "longer supported.")

    if not contributor_id:
        contributor_id = get_or_create_contributor(submitted_by)
    # owner_display_name still uses the name path; that's fine because
    # ownership is informational.
    tree_id = get_or_create_tree(tree_name, owner_display_name=submitted_by)
    # If we have an explicit contributor_id from auth, also set tree.owner_id
    # to it (only for brand-new trees that have no owner yet, so we don't
    # accidentally retake ownership of someone else's tree).
    if contributor_id:
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE tree SET owner_id = :c "
                "WHERE tree_id = :t AND owner_id IS NULL"
            ), {"c": contributor_id, "t": tree_id})
    species_id = get_or_create_species(int(ncbi_taxid), scientific_name.strip())
    # Populate clade + species_clade. Idempotent: re-adding the same species
    # to a different tree just no-ops on the conflicts.
    _link_clades_for_taxid(species_id, int(ncbi_taxid))

    if common_name:
        add_species_name(species_id, common_name, language="en",
                         category="common", source="community",
                         is_preferred=True, contributor_id=contributor_id)

    is_new = add_species_to_tree(tree_id, species_id,
                                 note=notes,
                                 added_by=contributor_id)
    # Story optional: if supplied, write to story table
    if story:
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO story (species_id, tree_id, body_text,
                                       contributed_by)
                    VALUES (:s, :t, :b, :c)
                """),
                {"s": species_id, "t": tree_id, "b": story,
                 "c": contributor_id},
            )
    return is_new


# ---------------------------------------------------------------------------
# Edits (back-compat for the dashboard editor)
# ---------------------------------------------------------------------------
def update_fields(tree_name: str, scientific_name: str, fields: dict) -> int:
    """Update editable fields on a species in a tree. v1 wrote to columns;
    v2 distributes the changes:
        common_name → upserted into species_name (en, common, preferred=true)
        notes       → updated in tree_species.note
        story       → inserted into story table
        ncbi_taxid  → ignored (species is keyed by taxid; changing it is a
                      delete + re-add)
        kingdom..genus → TODO: upsert clade + species_clade (logged for now)
    Returns the number of underlying writes performed."""
    fields = {k: v for k, v in fields.items() if k in EDITABLE_COLUMNS}
    if not fields:
        return 0

    engine = get_engine()
    n_writes = 0
    with engine.begin() as conn:
        row = conn.execute(
            text("""SELECT s.species_id, t.tree_id
                    FROM tree t, species s, tree_species ts
                    WHERE ts.tree_id = t.tree_id
                      AND ts.species_id = s.species_id
                      AND t.name = :tn
                      AND lower(s.canonical_scientific_name) = lower(:sn)
                    LIMIT 1"""),
            {"tn": tree_name, "sn": scientific_name},
        ).fetchone()
        if not row:
            return 0
        species_id, tree_id = str(row[0]), str(row[1])

        if "common_name" in fields:
            new_name = (fields["common_name"] or "").strip()
            # Always demote any other preferred common name for this species
            # in this language, so there's only ever one preferred at a time.
            conn.execute(
                text("""
                    UPDATE species_name
                    SET is_preferred = false
                    WHERE species_id = :s
                      AND language_code = 'en'
                      AND name_category = 'common'
                      AND lower(name_text) <> lower(:n)
                """),
                {"s": species_id, "n": new_name},
            )
            n_writes += 1
            if new_name:
                # Insert or promote the new preferred name
                conn.execute(
                    text("""
                        INSERT INTO species_name
                            (species_id, name_text, language_code,
                             name_category, source, is_preferred)
                        VALUES (:s, :n, 'en', 'common', 'community', true)
                        ON CONFLICT (species_id, name_text, language_code, name_category)
                        DO UPDATE SET is_preferred = true
                    """),
                    {"s": species_id, "n": new_name},
                )
                n_writes += 1

        if "notes" in fields:
            conn.execute(
                text("UPDATE tree_species SET note = :n "
                     "WHERE tree_id = :t AND species_id = :s"),
                {"n": fields["notes"], "t": tree_id, "s": species_id},
            )
            n_writes += 1

        if "story" in fields and fields["story"]:
            conn.execute(
                text("""
                    INSERT INTO story (species_id, tree_id, body_text)
                    VALUES (:s, :t, :b)
                """),
                {"s": species_id, "t": tree_id, "b": fields["story"]},
            )
            n_writes += 1
        # kingdom..genus / domain: TODO in next phase (clade upsert)
    return n_writes


def update_taxid(*args, **kwargs) -> None:
    """No-op in v2 — species is keyed by ncbi_taxid; you can't change it."""
    return None


# ---------------------------------------------------------------------------
# Reads (back-compat: same DataFrame shape as v1)
# ---------------------------------------------------------------------------
_READ_TREE_SQL = text("""
    SELECT
        t.name                              AS tree_name,
        COALESCE(
            (SELECT sn.name_text FROM species_name sn
                WHERE sn.name_id = ts.display_name_id),
            (SELECT sn.name_text FROM species_name sn
                WHERE sn.species_id = s.species_id
                  AND sn.language_code = 'ENG'
                  AND sn.name_category = 'common'
                  AND sn.is_preferred = true
                ORDER BY sn.contributed_at DESC LIMIT 1)
        )                                   AS common_name,
        s.canonical_scientific_name         AS scientific_name,
        s.ncbi_taxid                        AS ncbi_taxid,
        (CASE
            WHEN s.ncbi_taxid = 9606 THEN 'Human'
            WHEN EXISTS (SELECT 1 FROM species_clade sc JOIN clade c
                            ON c.clade_id = sc.clade_id
                            WHERE sc.species_id = s.species_id
                              AND c.ncbi_taxid = 50557) THEN 'Insect'
            WHEN EXISTS (SELECT 1 FROM species_clade sc JOIN clade c
                            ON c.clade_id = sc.clade_id
                            WHERE sc.species_id = s.species_id
                              AND c.ncbi_taxid = 33208) THEN 'Animal'
            WHEN EXISTS (SELECT 1 FROM species_clade sc JOIN clade c
                            ON c.clade_id = sc.clade_id
                            WHERE sc.species_id = s.species_id
                              AND c.ncbi_taxid = 33090) THEN 'Plant'
            WHEN EXISTS (SELECT 1 FROM species_clade sc JOIN clade c
                            ON c.clade_id = sc.clade_id
                            WHERE sc.species_id = s.species_id
                              AND c.ncbi_taxid = 4751) THEN 'Fungi'
            ELSE 'Other'
        END)                                AS domain,
        (SELECT c.name FROM species_clade sc JOIN clade c
            ON c.clade_id = sc.clade_id
            WHERE sc.species_id = s.species_id AND c.rank = 'kingdom' LIMIT 1)
                                            AS kingdom,
        (SELECT c.name FROM species_clade sc JOIN clade c
            ON c.clade_id = sc.clade_id
            WHERE sc.species_id = s.species_id AND c.rank = 'phylum' LIMIT 1)
                                            AS phylum,
        (SELECT c.name FROM species_clade sc JOIN clade c
            ON c.clade_id = sc.clade_id
            WHERE sc.species_id = s.species_id AND c.rank = 'class' LIMIT 1)
                                            AS class_,
        (SELECT c.name FROM species_clade sc JOIN clade c
            ON c.clade_id = sc.clade_id
            WHERE sc.species_id = s.species_id AND c.rank = 'order' LIMIT 1)
                                            AS order_,
        (SELECT c.name FROM species_clade sc JOIN clade c
            ON c.clade_id = sc.clade_id
            WHERE sc.species_id = s.species_id AND c.rank = 'family' LIMIT 1)
                                            AS family,
        (SELECT c.name FROM species_clade sc JOIN clade c
            ON c.clade_id = sc.clade_id
            WHERE sc.species_id = s.species_id AND c.rank = 'genus' LIMIT 1)
                                            AS genus,
        (SELECT st.body_text FROM story st
            WHERE st.species_id = s.species_id AND st.is_published = true
            ORDER BY st.contributed_at DESC LIMIT 1)
                                            AS story,
        co.display_name                     AS submitted_by,
        ts.note                             AS notes,
        ts.added_at                         AS created_at
    FROM tree_species ts
    JOIN tree t        ON t.tree_id     = ts.tree_id
    JOIN species s     ON s.species_id  = ts.species_id
    LEFT JOIN contributor co ON co.contributor_id = ts.added_by
    WHERE t.name = :tn
    ORDER BY s.canonical_scientific_name
""")


def read_tree(tree_name: str) -> pd.DataFrame:
    """All rows for one tree, in v1-compatible column shape."""
    return pd.read_sql(_READ_TREE_SQL, get_engine(), params={"tn": tree_name})


def list_trees() -> pd.DataFrame:
    """One row per tree with a species count. v2 always resolves taxids so we
    no longer surface a separate resolved_count column."""
    return pd.read_sql(
        text("""
            SELECT
                t.name                                       AS tree_name,
                (SELECT count(*) FROM tree_species ts
                    WHERE ts.tree_id = t.tree_id)            AS species_count,
                t.created_at
            FROM tree t
            ORDER BY t.name
        """),
        get_engine(),
    )


# ---------------------------------------------------------------------------
# Bulk loader (back-compat for etl.py)
# ---------------------------------------------------------------------------
def append_dedup(df: pd.DataFrame) -> int:
    """Append rows from a CSV-shaped DataFrame, skipping species already in
    that tree. Same return semantics as v1: number of new rows added."""
    if df.empty:
        return 0
    init_db()
    inserted = 0
    for _, row in df.iterrows():
        sci = row.get("scientific_name")
        tree_name = row.get("tree_name")
        if not isinstance(sci, str) or not sci.strip():
            continue
        if not isinstance(tree_name, str) or not tree_name.strip():
            continue
        taxid = row.get("ncbi_taxid")
        try:
            taxid_int = int(taxid) if taxid not in (None, "") and pd.notna(taxid) else None
        except (TypeError, ValueError):
            taxid_int = None
        if taxid_int is None:
            # Try to resolve from taxonomy_search at load time
            try:
                from src import taxonomy_search as ts
                hit = ts.resolve_exact(sci.strip())
                if hit:
                    taxid_int = hit["taxid"]
            except Exception:
                pass
        if taxid_int is None:
            print(f"  skip {sci}: no NCBI TaxID resolved")
            continue
        try:
            is_new = insert_request(
                tree_name=tree_name.strip(),
                scientific_name=sci.strip(),
                common_name=(row.get("common_name") or None),
                ncbi_taxid=taxid_int,
                domain=row.get("domain"),
                story=row.get("story"),
                submitted_by=row.get("submitted_by") or "csv-import",
                notes=row.get("notes"),
            )
            if is_new:
                inserted += 1
        except Exception as exc:
            print(f"  err {sci}: {exc}")
    return inserted


def backfill_clades() -> tuple[int, int]:
    """Walk every species and re-run the clade link. For species inserted
    before the v2 clade pipeline landed, this is the one-shot to populate
    their kingdom..genus rows. Returns (species_processed, clades_linked)."""
    engine = get_engine()
    init_db()
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT species_id, ncbi_taxid, canonical_scientific_name "
                 "FROM species ORDER BY canonical_scientific_name")
        ).fetchall()
    total_linked = 0
    for r in rows:
        species_id = str(r[0])
        taxid = int(r[1]) if r[1] is not None else None
        sci = r[2]
        if not taxid:
            print(f"  skip {sci}: no NCBI taxid")
            continue
        n = _link_clades_for_taxid(species_id, taxid)
        print(f"  {sci:40} linked {n} clades")
        total_linked += n
    return len(rows), total_linked




# ---------------------------------------------------------------------------
# Community-layer reads (Library tab)
#
# All return pandas DataFrames suitable for st.dataframe. Joins resolve
# species + tree + contributor display so the dataframes are self-explanatory
# without extra UI work.
# ---------------------------------------------------------------------------
def list_stories() -> pd.DataFrame:
    return pd.read_sql(text("""
        SELECT st.story_id, st.title,
               s.canonical_scientific_name        AS species,
               t.name                              AS tree,
               st.language_code                    AS language,
               st.region_code                      AS region,
               SUBSTRING(st.body_text, 1, 240)     AS body_preview,
               co.display_name                     AS contributor,
               st.contributed_at
        FROM story st
        LEFT JOIN species s     ON s.species_id = st.species_id
        LEFT JOIN tree t        ON t.tree_id    = st.tree_id
        LEFT JOIN contributor co ON co.contributor_id = st.contributed_by
        WHERE st.is_published = true
        ORDER BY st.contributed_at DESC
    """), get_engine())


def list_dishes() -> pd.DataFrame:
    return pd.read_sql(text("""
        SELECT d.dish_id, d.name, d.cuisine, d.origin_region, d.description,
               (SELECT count(DISTINCT ds.species_id) FROM dish_species ds
                  WHERE ds.dish_id = d.dish_id) AS ingredient_count,
               co.display_name AS contributor,
               d.contributed_at
        FROM dish d
        LEFT JOIN contributor co ON co.contributor_id = d.contributed_by
        ORDER BY d.contributed_at DESC
    """), get_engine())


def list_dish_ingredients(dish_id: str | None = None) -> pd.DataFrame:
    base = """
        SELECT d.name AS dish, d.cuisine,
               s.canonical_scientific_name AS species_scientific,
               (SELECT sn.name_text FROM species_name sn
                  WHERE sn.species_id = s.species_id
                    AND sn.language_code = 'ENG'
                    AND sn.name_category = 'common'
                    AND sn.is_preferred = true LIMIT 1) AS species_common,
               ds.role, ds.quantity_note
        FROM dish_species ds
        JOIN dish d    ON d.dish_id    = ds.dish_id
        JOIN species s ON s.species_id = ds.species_id
    """
    if dish_id:
        return pd.read_sql(
            text(base + " WHERE d.dish_id = :d ORDER BY ds.role"),
            get_engine(), params={"d": dish_id})
    return pd.read_sql(
        text(base + " ORDER BY d.name, ds.role"), get_engine())


def list_pantheons() -> pd.DataFrame:
    return pd.read_sql(text("""
        SELECT p.pantheon_id, p.name, p.region, p.tradition_type,
               (SELECT count(*) FROM deity
                  WHERE pantheon_id = p.pantheon_id) AS deities_count,
               (SELECT count(DISTINCT sd.species_id)
                  FROM deity de
                  JOIN species_deity sd ON sd.deity_id = de.deity_id
                  WHERE de.pantheon_id = p.pantheon_id) AS species_count
        FROM pantheon p
        ORDER BY p.name
    """), get_engine())


def list_species_deities() -> pd.DataFrame:
    return pd.read_sql(text("""
        SELECT s.canonical_scientific_name AS species,
               (SELECT sn.name_text FROM species_name sn
                  WHERE sn.species_id = s.species_id
                    AND sn.language_code = 'ENG'
                    AND sn.name_category = 'common'
                    AND sn.is_preferred = true LIMIT 1) AS common_name,
               de.name AS deity, p.name AS pantheon,
               sd.relationship, sd.note
        FROM species_deity sd
        JOIN species s   ON s.species_id   = sd.species_id
        JOIN deity de    ON de.deity_id    = sd.deity_id
        JOIN pantheon p  ON p.pantheon_id  = de.pantheon_id
        ORDER BY s.canonical_scientific_name, p.name, de.name
    """), get_engine())


def list_cultural_connections() -> pd.DataFrame:
    return pd.read_sql(text("""
        SELECT cc.connection_id,
               s.canonical_scientific_name AS species,
               (SELECT sn.name_text FROM species_name sn
                  WHERE sn.species_id = s.species_id
                    AND sn.language_code = 'ENG'
                    AND sn.name_category = 'common'
                    AND sn.is_preferred = true LIMIT 1) AS common_name,
               cc.culture, cc.significance_type, cc.description, cc.source,
               co.display_name AS contributor
        FROM cultural_connection cc
        JOIN species s ON s.species_id = cc.species_id
        LEFT JOIN contributor co ON co.contributor_id = cc.contributed_by
        ORDER BY s.canonical_scientific_name, cc.culture
    """), get_engine())


def list_all_names() -> pd.DataFrame:
    return pd.read_sql(text("""
        SELECT s.canonical_scientific_name AS species,
               sn.name_text,
               sn.language_code   AS language,
               sn.name_category   AS category,
               sn.region_code     AS region,
               sn.is_preferred,
               sn.source,
               co.display_name    AS contributor
        FROM species_name sn
        JOIN species s ON s.species_id = sn.species_id
        LEFT JOIN contributor co ON co.contributor_id = sn.contributed_by
        ORDER BY s.canonical_scientific_name, sn.language_code,
                 sn.is_preferred DESC, sn.name_text
    """), get_engine())


def list_species_for_picker() -> pd.DataFrame:
    """For dropdowns: species_id + canonical + preferred common name."""
    return pd.read_sql(text("""
        SELECT s.species_id, s.canonical_scientific_name,
               (SELECT sn.name_text FROM species_name sn
                  WHERE sn.species_id = s.species_id
                    AND sn.language_code = 'ENG'
                    AND sn.name_category = 'common'
                    AND sn.is_preferred = true LIMIT 1) AS common_name
        FROM species s
        ORDER BY common_name NULLS LAST, s.canonical_scientific_name
    """), get_engine())




def list_species_overview() -> pd.DataFrame:
    """Every canonical species with counts across the community layer.
    Lets the Library tab show how rich each species' kinship layer is."""
    return pd.read_sql(text("""
        SELECT
            s.canonical_scientific_name AS scientific_name,
            (SELECT sn.name_text FROM species_name sn
                WHERE sn.species_id = s.species_id
                  AND sn.language_code = 'ENG'
                  AND sn.name_category = 'common'
                  AND sn.is_preferred = true LIMIT 1) AS common_name,
            s.rank,
            s.ncbi_taxid,
            (CASE
              WHEN s.ncbi_taxid = 9606 THEN 'Human'
              WHEN EXISTS (SELECT 1 FROM species_clade sc JOIN clade c
                  ON c.clade_id = sc.clade_id
                  WHERE sc.species_id = s.species_id
                    AND c.ncbi_taxid = 50557) THEN 'Insect'
              WHEN EXISTS (SELECT 1 FROM species_clade sc JOIN clade c
                  ON c.clade_id = sc.clade_id
                  WHERE sc.species_id = s.species_id
                    AND c.ncbi_taxid = 33208) THEN 'Animal'
              WHEN EXISTS (SELECT 1 FROM species_clade sc JOIN clade c
                  ON c.clade_id = sc.clade_id
                  WHERE sc.species_id = s.species_id
                    AND c.ncbi_taxid = 33090) THEN 'Plant'
              WHEN EXISTS (SELECT 1 FROM species_clade sc JOIN clade c
                  ON c.clade_id = sc.clade_id
                  WHERE sc.species_id = s.species_id
                    AND c.ncbi_taxid = 4751) THEN 'Fungi'
              ELSE 'Other'
            END) AS "group",
            (SELECT count(*) FROM species_name sn
                WHERE sn.species_id = s.species_id) AS names_count,
            (SELECT count(DISTINCT sn.language_code) FROM species_name sn
                WHERE sn.species_id = s.species_id) AS languages_count,
            (SELECT count(*) FROM story st
                WHERE st.species_id = s.species_id) AS stories_count,
            (SELECT count(*) FROM dish_species ds
                WHERE ds.species_id = s.species_id) AS dishes_count,
            (SELECT count(*) FROM species_deity sd
                WHERE sd.species_id = s.species_id) AS deities_count,
            (SELECT count(*) FROM cultural_connection cc
                WHERE cc.species_id = s.species_id) AS connections_count,
            (SELECT count(DISTINCT tree_id) FROM tree_species ts
                WHERE ts.species_id = s.species_id) AS trees_count
        FROM species s
        ORDER BY s.canonical_scientific_name
    """), get_engine())


# ---------------------------------------------------------------------------
# Community-layer writes (Library admin entry forms)
# ---------------------------------------------------------------------------
def add_story(body_text: str,
              species_id: str | None = None,
              tree_id: str | None = None,
              title: str | None = None,
              language: str = "en",
              region: str | None = None,
              contributor_id: str | None = None) -> str:
    if not body_text or not body_text.strip():
        raise ValueError("Story body text is required.")
    if not species_id and not tree_id:
        raise ValueError("Story must be linked to a species or a tree.")
    engine = get_engine()
    with engine.begin() as conn:
        new = conn.execute(
            text("""INSERT INTO story (species_id, tree_id, title, body_text,
                                       language_code, region_code,
                                       contributed_by)
                    VALUES (:s, :t, :ti, :b, :l, :r, :c)
                    RETURNING story_id"""),
            {"s": species_id, "t": tree_id, "ti": title,
             "b": body_text.strip(), "l": language,
             "r": region, "c": contributor_id},
        ).fetchone()
        return str(new[0])


def add_dish(name: str,
             origin_region: str | None = None,
             cuisine: str | None = None,
             description: str | None = None,
             contributor_id: str | None = None) -> str:
    if not name or not name.strip():
        raise ValueError("Dish name is required.")
    engine = get_engine()
    with engine.begin() as conn:
        new = conn.execute(
            text("""INSERT INTO dish (name, origin_region, cuisine,
                                       description, contributed_by)
                    VALUES (:n, :o, :c, :d, :by)
                    RETURNING dish_id"""),
            {"n": name.strip(), "o": origin_region, "c": cuisine,
             "d": description, "by": contributor_id},
        ).fetchone()
        return str(new[0])


def link_dish_species(dish_id: str, species_id: str,
                      role: str = "ingredient",
                      quantity_note: str | None = None) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO dish_species
                       (dish_id, species_id, role, quantity_note)
                    VALUES (:d, :s, :r, :q)
                    ON CONFLICT (dish_id, species_id, role)
                    DO UPDATE SET quantity_note = EXCLUDED.quantity_note"""),
            {"d": dish_id, "s": species_id, "r": role, "q": quantity_note},
        )


def add_pantheon(name: str, region: str | None = None,
                 tradition_type: str = "mythological") -> str:
    if not name or not name.strip():
        raise ValueError("Pantheon name is required.")
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT pantheon_id FROM pantheon WHERE name = :n"),
            {"n": name.strip()},
        ).fetchone()
        if row:
            return str(row[0])
        new = conn.execute(
            text("""INSERT INTO pantheon (name, region, tradition_type)
                    VALUES (:n, :r, :t)
                    RETURNING pantheon_id"""),
            {"n": name.strip(), "r": region, "t": tradition_type},
        ).fetchone()
        return str(new[0])


def add_deity(pantheon_id: str, name: str,
              aliases: list[str] | None = None,
              domain: str | None = None) -> str:
    if not name or not name.strip():
        raise ValueError("Deity name is required.")
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT deity_id FROM deity "
                 "WHERE pantheon_id = :p AND name = :n"),
            {"p": pantheon_id, "n": name.strip()},
        ).fetchone()
        if row:
            return str(row[0])
        new = conn.execute(
            text("""INSERT INTO deity (pantheon_id, name, aliases, domain)
                    VALUES (:p, :n, :a, :d)
                    RETURNING deity_id"""),
            {"p": pantheon_id, "n": name.strip(),
             "a": aliases or [], "d": domain},
        ).fetchone()
        return str(new[0])


def link_species_deity(species_id: str, deity_id: str,
                       relationship: str = "sacred_to",
                       note: str | None = None,
                       contributor_id: str | None = None) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO species_deity
                       (species_id, deity_id, relationship,
                        note, contributed_by)
                    VALUES (:s, :d, :r, :n, :c)
                    ON CONFLICT (species_id, deity_id, relationship)
                    DO UPDATE SET note = EXCLUDED.note"""),
            {"s": species_id, "d": deity_id, "r": relationship,
             "n": note, "c": contributor_id},
        )


def add_cultural_connection(species_id: str, culture: str,
                            significance_type: str | None = None,
                            description: str | None = None,
                            source: str | None = None,
                            contributor_id: str | None = None) -> str:
    if not culture or not culture.strip():
        raise ValueError("Culture is required.")
    engine = get_engine()
    with engine.begin() as conn:
        new = conn.execute(
            text("""INSERT INTO cultural_connection
                       (species_id, culture, significance_type, description,
                        source, contributed_by)
                    VALUES (:s, :c, :t, :d, :src, :by)
                    RETURNING connection_id"""),
            {"s": species_id, "c": culture.strip(),
             "t": significance_type, "d": description,
             "src": source, "by": contributor_id},
        ).fetchone()
        return str(new[0])



if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "init"
    if cmd == "init":
        init_db()
    elif cmd == "trees":
        print(list_trees().to_string(index=False))
    elif cmd == "backfill-clades":
        n_species, n_links = backfill_clades()
        print(f"done. {n_species} species walked, {n_links} clade links written.")
    else:
        print(f"unknown command: {cmd}  "
              "(try: init, trees, backfill-clades)")

# ---------------------------------------------------------------------------
# Phase 2 — per-row contribution helpers (delete + ownership lookup)
#
# Every "delete" helper returns the contributor_id that originally added the
# row (before deleting) so the calling UI can confirm permission via
# auth.can_edit_contribution. None means the row never existed.
# ---------------------------------------------------------------------------
def _delete_and_return_owner(table: str, id_col: str, id_value: str) -> str | None:
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text(f"SELECT contributed_by FROM {table} WHERE {id_col} = :i"),
            {"i": id_value},
        ).fetchone()
        if not row:
            return None
        owner = str(row[0]) if row[0] is not None else None
        conn.execute(
            text(f"DELETE FROM {table} WHERE {id_col} = :i"),
            {"i": id_value},
        )
        return owner


def delete_story(story_id: str) -> str | None:
    return _delete_and_return_owner("story", "story_id", story_id)


def delete_dish(dish_id: str) -> str | None:
    return _delete_and_return_owner("dish", "dish_id", dish_id)


def delete_pantheon(pantheon_id: str) -> int:
    """Pantheons cascade-delete their deities (and the species links via
    deity). No contributed_by column on pantheon itself, so this returns the
    row count and the UI gates by admin-only (deletes affect many people)."""
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM pantheon WHERE pantheon_id = :i"),
            {"i": pantheon_id},
        )
        return int(result.rowcount or 0)


def delete_deity(deity_id: str) -> int:
    """Deities cascade-delete their species links. Admin / editor only."""
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM deity WHERE deity_id = :i"),
            {"i": deity_id},
        )
        return int(result.rowcount or 0)


def delete_species_deity_link(species_id: str, deity_id: str,
                              relationship: str) -> str | None:
    """species_deity has a composite key. Returns the contributor_id of the
    row before deleting, or None if no such link."""
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT contributed_by FROM species_deity "
                 "WHERE species_id = :s AND deity_id = :d "
                 "  AND relationship = :r"),
            {"s": species_id, "d": deity_id, "r": relationship},
        ).fetchone()
        if not row:
            return None
        owner = str(row[0]) if row[0] is not None else None
        conn.execute(
            text("DELETE FROM species_deity "
                 "WHERE species_id = :s AND deity_id = :d "
                 "  AND relationship = :r"),
            {"s": species_id, "d": deity_id, "r": relationship},
        )
        return owner


def delete_cultural_connection(connection_id: str) -> str | None:
    return _delete_and_return_owner(
        "cultural_connection", "connection_id", connection_id)


def delete_species_name(name_id: str) -> str | None:
    return _delete_and_return_owner("species_name", "name_id", name_id)


# ---------------------------------------------------------------------------
# Edit helpers for community datapoints. Each takes the row's primary key
# plus a dict of fields to set; returns the contributor_id of the row before
# editing (so the UI can gate).
# ---------------------------------------------------------------------------
def update_story(story_id: str, fields: dict) -> str | None:
    allowed = {"title", "body_text", "language_code", "region_code"}
    sets, params = [], {"i": story_id}
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k} = :{k}")
            params[k] = v
    if not sets:
        return None
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT contributed_by FROM story WHERE story_id = :i"),
            {"i": story_id},
        ).fetchone()
        if not row:
            return None
        conn.execute(
            text(f"UPDATE story SET {', '.join(sets)} WHERE story_id = :i"),
            params,
        )
        return str(row[0]) if row[0] is not None else None


def update_cultural_connection(connection_id: str, fields: dict) -> str | None:
    allowed = {"culture", "significance_type", "description", "source"}
    sets, params = [], {"i": connection_id}
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k} = :{k}")
            params[k] = v
    if not sets:
        return None
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT contributed_by FROM cultural_connection "
                 "WHERE connection_id = :i"),
            {"i": connection_id},
        ).fetchone()
        if not row:
            return None
        conn.execute(
            text(f"UPDATE cultural_connection SET {', '.join(sets)} "
                 "WHERE connection_id = :i"),
            params,
        )
        return str(row[0]) if row[0] is not None else None


def update_dish(dish_id: str, fields: dict) -> str | None:
    allowed = {"name", "cuisine", "origin_region", "description"}
    sets, params = [], {"i": dish_id}
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k} = :{k}")
            params[k] = v
    if not sets:
        return None
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT contributed_by FROM dish WHERE dish_id = :i"),
            {"i": dish_id},
        ).fetchone()
        if not row:
            return None
        conn.execute(
            text(f"UPDATE dish SET {', '.join(sets)} WHERE dish_id = :i"),
            params,
        )
        return str(row[0]) if row[0] is not None else None


# ---------------------------------------------------------------------------
# Per-user activity (Profile tab)
# ---------------------------------------------------------------------------
def list_user_trees(contributor_id: str) -> pd.DataFrame:
    return pd.read_sql(text("""
        SELECT t.name AS tree_name,
               (SELECT count(*) FROM tree_species ts
                  WHERE ts.tree_id = t.tree_id) AS species_count,
               t.created_at
        FROM tree t
        WHERE t.owner_id = :i
        ORDER BY t.created_at DESC
    """), get_engine(), params={"i": contributor_id})


def list_user_stories(contributor_id: str) -> pd.DataFrame:
    return pd.read_sql(text("""
        SELECT s.story_id, s.title,
               sp.canonical_scientific_name AS species,
               t.name AS tree, s.contributed_at
        FROM story s
        LEFT JOIN species sp ON sp.species_id = s.species_id
        LEFT JOIN tree t    ON t.tree_id    = s.tree_id
        WHERE s.contributed_by = :i
        ORDER BY s.contributed_at DESC
    """), get_engine(), params={"i": contributor_id})


def list_user_dishes(contributor_id: str) -> pd.DataFrame:
    return pd.read_sql(text("""
        SELECT d.dish_id, d.name, d.cuisine, d.contributed_at
        FROM dish d
        WHERE d.contributed_by = :i
        ORDER BY d.contributed_at DESC
    """), get_engine(), params={"i": contributor_id})


def list_user_names(contributor_id: str) -> pd.DataFrame:
    return pd.read_sql(text("""
        SELECT sn.name_id, sn.name_text,
               sn.language_code AS language, sn.name_category AS category,
               s.canonical_scientific_name AS species,
               sn.contributed_at
        FROM species_name sn
        JOIN species s ON s.species_id = sn.species_id
        WHERE sn.contributed_by = :i
        ORDER BY sn.contributed_at DESC
    """), get_engine(), params={"i": contributor_id})


def list_user_cultural(contributor_id: str) -> pd.DataFrame:
    return pd.read_sql(text("""
        SELECT cc.connection_id, cc.culture, cc.significance_type,
               s.canonical_scientific_name AS species,
               cc.contributed_at
        FROM cultural_connection cc
        JOIN species s ON s.species_id = cc.species_id
        WHERE cc.contributed_by = :i
        ORDER BY cc.contributed_at DESC
    """), get_engine(), params={"i": contributor_id})


def user_activity_counts(contributor_id: str) -> dict:
    """Single round-trip summary for the profile header tiles."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT
              (SELECT count(*) FROM tree WHERE owner_id = :i),
              (SELECT count(*) FROM story WHERE contributed_by = :i),
              (SELECT count(*) FROM dish WHERE contributed_by = :i),
              (SELECT count(*) FROM species_name WHERE contributed_by = :i),
              (SELECT count(*) FROM cultural_connection WHERE contributed_by = :i),
              (SELECT count(*) FROM species_deity WHERE contributed_by = :i)
        """), {"i": contributor_id}).fetchone()
    if not row:
        return {"trees": 0, "stories": 0, "dishes": 0, "names": 0,
                "cultural": 0, "deities": 0}
    return {
        "trees": int(row[0] or 0),
        "stories": int(row[1] or 0),
        "dishes": int(row[2] or 0),
        "names": int(row[3] or 0),
        "cultural": int(row[4] or 0),
        "deities": int(row[5] or 0),
    }


# ---------------------------------------------------------------------------
# "Recent contributions by others" — for editors & admins reviewing
# what's been added across the community recently.
# ---------------------------------------------------------------------------
def recent_contributions(limit: int = 50) -> pd.DataFrame:
    """Unified feed of recent additions across stories, dishes, names,
    cultural connections. UNION ALL with a 'kind' discriminator and the
    contributor name pre-joined so the UI is one dataframe."""
    return pd.read_sql(text("""
        SELECT 'story' AS kind, s.story_id::text AS row_id,
               coalesce(s.title, sp.canonical_scientific_name, '(untitled story)') AS title,
               co.display_name AS contributor, co.contributor_id AS contributor_id,
               s.contributed_at
        FROM story s
        LEFT JOIN species sp ON sp.species_id = s.species_id
        LEFT JOIN contributor co ON co.contributor_id = s.contributed_by
        UNION ALL
        SELECT 'dish', d.dish_id::text, d.name,
               co.display_name, co.contributor_id, d.contributed_at
        FROM dish d
        LEFT JOIN contributor co ON co.contributor_id = d.contributed_by
        UNION ALL
        SELECT 'name', sn.name_id::text,
               sn.name_text || ' (' || sn.language_code || ')',
               co.display_name, co.contributor_id, sn.contributed_at
        FROM species_name sn
        LEFT JOIN contributor co ON co.contributor_id = sn.contributed_by
        UNION ALL
        SELECT 'cultural_connection', cc.connection_id::text,
               cc.culture || ' / ' || coalesce(cc.significance_type,'tie'),
               co.display_name, co.contributor_id, cc.contributed_at
        FROM cultural_connection cc
        LEFT JOIN contributor co ON co.contributor_id = cc.contributed_by
        ORDER BY contributed_at DESC NULLS LAST
        LIMIT :lim
    """), get_engine(), params={"lim": limit})


def get_or_create_guest_contributor(display_name: str) -> tuple[str | None, bool]:
    """Like get_or_create_contributor, but only matches rows WITHOUT a
    username (i.e. other guests). Returns (contributor_id, is_registered).
    is_registered=True means the name belongs to a signed-in user and the
    caller must refuse: a guest can't impersonate a registered name."""
    if not display_name:
        return (None, False)
    engine = get_engine()
    with engine.begin() as conn:
        # If a registered (username NOT NULL) row owns this display_name,
        # refuse. The caller will ask the guest to pick another name.
        reg = conn.execute(
            text("SELECT 1 FROM contributor "
                 "WHERE display_name = :n AND username IS NOT NULL LIMIT 1"),
            {"n": display_name},
        ).fetchone()
        if reg:
            return (None, True)
        # Match an existing guest row with this name (so a returning guest
        # gets their old attribution), or create a fresh one.
        row = conn.execute(
            text("SELECT contributor_id FROM contributor "
                 "WHERE display_name = :n AND username IS NULL LIMIT 1"),
            {"n": display_name},
        ).fetchone()
        if row:
            return (str(row[0]), False)
        new = conn.execute(
            text("INSERT INTO contributor (display_name, role) "
                 "VALUES (:n, 'visitor') RETURNING contributor_id"),
            {"n": display_name},
        ).fetchone()
        return (str(new[0]), False)


def get_public_profile(contributor_id: str) -> dict | None:
    """Public-facing profile for any contributor (no password_hash, no email).
    Counts of trees / stories / dishes / names / cultural ties roll up the
    same way the owner's own profile sees them, so visitors can see what a
    contributor has added."""
    if not contributor_id:
        return None
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT contributor_id, display_name, username, role, bio,
                   avatar_url, created_at, last_login_at,
                   (SELECT count(*) FROM tree WHERE owner_id = c.contributor_id),
                   (SELECT count(*) FROM story WHERE contributed_by = c.contributor_id),
                   (SELECT count(*) FROM dish WHERE contributed_by = c.contributor_id),
                   (SELECT count(*) FROM species_name
                      WHERE contributed_by = c.contributor_id),
                   (SELECT count(*) FROM cultural_connection
                      WHERE contributed_by = c.contributor_id),
                   (SELECT count(*) FROM species_deity
                      WHERE contributed_by = c.contributor_id)
            FROM contributor c
            WHERE c.contributor_id = :i
            LIMIT 1
        """), {"i": contributor_id}).fetchone()
    if not row:
        return None
    return {
        "contributor_id": str(row[0]),
        "display_name":   row[1],
        "username":       row[2],
        "role":           row[3],
        "bio":            row[4],
        "avatar_url":     row[5],
        "created_at":     row[6],
        "last_login_at":  row[7],
        "trees":          int(row[8] or 0),
        "stories":        int(row[9] or 0),
        "dishes":         int(row[10] or 0),
        "names":          int(row[11] or 0),
        "cultural":       int(row[12] or 0),
        "deities":        int(row[13] or 0),
    }


# ---------------------------------------------------------------------------
# Forgot-password flow (after db/forgot_password_migration.sql)
# ---------------------------------------------------------------------------
def request_password_reset(username: str, email: str) -> dict | None:
    """If (username, email) matches a contributor row, log the request and
    return that user row so the auth layer can generate + set a new password.
    Returns None when no match (do NOT differentiate to the caller — we
    don't want to leak email enumeration through different UI messages)."""
    if not username or not email:
        return None
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(text(
            f"SELECT {_USER_COLS} FROM contributor "
            "WHERE lower(username) = lower(:u) AND lower(email) = lower(:e) "
            "LIMIT 1"
        ), {"u": username.strip(), "e": email.strip()}).fetchone()
        if not row:
            return None
        user = _row_to_user_dict(row)
        conn.execute(text(
            "INSERT INTO pending_reset (contributor_id) VALUES (:i)"
        ), {"i": user["contributor_id"]})
        return user


def complete_password_reset(contributor_id: str,
                             new_password_hash: str) -> None:
    """Set a new hash and mark must_change_password so the user is prompted
    to pick their own after the temp one works once."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE contributor SET password_hash = :p, "
            "must_change_password = true, last_reset_at = now() "
            "WHERE contributor_id = :i"
        ), {"p": new_password_hash, "i": contributor_id})
        # Mark any open pending_reset rows for this user as completed.
        conn.execute(text(
            "UPDATE pending_reset SET completed_at = now() "
            "WHERE contributor_id = :i AND completed_at IS NULL"
        ), {"i": contributor_id})


def clear_must_change_password(contributor_id: str) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE contributor SET must_change_password = false "
            "WHERE contributor_id = :i"
        ), {"i": contributor_id})


def list_pending_resets() -> pd.DataFrame:
    """Admin view: pending password-reset requests in the last 30 days,
    completed or not."""
    return pd.read_sql(text("""
        SELECT pr.reset_id, pr.requested_at, pr.completed_at,
               c.display_name, c.username, c.email
        FROM pending_reset pr
        JOIN contributor c ON c.contributor_id = pr.contributor_id
        WHERE pr.requested_at > now() - INTERVAL \'30 days\'
        ORDER BY pr.requested_at DESC
    """), get_engine())

# ---------------------------------------------------------------------------
# Edit helpers for the remaining community kinds (Phase 2-bis)
# ---------------------------------------------------------------------------
def update_species_name(name_id: str, fields: dict) -> bool:
    """Patch a multilingual-name row. If is_preferred is being set to True,
    demotes any other preferred name for the same (species, language,
    category) to keep the invariant. Returns True if a row was updated."""
    allowed = {"name_text", "language_code", "name_category",
               "region_code", "is_preferred"}
    sets, params = [], {"i": name_id}
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k} = :{k}")
            params[k] = v
    if not sets:
        return False
    engine = get_engine()
    with engine.begin() as conn:
        cur = conn.execute(text(
            "SELECT species_id, language_code, name_category "
            "FROM species_name WHERE name_id = :i"
        ), {"i": name_id}).fetchone()
        if not cur:
            return False
        # If turning is_preferred on, demote siblings first.
        if fields.get("is_preferred") is True:
            new_lang = fields.get("language_code", cur[1])
            new_cat  = fields.get("name_category", cur[2])
            conn.execute(text(
                "UPDATE species_name SET is_preferred = false "
                "WHERE species_id = :s AND language_code = :l "
                "  AND name_category = :c AND name_id <> :i"
            ), {"s": cur[0], "l": new_lang, "c": new_cat, "i": name_id})
        conn.execute(
            text(f"UPDATE species_name SET {', '.join(sets)} "
                 "WHERE name_id = :i"),
            params,
        )
        return True


def update_pantheon(pantheon_id: str, fields: dict) -> bool:
    allowed = {"name", "region", "tradition_type"}
    sets, params = [], {"i": pantheon_id}
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k} = :{k}")
            params[k] = v
    if not sets:
        return False
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text(f"UPDATE pantheon SET {', '.join(sets)} "
                 "WHERE pantheon_id = :i"),
            params,
        )
        return int(result.rowcount or 0) > 0


def update_deity(deity_id: str, fields: dict) -> bool:
    """Patch a deity row. `aliases` is a comma-separated string in the UI;
    we split it on commas + trim + drop blanks before saving as a Postgres
    TEXT[]."""
    allowed = {"name", "domain", "aliases"}
    sets, params = [], {"i": deity_id}
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == "aliases":
            if isinstance(v, str):
                parts = [s.strip() for s in v.split(",") if s.strip()]
            else:
                parts = list(v) if v else []
            params[k] = parts or None
            sets.append("aliases = :aliases")
        else:
            sets.append(f"{k} = :{k}")
            params[k] = v
    if not sets:
        return False
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text(f"UPDATE deity SET {', '.join(sets)} "
                 "WHERE deity_id = :i"),
            params,
        )
        return int(result.rowcount or 0) > 0


def update_species_deity_note(species_id: str, deity_id: str,
                                relationship: str, note: str | None) -> bool:
    """Just the note. Relationship is part of the composite key — to change
    that, delete + re-add."""
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(text(
            "UPDATE species_deity SET note = :n "
            "WHERE species_id = :s AND deity_id = :d "
            "  AND relationship = :r"
        ), {"n": (note or None), "s": species_id, "d": deity_id,
            "r": relationship})
        return int(result.rowcount or 0) > 0


# ---------------------------------------------------------------------------
# Per-tree display-name picker (after db/tree_species_display_name_migration)
# ---------------------------------------------------------------------------
def list_tree_species_with_names(tree_name: str) -> list[dict]:
    """For each species in this tree, return:
        species_id, scientific_name, current_name_id, current_name_text,
        choices: [(name_id|None, label), ...]
    Single round-trip — pulls every species + every available name for
    those species in one query, then groups in Python. Avoids the N+1
    that the per-tree picker used to run on every dashboard rerun."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT s.species_id::text, s.canonical_scientific_name,
                   ts.display_name_id::text,
                   sn.name_id::text, sn.name_text, sn.language_code,
                   sn.name_category, sn.is_preferred
            FROM tree_species ts
            JOIN tree t    ON t.tree_id    = ts.tree_id
            JOIN species s ON s.species_id = ts.species_id
            LEFT JOIN species_name sn ON sn.species_id = s.species_id
            WHERE t.name = :tn
            ORDER BY s.canonical_scientific_name,
                     sn.is_preferred DESC NULLS LAST,
                     sn.language_code, sn.name_text
        """), {"tn": tree_name}).fetchall()
    # Group rows by species_id, preserving the order they came in.
    from collections import OrderedDict
    species_by_id: OrderedDict[str, dict] = OrderedDict()
    for r in rows:
        sp_id, sci, dn_id, nid, ntext, lang, cat, is_pref = r
        bucket = species_by_id.setdefault(sp_id, {
            "species_id": sp_id,
            "scientific_name": sci,
            "current_name_id": dn_id,
            "name_rows": [],
        })
        if nid is not None:
            bucket["name_rows"].append(
                (nid, ntext, lang, cat, bool(is_pref))
            )

    out: list[dict] = []
    for bucket in species_by_id.values():
        name_rows = bucket["name_rows"]
            # Build choices: None means 'global preferred fallback'.
        global_pref = next(
            (r[1] for r in name_rows
                if r[2] == "en" and r[3] == "common" and r[4]),
            None,
        )
        global_label = (f"(default — {global_pref})"
                         if global_pref else
                         "(default — scientific name)")
        choices = [(None, global_label)]
        for nid, ntext, lang, cat, is_pref in name_rows:
            star = " ★" if is_pref else ""
            choices.append((nid, f"{ntext}  · {lang}/{cat}{star}"))
        dn_id = bucket["current_name_id"]
        current_text = None
        if dn_id:
            current_text = next(
                (r[1] for r in name_rows if r[0] == dn_id), None)
        out.append({
            "species_id": bucket["species_id"],
            "scientific_name": bucket["scientific_name"],
            "current_name_id": dn_id,
            "current_name_text": current_text or global_pref,
            "choices": choices,
        })
    return out


def set_tree_species_display_name(tree_name: str,
                                    species_id: str,
                                    name_id: str | None) -> int:
    """Set (or clear, when name_id is None) the per-tree display-name
    override for one species in one tree."""
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(text("""
            UPDATE tree_species
            SET display_name_id = :n
            FROM tree t
            WHERE tree_species.tree_id = t.tree_id
              AND t.name = :tn
              AND tree_species.species_id = :s
        """), {"n": name_id, "tn": tree_name, "s": species_id})
        return int(result.rowcount or 0)


def get_user_must_change_password(contributor_id: str) -> bool:
    """Defensive read of the must_change_password flag. Returns False when
    the column doesn't exist yet (forgot_password_migration not applied).
    Used by auth.must_change_password() so the rest of the user-row read
    path stays migration-agnostic."""
    if not contributor_id:
        return False
    engine = get_engine()
    try:
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT coalesce(must_change_password, false) "
                "FROM contributor WHERE contributor_id = :i LIMIT 1"
            ), {"i": contributor_id}).fetchone()
        return bool(row and row[0])
    except Exception:
        # Column missing or any other read error: don't block the user.
        return False


# ---------------------------------------------------------------------------
# Follow / favorite (after db/follow_favorite_migration.sql)
# ---------------------------------------------------------------------------
def follow_user(follower_id: str, following_id: str) -> bool:
    """follower_id starts following following_id. Idempotent + self-follow
    blocked. Returns True when a new follow row was created."""
    if not follower_id or not following_id or follower_id == following_id:
        return False
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(text(
            "INSERT INTO user_follow (follower_id, following_id) "
            "VALUES (:f, :g) ON CONFLICT DO NOTHING"
        ), {"f": follower_id, "g": following_id})
        return int(result.rowcount or 0) > 0


def unfollow_user(follower_id: str, following_id: str) -> int:
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(text(
            "DELETE FROM user_follow "
            "WHERE follower_id = :f AND following_id = :g"
        ), {"f": follower_id, "g": following_id})
        return int(result.rowcount or 0)


def is_following(follower_id: str, following_id: str) -> bool:
    if not follower_id or not following_id:
        return False
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT 1 FROM user_follow "
            "WHERE follower_id = :f AND following_id = :g LIMIT 1"
        ), {"f": follower_id, "g": following_id}).fetchone()
    return bool(row)


def list_following(contributor_id: str) -> pd.DataFrame:
    """People the contributor follows, with their counts so the Profile
    'Following' tab is a quick directory."""
    return pd.read_sql(text("""
        SELECT c.contributor_id::text AS contributor_id,
               c.display_name, c.username, c.avatar_url, c.bio, c.role,
               (SELECT count(*) FROM tree t WHERE t.owner_id = c.contributor_id)
                  AS trees,
               (SELECT count(*) FROM story s
                  WHERE s.contributed_by = c.contributor_id) AS stories,
               uf.followed_at
        FROM user_follow uf
        JOIN contributor c ON c.contributor_id = uf.following_id
        WHERE uf.follower_id = :i
        ORDER BY uf.followed_at DESC
    """), get_engine(), params={"i": contributor_id})


def list_followers(contributor_id: str) -> pd.DataFrame:
    return pd.read_sql(text("""
        SELECT c.contributor_id::text AS contributor_id,
               c.display_name, c.username, c.avatar_url, c.role,
               uf.followed_at
        FROM user_follow uf
        JOIN contributor c ON c.contributor_id = uf.follower_id
        WHERE uf.following_id = :i
        ORDER BY uf.followed_at DESC
    """), get_engine(), params={"i": contributor_id})


def favorite_tree(contributor_id: str, tree_id: str) -> bool:
    if not contributor_id or not tree_id:
        return False
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(text(
            "INSERT INTO tree_favorite (contributor_id, tree_id) "
            "VALUES (:c, :t) ON CONFLICT DO NOTHING"
        ), {"c": contributor_id, "t": tree_id})
        return int(result.rowcount or 0) > 0


def unfavorite_tree(contributor_id: str, tree_id: str) -> int:
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(text(
            "DELETE FROM tree_favorite "
            "WHERE contributor_id = :c AND tree_id = :t"
        ), {"c": contributor_id, "t": tree_id})
        return int(result.rowcount or 0)


def is_tree_favorited(contributor_id: str, tree_id: str) -> bool:
    if not contributor_id or not tree_id:
        return False
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT 1 FROM tree_favorite "
            "WHERE contributor_id = :c AND tree_id = :t LIMIT 1"
        ), {"c": contributor_id, "t": tree_id}).fetchone()
    return bool(row)


def list_favorite_trees(contributor_id: str) -> pd.DataFrame:
    return pd.read_sql(text("""
        SELECT t.tree_id::text, t.name AS tree_name,
               (SELECT count(*) FROM tree_species ts
                  WHERE ts.tree_id = t.tree_id) AS species_count,
               co.display_name AS owner,
               tf.favorited_at
        FROM tree_favorite tf
        JOIN tree t ON t.tree_id = tf.tree_id
        LEFT JOIN contributor co ON co.contributor_id = t.owner_id
        WHERE tf.contributor_id = :i
        ORDER BY tf.favorited_at DESC
    """), get_engine(), params={"i": contributor_id})


def follow_counts(contributor_id: str) -> dict:
    if not contributor_id:
        return {"followers": 0, "following": 0, "favorites": 0}
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT
              (SELECT count(*) FROM user_follow WHERE following_id = :i),
              (SELECT count(*) FROM user_follow WHERE follower_id = :i),
              (SELECT count(*) FROM tree_favorite WHERE contributor_id = :i)
        """), {"i": contributor_id}).fetchone()
    return {
        "followers": int(row[0] or 0),
        "following": int(row[1] or 0),
        "favorites": int(row[2] or 0),
    }


# ---------------------------------------------------------------------------
# Server-side session tokens (remember-me)
# After db/auth_session_migration.sql is applied.
# ---------------------------------------------------------------------------
def create_auth_session(contributor_id: str,
                         user_agent: str | None = None) -> str | None:
    """Create a new server-side session and return its UUID. The caller
    stores this UUID in a browser cookie. Returns None on DB error."""
    if not contributor_id:
        return None
    engine = get_engine()
    try:
        with engine.begin() as conn:
            row = conn.execute(text(
                "INSERT INTO auth_session (contributor_id, user_agent) "
                "VALUES (:c, :ua) RETURNING session_id"
            ), {"c": contributor_id, "ua": (user_agent or "")[:255]}
            ).fetchone()
            return str(row[0]) if row else None
    except Exception as exc:
        print(f"create_auth_session failed: {exc}")
        return None


def lookup_auth_session(session_id: str) -> str | None:
    """Resolve a session_id from a cookie into the contributor_id it
    represents. Returns None when the session is missing, expired, or the
    table doesn't exist yet (migration not applied)."""
    if not session_id:
        return None
    engine = get_engine()
    try:
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT contributor_id FROM auth_session "
                "WHERE session_id = :s AND expires_at > now() LIMIT 1"
            ), {"s": session_id}).fetchone()
        return str(row[0]) if row else None
    except Exception:
        return None


def touch_auth_session(session_id: str) -> None:
    """Update last_seen_at so we can prune truly idle sessions later."""
    if not session_id:
        return
    engine = get_engine()
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE auth_session SET last_seen_at = now() "
                "WHERE session_id = :s"
            ), {"s": session_id})
    except Exception:
        pass


def delete_auth_session(session_id: str) -> None:
    if not session_id:
        return
    engine = get_engine()
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "DELETE FROM auth_session WHERE session_id = :s"
            ), {"s": session_id})
    except Exception:
        pass


def cleanup_expired_sessions() -> int:
    """Best-effort housekeeping. Returns number of rows deleted."""
    engine = get_engine()
    try:
        with engine.begin() as conn:
            result = conn.execute(text(
                "DELETE FROM auth_session WHERE expires_at <= now()"
            ))
            return int(result.rowcount or 0)
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Clade dating (admin/editor contributable LCA mya)
# ---------------------------------------------------------------------------
def list_clades_for_dating() -> pd.DataFrame:
    """Every clade currently linked to at least one species, with its
    current divergence_mya. Editors/admins use this to fill in ages on
    the undated clades that show up as teal dots on the tree."""
    return pd.read_sql(text("""
        SELECT c.clade_id::text AS clade_id,
               c.name           AS clade_name,
               c.rank,
               c.divergence_mya AS mya,
               c.ncbi_taxid,
               (SELECT count(*) FROM species_clade sc
                  WHERE sc.clade_id = c.clade_id) AS species_count
        FROM clade c
        WHERE EXISTS (SELECT 1 FROM species_clade sc
                       WHERE sc.clade_id = c.clade_id)
        ORDER BY (c.divergence_mya IS NULL) DESC,
                 c.divergence_mya ASC NULLS LAST,
                 c.name
    """), get_engine())


def get_clade_id_by_name(clade_name: str) -> str | None:
    """Return clade_id for a given clade.name, or None. Case-sensitive
    on stored name; caller should pass the meta['name'] value."""
    if not clade_name:
        return None
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT clade_id::text FROM clade WHERE name = :n"),
            {"n": clade_name},
        ).fetchone()
    return row[0] if row else None


def set_clade_divergence_mya(clade_id: str,
                              mya: float | None) -> int:
    """Set (or clear, when mya is None) the divergence_mya field on one
    clade. Returns row count (0 if not found)."""
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(text(
            "UPDATE clade SET divergence_mya = :m WHERE clade_id = :i"
        ), {"m": mya, "i": clade_id})
        return int(result.rowcount or 0)

