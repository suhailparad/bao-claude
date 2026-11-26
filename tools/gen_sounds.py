"""Synthesize a character's sound cues as small WAV files (stdlib only).

    python tools/gen_sounds.py                    # panda chimes -> bao/characters/panda/sounds/
    python tools/gen_sounds.py --character cat    # cat meows    -> bao/characters/cat/sounds/
    python tools/gen_sounds.py --character penguin  # penguin peeps -> characters/penguin/sounds/
    python tools/gen_sounds.py --character hummingbird  # chirps + wing hum
    python tools/gen_sounds.py --character owl    # hoots + a screech
    python tools/gen_sounds.py --play done        # also plays one (macOS afplay)

Panda: soft marimba/bell-like tones (a few decaying partials per note).
Cat: synthesized meows, chirps and a purr (a harmonic voice whose pitch glides while
formants move from "ee" to "oo"). Penguin: the same voice, pitched up and buzzier: quick
peeps, raspy squawks and a little bray. Hummingbird: quick high chirps (pure tones that
sweep in pitch), twittering trills and a soft wing hum. Owl: soft, breathy hoots that
glide in pitch, and a raspy "kee-kee" screech for alerts. Updates the "sounds" section of
the character's manifest.json.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import struct
import subprocess
import wave
from pathlib import Path

RATE = 44100
CHARACTERS = Path(__file__).resolve().parent.parent / "bao" / "characters"

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


# ---------------------------------------------------------------- cat voice

# Vowel formants: (centre Hz, gain, bandwidth Hz). A meow is roughly "ee-ah-oo".
VOWELS: dict[str, tuple[tuple[float, float, float], ...]] = {
    "i": ((320, 1.0, 160), (2300, 0.55, 300), (3000, 0.3, 400)),
    "e": ((450, 1.0, 170), (2000, 0.5, 300), (2700, 0.3, 400)),
    "a": ((780, 1.0, 220), (1250, 0.7, 250), (2600, 0.25, 400)),
    "o": ((520, 1.0, 180), (880, 0.6, 200), (2500, 0.15, 400)),
    "u": ((360, 1.0, 160), (720, 0.4, 200), (2400, 0.1, 400)),
}

# A call: {"start", "dur", "pitch": [(frac, Hz)], "vowel": [(frac, v)], "gain",
#          optional "trill": (rate Hz, depth)} ; a purr: {"purr": True, "start", "dur", "gain"}
CAT_CUES: dict[str, dict] = {
    # "mrrp?" chirp then a short rising "mew": hi!
    "hello": {
        "calls": [
            {
                "start": 0.0,
                "dur": 0.24,
                "gain": 0.8,
                "trill": (30, 0.65),
                "pitch": [(0, 430), (0.7, 720), (1, 820)],
                "vowel": [(0, "u"), (0.5, "a"), (1, "e")],
            },
            {
                "start": 0.27,
                "dur": 0.34,
                "gain": 1.0,
                "pitch": [(0, 760), (0.35, 980), (1, 900)],
                "vowel": [(0, "i"), (0.45, "a"), (1, "e")],
            },
        ],
    },
    # one soft, questioning meow: still there?
    "waiting": {
        "calls": [
            {
                "start": 0.0,
                "dur": 0.62,
                "gain": 1.0,
                "pitch": [(0, 640), (0.35, 830), (0.8, 640), (1, 700)],
                "vowel": [(0, "e"), (0.3, "a"), (0.75, "o"), (1, "u")],
            },
        ],
        "peak": 0.45,
    },
    # two short, high, insistent meows: I need you!
    "alert": {
        "calls": [
            {
                "start": 0.0,
                "dur": 0.26,
                "gain": 1.0,
                "pitch": [(0, 880), (0.3, 1150), (1, 920)],
                "vowel": [(0, "i"), (0.4, "a"), (1, "o")],
            },
            {
                "start": 0.31,
                "dur": 0.3,
                "gain": 1.0,
                "pitch": [(0, 920), (0.3, 1220), (1, 960)],
                "vowel": [(0, "i"), (0.4, "a"), (1, "o")],
            },
        ],
        "peak": 0.6,
    },
    # happy rolling trill "brrrp" into a bright meow: done!
    "done": {
        "calls": [
            {
                "start": 0.0,
                "dur": 0.34,
                "gain": 0.75,
                "trill": (27, 0.7),
                "pitch": [(0, 480), (1, 780)],
                "vowel": [(0, "u"), (1, "a")],
            },
            {
                "start": 0.36,
                "dur": 0.46,
                "gain": 1.0,
                "pitch": [(0, 820), (0.35, 1080), (1, 880)],
                "vowel": [(0, "i"), (0.4, "a"), (1, "e")],
            },
        ],
    },
    # long, sleepy, falling meow and a purr: bye
    "bye": {
        "calls": [
            {
                "start": 0.0,
                "dur": 0.8,
                "gain": 1.0,
                "pitch": [(0, 720), (0.25, 790), (1, 420)],
                "vowel": [(0, "e"), (0.25, "a"), (0.7, "o"), (1, "u")],
            },
            {"purr": True, "start": 0.7, "dur": 0.95, "gain": 0.5},
        ],
        "peak": 0.5,
    },
}


def _peep(start: float, dur: float, lo: float, hi: float, gain: float = 1.0, **extra) -> dict:
    """A short nasal penguin peep that jumps up from ``lo`` to ``hi``."""
    return {
        "start": start,
        "dur": dur,
        "gain": gain,
        "pitch": [(0, lo), (0.3, hi), (1, hi * 0.94)],
        "vowel": [(0, "e"), (0.4, "a"), (1, "e")],
        **extra,
    }


BUZZ = (58, 0.45)  # fast amplitude ripple: the raspy edge of a penguin call

PENGUIN_CUES: dict[str, dict] = {
    # "pip-pip!": two quick rising peeps
    "hello": {"calls": [_peep(0.0, 0.11, 900, 1250), _peep(0.15, 0.16, 1000, 1450)]},
    # one soft peep that lifts at the end, like a question
    "waiting": {
        "calls": [
            {
                "start": 0.0,
                "dur": 0.36,
                "gain": 1.0,
                "pitch": [(0, 880), (0.6, 840), (1, 1180)],
                "vowel": [(0, "e"), (0.6, "a"), (1, "i")],
            }
        ],
        "peak": 0.42,
    },
    # three raspy, insistent squawks
    "alert": {
        "calls": [_peep(i * 0.17, 0.13, 760, 1050, trill=BUZZ) for i in range(3)],
        "peak": 0.6,
    },
    # happy bray: honks that climb, then a long buzzy "aaah"
    "done": {
        "calls": [
            _peep(0.0, 0.1, 620, 760, 0.8, trill=BUZZ),
            _peep(0.13, 0.1, 700, 860, 0.85, trill=BUZZ),
            _peep(0.26, 0.1, 780, 960, 0.9, trill=BUZZ),
            {
                "start": 0.4,
                "dur": 0.55,
                "gain": 1.0,
                "trill": (46, 0.35),
                "pitch": [(0, 900), (0.25, 1120), (1, 860)],
                "vowel": [(0, "e"), (0.3, "a"), (1, "o")],
            },
        ],
    },
    # two drowsy, falling peeps
    "bye": {
        "calls": [
            {
                "start": 0.0,
                "dur": 0.3,
                "gain": 1.0,
                "pitch": [(0, 1100), (1, 820)],
                "vowel": [(0, "e"), (1, "a")],
            },
            {
                "start": 0.36,
                "dur": 0.5,
                "gain": 0.85,
                "pitch": [(0, 900), (1, 560)],
                "vowel": [(0, "a"), (0.6, "o"), (1, "u")],
            },
        ],
        "peak": 0.5,
    },
}


def _lerp_points(points: list, x: float):
    """Piecewise-linear lookup in [(frac, value)], values being floats or float tuples."""
    if x <= points[0][0]:
        return points[0][1]
    for (x0, v0), (x1, v1) in zip(points, points[1:], strict=False):
        if x <= x1:
            k = (x - x0) / (x1 - x0) if x1 > x0 else 1.0
            if isinstance(v0, tuple):
                return tuple(
                    tuple(a + (b - a) * k for a, b in zip(f0, f1, strict=True))
                    for f0, f1 in zip(v0, v1, strict=True)
                )
            return v0 + (v1 - v0) * k
    return points[-1][1]


def _envelope(i: int, n: int, attack: float = 0.025, release: float = 0.35) -> float:
    a = min(1.0, i / (attack * RATE))
    x = i / n
    r = 1.0 if x < 1 - release else 0.5 * (1 + math.cos(math.pi * (x - 1 + release) / release))
    return a * r


def synth_meow(call: dict, rng: random.Random) -> list[float]:
    n = int(call["dur"] * RATE)
    out = [0.0] * n
    pitch = call["pitch"]
    vowel = [(x, VOWELS[v]) for x, v in call["vowel"]]
    trill = call.get("trill")
    vib_rate, vib_depth = 5.5, 0.012
    phase = 0.0
    block = 64
    for b0 in range(0, n, block):
        x = b0 / n
        f0 = _lerp_points(pitch, x)
        forms = _lerp_points(vowel, x)
        ks = range(1, max(2, int(5200 / f0)))
        amps = [
            k**-0.7
            * (0.12 + sum(g * math.exp(-(((k * f0 - fc) / bw) ** 2)) for fc, g, bw in forms))
            for k in ks
        ]
        for i in range(b0, min(b0 + block, n)):
            t = i / RATE
            f = _lerp_points(pitch, i / n) * (1 + vib_depth * math.sin(2 * math.pi * vib_rate * t))
            phase += 2 * math.pi * f / RATE
            v = sum(a * math.sin(k * phase) for k, a in zip(ks, amps, strict=True))
            env = _envelope(i, n)
            if trill:
                rate, depth = trill
                env *= 1 - depth * (0.5 + 0.5 * math.sin(2 * math.pi * rate * t))
            out[i] = call["gain"] * env * (v + 0.25 * rng.uniform(-1, 1))
    return out


def synth_purr(call: dict, rng: random.Random) -> list[float]:
    """Low rumbling noise pulsed ~26 times a second, like a purr."""
    n = int(call["dur"] * RATE)
    out = [0.0] * n
    lp = lp2 = 0.0
    for i in range(n):
        t = i / RATE
        lp += 0.06 * (rng.uniform(-1, 1) - lp)  # two one-pole low-passes: soft rumble
        lp2 += 0.06 * (lp - lp2)
        pulse = (0.5 + 0.5 * math.sin(2 * math.pi * 26 * t)) ** 2
        tone = 0.35 * math.sin(2 * math.pi * 130 * t)  # a little body small speakers can play
        out[i] = call["gain"] * _envelope(i, n, 0.08, 0.5) * pulse * (6 * lp2 + tone)
    return out


def synth_cat(spec: dict, seed: int) -> list[float]:
    rng = random.Random(seed)  # deterministic: regenerating gives identical files
    total = max(c["start"] + c["dur"] for c in spec["calls"]) + 0.05
    buf = [0.0] * int(total * RATE)
    for call in spec["calls"]:
        part = synth_purr(call, rng) if call.get("purr") else synth_meow(call, rng)
        s0 = int(call["start"] * RATE)
        for i, v in enumerate(part):
            buf[s0 + i] += v
    m = max(abs(x) for x in buf) or 1.0
    peak = spec.get("peak", 0.55)
    return [x / m * peak for x in buf]


# ---------------------------------------------------------------- hummingbird voice

# Parts: {"chirp": (f_start, f_end)} a short sweeping whistle; {"trill": (f_lo, f_hi), "rate"}
# a fast warbling twitter; {"hum": f} the buzz of wings. All have "start", "dur", "gain".
BIRD_CUES: dict[str, dict] = {
    # wings hum in, then a bright "tsee-tsee!"
    "hello": {
        "parts": [
            {"hum": 190, "start": 0.0, "dur": 0.5, "gain": 0.5},
            {"chirp": (2600, 3600), "start": 0.12, "dur": 0.08, "gain": 1.0},
            {"chirp": (2800, 4000), "start": 0.26, "dur": 0.11, "gain": 1.0},
        ],
    },
    # one soft, rising "tsip?"
    "waiting": {
        "parts": [{"chirp": (2400, 3300), "start": 0.0, "dur": 0.16, "gain": 1.0}],
        "peak": 0.36,
    },
    # five sharp, quick "chip!"s
    "alert": {
        "parts": [
            {"chirp": (3800, 2900), "start": i * 0.09, "dur": 0.045, "gain": 1.0} for i in range(5)
        ],
        "peak": 0.5,
    },
    # a happy twitter that climbs, a final sparkle chirp, and a hum underneath
    "done": {
        "parts": [
            {"hum": 200, "start": 0.0, "dur": 0.85, "gain": 0.4},
            {"trill": (2500, 3300), "rate": 22, "start": 0.0, "dur": 0.32, "gain": 0.8},
            {"trill": (2900, 3800), "rate": 26, "start": 0.3, "dur": 0.28, "gain": 0.9},
            {"chirp": (3200, 4300), "start": 0.62, "dur": 0.14, "gain": 1.0},
        ],
        "peak": 0.48,
    },
    # a falling chirp as the wing hum fades away
    "bye": {
        "parts": [
            {"chirp": (3400, 2300), "start": 0.0, "dur": 0.18, "gain": 1.0},
            {"hum": 185, "start": 0.1, "dur": 0.75, "gain": 0.55, "fade": True},
        ],
        "peak": 0.42,
    },
}


def synth_bird(spec: dict, seed: int) -> list[float]:
    rng = random.Random(seed)
    total = max(part["start"] + part["dur"] for part in spec["parts"]) + 0.05
    buf = [0.0] * int(total * RATE)
    for part in spec["parts"]:
        n = int(part["dur"] * RATE)
        s0 = int(part["start"] * RATE)
        phase = 0.0
        lp = 0.0
        for i in range(n):
            x = i / n
            t = i / RATE
            if "hum" in part:  # wing buzz: low tone + harmonics, pulsing with the wingbeat
                f = part["hum"] * (1 + 0.015 * math.sin(2 * math.pi * 7 * t))
                phase += 2 * math.pi * f / RATE
                lp += 0.15 * (rng.uniform(-1, 1) - lp)
                beat = 0.75 + 0.25 * math.sin(2 * math.pi * 48 * t)
                v = beat * (
                    math.sin(phase) + 0.5 * math.sin(2 * phase) + 0.25 * math.sin(3 * phase)
                )
                v += 0.6 * lp
                env = min(1.0, x / 0.25) * (1 - x if part.get("fade") else min(1.0, (1 - x) / 0.2))
            else:
                if "chirp" in part:
                    f0, f1 = part["chirp"]
                    f = f0 + (f1 - f0) * x**0.7
                else:  # trill: pitch warbles quickly between lo and hi while rising a bit
                    lo, hi = part["trill"]
                    wob = 0.5 + 0.5 * math.sin(2 * math.pi * part["rate"] * t)
                    f = (lo + (hi - lo) * wob) * (1 + 0.08 * x)
                phase += 2 * math.pi * f / RATE
                v = math.sin(phase) + 0.18 * math.sin(2 * phase)
                env = math.sin(math.pi * x) ** 0.6  # soft start and end: no clicks
            buf[s0 + i] += part["gain"] * env * v
    m = max(abs(x) for x in buf) or 1.0
    peak = spec.get("peak", 0.45)
    return [x / m * peak for x in buf]


# ---------------------------------------------------------------- owl voice

# Parts: {"hoot": (f_start, f_end)} a soft, breathy, hollow "hoo" whose pitch glides;
# {"screech": (f_start, f_end)} a short raspy "kee". Optional "vibrato" (Hz) on hoots.
OWL_CUES: dict[str, dict] = {
    # "hoo-HOO!": a friendly rising pair
    "hello": {
        "parts": [
            {"hoot": (360, 380), "start": 0.0, "dur": 0.2, "gain": 0.8},
            {"hoot": (430, 470), "start": 0.26, "dur": 0.38, "gain": 1.0},
        ],
    },
    # one soft, questioning "hoo?" that lifts at the end
    "waiting": {
        "parts": [{"hoot": (390, 450), "start": 0.0, "dur": 0.34, "gain": 1.0}],
        "peak": 0.42,
    },
    # two sharp, raspy "kee-kee!"s
    "alert": {
        "parts": [
            {"screech": (1900, 1500), "start": 0.0, "dur": 0.16, "gain": 1.0},
            {"screech": (2000, 1550), "start": 0.22, "dur": 0.2, "gain": 1.0},
        ],
        "peak": 0.5,
    },
    # the classic "hoo, hoo-hoo, hoooo" with a warbling last note
    "done": {
        "parts": [
            {"hoot": (420, 430), "start": 0.0, "dur": 0.16, "gain": 0.85},
            {"hoot": (440, 450), "start": 0.24, "dur": 0.1, "gain": 0.8},
            {"hoot": (450, 460), "start": 0.37, "dur": 0.1, "gain": 0.8},
            {"hoot": (470, 440), "start": 0.52, "dur": 0.55, "gain": 1.0, "vibrato": 7},
        ],
    },
    # a long, sleepy "hoooo" sinking and fading away
    "bye": {
        "parts": [{"hoot": (430, 320), "start": 0.0, "dur": 0.7, "gain": 1.0, "fade": True}],
        "peak": 0.42,
    },
}


def synth_owl(spec: dict, seed: int) -> list[float]:
    rng = random.Random(seed)
    total = max(part["start"] + part["dur"] for part in spec["parts"]) + 0.05
    buf = [0.0] * int(total * RATE)
    for part in spec["parts"]:
        n = int(part["dur"] * RATE)
        s0 = int(part["start"] * RATE)
        phase = 0.0
        lp = 0.0
        for i in range(n):
            x = i / n
            t = i / RATE
            if "hoot" in part:  # hollow tone (mostly fundamental) + a breath of air
                f0, f1 = part["hoot"]
                f = f0 + (f1 - f0) * x
                if part.get("vibrato"):
                    f *= 1 + 0.02 * math.sin(2 * math.pi * part["vibrato"] * t) * x
                phase += 2 * math.pi * f / RATE
                lp += 0.05 * (rng.uniform(-1, 1) - lp)
                v = math.sin(phase) + 0.12 * math.sin(2 * phase) + 0.05 * math.sin(3 * phase)
                v += 1.2 * lp * (1 - x)  # breathy onset
                attack = min(1.0, x / 0.18)
                env = attack * ((1 - x) ** 1.5 if part.get("fade") else min(1.0, (1 - x) / 0.35))
            else:  # screech: buzzy tone, roughened by fast noisy amplitude modulation
                f0, f1 = part["screech"]
                f = f0 + (f1 - f0) * x**0.8
                phase += 2 * math.pi * f / RATE
                lp += 0.4 * (rng.uniform(-1, 1) - lp)
                rough = 0.6 + 0.4 * math.sin(2 * math.pi * 90 * t) + 0.5 * lp
                v = rough * (
                    math.sin(phase) + 0.45 * math.sin(2 * phase) + 0.25 * math.sin(3 * phase)
                )
                env = math.sin(math.pi * x) ** 0.5
            buf[s0 + i] += part["gain"] * env * v
    m = max(abs(x) for x in buf) or 1.0
    peak = spec.get("peak", 0.5)
    return [x / m * peak for x in buf]


VOICES = {
    "panda": "chime",
    "cat": "cat",
    "penguin": "penguin",
    "hummingbird": "bird",
    "owl": "owl",
}


def render(voice: str, name: str) -> list[float]:
    if voice == "cat":
        return synth_cat(CAT_CUES[name], seed=sum(map(ord, name)))
    if voice == "bird":
        return synth_bird(BIRD_CUES[name], seed=sum(map(ord, name)) + 2)
    if voice == "owl":
        return synth_owl(OWL_CUES[name], seed=sum(map(ord, name)) + 3)
    if voice == "penguin":  # same voice model as the cat, different calls
        return synth_cat(PENGUIN_CUES[name], seed=sum(map(ord, name)) + 1)
    spec = CUES[name]
    return synth(spec["notes"], spec["decay"])


def write_wav(path: Path, samples: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, x)) * 32767)) for x in samples))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--character", choices=sorted(VOICES), default="panda")
    ap.add_argument("--out", type=Path, help="character folder (default: the built-in one)")
    ap.add_argument("--play", metavar="CUE", help="play one cue after generating (macOS)")
    args = ap.parse_args()
    args.out = args.out or CHARACTERS / args.character
    voice = VOICES[args.character]

    sounds = {}
    for name in CUES:
        path = args.out / "sounds" / f"{name}.wav"
        write_wav(path, render(voice, name))
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
