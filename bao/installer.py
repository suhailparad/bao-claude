"""Add/remove bao hooks in Claude Code's settings.json. No Qt.

Our entries are recognised by ``HOOK_MARKER`` in the command, so install is idempotent
(re-running replaces them, e.g. after moving the venv) and other hooks are never touched.
A backup (``settings.json.bak``) is written before every change.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HOOK_MARKER = "bao.hook"
# Commands from before the rename to bao; still recognised so install/uninstall replace them.
LEGACY_MARKERS = ("claude_pet.hook",)
HOOK_TIMEOUT = 5  # seconds; the hook normally finishes in ~40 ms

# event -> matcher (None = event has no matcher)
HOOK_EVENTS: dict[str, str | None] = {
    "SessionStart": None,
    "UserPromptSubmit": None,
    "PreToolUse": "*",
    "PostToolUse": "*",
    "Notification": None,
    "Stop": None,
    "SubagentStop": None,
    "PreCompact": None,
    "SessionEnd": None,
}


class SettingsError(RuntimeError):
    pass


def default_settings_path() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(base) if base else Path.home() / ".claude") / "settings.json"


def hook_python() -> str:
    """The executable that runs the hook: the venv's python, or Bao.app's fast helper."""
    if getattr(sys, "frozen", False):
        helper = Path(sys.executable).with_name("bao-hook")  # see bao.bundle.hook_main
        if helper.exists():
            return str(helper)
    return sys.executable


def hook_command(python: str | None = None) -> str:
    # Keep the venv path as-is (don't resolve symlinks: that would lose the venv).
    return f"{shlex.quote(python or hook_python())} -I -m {HOOK_MARKER}"


def _is_ours(hook: Any) -> bool:
    if not isinstance(hook, dict):
        return False
    command = str(hook.get("command", ""))
    return any(m in command for m in (HOOK_MARKER, *LEGACY_MARKERS))


def load_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text() or "{}")
    except ValueError as exc:
        raise SettingsError(f"{path} is not valid JSON ({exc}); not changing it") from exc
    if not isinstance(data, dict):
        raise SettingsError(f"{path} does not contain a JSON object; not changing it")
    if "hooks" in data and not isinstance(data["hooks"], dict):
        raise SettingsError(f"'hooks' in {path} is not an object; not changing it")
    return data


def strip_ours(settings: dict[str, Any]) -> int:
    """Remove our hook entries in place. Returns how many were removed."""
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return 0
    removed = 0
    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        kept_groups = []
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                kept_groups.append(group)
                continue
            kept = [h for h in group["hooks"] if not _is_ours(h)]
            removed += len(group["hooks"]) - len(kept)
            if kept:
                kept_groups.append({**group, "hooks": kept})
        if kept_groups:
            hooks[event] = kept_groups
        else:
            del hooks[event]
    if not hooks:
        del settings["hooks"]
    return removed


def add_ours(settings: dict[str, Any], command: str) -> None:
    hooks = settings.setdefault("hooks", {})
    for event, matcher in HOOK_EVENTS.items():
        group: dict[str, Any] = {}
        if matcher is not None:
            group["matcher"] = matcher
        group["hooks"] = [{"type": "command", "command": command, "timeout": HOOK_TIMEOUT}]
        hooks.setdefault(event, []).append(group)


def _write(path: Path, settings: dict[str, Any]) -> Path | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if path.exists():
        backup = path.with_name(path.name + ".bak")
        shutil.copy2(path, backup)
    tmp = path.with_name(path.name + ".bao.tmp")
    tmp.write_text(json.dumps(settings, indent=2) + "\n")
    os.replace(tmp, path)
    return backup


@dataclass
class Result:
    path: Path
    changed: bool
    removed: int = 0
    added: int = 0
    backup: Path | None = None
    command: str = ""


def install(path: Path | None = None, python: str | None = None) -> Result:
    path = path or default_settings_path()
    settings = load_settings(path)
    before = json.dumps(settings, sort_keys=True)
    command = hook_command(python)
    removed = strip_ours(settings)
    add_ours(settings, command)
    if json.dumps(settings, sort_keys=True) == before:
        return Result(path, changed=False, command=command)
    backup = _write(path, settings)
    return Result(path, True, removed, len(HOOK_EVENTS), backup, command)


def uninstall(path: Path | None = None) -> Result:
    path = path or default_settings_path()
    settings = load_settings(path)
    removed = strip_ours(settings)
    if not removed:
        return Result(path, changed=False)
    backup = _write(path, settings)
    return Result(path, True, removed=removed, backup=backup)


@dataclass
class HookStatus:
    path: Path
    installed: dict[str, list[str]] = field(default_factory=dict)  # event -> our commands

    @property
    def missing(self) -> list[str]:
        return [e for e in HOOK_EVENTS if e not in self.installed]


def status(path: Path | None = None) -> HookStatus:
    path = path or default_settings_path()
    st = HookStatus(path)
    hooks = load_settings(path).get("hooks") or {}
    for event, groups in hooks.items():
        for group in groups if isinstance(groups, list) else []:
            for h in group.get("hooks", []) if isinstance(group, dict) else []:
                if _is_ours(h):
                    st.installed.setdefault(event, []).append(str(h["command"]))
    return st


def setup_needed(path: Path | None = None, python: str | None = None) -> str | None:
    """Why the hooks should be (re)installed for this copy of bao, or None if they're fine.

    ``"missing"``: no hooks, or some events lack them. ``"elsewhere"``: they run another
    Python/app (e.g. Bao.app was moved, or they point at a dev venv).
    """
    st = status(path)
    if not st.installed or st.missing:
        return "missing"
    command = hook_command(python)
    if any(c != command for cmds in st.installed.values() for c in cmds):
        return "elsewhere"
    return None
