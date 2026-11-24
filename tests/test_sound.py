import os
import wave

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from bao import sound  # noqa: E402
from bao.character import BUILTIN_DIR, load_character  # noqa: E402
from bao.config import Config  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeEffect:
    def __init__(self):
        self.plays = 0

    def play(self):
        self.plays += 1

    def setVolume(self, v):  # noqa: N802
        self.volume = v


@pytest.fixture
def player(qapp, monkeypatch):
    p = sound.SoundPlayer(Config(), load_character(BUILTIN_DIR / "panda"))
    p._effects = {cue: FakeEffect() for cue in p._effects}
    clock = [1000.0]
    monkeypatch.setattr(sound.time, "monotonic", lambda: clock[0])
    p.clock = clock
    return p


def test_panda_has_all_cues_as_valid_wavs():
    panda = load_character(BUILTIN_DIR / "panda")
    for cue in sound.CUE_LABELS:
        path = panda.sound_for(cue)
        with wave.open(path) as w:
            assert w.getframerate() == 44100 and 0.2 < w.getnframes() / 44100 < 1.5


def test_play_mute_and_per_cue(player):
    assert player.play("done") and player._effects["done"].plays == 1
    player.config.muted = True
    player.clock[0] += 5
    assert not player.play("done")
    assert player.play("done", force=True)  # menu "test sound" ignores mute
    player.config.muted = False
    player.config.muted_cues = ["hello"]
    player.clock[0] += 5
    assert not player.play("hello") and player.play("alert")
    assert not player.play("nonexistent")


def test_repeat_gap(player):
    assert player.play("alert")
    player.clock[0] += 0.5
    assert not player.play("alert")  # too soon
    assert player.play("done")  # other cues unaffected
    player.clock[0] += 2
    assert player.play("alert")


def test_volume_applied(player):
    player.config.volume = 0.25
    player.apply_settings()
    assert all(e.volume == 0.25 for e in player._effects.values())


def test_system_sound_uses_afplay(player, monkeypatch, tmp_path):
    fake = tmp_path / "Glass.aiff"
    fake.write_bytes(b"x")
    import bao.desktop as desktop

    monkeypatch.setattr(desktop, "MAC_SOUNDS", tmp_path)
    monkeypatch.setattr(
        sound, "system_sound_path", lambda n: desktop.system_sound_path(n, "darwin")
    )
    monkeypatch.setattr(sound, "IS_MAC", True)
    calls = []
    monkeypatch.setattr(sound.subprocess, "Popen", lambda argv, **kw: calls.append(argv))
    player._files["alert"] = sound.resolve_sound("system:Glass")
    player._effects.pop("alert")
    assert player.play("alert")
    assert calls[0][0] == "/usr/bin/afplay" and calls[0][-1] == str(fake)
    assert sound.resolve_sound("system:DoesNotExist") is None


def test_do_not_disturb_silences_but_test_sound_still_plays(player):
    player.config.do_not_disturb = True
    assert not player.play("done")
    assert player.play("done", force=True)  # "Play test sound" from the menu
    player.config.do_not_disturb = False
    player._last_played.clear()
    assert player.play("done")


def test_system_sounds_on_linux_and_windows(monkeypatch, tmp_path):
    import bao.desktop as desktop

    stereo = tmp_path / "stereo"
    stereo.mkdir()
    (stereo / "complete.oga").write_bytes(b"x")
    monkeypatch.setattr(desktop, "LINUX_SOUND_DIRS", (stereo,))
    assert desktop.system_sound_path("Complete", "linux") == stereo / "complete.oga"
    assert desktop.system_sound_path("missing", "linux") is None
    media = tmp_path / "Media"
    media.mkdir()
    (media / "tada.wav").write_bytes(b"x")
    monkeypatch.setenv("WINDIR", str(tmp_path))
    assert desktop.system_sound_path("tada", "win32") == media / "tada.wav"
    assert desktop.system_sound_path("../tada", "win32") is None  # no path tricks


def test_non_wav_off_macos_uses_qt_media_player(player, monkeypatch, tmp_path):
    fake = tmp_path / "ding.mp3"
    fake.write_bytes(b"not really audio")
    monkeypatch.setattr(sound, "IS_MAC", False)
    popen = []
    monkeypatch.setattr(sound.subprocess, "Popen", lambda *a, **k: popen.append(a))
    player._files["alert"] = fake
    player._effects.pop("alert")
    assert player.play("alert") and popen == []  # no afplay
