"""Claude Code hook entry point.

Claude Code runs this for every hook event with a JSON payload on stdin; it forwards
a compact message to the pet app over the local socket.

GOLDEN RULE: always exit 0, never write to stdout, finish fast. Stdlib only, no Qt.

Usage (registered by ``bao install-hooks``):
    /path/to/.venv/bin/python -I -m bao.hook
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .desktop import gui_python
from .focus import terminal_info
from .ipc import PROTOCOL_VERSION, send_message

SEND_TIMEOUT = 0.2
LAUNCH_EVENTS = {"SessionStart"}
# Events that record which terminal the session runs in (costs a few ms of `ps`).
TERMINAL_EVENTS = {"SessionStart", "UserPromptSubmit"}


def read_payload() -> dict[str, Any]:
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return {}
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def build_message(payload: dict[str, Any], event_override: str | None = None) -> dict[str, Any]:
    event = event_override or payload.get("hook_event_name") or ""
    msg: dict[str, Any] = {
        "v": PROTOCOL_VERSION,
        "event": event,
        "session_id": str(payload.get("session_id") or "default"),
        "cwd": payload.get("cwd") or os.getcwd(),
        "tool_name": payload.get("tool_name"),
        "notification_type": payload.get("notification_type"),
        "message": payload.get("message"),
        "source": payload.get("source"),
        "reason": payload.get("reason"),
        "ts": time.time(),
    }
    if event in TERMINAL_EVENTS:
        msg["terminal"] = terminal_info()
    return msg


def launch_pet(initial: dict[str, Any]) -> None:
    """Start the pet app detached, handing it the event that we couldn't deliver."""
    kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        # No console window, and not killed when Claude Code's console closes.
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0x8) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200
        )
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        [
            gui_python(sys.executable),
            "-I",
            "-m",
            "bao",
            "run",
            "--initial-event",
            json.dumps(initial),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(Path.home()),
        close_fds=True,
        **kwargs,
    )


def main(argv: list[str] | None = None) -> int:
    try:
        args = sys.argv[1:] if argv is None else argv
        msg = build_message(read_payload(), args[0] if args else None)
        if not msg["event"]:
            return 0
        try:
            send_message(msg, timeout=SEND_TIMEOUT)
        except OSError:
            if msg["event"] in LAUNCH_EVENTS and not os.environ.get("BAO_NO_LAUNCH"):
                launch_pet(msg)
    except Exception:
        pass  # never let the pet interfere with Claude Code
    return 0


if __name__ == "__main__":
    main()
    sys.exit(0)
