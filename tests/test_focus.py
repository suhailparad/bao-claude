from bao import focus
from bao.sessions import SessionTracker


def test_terminal_info_from_env():
    info = focus.terminal_info({"__CFBundleIdentifier": "com.apple.Terminal"})
    assert info["app"] == "com.apple.Terminal"
    assert focus.terminal_info({"TERM_PROGRAM": "iTerm.app"})["app"] == focus.ITERM_APP
    assert "app" not in focus.terminal_info({"__CFBundleIdentifier": 'bad"; do shell script'})


def test_terminal_info_finds_a_tty_quickly():
    # pytest runs from a terminal or CI; either way it must not raise and must be fast.
    import time

    t = time.monotonic()
    info = focus.terminal_info({})
    assert time.monotonic() - t < 0.2
    assert set(info) <= {"app", "tty"}


def test_focus_command_by_app():
    tty = "/dev/ttys009"
    argv = focus.focus_command({"app": focus.TERMINAL_APP, "tty": tty})
    assert argv[0] == "/usr/bin/osascript" and f'tty of t is "{tty}"' in argv[2]
    argv = focus.focus_command({"app": focus.ITERM_APP, "tty": tty})
    assert argv[0] == "/usr/bin/osascript" and "sessions of t" in argv[2]
    assert focus.focus_command({"app": "com.microsoft.VSCode", "tty": tty}) == [
        "/usr/bin/open",
        "-b",
        "com.microsoft.VSCode",
    ]
    # Without a tty, Terminal is just activated.
    assert focus.focus_command({"app": focus.TERMINAL_APP})[0] == "/usr/bin/open"


def test_focus_command_rejects_bad_input():
    assert focus.focus_command(None) is None
    assert focus.focus_command({}) is None
    assert focus.focus_command({"tty": "/dev/ttys001"}) is None
    argv = focus.focus_command({"app": focus.TERMINAL_APP, "tty": '/dev/ttys1" & evil'})
    assert argv == ["/usr/bin/open", "-b", focus.TERMINAL_APP]  # bad tty dropped


def test_tracker_remembers_terminal():
    t = SessionTracker()
    term = {"app": focus.TERMINAL_APP, "tty": "/dev/ttys003"}
    t.apply({"event": "SessionStart", "session_id": "a", "terminal": term}, now=0)
    t.apply({"event": "PreToolUse", "session_id": "a", "tool_name": "Bash"}, now=1)  # no info
    assert t.terminal_for("a") == term
    assert t.terminal_for("missing") is None and t.terminal_for(None) is None
    assert t.snapshot()[0]["terminal"] == term


def test_click_focuses_displayed_session(monkeypatch):
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import pytest

    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from bao.app import PetController

    QApplication.instance() or QApplication([])
    calls = []
    monkeypatch.setattr(focus, "focus_terminal", lambda info: calls.append(info) or True)
    c = PetController()
    term = {"app": "com.microsoft.VSCode"}
    c.apply({"event": "UserPromptSubmit", "session_id": "a", "terminal": term})
    assert c.focus_session(c.display) and calls == [term]
    c.apply({"event": "UserPromptSubmit", "session_id": "b"})
    c.apply({"event": "Notification", "session_id": "b", "notification_type": "permission_prompt"})
    assert not c.focus_session(c.display)  # b has no terminal info
