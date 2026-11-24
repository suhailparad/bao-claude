"""Plays a character's sound cues, honouring mute, volume and per-cue switches.

* ``.wav`` files → ``QSoundEffect`` (preloaded, low latency).
* ``system:<Name>`` and other formats (aiff/mp3/m4a) → macOS ``afplay``.
"""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path

from PySide6.QtCore import QObject, QUrl
from PySide6.QtMultimedia import QSoundEffect

from .character import Character
from .config import Config
from .platform_mac import IS_MAC

log = logging.getLogger(__name__)

SYSTEM_SOUNDS_DIR = Path("/System/Library/Sounds")
REPEAT_GAP = 1.5  # seconds: the same cue won't replay faster than this
CUE_LABELS = {
    "hello": "Session started",
    "waiting": "Waiting for input",
    "alert": "Needs permission",
    "done": "Finished",
    "bye": "Session ended",
}


def resolve_sound(ref: str) -> Path | None:
    if ref.startswith("system:"):
        p = SYSTEM_SOUNDS_DIR / f"{ref.split(':', 1)[1]}.aiff"
    else:
        p = Path(ref)
    return p if p.is_file() else None


class SoundPlayer(QObject):
    def __init__(self, config: Config, character: Character) -> None:
        super().__init__()
        self.config = config
        self._effects: dict[str, QSoundEffect] = {}
        self._files: dict[str, Path] = {}
        self._last_played: dict[str, float] = {}
        self.set_character(character)

    def set_character(self, character: Character) -> None:
        self._effects.clear()
        self._files.clear()
        for cue in character.sounds:
            ref = character.sound_for(cue)
            path = resolve_sound(ref) if ref else None
            if path is None:
                log.warning("sound %r for cue %r not found", ref, cue)
                continue
            self._files[cue] = path
            if path.suffix.lower() == ".wav":
                effect = QSoundEffect(self)
                effect.statusChanged.connect(
                    lambda e=effect, c=cue, p=path: (
                        e.status() == QSoundEffect.Status.Error
                        and log.warning("could not load sound %s for %r", p, c)
                    )
                )
                effect.setSource(QUrl.fromLocalFile(str(path)))
                self._effects[cue] = effect
        self.apply_settings()

    def apply_settings(self) -> None:
        for effect in self._effects.values():
            effect.setVolume(self.config.volume)

    def cues(self) -> list[str]:
        return list(self._files)

    def play(self, cue: str, force: bool = False) -> bool:
        """Play a cue. Returns True if a sound was started."""
        if not force and (
            self.config.muted or cue in self.config.muted_cues or self.config.sounds_silenced()
        ):
            return False
        path = self._files.get(cue)
        if path is None:
            return False
        now = time.monotonic()
        if not force and now - self._last_played.get(cue, -1e9) < REPEAT_GAP:
            return False
        self._last_played[cue] = now

        effect = self._effects.get(cue)
        if effect is not None:
            effect.play()
            log.debug("play %s (%s)", cue, path.name)
            return True
        if IS_MAC:
            try:
                subprocess.Popen(  # noqa: S603 - fixed argv
                    ["/usr/bin/afplay", "-v", f"{self.config.volume:.2f}", str(path)],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                log.debug("afplay %s (%s)", cue, path.name)
                return True
            except OSError as exc:
                log.warning("afplay failed: %s", exc)
        else:
            log.info("cannot play %s on this platform", path.suffix)
        return False
