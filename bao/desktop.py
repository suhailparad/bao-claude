"""Small per-OS helpers (macOS, Linux, Windows). Stdlib only, no Qt.

Everything that differs between desktops lives here or in ``focus.py`` / ``ipc.py``,
so the rest of the app stays platform-neutral.
"""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Mapping, MutableMapping
from pathlib import Path

IS_MAC = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")

MAC_SOUNDS = Path("/System/Library/Sounds")
LINUX_SOUND_DIRS = (
    Path("/usr/share/sounds/freedesktop/stereo"),
    Path("/usr/share/sounds"),
)
LINUX_SOUND_EXTS = (".oga", ".ogg", ".wav")


def os_name() -> str:
    return "macOS" if IS_MAC else "Windows" if IS_WINDOWS else "Linux" if IS_LINUX else sys.platform


def windows_media_dir(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    return Path(env.get("WINDIR") or env.get("SystemRoot") or r"C:\Windows") / "Media"


def system_sound_path(name: str, platform: str | None = None) -> Path | None:
    """Resolve ``system:<name>`` to a file of the desktop's own sound theme.

    macOS: ``Glass`` → /System/Library/Sounds/Glass.aiff
    Linux: ``complete`` → /usr/share/sounds/freedesktop/stereo/complete.oga
    Windows: ``tada`` / ``Windows Notify`` → C:\\Windows\\Media\\tada.wav
    """
    platform = platform or sys.platform
    if not name or "/" in name or "\\" in name or ".." in name:
        return None
    candidates: list[Path] = []
    if platform == "darwin":
        candidates = [MAC_SOUNDS / f"{name}.aiff"]
    elif platform == "win32":
        candidates = [windows_media_dir() / f"{name}.wav"]
    else:
        for d in LINUX_SOUND_DIRS:
            for n in dict.fromkeys((name.lower(), name)):
                candidates += [d / f"{n}{ext}" for ext in LINUX_SOUND_EXTS]
    return next((p for p in candidates if p.is_file()), None)


def configure_qt_platform(env: MutableMapping[str, str] | None = None) -> str | None:
    """Pick a Qt platform plugin before QApplication starts. Returns what it set, if any.

    On a Wayland session apps can't place their own windows (no dragging to a saved
    spot, no wandering), so prefer X11 through XWayland and fall back to Wayland.
    An explicit QT_QPA_PLATFORM always wins.
    """
    env = os.environ if env is None else env
    if env.get("QT_QPA_PLATFORM"):
        return None
    if IS_LINUX and env.get("WAYLAND_DISPLAY") and env.get("DISPLAY"):
        env["QT_QPA_PLATFORM"] = "xcb;wayland"
        return env["QT_QPA_PLATFORM"]
    return None


def gui_python(python: str) -> str:
    """On Windows, the console-less ``pythonw.exe`` next to ``python.exe`` (if present)."""
    if not IS_WINDOWS:
        return python
    p = Path(python)
    w = p.with_name("pythonw.exe")
    return str(w) if p.name.lower() == "python.exe" and w.is_file() else python


def which(*names: str) -> str | None:
    """First of ``names`` found on PATH."""
    return next((path for n in names if (path := shutil.which(n))), None)
