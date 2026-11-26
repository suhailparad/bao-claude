"""Roaming idle: where the pet wanders while nothing is happening. No Qt.

``Roamer`` moves the window's top-left corner around its *home* (the spot the user
dragged it to) and always comes back there when work starts:

* ``walk``: strolls left and right along the home's height, pausing in between.
* ``fly``: flits around in the air above and beside home, hovering in between.
* ``stay``: doesn't wander at all; its idle animation does the entertaining (the panda
  sits and munches bamboo).

The window calls ``start()`` when the pet becomes idle, ``go_home()`` when it gets busy
and ``step(now)`` on every tick; ``step`` returns the new top-left corner.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

STYLES = ("walk", "fly", "stay")
FACINGS = ("front", "left", "right")

WALK_RANGE = 320.0  # px either side of home
FLY_RANGE = 280.0
FLY_HEIGHT = 220.0  # px above home at most
MIN_TRIP = 60.0  # don't bother with shorter moves
HOME_SPEEDUP = 4.0  # going home is quicker than wandering
FLY_BOB = 6.0  # px of gentle up/down while airborne


@dataclass(frozen=True)
class RoamSpec:
    style: str = "walk"
    speed: float = 40.0  # px/s at scale 1
    faces: str = "front"  # which way the sprite looks; "left"/"right" get mirrored to travel

    @classmethod
    def parse(cls, data: object) -> RoamSpec:
        """From a manifest's optional ``"roam"`` object; raises ValueError if malformed."""
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise ValueError("'roam' must be an object")
        style = data.get("style", "walk")
        speed = data.get("speed", 40.0)
        faces = data.get("faces", "front")
        if style not in STYLES:
            raise ValueError(f"roam.style must be one of {', '.join(STYLES)}")
        if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not 5 <= speed <= 400:
            raise ValueError("roam.speed must be a number of px/s between 5 and 400")
        if faces not in FACINGS:
            raise ValueError(f"roam.faces must be one of {', '.join(FACINGS)}")
        return cls(style, float(speed), faces)


Bounds = tuple[float, float, float, float]  # left, top, right, bottom for the top-left corner


class Roamer:
    def __init__(
        self,
        spec: RoamSpec | None = None,
        scale: float = 1.0,
        rng: random.Random | None = None,
    ) -> None:
        self.spec = spec or RoamSpec()
        self.scale = scale
        self.rng = rng or random.Random()
        self.home: tuple[float, float] | None = None
        self.pos = (0.0, 0.0)  # path position (without the airborne bob)
        self.target: tuple[float, float] | None = None
        self.bounds: Bounds = (0.0, 0.0, 0.0, 0.0)
        self.phase = "off"  # off | pausing | moving | returning
        self.facing = 0  # -1 travelling left, 1 right, 0 not moving
        self._next_move_at = 0.0
        self._last = 0.0

    # -- control --------------------------------------------------------------------------

    @property
    def active(self) -> bool:
        return self.phase != "off"

    @property
    def moving(self) -> bool:
        return self.phase in ("moving", "returning")

    @property
    def away(self) -> bool:
        """Not standing on its home spot."""
        return self.home is not None and self.active and _dist(self.pos, self.home) > 0.5

    @property
    def airborne(self) -> bool:
        return self.spec.style == "fly" and self.away

    def start(self, home: tuple[float, float], bounds: Bounds, now: float, delay: float) -> None:
        """Begin wandering from ``home`` after ``delay`` seconds."""
        if self.phase in ("pausing", "moving"):
            return
        if self.phase == "returning" and self.home is not None:
            home = self.home  # was heading home; keep that home and carry on from here
        else:
            self.pos = home
        self.home = home
        self.bounds = bounds
        self.phase = "pausing"
        self.target = None
        self.facing = 0
        self._next_move_at = now + delay
        self._last = now

    def go_home(self, now: float) -> None:
        if not self.active:
            return
        if self.home is None or not self.away:
            self.stop()
            return
        self.phase = "returning"
        self.target = self.home
        self._last = now

    def stop(self) -> None:
        """Stop where it is (e.g. the user grabbed it)."""
        self.phase = "off"
        self.target = None
        self.facing = 0

    # -- movement -------------------------------------------------------------------------

    def step(self, now: float) -> tuple[float, float]:
        """Advance to ``now``; returns where the window's top-left corner should be."""
        dt = max(0.0, min(0.25, now - self._last))  # clamp: a stalled timer shouldn't teleport
        self._last = now
        if self.phase == "pausing" and now >= self._next_move_at:
            self.target = self._pick_target()
            self.phase = "moving" if self.target else "pausing"
            if self.target is None:
                self._next_move_at = now + self._pause()
        if self.moving and self.target is not None:
            speed = self.spec.speed * self.scale
            if self.phase == "returning":
                speed = max(speed * HOME_SPEEDUP, 160.0)
            self._advance(self.target, speed * dt)
            if _dist(self.pos, self.target) < 0.5:
                self.pos = self.target
                self.facing = 0
                if self.phase == "returning":
                    self.stop()
                else:
                    self.phase = "pausing"
                    self._next_move_at = now + self._pause()
        return self._with_bob(now)

    def _advance(self, target: tuple[float, float], distance: float) -> None:
        dx, dy = target[0] - self.pos[0], target[1] - self.pos[1]
        d = math.hypot(dx, dy)
        if abs(dx) > 0.5:
            self.facing = 1 if dx > 0 else -1
        if d <= distance:
            self.pos = target
        else:
            self.pos = (self.pos[0] + dx / d * distance, self.pos[1] + dy / d * distance)

    def _with_bob(self, now: float) -> tuple[float, float]:
        if not self.airborne or self.home is None:
            return self.pos
        # fade the bob in/out near home so take-off and landing are smooth
        k = min(1.0, _dist(self.pos, self.home) / 30.0)
        return self.pos[0], self.pos[1] + math.sin(now * 2.4) * FLY_BOB * self.scale * k

    def _pause(self) -> float:
        lo, hi = (2.0, 5.0) if self.spec.style == "fly" else (3.0, 8.0)
        return self.rng.uniform(lo, hi)

    def _pick_target(self) -> tuple[float, float] | None:
        assert self.home is not None
        hx, hy = self.home
        left, top, right, bottom = self.bounds
        reach = (FLY_RANGE if self.spec.style == "fly" else WALK_RANGE) * self.scale
        x_lo, x_hi = max(left, hx - reach), min(right, hx + reach)
        if self.spec.style == "fly":
            y_lo, y_hi = max(top, hy - FLY_HEIGHT * self.scale), min(bottom, hy)
        else:
            y_lo = y_hi = hy
        if x_hi - x_lo < MIN_TRIP and y_hi - y_lo < MIN_TRIP:
            return None  # boxed in (e.g. a tiny screen): just stay put
        for _ in range(12):
            if self.spec.style == "fly" and self.rng.random() < 0.3:
                target = self.home  # birds like to land back home now and then
            else:
                target = (self.rng.uniform(x_lo, x_hi), self.rng.uniform(y_lo, y_hi))
            if _dist(target, self.pos) >= MIN_TRIP:
                return target
        return None


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])
