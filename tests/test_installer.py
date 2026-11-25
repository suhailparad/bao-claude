import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from bao import installer


@pytest.fixture(autouse=True)
def posix_hook_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    """Expected commands below are POSIX-quoted; Windows quoting has its own test."""
    monkeypatch.setattr(installer, "IS_WINDOWS", False)


OTHER = {"type": "command", "command": "afplay /System/Library/Sounds/Glass.aiff"}


def write(path, data):
    path.write_text(json.dumps(data))


def read(path):
    return json.loads(path.read_text())


def test_install_into_missing_file(tmp_path):
    path = tmp_path / "settings.json"
    res = installer.install(path, python="/venv/bin/python")
    assert res.changed and res.backup is None
    hooks = read(path)["hooks"]
    assert set(hooks) == set(installer.HOOK_EVENTS)
    assert hooks["PreToolUse"][0]["matcher"] == "*"
    assert "matcher" not in hooks["Stop"][0]
    h = hooks["Stop"][0]["hooks"][0]
    assert h == {
        "type": "command",
        "command": "/venv/bin/python -I -m bao.hook",
        "timeout": installer.HOOK_TIMEOUT,
    }


def test_preserves_other_settings_and_hooks_and_backs_up(tmp_path):
    path = tmp_path / "settings.json"
    original = {"theme": "dark", "hooks": {"Stop": [{"hooks": [OTHER]}]}}
    write(path, original)
    res = installer.install(path, python="/venv/bin/python")
    data = read(path)
    assert data["theme"] == "dark"
    assert data["hooks"]["Stop"][0] == {"hooks": [OTHER]}  # untouched, ours appended
    assert len(data["hooks"]["Stop"]) == 2
    assert read(res.backup) == original


def test_install_is_idempotent_and_updates_python(tmp_path):
    path = tmp_path / "settings.json"
    installer.install(path, python="/old/python")
    assert not installer.install(path, python="/old/python").changed
    res = installer.install(path, python="/new venv/python")
    assert res.changed and res.removed == len(installer.HOOK_EVENTS)
    cmds = [h["command"] for g in read(path)["hooks"]["Stop"] for h in g["hooks"]]
    assert cmds == ["'/new venv/python' -I -m bao.hook"]  # quoted, no duplicates


def test_uninstall_restores_original(tmp_path):
    path = tmp_path / "settings.json"
    original = {"theme": "dark", "hooks": {"Stop": [{"hooks": [OTHER]}]}}
    write(path, original)
    installer.install(path, python="/venv/bin/python")
    res = installer.uninstall(path)
    assert res.changed and res.removed == len(installer.HOOK_EVENTS)
    assert read(path) == original
    assert not installer.uninstall(path).changed


def test_uninstall_removes_empty_hooks_key(tmp_path):
    path = tmp_path / "settings.json"
    write(path, {"theme": "dark"})
    installer.install(path, python="/p")
    installer.uninstall(path)
    assert read(path) == {"theme": "dark"}


def test_mixed_group_keeps_other_hook(tmp_path):
    path = tmp_path / "settings.json"
    ours = {"type": "command", "command": "/p -I -m bao.hook"}
    write(path, {"hooks": {"Stop": [{"hooks": [OTHER, ours]}]}})
    installer.uninstall(path)
    assert read(path) == {"hooks": {"Stop": [{"hooks": [OTHER]}]}}


@pytest.mark.parametrize("content", ["{broken", "[1, 2]", '{"hooks": []}'])
def test_refuses_to_touch_invalid_settings(tmp_path, content):
    path = tmp_path / "settings.json"
    path.write_text(content)
    with pytest.raises(installer.SettingsError):
        installer.install(path)
    assert path.read_text() == content
    assert not (tmp_path / "settings.json.bak").exists()


def test_status(tmp_path):
    path = tmp_path / "settings.json"
    assert installer.status(path).missing == list(installer.HOOK_EVENTS)
    installer.install(path, python="/p")
    st = installer.status(path)
    assert st.missing == [] and st.installed["Stop"] == ["/p -I -m bao.hook"]


def test_install_replaces_pre_rename_hooks(tmp_path):
    path = tmp_path / "settings.json"
    legacy = {"type": "command", "command": "/venv/bin/python -I -m claude_pet.hook"}
    write(path, {"hooks": {"Stop": [{"hooks": [legacy]}, {"hooks": [OTHER]}]}})
    res = installer.install(path, python="/venv/bin/python")
    assert res.removed == 1
    cmds = [h["command"] for g in read(path)["hooks"]["Stop"] for h in g["hooks"]]
    assert sorted(cmds) == sorted([OTHER["command"], "/venv/bin/python -I -m bao.hook"])


def _fake_plugin(config_dir: Path) -> Path:
    hook = config_dir / "plugins/cache/bao/bao/0.1.0/hooks/bao-hook"
    hook.parent.mkdir(parents=True)
    hook.write_text("#!/bin/sh\n")
    return hook


def test_plugin_hooks_count_as_set_up(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    assert installer.setup_needed(settings, python="/x/python") == "missing"
    hook = _fake_plugin(tmp_path)
    assert installer.plugin_hook_paths(tmp_path) == [hook]
    assert installer.setup_needed(settings, python="/x/python") is None


SH = shutil.which("sh")
HOOK_SCRIPT = Path(__file__).resolve().parents[1] / "hooks" / "bao-hook"


def _run_plugin_hook(tmp_path: Path, **env: str) -> subprocess.CompletedProcess[bytes]:
    base = {"HOME": str(tmp_path), "BAO_HOME": str(tmp_path / "b"), "PATH": os.environ["PATH"]}
    return subprocess.run(
        [SH, str(HOOK_SCRIPT)],
        input=b'{"hook_event_name":"Stop"}',
        capture_output=True,
        env={**base, **env},
        timeout=10,
    )


@pytest.mark.skipif(SH is None, reason="needs sh (Git Bash on Windows)")
def test_plugin_hook_script_finishes_quietly_without_runtime(tmp_path: Path) -> None:
    out = _run_plugin_hook(tmp_path)
    assert out.returncode == 0 and out.stdout == b""


@pytest.mark.skipif(SH is None, reason="needs sh (Git Bash on Windows)")
def test_plugin_hook_script_runs_linked_runtime(tmp_path: Path) -> None:
    # A fake runtime that records its argv and stdin; Windows-style line ending on purpose.
    log = tmp_path / "called"
    fake = tmp_path / "fake-python"
    fake.write_text(f'#!/bin/sh\necho "$@" > "{log.as_posix()}"\ncat >> "{log.as_posix()}"\n')
    fake.chmod(0o755)
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "runtime").write_bytes(fake.as_posix().encode() + b"\r\n")
    out = _run_plugin_hook(tmp_path)
    assert out.returncode == 0 and out.stdout == b""
    assert log.read_text().splitlines() == ["-I -m bao.hook", '{"hook_event_name":"Stop"}']

    # Hooks from install-hooks in settings.json: the plugin stands down.
    log.unlink()
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text('{"x": "py -I -m bao.hook"}')
    assert _run_plugin_hook(tmp_path).returncode == 0
    assert not log.exists()


def test_link_plugin_writes_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BAO_HOME", str(tmp_path))
    path = installer.link_plugin(r"C:\Users\Me\.venv\Scripts\python.exe")
    assert path.read_bytes() == b"C:/Users/Me/.venv/Scripts/python.exe\n"


def test_plugin_hooks_json_matches_install_hooks() -> None:
    data = json.loads((HOOK_SCRIPT.parent / "hooks.json").read_text())
    assert set(data["hooks"]) == set(installer.HOOK_EVENTS)
    for event, matcher in installer.HOOK_EVENTS.items():
        (group,) = data["hooks"][event]
        assert group.get("matcher") == matcher


def test_hook_command_per_platform():
    from bao.installer import hook_command

    assert hook_command("/opt/my venv/bin/python", windows=False) == (
        "'/opt/my venv/bin/python' -I -m bao.hook"
    )
    win = hook_command(r"C:\Users\Me\bao\.venv\Scripts\python.exe", windows=True)
    assert win == '"C:/Users/Me/bao/.venv/Scripts/python.exe" -I -m bao.hook'
    import shlex

    assert shlex.split(win)[0] == "C:/Users/Me/bao/.venv/Scripts/python.exe"  # doctor parses it


def test_configure_qt_platform():
    from bao import desktop

    env = {"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}
    expected = "xcb;wayland" if desktop.IS_LINUX else None
    assert desktop.configure_qt_platform(env) == expected
    assert desktop.configure_qt_platform({"QT_QPA_PLATFORM": "offscreen"}) is None
