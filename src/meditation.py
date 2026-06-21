"""
Meditation tracks.

Two simple layers per tree:

  * The ecosystem chord (microtonal sine drone from sonify.py), regenerated at
    the exact target length so there is no loop seam.
  * The animal chorus (the per-tree species blend from audio_blend.py), looped
    with short crossfades when the source is shorter than the target.

The two layers are summed, given a long meditation-friendly fade in and out,
normalized, and written to outputs/<stem>_meditation_<seconds>s.wav.

Three durations are exposed: 60, 120, and 300 seconds.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

SR = 44100
DURATIONS = (60, 120, 300)


def _ages_for(tree_name: str) -> dict:
    stem = tree_name.strip().replace(" ", "_").lower()
    meta_path = config.OUTPUT_DIR / f"{stem}_nodes.json"
    if not meta_path.exists():
        return {}
    meta = json.loads(meta_path.read_text())
    return {k: v["mya"] for k, v in meta.items()
            if not v.get("is_leaf") and v.get("mya") is not None}


def _drone_at(tree_name: str, seconds: int) -> np.ndarray | None:
    """Render the chord at exactly `seconds` long. Returns mono float32 array."""
    from src import sonify
    ages = _ages_for(tree_name)
    if not ages:
        return None
    voices = sonify.chord_voices(ages)
    if not voices:
        return None
    t = np.linspace(0, seconds, int(SR * seconds), endpoint=False)
    chord = np.zeros_like(t)
    for v in voices:
        chord += np.sin(2 * np.pi * v["hz"] * t)
    peak = float(np.max(np.abs(chord)) or 1.0)
    return (chord / peak).astype(np.float32)


def _chorus_stereo(tree_name: str) -> np.ndarray | None:
    """Load the chorus WAV as (samples, 2) float32 at SR. Returns None if missing."""
    import soundfile as sf
    stem = tree_name.strip().replace(" ", "_").lower()
    chorus_path = config.OUTPUT_DIR / f"{stem}_chorus.wav"
    if not chorus_path.exists():
        return None
    y, sr = sf.read(str(chorus_path), dtype="float32", always_2d=True)
    if sr != SR:
        # simple polyphase resample
        from scipy.signal import resample_poly
        from math import gcd
        g = gcd(sr, SR)
        y = resample_poly(y, SR // g, sr // g, axis=0).astype(np.float32)
    if y.shape[1] == 1:
        y = np.repeat(y, 2, axis=1)
    return y


def _loop_xfade(audio: np.ndarray, target_n: int,
                fade_seconds: float = 0.6) -> np.ndarray:
    """Tile `audio` ((n,channels) float32) with crossfades to reach target_n."""
    n, ch = audio.shape
    if n >= target_n:
        return audio[:target_n]
    fade_n = min(int(fade_seconds * SR), n // 2)
    out = np.zeros((target_n + n, ch), dtype=np.float32)
    fade_in = np.linspace(0, 1, fade_n)[:, None].astype(np.float32)
    fade_out = (1.0 - fade_in).astype(np.float32)
    pos = 0
    first = True
    while pos < target_n:
        seg = audio.astype(np.float32, copy=True)
        if not first and fade_n > 0:
            seg[:fade_n] *= fade_in
            out[pos:pos + fade_n] *= fade_out
        out[pos:pos + n] += seg
        pos += (n - fade_n) if fade_n else n
        first = False
    return out[:target_n]




def _extract_snippets(audio_path, n: int = 2, seconds: float = 4.5) -> list:
    """Return up to n non-overlapping high-energy snippets from a source file."""
    import librosa
    y, _ = librosa.load(str(audio_path), sr=SR, mono=True, duration=60.0)
    win = int(seconds * SR)
    if len(y) < win:
        return [np.pad(y, (0, win - len(y))).astype(np.float32)]
    step = SR // 2
    rms = np.array([float(np.sqrt(np.mean(y[i:i + win] ** 2)))
                    for i in range(0, len(y) - win, step)])
    order = np.argsort(rms)[::-1] * step
    chosen = []
    for s in order:
        if all(abs(int(s) - c) >= win for c in chosen):
            chosen.append(int(s))
            if len(chosen) >= n:
                break
    return [y[c:c + win].astype(np.float32) for c in chosen]


def _stereo_pan(mono: np.ndarray, pan: float) -> np.ndarray:
    a = (pan + 1) * np.pi / 4
    return np.stack([mono * np.cos(a), mono * np.sin(a)], axis=1)


def _shape_clip(stereo: np.ndarray, fade_seconds: float = 0.4) -> np.ndarray:
    n = len(stereo)
    fade = min(int(fade_seconds * SR), n // 4)
    env = np.ones(n, dtype=np.float32)
    env[:fade] = np.linspace(0, 1, fade)
    env[-fade:] = np.linspace(1, 0, fade)
    return stereo * env[:, None]


def _sparse_chorus(tree_name: str, target_n: int, seed: int,
                   events_per_min_per_species: float = 1.5):
    """Scatter species snippets across the track in stereo with random times,
    pans, and gains. Returns (stereo array (target_n, 2), n_events_placed)."""
    from src import species_audio
    rng = np.random.default_rng(seed)
    stem = tree_name.strip().replace(" ", "_").lower()
    meta = json.loads((config.OUTPUT_DIR / f"{stem}_nodes.json").read_text())
    out = np.zeros((target_n, 2), dtype=np.float32)
    n_events = 0
    minutes = target_n / (SR * 60)
    per_species = max(2, int(round(events_per_min_per_species * minutes)))

    for tip_name, info in meta.items():
        if not info.get("is_leaf"):
            continue
        sci = info.get("scientific_name") or tip_name.replace("_", " ")
        common = info.get("common_name")
        try:
            rec = species_audio.find_recording(sci, common)
        except Exception:
            rec = None
        if not rec:
            continue
        wav = species_audio.ensure_wav(rec["path"])
        snippets = _extract_snippets(wav, n=2, seconds=4.5)
        if not snippets:
            continue
        for i in range(per_species):
            clip = snippets[i % len(snippets)]
            pan = float(rng.uniform(-0.85, 0.85))
            gain = float(rng.uniform(0.45, 0.8))
            shaped = _shape_clip(_stereo_pan(clip * gain, pan))
            max_start = target_n - len(shaped)
            if max_start <= 0:
                continue
            start = int(rng.integers(0, max_start))
            out[start:start + len(shaped)] += shaped
            n_events += 1
    return out, n_events


def _apply_fade(track: np.ndarray, fade_seconds: float = 4.0) -> np.ndarray:
    n = len(track)
    fade = min(int(fade_seconds * SR), n // 4)
    env = np.ones(n, dtype=np.float32)
    env[:fade] = np.linspace(0, 1, fade)
    env[-fade:] = np.linspace(1, 0, fade)
    return track * env[:, None]


def build_meditation(tree_name: str, seconds: int = 60,
                     out_dir: Path | None = None) -> dict | None:
    """Build one meditation track for one tree at a given duration."""
    import soundfile as sf

    out_dir = out_dir or config.OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    target_n = int(SR * seconds)

    # Drone (chord) — synthesized at exact length, mono -> stereo, half volume
    drone = _drone_at(tree_name, seconds)
    if drone is None:
        print(f"no dated clades to make a drone for {tree_name}")
        return None
    drone_st = np.stack([drone, drone], axis=1) * 0.30

    # Chorus — sparse scatter so the meditation does not feel like a 6s loop.
    # Seed by (tree, length) so the same selection plays back reproducibly.
    seed = (abs(hash(tree_name)) ^ (seconds * 1000003)) & 0xFFFFFFFF
    scatter, n_events = _sparse_chorus(tree_name, target_n, seed)
    if n_events > 0:
        track = drone_st + scatter * 0.85
        used_chorus = True
        print(f"  scattered {n_events} voice events across {seconds}s")
    else:
        track = drone_st
        used_chorus = False

    track = _apply_fade(track, fade_seconds=4.0)
    peak = float(np.max(np.abs(track)) or 1.0)
    track = (track / peak) * 0.95

    stem = tree_name.strip().replace(" ", "_").lower()
    out_path = out_dir / f"{stem}_meditation_{seconds}s.wav"
    sf.write(str(out_path), track.astype(np.float32), SR, subtype="PCM_16")
    print(f"wrote {out_path.name} ({seconds}s, chorus={'yes' if used_chorus else 'no'})")
    return {"path": out_path, "seconds": seconds, "has_chorus": used_chorus}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('usage: python -m src.meditation "Tree Name" [seconds]')
        raise SystemExit(1)
    sec = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    build_meditation(sys.argv[1], sec)
