"""
Audio chorus: blend each tree's species recordings into one stereo WAV.

For every species in a tree that has a recording (found via species_audio),
take a six-second window of the loudest part, normalize it, pan it across
the stereo field by its position in the tree, and sum all voices into one
chord-like wash. The result is saved next to the chord and the tree files.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
from src import usage_log  # noqa: E402

SR = 22050
SECONDS = 6.0


def _load_loudest_window(path: Path, seconds: float = SECONDS) -> np.ndarray:
    """Decode the file to mono and return the loudest seconds-long window."""
    import librosa
    from src.species_audio import ensure_wav
    y, _ = librosa.load(str(ensure_wav(path)), sr=SR, mono=True, duration=20.0)
    win = int(SR * seconds)
    if len(y) <= win:
        return np.pad(y, (0, max(0, win - len(y))))
    step = SR  # slide one second at a time
    span = len(y) - win
    if span < step:
        return y[:win]
    rms = [float(np.sqrt(np.mean(y[i:i+win] ** 2)))
           for i in range(0, span, step)]
    if not rms:
        return y[:win]
    start = int(np.argmax(rms)) * step
    return y[start:start + win]


def _stereo(mono: np.ndarray, pan: float) -> np.ndarray:
    """Equal-power pan: pan = -1 hard left, +1 hard right."""
    a = (pan + 1) * np.pi / 4
    return np.stack([mono * np.cos(a), mono * np.sin(a)], axis=1)


def build_chorus(tree_name: str, out_dir: Path | None = None) -> dict | None:
    """Build the per-tree chorus WAV. Uses the tree's leaf metadata (NCBI
    canonical names) so synonyms resolve cleanly."""
    import json, soundfile as sf
    from src import species_audio

    out_dir = out_dir or config.OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = tree_name.strip().replace(" ", "_").lower()

    meta_path = config.OUTPUT_DIR / f"{stem}_nodes.json"
    if not meta_path.exists():
        print(f"build the tree first: {stem}_named_tree.nwk")
        return None
    meta = json.loads(meta_path.read_text())
    tips = [(name, info) for name, info in meta.items() if info.get("is_leaf")]

    voices_data = []
    for name, info in tips:
        sci = info.get("scientific_name") or name.replace("_", " ")
        common = info.get("common_name")
        try:
            rec = species_audio.find_recording(sci, common)
        except Exception as exc:
            print(f"  err {sci}: {exc}")
            rec = None
        if rec:
            print(f"  {sci:30} -> {rec.get('source','?')}")
            voices_data.append((sci, common, rec))
        else:
            print(f"  {sci:30} -> no audio")

    if not voices_data:
        print("no recordings found")
        return None

    length = int(SR * SECONDS)
    mix = np.zeros((length, 2), dtype=np.float32)
    used = []
    for i, (sci, common, rec) in enumerate(voices_data):
        try:
            y = _load_loudest_window(rec["path"])
        except Exception as exc:
            print(f"  decode failed for {sci}: {exc!r}")
            continue
        peak = float(np.max(np.abs(y)) or 1.0)
        y = y / peak
        pan = -1 + 2 * (i / max(1, len(voices_data) - 1))
        mix += _stereo(y * 0.7, pan)
        used.append({"common_name": common, "scientific_name": sci,
                     "attribution": rec.get("attribution"),
                     "source": rec.get("source"),
                     "file": rec["path"].name})
    peak = float(np.max(np.abs(mix)) or 1.0)
    mix = (mix / peak) * 0.9
    out_path = out_dir / f"{stem}_chorus.wav"
    sf.write(str(out_path), mix.astype(np.float32), SR)
    print(f"wrote {out_path.name} with {len(used)} voices")
    return {"path": out_path, "voices": used}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('usage: python -m src.audio_blend "Tree Name"')
        raise SystemExit(1)
    build_chorus(sys.argv[1])
