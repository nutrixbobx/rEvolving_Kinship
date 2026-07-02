"""
Full-page loading screen for the one-time NCBI taxonomy fetch.

Shown on first visit (or after a cold container start) when the local
taxa.sqlite is missing. Kicks off a background thread that runs
setup_ncbi.ensure_taxonomy_from_url, then reruns every ~5 seconds so
the rotating fun fact stays fresh and the file check picks up when
taxa.sqlite lands.

Public entry: `render_loading_gate_if_needed()`. Call this near the
top of app/station.py, after theme.inject_css() and before the auth
gate. If the NCBI file is ready, the function returns False and the
app continues normally.

Failure modes handled visibly (not silently):
  - NCBI_TAXA_URL not set: prompt admin to set it, offer fallback
    to ete3 full build, allow bypass.
  - Download error: print the exception on the loading card.
  - File landing but < 100MB: show current size so the wait feels
    like it's making progress.
"""

from __future__ import annotations

import os
import random
import threading
import time

import streamlit as st

from src import setup_ncbi


# Rotating tips. Kept short + fun. No em-dashes, no writing-in-threes,
# no AI-buzzwordy language. Written to feel like a museum wall placard
# rather than a chatbot.
FUN_FACTS: list[str] = [
    "The dawn redwood was known only from fossils until 1944, when a "
    "Chinese forester found one alive in Sichuan.",
    "Octopus ancestors and human ancestors last shared a common form "
    "around 600 million years ago.",
    "Every banana you have ever eaten is a clone of the same plant, "
    "propagated by root cuttings for centuries.",
    "The lichen on a rock is two lives braided together: a fungus and "
    "an algae, one shape, one name.",
    "A pod of orcas off the Pacific Northwest calls in a dialect no "
    "other pod on earth uses.",
    "Whale songs pass through open ocean like radio, sometimes "
    "carrying more than 10,000 kilometers.",
    "The mycelium under a healthy forest is often larger than any "
    "living animal on the surface.",
    "Bristlecone pines in California are older than most nation-states.",
    "The color of a flamingo is on loan from the shrimp it eats.",
    "A single strawberry is not a fruit at all. It is a fleshy stem "
    "wearing the actual fruits as tiny seeds on its skin.",
    "The scientific name of the coyote, Canis latrans, means barking "
    "dog.",
    "Sequoias regenerate through fire. Their cones need heat to open.",
    "The oldest known living tree, a Great Basin bristlecone, was a "
    "seedling around the time the pyramids of Giza went up.",
    "Corals are colonies, not individuals. What we call a reef is a "
    "city.",
    "Rivers braid, meander, oxbow, and cut across time. No river is "
    "the shape it was a century ago.",
    "The word taxonomy comes from the Greek taxis (order) and nomos "
    "(law). Linnaeus wrote the first modern one.",
    "A newt can regrow a whole leg. A human liver can regrow itself. "
    "Regeneration is older than us.",
    "Barn owls hunt in the dark by ear, mapping mice in stereo.",
    "The passenger pigeon once flew in flocks so large they darkened "
    "the sky for hours. The last one died in 1914.",
    "The kingdom of fungi is closer to animals than to plants on the "
    "tree of life.",
    "Turtles have carried the same body plan for over 200 million years.",
    "The Amazon river is fed by hundreds of tributaries, some starting "
    "as glaciers in the Andes.",
    "A honeybee hive keeps itself at 35C year-round, warming by "
    "shivering and cooling by fanning.",
    "The mitochondria in your cells were once free-living bacteria.",
    "The tallest known tree, Hyperion, is a coast redwood over 115 "
    "meters tall.",
    "Sharks have been swimming the oceans since before there were "
    "trees on land.",
    "A slime mold can solve mazes by remembering where its arms have "
    "already been.",
    "The word plankton comes from a Greek word meaning wanderer.",
    "Dolphins name each other. Every pod member has a signature "
    "whistle used only for them.",
    "Ants have been farming aphids and fungi for tens of millions of "
    "years before humans farmed anything.",
]

# Roughly 5 seconds per tip (was 3s, now ~40% slower).
ROTATION_SECONDS = 5.0


def random_tip() -> str:
    """A random fun fact from the pool. Used anywhere in the app for
    a quick 'while you wait' popup."""
    return random.choice(FUN_FACTS)


import contextlib as _contextlib


@_contextlib.contextmanager
def spinner_with_tip(message: str):
    """Same as `st.spinner(message)` but also fires a `st.toast` with
    a random fun fact so users have something to read during any long
    operation, not just the first-visit NCBI load."""
    try:
        st.toast(random_tip(), icon=":material/water_drop:")
    except Exception:
        pass
    with st.spinner(message):
        yield


def _current_status() -> dict:
    """Read + return the shared status dict for the download."""
    st.session_state.setdefault("_ncbi_status", {
        "phase": "idle",   # idle, downloading, done, error, no_url
        "message": "",
        "started_at": None,
    })
    return st.session_state["_ncbi_status"]


def _kick_off_download() -> None:
    """Fire the NCBI download on a background thread once per session.
    Writes progress into session_state so the loading card can show
    real status instead of a spinning silence."""
    status = _current_status()
    if status["phase"] in ("downloading", "done"):
        return
    if not os.environ.get("NCBI_TAXA_URL"):
        status["phase"] = "no_url"
        status["message"] = (
            "NCBI_TAXA_URL is not set. Ask an admin to configure it in "
            "Streamlit secrets, or use the fallback build below.")
        return
    status["phase"] = "downloading"
    status["started_at"] = time.time()

    def _run(status_ref):
        try:
            ok = setup_ncbi.ensure_taxonomy_from_url()
            status_ref["phase"] = "done" if ok else "error"
            if not ok:
                status_ref["message"] = (
                    "Download returned no data. Check that NCBI_TAXA_URL "
                    "points at a valid taxa.sqlite(.gz).")
        except Exception as exc:
            status_ref["phase"] = "error"
            status_ref["message"] = f"{type(exc).__name__}: {exc}"
            print(f"NCBI auto-fetch failed: {exc}", flush=True)

    t = threading.Thread(target=_run, args=(status,), daemon=True)
    t.start()


def _run_ete3_build() -> None:
    """Fallback: full ete3 rebuild from NCBI FTP (~5 minutes). Blocks
    the UI while running, since it's an explicit admin choice."""
    from ete3 import NCBITaxa
    NCBITaxa()


def render_loading_gate_if_needed() -> bool:
    """If NCBI is not ready, take over the screen with a loading page,
    kick off the fetch, and return True. Returns False when NCBI is
    already ready."""
    if setup_ncbi.is_ready():
        return False

    _kick_off_download()
    status = _current_status()

    # File-size progress: shows the user real numbers instead of a
    # frozen "waiting" state during the ~30 second download.
    from pathlib import Path
    taxa_path = Path(setup_ncbi._default_path())
    size_mb = 0.0
    if taxa_path.exists():
        size_mb = taxa_path.stat().st_size / 1_000_000.0

    # Elapsed since we kicked the thread.
    elapsed = 0
    if status.get("started_at"):
        elapsed = int(time.time() - status["started_at"])

    # Rotating tip. Seeded so it stays stable within a single rerun,
    # but rolls to the next value every ROTATION_SECONDS.
    seed = int(time.time() // ROTATION_SECONDS)
    tip = random.Random(seed).choice(FUN_FACTS)

    # Compose the status banner based on phase.
    phase = status.get("phase", "idle")
    if phase == "no_url":
        banner = (
            "<b>NCBI_TAXA_URL is not configured.</b> Ask an admin to "
            "set it in Streamlit secrets so first-load is fast. "
            "You can also do a full rebuild below (~5 minutes).")
    elif phase == "error":
        banner = (
            f"<b>Download failed.</b> {status.get('message','')} "
            "You can retry, or use the fallback rebuild below.")
    elif phase == "downloading":
        banner = (
            f"Downloading taxa.sqlite. "
            f"{size_mb:.0f} MB on disk so far. "
            f"Elapsed: {elapsed}s.")
    else:
        banner = "Preparing the taxonomy fetch..."

    st.markdown(
        """
<div style="
    max-width:720px; margin:6vh auto 0 auto;
    padding:36px 40px; text-align:center;
    background:rgba(0,0,0,0.22); border-radius:14px;
    border:1px solid var(--kn-rule);
">
  <div style="font-size:12px; letter-spacing:0.18em;
              text-transform:uppercase; color:var(--kn-muted);">
    Setting up your first visit
  </div>
  <h1 style="margin:12px 0 4px 0; font-family:Georgia, serif;
             color:var(--kn-ink); font-size:38px;">
    {r}Evolving Kinship
  </h1>
  <div style="color:var(--kn-muted); font-size:14px; margin-bottom:8px;">
    Downloading the NCBI taxonomy that every tree is built on. This
    happens once, then never again on this server.
  </div>
  <div style="color:var(--kn-ink); font-size:13px; margin-bottom:22px;
              padding:8px 14px; background:rgba(0,0,0,0.28);
              border-radius:6px; display:inline-block;">
    __BANNER__
  </div>
  <div style="
      background:var(--kn-bg-alt); border-radius:10px;
      padding:20px 22px; text-align:left;
      color:var(--kn-ink); font-size:15px; line-height:1.55;
      border-left:4px solid var(--kn-accent);">
    <div style="font-size:11px; letter-spacing:0.12em;
                text-transform:uppercase; color:var(--kn-accent);
                margin-bottom:8px;">
      Something to hold you while the river fills
    </div>
    __TIP__
  </div>
  <div style="margin-top:22px; color:var(--kn-muted); font-size:12px;">
    Card refreshes on its own every few seconds.
  </div>
</div>
        """.replace("__BANNER__", banner).replace("__TIP__", tip),
        unsafe_allow_html=True,
    )

    # Escape hatches, once we've been stuck long enough OR errored out.
    is_stuck = (phase in ("no_url", "error")
                or (phase == "downloading" and elapsed > 90))
    if is_stuck:
        st.markdown("<br>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            if st.button("Retry download", use_container_width=True,
                          key="ncbi_retry"):
                st.session_state["_ncbi_status"] = {
                    "phase": "idle", "message": "", "started_at": None}
                _kick_off_download()
                st.rerun()
        with c2:
            if st.button("Full rebuild from NCBI (~5 min)",
                          use_container_width=True,
                          key="ncbi_full_rebuild"):
                with st.spinner("Building from NCBI FTP. Do not close "
                                  "the tab."):
                    try:
                        _run_ete3_build()
                        st.success("Built. Reloading.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Rebuild failed: {exc}")
        with c3:
            if st.button("Skip and continue (admin)",
                          use_container_width=True,
                          key="ncbi_skip",
                          help="Enters the app without taxa.sqlite. "
                                "Species search + tree building will "
                                "be broken until it's provisioned."):
                st.session_state["_ncbi_skip_gate"] = True
                st.rerun()

    if st.session_state.get("_ncbi_skip_gate"):
        return False

    # Slow poll: sleep, then rerun. The 5s cadence doubles as the tip
    # rotation interval, so the fact rolls to the next one on each poll.
    time.sleep(ROTATION_SECONDS)
    st.rerun()
    return True
