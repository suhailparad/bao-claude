"""Character packs: manifest parsing, validation and discovery. No Qt.

A character is a folder with a ``manifest.json`` (see CLAUDE.md). Frames are listed
either as a directory of PNGs (``"frames"``) or as a horizontal sprite sheet
(``"sheet"`` + ``"frame_size"`` + ``"count"``). The Qt side turns them into pixmaps.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .paths import home_dir

log = logging.getLogger(__name__)

BUILTIN_DIR = Path(__file__).parent / "characters"
SOUND_EXTS = {".wav", ".aiff", ".aif", ".mp3", ".m4a"}


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class SheetSpec:
    path: Path
    frame_size: tuple[int, int]
    count: int


@dataclass(frozen=True)
class Animation:
    name: str
    fps: float
    loop: bool
    next: str | None
    frames: tuple[Path, ...] = ()
    sheet: SheetSpec | None = None

    @property
    def frame_count(self) -> int:
        return self.sheet.count if self.sheet else len(self.frames)


@dataclass
class Character:
    id: str
    name: str
    root: Path
    size: tuple[int, int]
    animations: dict[str, Animation]
    sounds: dict[str, str] = field(default_factory=dict)
    fallback_state: str = "idle"

    def animation_for(self, state: str, variant: str | None = None) -> Animation:
        """Most specific animation available: variant → state → fallback."""
        for key in (variant, state, self.fallback_state):
            if key and key in self.animations:
                return self.animations[key]
        raise KeyError(state)  # unreachable for a validated character

    def sound_for(self, cue: str) -> str | None:
        """Absolute file path, or ``"system:<Name>"``, or None."""
        ref = self.sounds.get(cue)
        if not ref:
            return None
        if ref.startswith("system:"):
            return ref
        return str(self.root / ref)


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ManifestError(msg)


def _inside(root: Path, rel: str) -> Path:
    p = (root / rel).resolve()
    _require(p.is_relative_to(root.resolve()), f"path escapes character folder: {rel}")
    return p


def _parse_animation(root: Path, name: str, spec: Any, default_fps: float) -> Animation:
    _require(isinstance(spec, dict), f"state {name!r} must be an object")
    fps = spec.get("fps", default_fps)
    _require(isinstance(fps, (int, float)) and 0 < fps <= 60, f"state {name!r}: bad fps")
    loop = bool(spec.get("loop", True))
    nxt = spec.get("next")
    _require(nxt is None or isinstance(nxt, str), f"state {name!r}: 'next' must be a string")

    if "frames" in spec:
        d = _inside(root, str(spec["frames"]))
        frames = tuple(sorted(d.glob("*.png"))) if d.is_dir() else ()
        _require(bool(frames), f"state {name!r}: no PNG frames in {spec['frames']}")
        return Animation(name, float(fps), loop, nxt, frames=frames)

    if "sheet" in spec:
        path = _inside(root, str(spec["sheet"]))
        _require(path.is_file(), f"state {name!r}: sheet not found: {spec['sheet']}")
        fs = spec.get("frame_size")
        count = spec.get("count")
        _require(
            isinstance(fs, list) and len(fs) == 2 and all(isinstance(v, int) and v > 0 for v in fs),
            f"state {name!r}: 'frame_size' must be [w, h]",
        )
        _require(isinstance(count, int) and count > 0, f"state {name!r}: 'count' must be > 0")
        return Animation(name, float(fps), loop, nxt, sheet=SheetSpec(path, (fs[0], fs[1]), count))

    raise ManifestError(f"state {name!r} needs 'frames' or 'sheet'")


def load_character(root: Path) -> Character:
    manifest = root / "manifest.json"
    try:
        data = json.loads(manifest.read_text())
    except (OSError, ValueError) as exc:
        raise ManifestError(f"cannot read {manifest}: {exc}") from exc
    _require(isinstance(data, dict), "manifest must be an object")

    cid = data.get("id") or root.name
    _require(isinstance(cid, str), "'id' must be a string")
    size = data.get("size", [160, 160])
    _require(
        isinstance(size, list)
        and len(size) == 2
        and all(isinstance(v, int) and v > 0 for v in size),
        "'size' must be [w, h]",
    )
    default_fps = data.get("fps", 8)
    states = data.get("states")
    _require(isinstance(states, dict) and bool(states), "'states' must be a non-empty object")
    anims = {name: _parse_animation(root, name, spec, default_fps) for name, spec in states.items()}

    fallback = data.get("fallback_state", "idle")
    _require(fallback in anims, f"fallback_state {fallback!r} is not defined")
    for a in anims.values():
        _require(a.next is None or a.next in anims, f"state {a.name!r}: unknown next {a.next!r}")

    sounds: dict[str, str] = {}
    for cue, ref in (data.get("sounds") or {}).items():
        if not isinstance(ref, str):
            continue
        if ref.startswith("system:"):
            sounds[cue] = ref
            continue
        p = _inside(root, ref)
        if p.is_file() and p.suffix.lower() in SOUND_EXTS:
            sounds[cue] = ref
        else:
            log.warning("character %s: sound %r for %r not found, skipping", cid, ref, cue)

    return Character(
        id=cid,
        name=str(data.get("name") or cid),
        root=root,
        size=(size[0], size[1]),
        animations=anims,
        sounds=sounds,
        fallback_state=fallback,
    )


def character_dirs() -> list[Path]:
    """Search order; later entries override earlier ones with the same id."""
    return [BUILTIN_DIR, home_dir() / "characters"]


def discover_characters(dirs: list[Path] | None = None) -> dict[str, Character]:
    found: dict[str, Character] = {}
    for base in dirs if dirs is not None else character_dirs():
        if not base.is_dir():
            continue
        for sub in sorted(base.iterdir()):
            if not (sub / "manifest.json").is_file():
                continue
            try:
                ch = load_character(sub)
            except ManifestError as exc:
                log.error("skipping character %s: %s", sub, exc)
                continue
            found[ch.id] = ch
    return found
