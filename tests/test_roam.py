import random

import pytest

from bao.roam import Roamer, RoamSpec

SCREEN = (0.0, 0.0, 1000.0, 700.0)  # bounds for the window's top-left corner
HOME = (800.0, 600.0)


def run(r: Roamer, start: float, end: float, dt: float = 0.033):
    t, positions = start, []
    while t < end:
        positions.append(r.step(t))
        t += dt
    return positions


def test_spec_parse_and_validation():
    assert RoamSpec.parse(None) == RoamSpec()
    spec = RoamSpec.parse({"style": "fly", "speed": 70, "faces": "left"})
    assert (spec.style, spec.speed, spec.faces) == ("fly", 70.0, "left")
    for bad in ({"style": "swim"}, {"speed": 0}, {"speed": True}, {"faces": "up"}, "walk"):
        with pytest.raises(ValueError):
            RoamSpec.parse(bad)


def test_walker_waits_then_strolls_along_home_height_within_bounds():
    r = Roamer(RoamSpec("walk", 40), rng=random.Random(1))
    r.start(HOME, SCREEN, now=0, delay=8)
    assert run(r, 0, 7.9)[-1] == HOME and r.phase == "pausing"  # waits first
    positions = run(r, 8, 60)
    assert r.moving or r.phase == "pausing"
    assert {y for _, y in positions} == {600.0}  # walking stays on its line
    xs = [x for x, _ in positions]
    assert min(xs) >= 800 - 320 and max(xs) <= 1000  # range around home, inside the screen
    assert max(xs) - min(xs) > 60  # it actually went somewhere
    steps = [abs(b[0] - a[0]) for a, b in zip(positions, positions[1:], strict=False)]
    moving = sorted(d for d in steps if d > 0)
    assert moving[len(moving) // 2] == pytest.approx(40 * 0.033, rel=0.05)  # slowly: 40 px/s
    assert max(steps) <= 40 * 0.25  # even after a stalled timer (dt is clamped)


def test_going_home_is_quick_and_stops():
    r = Roamer(RoamSpec("walk", 40), rng=random.Random(2))
    r.start(HOME, SCREEN, now=0, delay=0)
    run(r, 0, 5)
    assert r.away
    r.go_home(5)
    assert r.phase == "returning"
    final = run(r, 5, 8)[-1]  # ≤ 320 px at ≥ 160 px/s
    assert final == HOME and not r.active and r.facing == 0


def test_go_home_when_already_home_just_stops():
    r = Roamer()
    r.start(HOME, SCREEN, now=0, delay=10)
    r.go_home(1)
    assert not r.active


def test_flyer_moves_in_the_air_above_home_and_bobs():
    r = Roamer(RoamSpec("fly", 70, "left"), rng=random.Random(3))
    r.start(HOME, SCREEN, now=0, delay=0)
    positions = run(r, 0, 40)
    ys = [y for _, y in positions]
    assert min(ys) < 600 - 60  # went up
    assert max(ys) <= 600 + 6.01  # never below home (bob aside)
    assert any(r.airborne for _ in [0]) or r.phase == "pausing"


def test_facing_follows_direction():
    r = Roamer(RoamSpec("walk", 40), rng=random.Random(4))
    r.start((500.0, 600.0), SCREEN, now=0, delay=0)
    r.step(0)
    assert r.target is not None
    r.step(0.03)
    assert r.facing == (1 if r.target[0] > 500 else -1)


def test_boxed_in_stays_put():
    r = Roamer(RoamSpec("walk", 40), rng=random.Random(5))
    r.start((10.0, 10.0), (0.0, 0.0, 30.0, 30.0), now=0, delay=0)
    assert run(r, 0, 20)[-1] == (10.0, 10.0) and not r.moving


def test_scale_scales_speed_and_range():
    r = Roamer(RoamSpec("walk", 40), scale=0.5, rng=random.Random(6))
    r.start(HOME, SCREEN, now=0, delay=0)
    xs = [x for x, _ in run(r, 0, 60)]
    assert min(xs) >= 800 - 160
