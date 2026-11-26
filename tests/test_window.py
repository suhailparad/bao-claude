import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from bao.character import discover_characters  # noqa: E402
from bao.config import Config  # noqa: E402
from bao.sessions import Display, State  # noqa: E402
from bao.window import PetWindow  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp, pet_home):
    w = PetWindow(Config(), discover_characters())
    yield w
    w.close()


def disp(state, variant=None, text="x", project="proj", count=1):
    return Display(state, variant, text, project, "s", count)


def test_plays_variant_animation_and_advances(window):
    window.set_display(disp(State.WORKING, "typing"))
    assert window._anim.name == "typing"
    n = len(window._frames)
    assert n > 1
    for _ in range(n):
        window._next_frame()
    assert window._frame == 0  # looped


def test_bubble_rules(window):
    window.set_display(disp(State.NEEDS_PERMISSION))
    assert window._bubble_visible and not window._bubble_timer.isActive()  # sticky
    window.set_display(disp(State.THINKING))
    assert window._bubble_visible and window._bubble_timer.isActive()  # auto-hides
    window.set_display(disp(State.SLEEPING))
    assert not window._bubble_visible
    assert window._bubble_lines()[1] == ""  # no folder name: only extras go on line two
    window.set_display(disp(State.WAITING, count=3))
    assert window._bubble_lines()[1] == "3 sessions"


def test_grab_renders(window):
    window.set_display(disp(State.DONE))
    img = window.grab().toImage()
    assert not img.isNull() and img.width() == window.width()


def test_scale_menu_and_config(window, pet_home):
    w0 = window.width()
    window._set_scale(1.4)
    assert window.height() > 214 and window.width() > w0
    assert Config.load().scale == 1.4
    titles = [a.text() for a in window.build_menu().actions()]
    assert {"Character", "Size", "Sound", "Show speech bubble", "Quit Bao"} <= set(titles)


def test_unknown_character_falls_back(qapp, pet_home):
    w = PetWindow(Config(character="dragon"), discover_characters())
    assert {"cat", "penguin", "hummingbird", "owl"} <= set(
        w.characters
    )  # panda is still the default
    assert w.character.id == "panda"
    w.close()


def test_auto_quit_after_last_session(qapp):
    from bao.app import PetController

    c = PetController(quit_after=60)
    fired = []
    c.quit_requested.connect(lambda: fired.append(1))
    c._check_auto_quit(0)
    c._check_auto_quit(1000)
    assert not fired  # never had a session: stay (manual `run`)
    c.apply({"event": "SessionStart", "session_id": "s"})
    c._check_auto_quit(1000)
    c.apply({"event": "SessionEnd", "session_id": "s"})
    c._check_auto_quit(1001)
    c._check_auto_quit(1050)
    assert not fired
    c._check_auto_quit(1062)
    c._check_auto_quit(1100)
    assert fired == [1]  # once


def test_show_offscreen_does_not_touch_cocoa(window, monkeypatch):
    import bao.platform_mac as pm

    calls = []
    monkeypatch.setattr(pm, "float_on_all_spaces", lambda wid: calls.append(wid))
    window.show()  # used to segfault: winId() isn't an NSView off-screen
    assert window.isVisible() and calls == []


def test_bubble_shows_how_long_the_turn_took(window):
    text = "Bao is waiting for you"
    window.set_display(Display(State.WAITING, None, text, "proj", "s", 2, 252))
    assert window._bubble_lines() == (text, "took 4m 12s · 2 sessions")
    window.set_display(Display(State.DONE, None, "Bao finished in 4m 12s!", None, "s", 1, 252))
    assert window._bubble_lines() == ("Bao finished in 4m 12s!", "")


def test_nudge_shakes_and_shows_bubble(window, monkeypatch):
    import bao.window as wmod

    window.set_display(disp(State.NEEDS_PERMISSION))
    window._hide_bubble()
    clock = [100.0]
    monkeypatch.setattr(wmod.time, "monotonic", lambda: clock[0])
    window.nudge()
    assert window._bubble_visible and window._shake_timer.isActive()
    clock[0] += 0.03
    assert window._shake_offset() != 0
    clock[0] += wmod.SHAKE_SECONDS
    window._shake_step()
    assert window._shake_offset() == 0 and not window._shake_timer.isActive()


def test_reminder_menu_toggle(window, pet_home):
    got = []
    window.reminder_changed.connect(got.append)
    window._set_reminder(False)
    window._set_reminder(True)
    assert got == [0.0, 60.0] and Config.load().permission_reminder_seconds == 60.0


def test_controller_reminds_with_alert_and_nudge(qapp):
    from bao.app import PetController
    from bao.sessions import Timings

    c = PetController(Timings(permission_reminder=0.001))
    cues, nudges = [], []
    c.cue.connect(cues.append)
    c.nudge.connect(nudges.append)
    c.apply({"event": "Notification", "session_id": "s", "notification_type": "permission_prompt"})
    import time

    time.sleep(0.01)
    c._on_tick()
    c._on_tick()
    assert cues == ["alert", "alert"] and nudges == ["s"]  # first alert is the request itself


def test_do_not_disturb_menu_moon_and_ipc(window, pet_home):
    from bao.app import PetController

    titles = [a.text() for a in window.build_menu().actions()]
    assert "Do Not Disturb" in titles and not any(t.startswith("Quiet hours") for t in titles)
    window.set_do_not_disturb(True)
    assert Config.load().do_not_disturb
    window.set_display(disp(State.WORKING))
    assert not window.grab().toImage().isNull()  # paints the moon without errors
    window.config.quiet_hours = ["22:00", "08:00"]
    assert any(
        a.text().startswith("Quiet hours 22:00–08:00") for a in window.build_menu().actions()
    )

    c = PetController(config=window.config)
    c.dnd_requested.connect(window.set_do_not_disturb)
    assert c.handle_from_thread({"cmd": "dnd", "on": False}) == {"ok": True}
    assert window.config.do_not_disturb is False
    status = c.handle_from_thread({"cmd": "status"})
    assert status["do_not_disturb"]["manual"] is False
    assert status["do_not_disturb"]["quiet_hours"] == ["22:00", "08:00"]


def test_wrap_text(qapp):
    from PySide6.QtGui import QFont, QFontMetricsF

    from bao.window import wrap_text

    f = QFont()
    f.setPixelSize(13)
    f.setBold(True)
    m = QFontMetricsF(f)
    # Widths are relative to the text, so the test doesn't depend on each OS's default font.
    short = "Bao is thinking…"
    assert wrap_text(short, m, m.horizontalAdvance(short) + 1, 2) == [short]
    for text in ("Bao needs your permission!", "Bao is waiting for you", "Bao finished in 4m 12s!"):
        width = 0.75 * m.horizontalAdvance(text)
        lines = wrap_text(text, m, width, 2)
        assert len(lines) == 2 and " ".join(lines) == text
        assert all(m.horizontalAdvance(line) <= width for line in lines)
        a, b = (m.horizontalAdvance(line) for line in lines)
        assert min(a, b) >= 0.5 * max(a, b)  # balanced: no lonely "you" on line two
    long = wrap_text("word " * 40, m, 132, 2)
    assert len(long) == 2 and long[1].endswith("…")  # never more than two lines
    assert wrap_text("", m, 132, 2) == [""]


def _roam_window(qapp, pet_home, character, monkeypatch, clock):
    import bao.window as wmod
    from bao.roam import RoamSpec

    monkeypatch.setattr(wmod.time, "monotonic", lambda: clock[0])
    w = PetWindow(Config(character=character), discover_characters())
    w.move(300, 300)
    w._roam_bounds = lambda: (0.0, 0.0, 1000.0, 700.0)
    w._roamer.rng.seed(7)
    assert isinstance(w._roamer.spec, RoamSpec)
    return w


def _tick(w, clock, seconds, dt=0.05):
    end = clock[0] + seconds
    while clock[0] < end:
        clock[0] += dt
        w._roam_tick()


def test_roams_when_idle_and_comes_home_for_work(qapp, pet_home, monkeypatch):
    clock = [1000.0]
    w = _roam_window(qapp, pet_home, "penguin", monkeypatch, clock)
    w.set_display(disp(State.WAITING))
    assert w._roam_timer.isActive()
    _tick(w, clock, 7)
    assert (w.x(), w.y()) == (300, 300)  # waits a bit first
    _tick(w, clock, 20)
    assert w.y() == 300 and w.x() != 300  # strolled sideways
    if w._roamer.moving:
        assert w._anim.name == "roaming"
    w.set_display(disp(State.WORKING, "typing"))
    _tick(w, clock, 4)
    assert (w.x(), w.y()) == (300, 300) and not w._roam_timer.isActive()
    assert w._anim.name == "typing" and not w._mirror
    w.close()


def test_bird_flies_and_mirrors_toward_travel(qapp, pet_home, monkeypatch):
    clock = [1000.0]
    w = _roam_window(qapp, pet_home, "hummingbird", monkeypatch, clock)
    w.set_display(disp(State.IDLE))
    _tick(w, clock, 9)
    seen = set()
    for _ in range(600):
        _tick(w, clock, 0.05)
        if w._roamer.facing:
            seen.add((w._roamer.facing, w._mirror))
        if w._roamer.airborne:
            assert w._anim.name == "roaming"
    assert (1, True) in seen or (-1, False) in seen  # faces left: flipped only going right
    assert all(mirror == (facing > 0) for facing, mirror in seen)
    w.close()


def test_drag_sets_new_home_and_position_saves_home(qapp, pet_home, monkeypatch):
    clock = [1000.0]
    w = _roam_window(qapp, pet_home, "cat", monkeypatch, clock)
    w.set_display(disp(State.WAITING))
    _tick(w, clock, 20)
    w._save_position()
    assert Config.load().position == [300, 300]  # home, not wherever it wandered to
    w.move(500, 200)  # the user drops it here
    w._drag_offset, w._dragged = None, True
    w._roamer.stop()
    w._roam_stopped()
    w._save_position()
    w._update_roaming()
    assert Config.load().position == [500, 200] and w._roamer.home == (500, 200)
    w.close()


def test_panda_stays_home_and_eats_bamboo(qapp, pet_home, monkeypatch):
    clock = [1000.0]
    w = _roam_window(qapp, pet_home, "panda", monkeypatch, clock)
    w.set_display(disp(State.IDLE))
    _tick(w, clock, 30)
    assert not w._roamer.active and not w._roam_timer.isActive()  # "stay": no strolling
    assert w._anim.name == "idle"  # sitting with its bamboo
    w.close()


def test_roam_menu_toggle(qapp, pet_home, monkeypatch):
    clock = [1000.0]
    w = _roam_window(qapp, pet_home, "cat", monkeypatch, clock)
    assert "Wander around when idle" in [a.text() for a in w.build_menu().actions()]
    w.set_display(disp(State.IDLE))
    _tick(w, clock, 20)
    w._set_roam(False)
    _tick(w, clock, 4)
    assert (w.x(), w.y()) == (300, 300) and not w._roam_timer.isActive()
    assert Config.load().roam is False
    w.close()
