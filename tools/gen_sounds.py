"""Synthesize the panda's sound cues as small WAV files (stdlib only).

    python tools/gen_sounds.py                # writes bao/characters/panda/sounds/
    python tools/gen_sounds.py --play done    # also plays one (macOS afplay)

Soft marimba/bell-like tones: a few decaying partials per note, short attack,
no clipping. Updates the "sounds" section of the character's manifest.json.
"""

from __future__ import annotations

import argparse
import json
import math
import struct
import subprocess
import wave
from pathlib import Path

RATE = 44100
OUT = Path(__file__).resolve().parent.parent / "bao" / "characters" / "panda"

# Note = (frequency Hz, start s, duration s, gain)
Note = tuple[float, float, float, float]

C5, D5, E5, G5, A5, C6, E6, G6 = 523.25, 587.33, 659.25, 783.99, 880.0, 1046.5, 1318.5, 1568.0

CUES: dict[str, dict] = {
    # rising two-note "hi!"
    "hello": {"notes": [(C5, 0.0, 0.35, 0.8), (G5, 0.11, 0.5, 0.9)], "decay": 7},
    # gentle descending "ding-dong": I'm waiting for you
    "waiting": {"notes": [(G5, 0.0, 0.5, 0.8), (E5, 0.22, 0.7, 0.8)], "decay": 5},
    # attention: two bright repeated pings, a bit louder
    "alert": {
        "notes": [
            (A5, 0.0, 0.25, 1.0),
            (E6, 0.0, 0.25, 0.35),
            (A5, 0.16, 0.4, 1.0),
            (E6, 0.16, 0.4, 0.35),
        ],
        "decay": 9,
    },
    # happy arpeggio + sparkle
    "done": {
        "notes": [
            (C5, 0.0, 0.4, 0.7),
            (E5, 0.08, 0.4, 0.7),
            (G5, 0.16, 0.45, 0.75),
            (C6, 0.24, 0.8, 0.9),
            (G6, 0.30, 0.6, 0.25),
        ],
        "decay": 5.5,
    },
    # descending goodbye
    "bye": {
        "notes": [(G5, 0.0, 0.35, 0.8), (D5, 0.12, 0.35, 0.7), (C5, 0.24, 0.6, 0.7)],
        "decay": 6,
    },
}

# Partials (multiple of f, relative gain, extra decay) — gives a soft mallet timbre.
PARTIALS = [(1.0, 1.0, 1.0), (2.0, 0.28, 1.8), (3.0, 0.08, 2.6), (4.01, 0.05, 3.5)]


def synth(notes: list[Note], decay: float, peak: float = 0.55) -> list[float]:
    total = max(start + dur for _, start, dur, _ in notes) + 0.05
    buf = [0.0] * int(total * RATE)
    attack = 0.006
    for freq, start, dur, gain in notes:
        s0 = int(start * RATE)
        n = int(dur * RATE)
        for i in range(n):
            t = i / RATE
            env = min(1.0, t / attack) * math.exp(-decay * t)
            tail = min(1.0, (n - i) / (0.03 * RATE))  # fade out the end of each note
            v = 0.0
            for mult, g, extra in PARTIALS:
                v += (
                    g * math.exp(-decay * (extra - 1) * t) * math.sin(2 * math.pi * freq * mult * t)
                )
            buf[s0 + i] += gain * env * tail * v
    m = max(abs(x) for x in buf) or 1.0
    return [x / m * peak for x in buf]


def write_wav(path: Path, samples: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, x)) * 32767)) for x in samples))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--play", metavar="CUE", help="play one cue after generating (macOS)")
    args = ap.parse_args()

    sounds = {}
    for name, spec in CUES.items():
        path = args.out / "sounds" / f"{name}.wav"
        write_wav(path, synth(spec["notes"], spec["decay"]))
        sounds[name] = f"sounds/{name}.wav"
        print(f"wrote {path.relative_to(args.out)} ({path.stat().st_size // 1024} KB)")

    manifest = args.out / "manifest.json"
    if manifest.exists():
        data = json.loads(manifest.read_text())
        data["sounds"] = sounds
        manifest.write_text(json.dumps(data, indent=2) + "\n")
        print(f"updated sounds in {manifest.name}")

    if args.play:
        subprocess.run(["afplay", str(args.out / "sounds" / f"{args.play}.wav")], check=False)


if __name__ == "__main__":
    main()
