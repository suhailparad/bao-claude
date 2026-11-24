"""Entry point of the bundled ``Bao.app`` (PyInstaller). Stdlib only until it dispatches.

The app's executable stands in for the venv's ``python`` everywhere bao calls itself, so the
hook command, the hook's launcher and ``doctor`` work unchanged:

    Bao -I -m bao.hook            → the Claude Code hook (fast path, no Qt)
    Bao -I -m bao run ...         → the CLI (``bao run``, ``bao doctor``, ...)
    Bao -I -c "import bao.hook"   → doctor's import probe
    Bao doctor                    → the CLI, for a ``bao`` symlink on PATH
    Bao                           → double-clicked in Finder: start the pet, offer hook setup
"""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence

APP_EXECUTABLE = "Bao"  # Contents/MacOS/Bao: the full app (Qt)

# Interpreter flags we accept (and ignore) so the binary can be called like python.
_IGNORED_FLAGS = {"-I", "-E", "-s", "-S", "-B", "-u"}


def parse(argv: Sequence[str]) -> tuple[str, list[str]]:
    """Split argv into (mode, rest). mode: ``hook`` | ``cli`` | ``code`` | ``app``."""
    args = list(argv)
    while args and args[0] in _IGNORED_FLAGS:
        args.pop(0)
    # Finder used to pass a process serial number; drop it if it shows up.
    args = [a for a in args if not a.startswith("-psn_")]
    if not args:
        return "app", []
    if args[0] == "-m" and len(args) >= 2:
        module, rest = args[1], args[2:]
        if module == "bao.hook":
            return "hook", rest
        if module in ("bao", "bao.__main__"):
            return "cli", rest
        return "cli", [module, *rest]  # unknown module: let the CLI print usage
    if args[0] == "-c" and len(args) >= 2:
        return "code", [args[1]]
    return "cli", args


def main(argv: Sequence[str] | None = None) -> int:
    mode, rest = parse(sys.argv[1:] if argv is None else argv)
    if mode == "hook":
        from bao.hook import main as hook_main

        hook_main(rest)
        return 0  # golden rule: the hook always exits 0
    if mode == "code":
        exec(compile(rest[0], "<-c>", "exec"), {"__name__": "__main__"})  # noqa: S102
        return 0
    if mode == "app":
        from bao.app import run

        return run(offer_setup=True)
    from bao.__main__ import main as cli_main

    return cli_main(rest)


def hook_main(argv: Sequence[str] | None = None) -> int:
    """Entry of the Qt-free ``bao-hook`` helper next to ``Bao`` in Contents/MacOS.

    PyInstaller's PySide6 runtime hook imports Qt in every process of the main binary
    (~100 ms), too slow for a hook that runs on every tool call. This helper only does
    the hook and ``-c`` probes; anything else (e.g. the hook launching ``-m bao run``)
    is handed to the main binary with the same arguments.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    mode, rest = parse(args)
    if mode in ("hook", "code"):
        return main(args)
    app = os.path.join(os.path.dirname(sys.executable), APP_EXECUTABLE)
    os.execv(app, [app, *args])
    return 1  # not reached
