import json
from pathlib import Path

import pytest

from bao.character import (
    BUILTIN_DIR,
    ManifestError,
    discover_characters,
    load_character,
)
from bao.config import Config
from bao.sessions import State

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


def make_char(root: Path, cid="cat", states=None, **extra) -> Path:
    d = root / cid
    for name in states or ["idle", "working"]:
        (d / "frames" / name).mkdir(parents=True)
        (d / "frames" / name / "000.png").write_bytes(PNG)
    manifest = {
        "id": cid,
        "name": cid.title(),
        "states": {n: {"frames": f"frames/{n}", "fps": 6} for n in states or ["idle", "working"]},
        **extra,
    }
    (d / "manifest.json").write_text(json.dumps(manifest))
    return d


@pytest.mark.parametrize("cid", ["panda", "cat"])
def test_builtin_character_covers_every_state(cid):
    ch = load_character(BUILTIN_DIR / cid)
    assert ch.id == cid
    for s in State:
        assert s.value in ch.animations, s
    for variant in ("reading", "typing", "running"):
        assert ch.animation_for("working", variant).name == variant
    for cue in ("hello", "waiting", "alert", "done", "bye"):
        assert ch.sound_for(cue), cue


def test_fallbacks(tmp_path):
    ch = load_character(make_char(tmp_path))
    assert ch.animation_for("working", "typing").name == "working"  # variant → state
    assert ch.animation_for("sleeping").name == "idle"  # state → fallback


def test_user_dir_overrides_builtin(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    make_char(a, "cat", name="Old")
    make_char(b, "cat", name="New")
    assert discover_characters([a, b])["cat"].name == "New"


@pytest.mark.parametrize(
    "patch",
    [
        {"states": {}},
        {"fallback_state": "nope"},
        {"states": {"idle": {"frames": "frames/missing"}}},
        {"states": {"idle": {"frames": "../../etc"}}},
        {"states": {"idle": {"frames": "frames/idle", "fps": 0}}},
        {"states": {"idle": {"frames": "frames/idle", "next": "ghost"}}},
    ],
)
def test_invalid_manifests_are_rejected(tmp_path, patch):
    d = make_char(tmp_path)
    m = json.loads((d / "manifest.json").read_text())
    m.update(patch)
    (d / "manifest.json").write_text(json.dumps(m))
    with pytest.raises(ManifestError):
        load_character(d)
    assert discover_characters([tmp_path]) == {}  # skipped, not crashed


def test_sheet_and_sounds(tmp_path):
    d = make_char(tmp_path)
    (d / "sheet.png").write_bytes(PNG)
    (d / "s.wav").write_bytes(b"RIFF")
    m = json.loads((d / "manifest.json").read_text())
    m["states"]["done"] = {"sheet": "sheet.png", "frame_size": [1, 1], "count": 1, "loop": False}
    m["sounds"] = {"done": "s.wav", "alert": "system:Glass", "bye": "missing.wav"}
    (d / "manifest.json").write_text(json.dumps(m))
    ch = load_character(d)
    assert ch.animations["done"].frame_count == 1 and not ch.animations["done"].loop
    assert ch.sound_for("done") == str(d / "s.wav")
    assert ch.sound_for("alert") == "system:Glass"
    assert ch.sound_for("bye") is None


def test_config_roundtrip_and_sanitize(tmp_path):
    path = tmp_path / "config.json"
    assert Config.load(path) == Config()
    Config(character="cat", scale=1.4, muted=True, position=[10, 20]).save(path)
    c = Config.load(path)
    assert (c.character, c.scale, c.muted, c.position) == ("cat", 1.4, True, [10, 20])
    path.write_text(json.dumps({"scale": 99, "volume": "loud", "position": "x", "junk": 1}))
    c = Config.load(path)
    assert (c.scale, c.volume, c.position) == (4.0, 0.7, None)
    path.write_text("{not json")
    assert Config.load(path) == Config()


def test_builtin_characters_have_their_own_sounds():
    panda = load_character(BUILTIN_DIR / "panda")
    cat = load_character(BUILTIN_DIR / "cat")
    for cue in ("hello", "waiting", "alert", "done", "bye"):
        assert Path(panda.sound_for(cue)).read_bytes() != Path(cat.sound_for(cue)).read_bytes(), cue


def test_quiet_hours():
    from datetime import datetime
    from datetime import time as t

    from bao.config import Config, in_quiet_hours

    night = ["22:00", "08:00"]
    assert in_quiet_hours(night, t(23, 30)) and in_quiet_hours(night, t(7, 59))
    assert not in_quiet_hours(night, t(8, 0)) and not in_quiet_hours(night, t(12, 0))
    lunch = ["12:00", "13:00"]
    assert in_quiet_hours(lunch, t(12, 30)) and not in_quiet_hours(lunch, t(13, 0))
    assert not in_quiet_hours(None, t(0, 0)) and not in_quiet_hours(["9:00", "9:00"], t(9, 0))

    cfg = Config(quiet_hours=night)
    assert cfg.sounds_silenced(datetime(2026, 1, 1, 23, 0))
    assert not cfg.sounds_silenced(datetime(2026, 1, 1, 12, 0))
    cfg.do_not_disturb = True
    assert cfg.sounds_silenced(datetime(2026, 1, 1, 12, 0))


def test_quiet_hours_sanitized(pet_home):
    import json

    from bao.config import Config
    from bao.paths import config_path

    for bad in (["25:00", "08:00"], ["22:00"], "22-08", [22, 8]):
        config_path().write_text(json.dumps({"quiet_hours": bad, "do_not_disturb": 1}))
        cfg = Config.load()
        assert cfg.quiet_hours is None and cfg.do_not_disturb is True
    config_path().write_text(json.dumps({"quiet_hours": ["22:00", "7:30"]}))
    assert Config.load().quiet_hours == ["22:00", "7:30"]
