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
    assert window._bubble_lines()[1] == "proj"
    window.set_display(disp(State.WAITING, count=3))
    assert window._bubble_lines()[1] == "proj · 3 sessions"


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
    assert {"Character", "Size", "Sound", "Show speech bubble", "Quit Claude Pet"} <= set(titles)


def test_unknown_character_falls_back(qapp, pet_home):
    w = PetWindow(Config(character="dragon"), discover_characters())
    assert {"cat", "penguin", "hummingbird"} <= set(w.characters)  # panda is still the default
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
    assert window._bubble_lines() == (text, "proj · took 4m 12s · 2 sessions")
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
