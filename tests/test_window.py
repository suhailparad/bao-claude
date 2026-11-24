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
    assert "cat" in w.characters  # sorts before panda, but panda is still the default
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
