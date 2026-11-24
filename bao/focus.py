"""Bring the terminal that runs a Claude Code session to the front. No Qt.

The hook records where a session lives (``terminal_info()``: the terminal app's bundle id
and the session's tty). Clicking the pet calls ``focus_terminal()`` with that info:

* Terminal.app and iTerm2 → AppleScript selects the exact window/tab with that tty
  (falls back to just activating the app if the tab can't be found).
* Any other app → ``open -b <bundle id>`` brings it to the front.

macOS only; elsewhere these are no-ops. ``terminal_info`` is stdlib-only (used by the hook).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from typing import Any

IS_MAC = sys.platform == "darwin"

TERMINAL_APP = "com.apple.Terminal"
ITERM_APP = "com.googlecode.iterm2"

# TERM_PROGRAM → bundle id, for when __CFBundleIdentifier isn't inherited.
TERM_PROGRAM_APPS = {
    "Apple_Terminal": TERMINAL_APP,
    "iTerm.app": ITERM_APP,
    "vscode": "com.microsoft.VSCode",
    "WezTerm": "com.github.wez.wezterm",
    "ghostty": "com.mitchellh.ghostty",
    "WarpTerminal": "dev.warp.Warp-Stable",
}

_BUNDLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]{1,200}$")
_TTY_RE = re.compile(r"^/dev/ttys?\d{1,4}$")
_MAX_ANCESTORS = 6
_TTY_BUDGET = 0.08  # seconds for the whole walk; the hook must stay fast


def _find_tty(pid: int) -> str | None:
    """Walk up from ``pid`` until a process with a controlling terminal is found."""
    deadline = time.monotonic() + _TTY_BUDGET
    for _ in range(_MAX_ANCESTORS):
        left = deadline - time.monotonic()
        if pid <= 1 or left <= 0:
            return None
        out = subprocess.run(  # noqa: S603 - fixed argv
            ["/bin/ps", "-o", "ppid=,tty=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=left,
        ).stdout.split()
        if len(out) != 2:
            return None
        ppid, tty = out
        if tty not in ("??", "?", "-"):
            return tty if tty.startswith("/dev/") else f"/dev/{tty}"
        pid = int(ppid)
    return None


def terminal_info(env: dict[str, str] | None = None) -> dict[str, str]:
    """Describe the terminal this process runs in. Never raises; may return {}."""
    env = os.environ if env is None else env
    info: dict[str, str] = {}
    try:
        app = env.get("__CFBundleIdentifier") or TERM_PROGRAM_APPS.get(
            env.get("TERM_PROGRAM", ""), ""
        )
        if app and _BUNDLE_RE.match(app):
            info["app"] = app
        if IS_MAC:
            tty = _find_tty(os.getppid())
            if tty and _TTY_RE.match(tty):
                info["tty"] = tty
    except Exception:
        pass
    return info


def _terminal_script(tty: str) -> str:
    return f'''
tell application id "{TERMINAL_APP}"
  repeat with w in windows
    repeat with t in tabs of w
      if tty of t is "{tty}" then
        set selected of t to true
        set index of w to 1
        activate
        return
      end if
    end repeat
  end repeat
  activate
end tell'''


def _iterm_script(tty: str) -> str:
    return f'''
tell application id "{ITERM_APP}"
  repeat with w in windows
    repeat with t in tabs of w
      repeat with s in sessions of t
        if tty of s is "{tty}" then
          select w
          select t
          select s
          activate
          return
        end if
      end repeat
    end repeat
  end repeat
  activate
end tell'''


def focus_command(info: Any) -> list[str] | None:
    """The argv that focuses the terminal described by ``info``, or None if unknown."""
    if not isinstance(info, dict):
        return None
    app, tty = info.get("app"), info.get("tty")
    app = app if isinstance(app, str) and _BUNDLE_RE.match(app) else None
    tty = tty if isinstance(tty, str) and _TTY_RE.match(tty) else None
    if app == TERMINAL_APP and tty:
        return ["/usr/bin/osascript", "-e", _terminal_script(tty)]
    if app == ITERM_APP and tty:
        return ["/usr/bin/osascript", "-e", _iterm_script(tty)]
    if app:
        return ["/usr/bin/open", "-b", app]
    return None


def focus_terminal(info: Any) -> bool:
    """Start focusing the session's terminal in the background. True if something ran."""
    if not IS_MAC:
        return False
    argv = focus_command(info)
    if argv is None:
        return False
    try:
        subprocess.Popen(  # noqa: S603 - argv built from validated values
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except OSError:
        return False
