"""Locations of per-user runtime files. Stdlib only (imported by the hook)."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def home_dir() -> Path:
    """Root for all user state. Override with BAO_HOME (used by tests)."""
    override = os.environ.get("BAO_HOME")
    return Path(override) if override else Path.home() / ".bao"


def socket_path() -> Path:
    """Unix socket the pet listens on (macOS, Linux)."""
    return home_dir() / "pet.sock"


def port_path() -> Path:
    """Where the pet writes its localhost port + token when it uses TCP (Windows)."""
    return home_dir() / "pet.port"


def use_tcp() -> bool:
    """Windows has no AF_UNIX in Python; BAO_IPC=tcp forces TCP elsewhere (tests)."""
    return sys.platform == "win32" or os.environ.get("BAO_IPC") == "tcp"


def endpoint_path() -> Path:
    """The file that exists while the pet is listening (socket or port file)."""
    return port_path() if use_tcp() else socket_path()


def lock_path() -> Path:
    return home_dir() / "pet.lock"


def log_path() -> Path:
    return home_dir() / "pet.log"


def config_path() -> Path:
    return home_dir() / "config.json"
