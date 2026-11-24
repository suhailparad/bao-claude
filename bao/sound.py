"""Plays a character's sound cues, honouring mute, volume and per-cue switches.

* ``.wav`` files → ``QSoundEffect`` (preloaded, low latency), on every OS.
* Other formats (aiff/mp3/m4a/oga) → ``afplay`` on macOS, Qt's media player elsewhere.
* ``system:<Name>`` → the desktop's own sound theme (see ``desktop.system_sound_path``):
  ``system:Glass`` on macOS, ``system:complete`` on Linux, ``system:tada`` on Windows.
"""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path

from PySide6.QtCore import QObject, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QSoundEffect

from .character import Character
from .config import Config
from .desktop import IS_MAC, system_sound_path

log = logging.getLogger(__name__)

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
        return system_sound_path(ref.split(":", 1)[1])
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
        if not IS_MAC:
            return self._play_media(cue, path)
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
            return False

    def _play_media(self, cue: str, path: Path) -> bool:
        """Non-wav files off macOS: Qt's media player (FFmpeg backend in PySide6)."""
        player = QMediaPlayer(self)
        output = QAudioOutput(player)  # owned by the player: deleted with it
        output.setVolume(self.config.volume)
        player.setAudioOutput(output)

        def finished(status: QMediaPlayer.MediaStatus) -> None:
            if status in (
                QMediaPlayer.MediaStatus.EndOfMedia,
                QMediaPlayer.MediaStatus.InvalidMedia,
            ):
                player.deleteLater()

        player.mediaStatusChanged.connect(finished)
        player.errorOccurred.connect(lambda *_: player.deleteLater())
        player.setSource(QUrl.fromLocalFile(str(path)))
        player.play()
        log.debug("media %s (%s)", cue, path.name)
        return True
