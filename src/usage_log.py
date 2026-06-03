"""
Approximate energy + usage metrics for the pipeline.

Every meaningful build action appends an event to outputs/usage_log.json.
get_totals() rolls them up. The numbers are rough estimates, not certified
measurements, so the dashboard frames them as "approximate" and pairs the
total with an invitation to offset by stewarding the watershed of the species
the visitor chose.

Energy estimates come from a small table at the top of this file. They are
intentionally conservative for compute-light tasks (rendering a tree on a
laptop) and a little more generous for tasks that pull data over the network
(audio downloads, AI calls) or run a remote model.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

LOG_PATH = config.OUTPUT_DIR / "usage_log.json"

# Approximate Wh per event. Source: rule-of-thumb for laptop compute + small
# network call. Numbers chosen to be a useful order-of-magnitude rather than
# precise. Adjust as you learn your own gallery's footprint.
ENERGY_WH = {
    "tree_build": 6.0,        # NCBI lookup + ete3 topology + write files
    "render_tree": 1.5,        # toytree + matplotlib draw
    "sonify_chord": 0.8,
    "build_chorus": 8.0,       # fetches species recordings if not cached
    "build_sound_tree": 4.5,   # spectrograms for ~10 species
    "build_photo_tree": 5.5,   # fetches species photos if not cached
    "build_meditation": 3.0,
    "ai_blurb_remote": 4.0,    # remote model call
    "ai_blurb_template": 0.1,  # local string only
    "fetch_species_profile": 0.4,
    "fetch_species_audio": 1.2,
}

# Approximate grams of CO2 per Wh, based on a global-average grid (~475 g/kWh).
# Adjust this for greener grids if you want a less conservative readout.
CO2_G_PER_WH = 0.475


def _load() -> list[dict]:
    if LOG_PATH.exists():
        try:
            return json.loads(LOG_PATH.read_text())
        except Exception:
            return []
    return []


def log_event(event_type: str, tree_name: str | None = None,
              note: str | None = None) -> None:
    """Append one event. Silent on failure (logging is best-effort)."""
    try:
        events = _load()
        events.append({
            "ts": int(time.time()),
            "type": event_type,
            "tree": tree_name,
            "note": note,
            "wh": ENERGY_WH.get(event_type, 0.5),
        })
        LOG_PATH.write_text(json.dumps(events, indent=2))
    except Exception:
        pass


def get_totals() -> dict:
    events = _load()
    total_wh = sum(e.get("wh", 0) for e in events)
    by_type = {}
    by_tree = {}
    for e in events:
        by_type[e["type"]] = by_type.get(e["type"], 0) + e.get("wh", 0)
        if e.get("tree"):
            by_tree[e["tree"]] = by_tree.get(e["tree"], 0) + e.get("wh", 0)
    return {
        "events": len(events),
        "total_wh": round(total_wh, 1),
        "total_co2_g": round(total_wh * CO2_G_PER_WH, 1),
        "by_type": {k: round(v, 1) for k, v in by_type.items()},
        "by_tree": {k: round(v, 1) for k, v in by_tree.items()},
        "first_event": events[0]["ts"] if events else None,
        "last_event": events[-1]["ts"] if events else None,
    }


def invitation(tree_name: str | None = None) -> str:
    """Short invitation to offset by stewarding the watershed."""
    if tree_name:
        return (
            f"This tree was made with care and a small amount of electricity. "
            f"The kin you chose for {tree_name} live in real water, real soil, "
            f"real wind. The strongest way to offset what this app cost is to "
            f"learn the watershed they share with you and give one afternoon "
            f"a season to the people already keeping it.")
    return (
        "Every build here ran on a small amount of electricity. The strongest "
        "way to offset what these tools cost is to learn the watershed of the "
        "species you chose and give one afternoon a season to keeping it.")





# Relatable benchmarks. Chosen for a gallery audience that may not own a car
# or know how to compare watt-hours. An 8 W LED bulb consumes about
# 0.133 Wh per minute, so 1 Wh equals roughly 7.5 LED-minutes. The car
# benchmark assumes a small petrol car at highway cruise.
LED_W = 8.0          # standard household LED
CAR_W_AT_CRUISE = 33_000.0  # ~33 kW at 100 km/h cruise


def wh_to_lightbulb_minutes(wh: float) -> float:
    return wh * 60.0 / LED_W


def wh_to_car_seconds(wh: float) -> float:
    return wh * 3600.0 / CAR_W_AT_CRUISE


def relatable(wh: float) -> str:
    """Return a short, human readable comparison string."""
    if wh <= 0:
        return "no measurable cost"
    led_min = wh_to_lightbulb_minutes(wh)
    if led_min < 1:
        return f"about an LED bulb on for {led_min * 60:.0f} seconds"
    if led_min < 60:
        return f"about an LED bulb on for {led_min:.0f} minutes"
    if led_min < 24 * 60:
        return f"about an LED bulb on for {led_min / 60:.1f} hours"
    return f"about an LED bulb on for {led_min / (60 * 24):.1f} days"


def last_event_summary() -> dict | None:
    events = _load()
    if not events:
        return None
    e = events[-1]
    wh = e.get("wh", 0)
    return {
        "type": e["type"],
        "tree": e.get("tree"),
        "wh": wh,
        "relatable": relatable(wh),
    }


def tree_total(tree_name: str) -> float:
    events = _load()
    return round(sum(e.get("wh", 0) for e in events if e.get("tree") == tree_name), 1)


if __name__ == "__main__":
    print(json.dumps(get_totals(), indent=2))
    print("\n" + invitation())
