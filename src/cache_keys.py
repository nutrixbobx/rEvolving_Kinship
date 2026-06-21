"""
Cache TTLs and cross-module invalidation, in one place.

Why centralize:

  - Before this module, scattered @st.cache_data(ttl=N) calls used a mix
    of 30/60/90/300 with no consistent meaning. Read this file once and
    you know how stale any cache can be.
  - Library + Profile both had their own _invalidate_all_caches helpers.
    A write in one module had to know to also clear the other module's
    caches, which is brittle. invalidate_after_write() does both.

Naming convention:

  TTL_FAST   = 30s   moderation feeds, fresh-ish reads
  TTL_NORMAL = 90s   library Browse, profile activity
  TTL_SLOW   = 300s  dashboard reads (tree species, names; only change on
                     explicit writes which call invalidate_after_write())
"""

TTL_FAST = 30
TTL_NORMAL = 90
TTL_SLOW = 300


def invalidate_after_write() -> None:
    """Clear every cached read across the app modules so the next render
    reflects the change. Cheap (just calls .clear() on cache_data
    decorators). Call from any write path; safe to call before the
    target modules have been imported."""
    for module_name, helper_name in (
        ("src.library", "_invalidate_all_caches"),
        ("src.profile", "_invalidate_profile_caches"),
    ):
        try:
            mod = __import__(module_name, fromlist=[helper_name])
            getattr(mod, helper_name)()
        except Exception:
            pass


def invalidate_dashboard_only() -> None:
    """Lighter version for kiosk-style writes that don't touch library
    counts. Clears only the dashboard tree picker + read_tree."""
    try:
        from app import station as _s
        _s._invalidate_dashboard_caches()
    except Exception:
        pass
