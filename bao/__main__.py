"""Command line interface: ``python -m bao <command>``."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from .ipc import PROTOCOL_VERSION, send_message

# Friendly names for `send`, mapped to (hook event, extra fields).
ALIASES: dict[str, tuple[str, dict[str, Any]]] = {
    "start": ("SessionStart", {"source": "startup"}),
    "thinking": ("UserPromptSubmit", {}),
    "prompt": ("UserPromptSubmit", {}),
    "working": ("PreToolUse", {"tool_name": "Task"}),
    "reading": ("PreToolUse", {"tool_name": "Read"}),
    "typing": ("PreToolUse", {"tool_name": "Edit"}),
    "running": ("PreToolUse", {"tool_name": "Bash"}),
    "tool-done": ("PostToolUse", {}),
    "permission": (
        "Notification",
        {
            "notification_type": "permission_prompt",
            "message": "Claude needs your permission to use Bash",
        },
    ),
    "waiting": (
        "Notification",
        {"notification_type": "idle_prompt", "message": "Claude is waiting for your input"},
    ),
    "done": ("Stop", {}),
    "compact": ("PreCompact", {}),
    "end": ("SessionEnd", {}),
}


def _not_running() -> int:
    print("bao is not running (start it with: python -m bao run)", file=sys.stderr)
    return 1


def cmd_run(args: argparse.Namespace) -> int:
    from .app import run  # imports Qt; keep it out of the light commands

    initial = json.loads(args.initial_event) if args.initial_event else None
    return run(initial_event=initial, verbose=args.verbose)


def cmd_send(args: argparse.Namespace) -> int:
    event, extra = ALIASES.get(args.event, (args.event, {}))
    msg: dict[str, Any] = {
        "v": PROTOCOL_VERSION,
        "event": event,
        "session_id": args.session,
        "cwd": args.cwd or os.getcwd(),
        "ts": time.time(),
        **extra,
    }
    if args.tool:
        msg["tool_name"] = args.tool
    if args.message:
        msg["message"] = args.message
    try:
        send_message(msg, timeout=1.0)
    except OSError:
        return _not_running()
    print(f"sent {event}" + (f" ({args.event})" if event != args.event else ""))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    try:
        reply = send_message({"cmd": "status"}, timeout=1.0, expect_reply=True)
    except OSError:
        return _not_running()
    print(json.dumps(reply, indent=2))
    return 0


def cmd_sound(args: argparse.Namespace) -> int:
    try:
        send_message({"cmd": "play", "cue": args.cue}, timeout=1.0, expect_reply=True)
    except OSError:
        return _not_running()
    print(f"asked the pet to play {args.cue!r} (respects mute and per-sound settings)")
    return 0


def cmd_quit(args: argparse.Namespace) -> int:
    try:
        send_message({"cmd": "quit"}, timeout=1.0, expect_reply=True)
    except OSError:
        return _not_running()
    print("bao quit")
    return 0


def cmd_install_hooks(args: argparse.Namespace) -> int:
    from . import installer

    try:
        res = installer.install(args.settings)
    except installer.SettingsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if not res.changed:
        print(f"hooks already installed in {res.path}")
    else:
        print(f"installed {res.added} hooks in {res.path}")
        if res.backup:
            print(f"backup: {res.backup}")
    print(f"hook command: {res.command}")
    print("start a new `claude` session to see the pet")
    return 0


def cmd_uninstall_hooks(args: argparse.Namespace) -> int:
    from . import installer

    try:
        res = installer.uninstall(args.settings)
    except installer.SettingsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if not res.changed:
        print(f"no bao hooks found in {res.path}")
    else:
        print(f"removed {res.removed} hooks from {res.path} (backup: {res.backup})")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from .doctor import run_doctor

    return run_doctor(args.settings)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bao", description="Desktop buddy for Claude Code")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="start the pet")
    r.add_argument("--initial-event", help=argparse.SUPPRESS)
    r.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    r.set_defaults(func=cmd_run)

    s = sub.add_parser("send", help="simulate a Claude Code event")
    s.add_argument("event", help=f"hook name or alias: {', '.join(ALIASES)}")
    s.add_argument("--session", default="manual", help="session id (default: manual)")
    s.add_argument("--cwd", help="project directory to report (default: current)")
    s.add_argument("--tool", help="tool name for PreToolUse")
    s.add_argument("--message", help="notification message")
    s.set_defaults(func=cmd_send)

    sub.add_parser("status", help="show what the pet is displaying").set_defaults(func=cmd_status)
    so = sub.add_parser("sound", help="play a sound cue through the running pet")
    so.add_argument("cue", nargs="?", default="done", help="hello | waiting | alert | done | bye")
    so.set_defaults(func=cmd_sound)

    for name, func, text in [
        ("install-hooks", cmd_install_hooks, "register the pet's hooks in Claude Code settings"),
        (
            "uninstall-hooks",
            cmd_uninstall_hooks,
            "remove the pet's hooks from Claude Code settings",
        ),
        ("doctor", cmd_doctor, "check that everything is set up"),
    ]:
        sp = sub.add_parser(name, help=text)
        sp.add_argument("--settings", type=Path, help="settings.json path (default: ~/.claude)")
        sp.set_defaults(func=func)

    sub.add_parser("quit", help="stop the running pet").set_defaults(func=cmd_quit)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
