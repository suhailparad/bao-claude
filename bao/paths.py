"""Locations of per-user runtime files. Stdlib only (imported by the hook)."""

from __future__ import annotations

import os
from pathlib import Path


def home_dir() -> Path:
    """Root for all user state. Override with BAO_HOME (used by tests)."""
    override = os.environ.get("BAO_HOME")
    return Path(override) if override else Path.home() / ".bao"


def socket_path() -> Path:
    return home_dir() / "pet.sock"


def lock_path() -> Path:
    return home_dir() / "pet.lock"


def log_path() -> Path:
    return home_dir() / "pet.log"


def config_path() -> Path:
    return home_dir() / "config.json"
