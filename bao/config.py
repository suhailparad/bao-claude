"""User preferences in ~/.bao/config.json. No Qt."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from datetime import time as dtime
from pathlib import Path
from typing import Any

from .paths import config_path

log = logging.getLogger(__name__)


DEFAULT_CHARACTER = "panda"
_HHMM = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def parse_hhmm(value: Any) -> dtime | None:
    m = _HHMM.match(value) if isinstance(value, str) else None
    return dtime(int(m.group(1)), int(m.group(2))) if m else None


def in_quiet_hours(hours: list[str] | None, now: dtime) -> bool:
    """True if ``now`` is inside [start, end). Wraps past midnight (e.g. 22:00 → 08:00)."""
    if not hours:
        return False
    start, end = parse_hhmm(hours[0]), parse_hhmm(hours[1])
    if start is None or end is None or start == end:
        return False
    if start < end:
        return start <= now < end
    return now >= start or now < end


@dataclass
class Config:
    character: str = DEFAULT_CHARACTER
    scale: float = 1.0
    muted: bool = False
    volume: float = 0.7
    show_bubble: bool = True
    muted_cues: list[str] = field(default_factory=list)  # e.g. ["hello", "bye"]
    permission_reminder_seconds: float = 60.0  # nudge again about a pending permission (0 = off)
    do_not_disturb: bool = False  # no sounds; the pet still animates
    quiet_hours: list[str] | None = None  # ["22:00", "08:00"]: daily Do Not Disturb window
    quit_after_minutes: float = 15.0  # quit this long after the last session ends (0 = never)
    position: list[int] | None = None  # [x, y] of the window's top-left corner

    @classmethod
    def load(cls, path: Path | None = None) -> Config:
        path = path or config_path()
        try:
            data = json.loads(path.read_text())
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError) as exc:
            log.warning("ignoring unreadable config %s: %s", path, exc)
            return cls()
        if not isinstance(data, dict):
            return cls()
        known = {f.name for f in fields(cls)}
        cfg = cls(**{k: v for k, v in data.items() if k in known})
        cfg._sanitize()
        return cfg

    def in_quiet_hours(self, now: datetime | None = None) -> bool:
        return in_quiet_hours(self.quiet_hours, (now or datetime.now()).time())

    def sounds_silenced(self, now: datetime | None = None) -> bool:
        """Do Not Disturb is on, by hand or by the clock."""
        return self.do_not_disturb or self.in_quiet_hours(now)

    def save(self, path: Path | None = None) -> None:
        path = path or config_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(asdict(self), indent=2) + "\n")
            os.replace(tmp, path)
        except OSError as exc:
            log.warning("could not save config: %s", exc)

    def _sanitize(self) -> None:
        defaults = Config()
        self.scale = _num(self.scale, defaults.scale, 0.25, 4.0)
        self.volume = _num(self.volume, defaults.volume, 0.0, 1.0)
        self.quit_after_minutes = _num(
            self.quit_after_minutes, defaults.quit_after_minutes, 0, 1440
        )
        self.permission_reminder_seconds = _num(
            self.permission_reminder_seconds, defaults.permission_reminder_seconds, 0, 3600
        )
        self.muted = bool(self.muted)
        self.show_bubble = bool(self.show_bubble)
        self.do_not_disturb = bool(self.do_not_disturb)
        qh = self.quiet_hours
        if qh is not None and not (
            isinstance(qh, list) and len(qh) == 2 and all(parse_hhmm(v) for v in qh)
        ):
            log.warning('ignoring quiet_hours %r (expected ["22:00", "08:00"])', qh)
            self.quiet_hours = None
        if not isinstance(self.character, str) or not self.character:
            self.character = defaults.character
        if not isinstance(self.muted_cues, list):
            self.muted_cues = []
        self.muted_cues = [c for c in self.muted_cues if isinstance(c, str)]
        pos = self.position
        if not (isinstance(pos, list) and len(pos) == 2 and all(isinstance(v, int) for v in pos)):
            self.position = None


def _num(value: Any, default: float, lo: float, hi: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return min(hi, max(lo, float(value)))
