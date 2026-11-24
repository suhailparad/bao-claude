import json

import pytest

from bao import installer

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
