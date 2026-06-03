"""
Sonification.

Each dated clade becomes one sustained tone, and the chord is the sum of those
tones. No scale snapping, no key. The pitch comes straight from the divergence
age, so the chord is true to the deep-time distances between species.

How it is built, in four steps:
  1. Take the log of the clade's age in millions of years.
  2. Linearly place that log value on a 5-octave window, deepest age at the
     bottom, most recent at the top.
  3. That position, measured in cents above C2, is the exact frequency in Hz.
  4. Sum a pure sine wave at each clade's frequency. That is the chord.

The .wav holds the exact pitches by additive sine synthesis. The .mid stores
the same pitches as MIDI notes plus a per-voice pitch bend, so any DAW that
honors pitch bend plays the chord microtonally rather than snapping to keys.
"""

from __future__ import annotations

import math
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
from src import usage_log  # noqa: E402

# Fixed time-pitch frame so the same clade always sounds at the same Hz, across
# trees. These bounds bracket the curated chronology and typical TimeTree dates.
MYA_MIN = 10           # most recent we ever expect (high notes)
MYA_MAX = 2000         # deepest we ever expect (low notes)
REFERENCE_MIDI = config.MIDI_PITCH_LOW
CENTS_RANGE = (config.MIDI_PITCH_HIGH - config.MIDI_PITCH_LOW) * 100
REFERENCE_HZ = 440.0 * 2 ** ((REFERENCE_MIDI - 69) / 12)   # MIDI 36 -> ~65.41 Hz

SAMPLE_RATE = 44100


def mya_to_cents(mya: float) -> float:
    """Log-time -> cents above the reference. Deepest age = 0, most recent = max."""
    lmya = math.log10(max(float(mya), 1.0))
    lmin = math.log10(MYA_MIN)
    lmax = math.log10(MYA_MAX)
    frac = (lmax - lmya) / (lmax - lmin)
    frac = max(0.0, min(1.0, frac))
    return frac * CENTS_RANGE


def cents_to_freq(cents: float) -> float:
    """Exact frequency in Hz for a value in cents above the reference pitch."""
    return REFERENCE_HZ * (2 ** (cents / 1200))


def chord_voices(ages: dict[str, float]) -> list[dict]:
    """One voice per clade, with the exact pitch and a MIDI breakdown.

    Returns dicts with: name, mya, cents, hz, midi (nearest semitone),
    bend_cents (the offset that the MIDI pitch bend will carry).
    """
    voices = []
    for name, mya in sorted(ages.items(), key=lambda kv: -float(kv[1])):
        c = mya_to_cents(mya)
        midi = REFERENCE_MIDI + round(c / 100)
        bend_cents = c - (midi - REFERENCE_MIDI) * 100
        voices.append({
            "name": name,
            "mya": float(mya),
            "cents": c,
            "hz": cents_to_freq(c),
            "midi": int(midi),
            "bend_cents": bend_cents,
        })
    return voices


def write_wav(voices: list[dict], out_path: Path, seconds: float = 8.0) -> Path:
    """Sum a pure sine at each voice's exact Hz. Fade in and out."""
    t = np.linspace(0, seconds, int(SAMPLE_RATE * seconds), endpoint=False)
    chord = np.zeros_like(t)
    for v in voices:
        chord += np.sin(2 * np.pi * v["hz"] * t)
    fade = int(SAMPLE_RATE * 0.4)
    env = np.ones_like(t)
    env[:fade] = np.linspace(0, 1, fade)
    env[-fade:] = np.linspace(1, 0, fade)
    chord *= env
    peak = float(np.max(np.abs(chord)) or 1.0)
    pcm = ((chord / peak) * 0.9 * 32767).astype(np.int16)
    with wave.open(str(out_path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())
    return out_path


def write_midi(voices: list[dict], out_path: Path) -> Path:
    """One channel per voice with pitch bend, so each note plays at its exact
    cents. Default pitch-bend range is 2 semitones; our bends are always under
    50 cents (we round to the nearest semitone for the note number).
    """
    from midiutil import MIDIFile
    m = MIDIFile(numTracks=1, deinterleave=False)
    m.addTempo(0, 0, config.MIDI_TEMPO_BPM)
    beats = config.MIDI_CHORD_DURATION_BEATS
    for ch, v in enumerate(voices[:16]):    # MIDI has 16 channels
        # Set the pitch bend range to 2 semitones (RPN 0,0 -> data 2 / 0).
        m.addControllerEvent(0, ch, 0, 101, 0)
        m.addControllerEvent(0, ch, 0, 100, 0)
        m.addControllerEvent(0, ch, 0, 6, 2)
        m.addControllerEvent(0, ch, 0, 38, 0)
        # Pitch bend value: ±8191 spans ±200 cents at a 2-semitone range.
        bend = int(round(v["bend_cents"] / 200 * 8192))
        m.addPitchWheelEvent(0, ch, 0, bend)
        m.addNote(0, ch, v["midi"], 0, beats, config.MIDI_VELOCITY)
    with open(out_path, "wb") as f:
        m.writeFile(f)
    return out_path


def sonify_tree(ages: dict, stem: str) -> dict:
    """Write a .mid and a .wav of the chord, and print the mapping table so
    the path from mya to Hz is visible.
    """
    out_dir = config.OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    voices = chord_voices({k: v for k, v in ages.items() if v is not None})
    if not voices:
        print("no dated clades to sonify")
        return {"voices": [], "midi": None, "wav": None}

    print(f"{'clade':<16} {'mya':>6}  {'cents':>7}  {'Hz':>8}  {'MIDI':>4}  bend")
    for v in voices:
        print(f"  {v['name']:<14} {v['mya']:>5.0f}   "
              f"{v['cents']:6.1f}   {v['hz']:7.2f}   "
              f"{v['midi']:>3}    {v['bend_cents']:+6.1f} cents")

    mid = write_midi(voices, out_dir / f"{stem}_chord.mid")
    wav = write_wav(voices, out_dir / f"{stem}_chord.wav")
    usage_log.log_event("sonify_chord", stem)
    print(f"wrote {mid.name} and {wav.name}")
    return {"voices": voices, "midi": mid, "wav": wav}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print('usage: python -m src.sonify "<stem>" mya1 mya2 ...')
        raise SystemExit(1)
    stem = sys.argv[1]
    ages = {f"v{i+1}": float(x) for i, x in enumerate(sys.argv[2:])}
    sonify_tree(ages, stem)
