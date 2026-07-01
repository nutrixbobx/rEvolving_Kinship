"""
Full-page loading screen for the one-time NCBI taxonomy fetch.

Shown on first visit (or after a cold container start) when the local
taxa.sqlite is missing. Kicks off a background thread that runs
setup_ncbi.ensure_taxonomy_from_url, then polls once a second and
reruns Streamlit when the file lands. While waiting, a rotating fun
fact keeps the screen alive (like a video game loading tip).

Public entry: `render_loading_gate_if_needed()`. Call this near the
top of app/station.py, after theme.inject_css() and before the auth
gate. If the NCBI file is ready, the function returns False and the
app continues normally.
"""

from __future__ import annotations

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


def _kick_off_download() -> None:
    """Fire the NCBI download on a background thread once per session.
    Uses session_state as a lock so a rerun does not spawn duplicates."""
    if st.session_state.get("_ncbi_thread_started"):
        return
    st.session_state["_ncbi_thread_started"] = True

    def _run():
        try:
            setup_ncbi.ensure_taxonomy_from_url()
        except Exception as exc:
            print(f"NCBI auto-fetch failed: {exc}", flush=True)

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def render_loading_gate_if_needed() -> bool:
    """If NCBI is not ready, take over the screen with a loading page,
    kick off the fetch, and return True (caller should stop rendering
    the rest of the app). Returns False when NCBI is already ready."""
    if setup_ncbi.is_ready():
        return False

    _kick_off_download()

    # Pick a fresh tip on each rerun so the wait feels alive. Seeded
    # so the same rerun consistently shows the same tip (no flicker
    # between first render and after the auto-rerun below).
    seed = int(time.time() // 4)  # rotates every 4 seconds
    rng = random.Random(seed)
    tip = rng.choice(FUN_FACTS)

    # Full-screen card. Matches the theme's palette but bigger and
    # more centered than a normal Streamlit block.
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
  <div style="color:var(--kn-muted); font-size:14px; margin-bottom:22px;">
    Downloading the NCBI taxonomy that every tree is built on. Around
    thirty seconds on a good connection. This happens once, then never
    again on this server.
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
    Waiting for taxa.sqlite. This card will refresh itself.
  </div>
</div>
        """.replace("__TIP__", tip),
        unsafe_allow_html=True,
    )

    # Poll: sleep briefly, then rerun so the fun fact rotates AND we
    # notice when taxa.sqlite lands. Streamlit's cache_resource for
    # setup_ncbi.is_ready would cache-freeze the answer, so we skip
    # caching there.
    time.sleep(3.0)
    st.rerun()
    return True
