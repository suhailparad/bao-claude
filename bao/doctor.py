"""`python -m bao doctor`: check the whole setup and say what to fix."""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

from . import desktop, focus, installer
from .character import discover_characters
from .config import Config
from .ipc import send_message
from .paths import config_path, home_dir, log_path
from .sessions import State

OK, WARN, BAD = "✓", "!", "✗"


def _line(mark: str, text: str) -> None:
    print(f"  {mark} {text}")


def _desktop_checks() -> int:
    """Per-OS notes: what works here and what needs an extra package."""
    if desktop.IS_MAC:
        _line(OK, "macOS: Dock-less floating window, AppleScript/`open` for click-to-focus")
        return 0
    if desktop.IS_WINDOWS:
        _line(OK, "Windows: talks to the pet over localhost TCP (token in ~/.bao/pet.port)")
        _line(OK, "click-to-focus uses the Win32 API (no extra tools needed)")
        return 0
    import os

    session = os.environ.get("XDG_SESSION_TYPE") or (
        "wayland"
        if os.environ.get("WAYLAND_DISPLAY")
        else "x11"
        if os.environ.get("DISPLAY")
        else "none"
    )
    if session == "wayland" and not os.environ.get("DISPLAY"):
        _line(WARN, "Wayland without XWayland: the pet can't remember its spot or wander")
    elif session == "wayland":
        _line(OK, "Wayland: the pet runs through XWayland so it can place its window")
    elif session == "none":
        _line(WARN, "no graphical session found (DISPLAY / WAYLAND_DISPLAY unset)")
    else:
        _line(OK, "X11 session")
    tool = focus.linux_focus_tool()
    if tool:
        _line(OK, f"click-to-focus uses {Path(tool).name}")
    else:
        _line(WARN, "click-to-focus needs xdotool or wmctrl: sudo apt install xdotool")
    return 0


def run_doctor(settings: Path | None = None) -> int:
    problems = 0
    print(f"bao doctor  (python {sys.version.split()[0]} at {sys.executable})")

    print(f"\nDesktop  ({desktop.os_name()})")
    problems += _desktop_checks()

    print("\nCharacters")
    chars = discover_characters()
    if not chars:
        _line(BAD, "no usable characters found; run: python tools/gen_panda.py")
        problems += 1
    for c in chars.values():
        missing = [s.value for s in State if s.value not in c.animations]
        note = f"; falls back to {c.fallback_state} for: {', '.join(missing)}" if missing else ""
        _line(
            OK if not missing else WARN,
            f"{c.name} ({c.id}): {len(c.animations)} animations, {len(c.sounds)} sounds{note}",
        )

    cfg = Config.load()
    print(f"\nConfig  ({config_path()})")
    if cfg.character not in chars:
        _line(WARN, f"character {cfg.character!r} not found; the first available one is used")
    sound = "muted" if cfg.muted else f"volume {int(cfg.volume * 100)}%"
    off = f", off: {', '.join(cfg.muted_cues)}" if cfg.muted_cues else ""
    _line(OK, f"character={cfg.character}, size={cfg.scale}, sound {sound}{off}")

    print("\nClaude Code hooks")
    try:
        st = installer.status(settings)
    except installer.SettingsError as exc:
        _line(BAD, str(exc))
        return 1
    plugin_hooks = installer.plugin_hook_paths(st.path.parent)
    if not st.installed and plugin_hooks:
        _line(OK, f"provided by the bao Claude Code plugin ({plugin_hooks[-1].parent.parent})")
    elif not st.installed:
        _line(
            BAD,
            f"not installed in {st.path}; run: python -m bao install-hooks"
            " (or install the bao Claude Code plugin)",
        )
        problems += 1
    else:
        if plugin_hooks:
            _line(
                WARN,
                "the bao plugin is installed too; its hooks stand down while these exist"
                " (run uninstall-hooks to let the plugin take over)",
            )
        if st.missing:
            _line(WARN, f"missing events: {', '.join(st.missing)} (re-run install-hooks)")
        else:
            _line(OK, f"all {len(installer.HOOK_EVENTS)} events registered in {st.path}")
        commands = {c for cmds in st.installed.values() for c in cmds}
        for cmd in sorted(commands):
            argv = shlex.split(cmd)
            if not Path(argv[0]).exists():
                _line(BAD, f"hook python not found: {argv[0]} (re-run install-hooks)")
                problems += 1
                continue
            probe = subprocess.run(
                [argv[0], "-I", "-c", "import bao.hook"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if probe.returncode != 0:
                _line(BAD, f"hook python cannot import bao: {argv[0]}")
                problems += 1
            else:
                _line(OK, f"hook command works: {cmd}")

    print(f"\nPet app  ({home_dir()})")
    try:
        reply = send_message({"cmd": "status"}, timeout=1.0, expect_reply=True) or {}
        d = reply.get("display", {})
        _line(OK, f"running, showing {d.get('state')!r} for {d.get('session_count')} session(s)")
    except OSError:
        _line(
            WARN,
            "not running (it starts with the next `claude` session, or: python -m bao run)",
        )
    _line(OK, f"log: {log_path()}")

    print("\n" + ("All good!" if not problems else f"{problems} problem(s) found."))
    return 1 if problems else 0
