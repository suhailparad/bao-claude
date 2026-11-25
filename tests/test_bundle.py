"""Bao.app entry points (bao.bundle) and the installer's frozen-app support."""

import json
import sys

import pytest

from bao import bundle, installer


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        ([], ("app", [])),
        (["-psn_0_12345"], ("app", [])),
        (["-I", "-m", "bao.hook"], ("hook", [])),
        (["-I", "-m", "bao.hook", "Stop"], ("hook", ["Stop"])),
        (
            ["-I", "-m", "bao", "run", "--initial-event", "{}"],
            ("cli", ["run", "--initial-event", "{}"]),
        ),
        (["-m", "bao.__main__", "status"], ("cli", ["status"])),
        (["-I", "-c", "import bao.hook"], ("code", ["import bao.hook"])),
        (["doctor", "--settings", "x.json"], ("cli", ["doctor", "--settings", "x.json"])),
        (["-m", "other"], ("cli", ["other"])),
    ],
)
def test_parse(argv, expected):
    assert bundle.parse(argv) == expected


def test_main_runs_hook_and_always_returns_zero(pet_home, monkeypatch):
    calls = []
    monkeypatch.setattr("bao.hook.main", lambda args: calls.append(args) or 1)
    assert bundle.main(["-I", "-m", "bao.hook", "Stop"]) == 0
    assert calls == [["Stop"]]


def test_main_code_probe():
    assert bundle.main(["-I", "-c", "import bao.hook"]) == 0
    with pytest.raises(ImportError):
        bundle.main(["-c", "import bao.does_not_exist"])


def test_main_cli(pet_home, capsys):
    assert bundle.main(["-I", "-m", "bao", "status"]) == 1  # nothing running
    assert "not running" in capsys.readouterr().err


def test_hook_helper_hands_other_commands_to_the_app(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "executable", str(tmp_path / "bao-hook"))
    execs = []
    monkeypatch.setattr(bundle.os, "execv", lambda path, argv: execs.append((path, argv)))
    bundle.hook_main(["-I", "-m", "bao", "run", "--initial-event", "{}"])
    app = str(tmp_path / "Bao")
    assert execs == [(app, [app, "-I", "-m", "bao", "run", "--initial-event", "{}"])]


def test_hook_helper_runs_the_hook_itself(pet_home, monkeypatch):
    monkeypatch.setattr(bundle.os, "execv", lambda *a: pytest.fail("should not exec"))
    calls = []
    monkeypatch.setattr("bao.hook.main", lambda args: calls.append(args))
    assert bundle.hook_main(["-I", "-m", "bao.hook"]) == 0
    assert calls == [[]]


def test_hook_python_uses_helper_when_frozen(monkeypatch, tmp_path):
    macos = tmp_path / "Bao.app" / "Contents" / "MacOS"
    macos.mkdir(parents=True)
    (macos / "Bao").touch()
    monkeypatch.setattr(sys, "executable", str(macos / "Bao"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert installer.hook_python() == str(macos / "Bao")  # no helper: fall back to the app
    (macos / "bao-hook").touch()
    assert installer.hook_python() == str(macos / "bao-hook")
    assert installer.hook_command() == installer.hook_command(str(macos / "bao-hook"))


def test_hook_python_is_sys_executable_when_not_frozen(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert installer.hook_python() == sys.executable


def test_setup_needed(tmp_path):
    path = tmp_path / "settings.json"
    assert installer.setup_needed(path, python="/a/bao-hook") == "missing"
    installer.install(path, python="/a/bao-hook")
    assert installer.setup_needed(path, python="/a/bao-hook") is None
    assert installer.setup_needed(path, python="/moved/bao-hook") == "elsewhere"
    data = json.loads(path.read_text())
    del data["hooks"]["Stop"]
    path.write_text(json.dumps(data))
    assert installer.setup_needed(path, python="/a/bao-hook") == "missing"


# --- first-launch dialog -----------------------------------------------------------------


class FakeBox:
    """Stands in for QMessageBox: clicks `choice` ("Connect" / "Not Now")."""

    choice = "Connect"
    shown: list[str] = []
    notes: list[str] = []

    def __init__(self, _parent=None):
        self.buttons = {}
        self.clicked = None

    def setWindowTitle(self, _t):
        pass

    def setText(self, t):
        FakeBox.shown.append(t)

    def setInformativeText(self, _t):
        pass

    def addButton(self, label, _role):
        self.buttons[label] = object()
        return self.buttons[label]

    def setDefaultButton(self, _b):
        pass

    def exec(self):
        self.clicked = self.buttons[FakeBox.choice]

    def clickedButton(self):
        return self.clicked

    @staticmethod
    def information(_p, _t, text):
        FakeBox.notes.append(text)

    @staticmethod
    def warning(_p, _t, text):
        FakeBox.notes.append("warning: " + text)

    class ButtonRole:
        AcceptRole = RejectRole = None


@pytest.fixture
def dialog(monkeypatch, tmp_path):
    pytest.importorskip("PySide6")
    from bao import app

    settings = tmp_path / "settings.json"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(installer, "hook_python", lambda: "/Apps/Bao.app/Contents/MacOS/bao-hook")
    monkeypatch.setattr(app, "QMessageBox", FakeBox)
    monkeypatch.setattr(app.platform_mac, "bring_to_front", lambda: None)
    FakeBox.shown, FakeBox.notes = [], []
    return app, settings


def test_offer_setup_installs_on_connect(dialog):
    app, settings = dialog
    FakeBox.choice = "Connect"
    app.offer_hook_setup()
    assert FakeBox.shown == ["Connect Bao to Claude Code?"]
    assert installer.setup_needed(settings) is None
    assert FakeBox.notes and "All set" in FakeBox.notes[0]
    app.offer_hook_setup()  # already set up: no second dialog
    assert len(FakeBox.shown) == 1


def test_offer_setup_not_now_changes_nothing(dialog):
    app, settings = dialog
    FakeBox.choice = "Not Now"
    app.offer_hook_setup()
    assert not settings.exists()


def test_offer_setup_after_moving_the_app(dialog):
    app, settings = dialog
    installer.install(settings, python="/old/place/bao-hook")
    FakeBox.choice = "Connect"
    app.offer_hook_setup()
    assert FakeBox.shown == ["Point Claude Code at this copy of Bao?"]
    assert installer.setup_needed(settings) is None
