"""Bring the terminal that runs a Claude Code session to the front. No Qt.

The hook records where a session lives (``terminal_info()``); clicking the pet calls
``focus_terminal()`` with that info.

macOS: the terminal app's bundle id and the session's tty.
  * Terminal.app and iTerm2 → AppleScript selects the exact window/tab with that tty.
  * Any other app → ``open -b <bundle id>`` brings it to the front.
Linux (X11 / XWayland): the session's ancestor process ids (and ``$WINDOWID`` if set).
  * ``xdotool`` or ``wmctrl`` activates a window owned by the nearest ancestor
    (the terminal emulator). Without either tool, clicking does nothing.
Windows: the ancestor process ids and the console window handle.
  * The Win32 API brings the nearest ancestor's window (Windows Terminal, VS Code, …)
    or the classic console window to the front.

``terminal_info`` is stdlib-only and fast: the hook calls it.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Any

IS_MAC = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")

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
_MAX_PIDS = 10


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


def _linux_ancestors(pid: int, proc: str = "/proc") -> list[int]:
    """``pid`` and its parents (nearest first), read from /proc without subprocesses."""
    chain: list[int] = []
    while pid > 1 and len(chain) < _MAX_PIDS:
        chain.append(pid)
        try:
            with open(f"{proc}/{pid}/stat") as fh:
                stat = fh.read()
            pid = int(stat[stat.rindex(")") + 2 :].split()[1])  # comm may hold spaces/parens
        except (OSError, ValueError, IndexError):
            break
    return chain


def _windows_ancestors(pid: int) -> list[int]:
    """``pid`` and its parents (nearest first), from one Toolhelp process snapshot."""
    import ctypes
    from ctypes import wintypes

    class ProcessEntry(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_void_p),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if not snapshot or snapshot == wintypes.HANDLE(-1).value:
        return [pid]
    parents: dict[int, int] = {}
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(ProcessEntry)
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            parents[entry.th32ProcessID] = entry.th32ParentProcessID
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    chain = [pid]
    while len(chain) < _MAX_PIDS and parents.get(chain[-1], 0) not in (0, *chain):
        chain.append(parents[chain[-1]])
    return chain


def terminal_info(env: dict[str, str] | None = None) -> dict[str, Any]:
    """Describe the terminal this process runs in. Never raises; may return {}."""
    env = os.environ if env is None else env
    info: dict[str, Any] = {}
    try:
        if IS_MAC or "__CFBundleIdentifier" in env or "TERM_PROGRAM" in env:
            app = env.get("__CFBundleIdentifier") or TERM_PROGRAM_APPS.get(
                env.get("TERM_PROGRAM", ""), ""
            )
            if app and _BUNDLE_RE.match(app):
                info["app"] = app
        if IS_MAC:
            tty = _find_tty(os.getppid())
            if tty and _TTY_RE.match(tty):
                info["tty"] = tty
        elif IS_LINUX:
            info["pids"] = _linux_ancestors(os.getppid())
            if env.get("WINDOWID", "").isdigit():
                info["windowid"] = int(env["WINDOWID"])
        elif IS_WINDOWS:
            import ctypes

            info["pids"] = _windows_ancestors(os.getppid())
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()  # type: ignore[attr-defined]
            if hwnd:
                info["console"] = int(hwnd)
    except Exception:
        pass
    return info


def clean_info(info: Any) -> dict[str, Any]:
    """Keep only well-formed fields of a ``terminal_info`` dict (it crossed a socket)."""
    if not isinstance(info, dict):
        return {}
    out: dict[str, Any] = {}
    for key in ("app", "tty"):
        if isinstance(info.get(key), str):
            out[key] = info[key]
    pids = info.get("pids")
    if isinstance(pids, list):
        ok = [p for p in pids if isinstance(p, int) and not isinstance(p, bool) and p > 0]
        if ok:
            out["pids"] = ok[:_MAX_PIDS]
    for key in ("windowid", "console"):
        v = info.get(key)
        if isinstance(v, int) and not isinstance(v, bool) and v > 0:
            out[key] = v
    return out


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
    info = clean_info(info)
    if IS_WINDOWS:
        return _focus_windows(info)
    if IS_LINUX:
        if not (info.get("pids") or info.get("windowid")) or not linux_focus_tool():
            return False
        threading.Thread(target=_focus_linux, args=(info,), daemon=True).start()
        return True
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


# -- Linux ------------------------------------------------------------------------------


def linux_focus_tool() -> str | None:
    """``xdotool`` or ``wmctrl`` if installed (needed to raise another app's window)."""
    return shutil.which("xdotool") or shutil.which("wmctrl")


def _run(argv: list[str]) -> str:
    return subprocess.run(  # noqa: S603 - argv from validated ints
        argv, capture_output=True, text=True, timeout=2, stdin=subprocess.DEVNULL
    ).stdout


def parse_wmctrl(listing: str) -> list[tuple[int, int]]:
    """``wmctrl -lp`` lines → [(window id, pid)]."""
    out = []
    for line in listing.splitlines():
        parts = line.split(None, 3)
        if len(parts) >= 3:
            try:
                out.append((int(parts[0], 16), int(parts[2])))
            except ValueError:
                continue
    return out


def _focus_linux(info: dict[str, Any]) -> None:
    try:
        xdotool, wmctrl = shutil.which("xdotool"), shutil.which("wmctrl")
        window = info.get("windowid")
        if window is None and xdotool:
            for pid in info.get("pids", []):
                found = _run([xdotool, "search", "--onlyvisible", "--pid", str(pid)]).split()
                if found:
                    window = int(found[-1])
                    break
        elif window is None and wmctrl:
            owners = parse_wmctrl(_run([wmctrl, "-lp"]))
            window = pick_window(owners, info.get("pids", []))
        if window is None:
            return
        if xdotool:
            _run([xdotool, "windowactivate", str(window)])
        elif wmctrl:
            _run([wmctrl, "-i", "-a", hex(window)])
    except (OSError, subprocess.SubprocessError, ValueError):
        pass


# -- Windows ----------------------------------------------------------------------------


def pick_window(
    windows: list[tuple[int, int]], pids: list[int], fallback: int | None = None
) -> int | None:
    """The window owned by the nearest ancestor in ``pids`` (windows = [(handle, pid)])."""
    owner: dict[int, int] = {}
    for handle, pid in windows:
        owner.setdefault(pid, handle)
    for pid in pids:
        if pid in owner:
            return owner[pid]
    return fallback


def _focus_windows(info: dict[str, Any]) -> bool:
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        windows: list[tuple[int, int]] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def collect(hwnd: int, _lparam: int) -> bool:
            if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                windows.append((int(hwnd), int(pid.value)))
            return True

        user32.EnumWindows(collect, 0)
        console = info.get("console")
        fallback = console if console and user32.IsWindowVisible(console) else None
        hwnd = pick_window(windows, info.get("pids", []), fallback)
        if hwnd is None:
            return False
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        return bool(user32.SetForegroundWindow(hwnd))
    except (OSError, AttributeError, ValueError):
        return False
