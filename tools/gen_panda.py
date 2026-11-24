"""Generate the default panda character's frames with QPainter.

    python tools/gen_panda.py            # writes bao/characters/panda/
    python tools/gen_panda.py --sheet    # also writes a contact sheet preview PNG

Everything is drawn in a 160x160 logical canvas and rendered at 2x for Retina.
Replace these PNGs with hand-drawn art any time; the manifest is all the app needs.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor,
    QFont,
    QGuiApplication,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
)

SIZE = 160
RENDER_SCALE = 2
OUT = Path(__file__).resolve().parent.parent / "bao" / "characters" / "panda"

WHITE = QColor("#fbfbf8")
BLACK = QColor("#26262b")
OUTLINE = QColor("#3a3a40")
PINK = QColor(255, 150, 170, 150)
TONGUE = QColor("#f07a8c")
SHADOW = QColor(0, 0, 0, 45)
FUR_EDGE = QColor("#6a6a74")  # keeps black fur readable on dark desktops
ACCENT = QColor("#d97757")  # Claude-ish orange for props
SCREEN = QColor("#2b3140")
CODE = [QColor("#7fd1b9"), QColor("#f4c26b"), QColor("#9ab8ff"), QColor("#f28fad")]

Prop = Callable[[QPainter, float], None]  # (painter, t in [0,1)) -> None


@dataclass
class Pose:
    bob: float = 0.0  # whole-body vertical offset (negative = up)
    head_tilt: float = 0.0  # degrees
    eyes: str = "open"  # open | closed | happy | wide | down
    look: tuple[float, float] = (0.0, 0.0)  # pupil offset
    mouth: str = "smile"  # smile | open | o | flat | sleepy
    arm_l: float = 15.0  # degrees raised from hanging (0 = straight down, 180 = up)
    arm_r: float = 15.0
    squash: float = 1.0  # vertical body scale
    blush: bool = True
    step: float = 0.0  # walking: >0 lifts the left foot, <0 the right one (−1..1)
    flying: bool = False  # airborne: no ground shadow, feet tucked (birds)
    behind: list[Prop] = field(default_factory=list)  # drawn behind the arms
    front: list[Prop] = field(default_factory=list)  # drawn on top of everything


# ---------------------------------------------------------------------------------------
# Drawing primitives
# ---------------------------------------------------------------------------------------


def outline_pen(w: float = 2.2) -> QPen:
    pen = QPen(OUTLINE, w)
    pen.setJoinStyle(Qt.RoundJoin)
    pen.setCapStyle(Qt.RoundCap)
    return pen


def ellipse(p: QPainter, cx: float, cy: float, rx: float, ry: float) -> None:
    p.drawEllipse(QPointF(cx, cy), rx, ry)


def foot_lift(pose: Pose, height: float = 5.0) -> tuple[float, float]:
    """How far (px) the left / right foot is raised for this pose's walking step."""
    return max(0.0, pose.step) * height, max(0.0, -pose.step) * height


def draw_arm(p: QPainter, sx: float, sy: float, angle: float) -> None:
    p.save()
    p.translate(sx, sy)
    p.rotate(angle)
    p.setPen(QPen(FUR_EDGE, 1.3))
    p.setBrush(BLACK)
    p.drawRoundedRect(QRectF(-8, -6, 16, 34), 8, 8)
    p.restore()


def draw_eye(p: QPainter, cx: float, cy: float, pose: Pose, side: int) -> None:
    # black patch, tilted outward
    p.save()
    p.translate(cx, cy)
    p.rotate(-22 * side)
    p.setPen(Qt.NoPen)
    p.setBrush(BLACK)
    ellipse(p, 0, 0, 10.5, 13.5)
    p.restore()

    lx, ly = pose.look
    if pose.eyes in ("open", "wide", "down"):
        r = 4.6 if pose.eyes == "wide" else 4.0
        dy = 2.5 if pose.eyes == "down" else 0
        p.setBrush(QColor("white"))
        ellipse(p, cx + lx, cy - 1 + ly + dy, r, r)
        p.setBrush(BLACK)
        ellipse(p, cx + lx * 1.3, cy - 0.5 + ly * 1.3 + dy, r * 0.55, r * 0.55)
        p.setBrush(QColor("white"))
        ellipse(p, cx + lx - 1.3, cy - 2.4 + ly + dy, 1.2, 1.2)
    else:
        pen = QPen(QColor("white"), 2.2)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        path = QPainterPath()
        if pose.eyes == "happy":  # ^ ^
            path.moveTo(cx - 4.5, cy + 1.5)
            path.quadTo(cx, cy - 5, cx + 4.5, cy + 1.5)
        else:  # closed: gentle downward arc
            path.moveTo(cx - 4.5, cy - 0.5)
            path.quadTo(cx, cy + 3.5, cx + 4.5, cy - 0.5)
        p.drawPath(path)
        p.setPen(Qt.NoPen)


def draw_mouth(p: QPainter, cx: float, cy: float, kind: str) -> None:
    pen = QPen(BLACK, 1.8)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    if kind == "smile":
        path = QPainterPath()
        path.moveTo(cx - 5, cy)
        path.quadTo(cx - 2.5, cy + 3, cx, cy)
        path.quadTo(cx + 2.5, cy + 3, cx + 5, cy)
        p.drawPath(path)
    elif kind == "flat":
        p.drawLine(QPointF(cx - 3, cy + 1), QPointF(cx + 3, cy + 1))
    elif kind == "sleepy":
        p.drawLine(QPointF(cx - 2, cy + 1.5), QPointF(cx + 2, cy + 1.5))
    elif kind == "o":
        p.setBrush(TONGUE.darker(140))
        ellipse(p, cx, cy + 2.5, 2.8, 3.4)
    elif kind == "open":
        path = QPainterPath()
        path.moveTo(cx - 6, cy)
        path.quadTo(cx, cy + 10, cx + 6, cy)
        path.closeSubpath()
        p.setBrush(TONGUE)
        p.drawPath(path)
    p.setPen(Qt.NoPen)


def draw_panda(p: QPainter, pose: Pose, t: float) -> None:
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)

    # ground shadow (does not bob; shrinks when jumping)
    shrink = max(0.55, 1 + pose.bob / 40)
    p.setPen(Qt.NoPen)
    p.setBrush(SHADOW)
    ellipse(p, 80, 150, 34 * shrink, 5 * shrink)

    p.save()
    p.translate(0, pose.bob)

    # legs
    lift_l, lift_r = foot_lift(pose)
    p.setPen(QPen(FUR_EDGE, 1.3))
    p.setBrush(BLACK)
    ellipse(p, 60, 140 - lift_l, 13, 9)
    ellipse(p, 100, 140 - lift_r, 13, 9)
    p.setPen(Qt.NoPen)

    # body (squash anchored at the feet)
    p.save()
    p.translate(80, 146)
    p.scale(1 + (1 - pose.squash) * 0.6, pose.squash)
    p.translate(-80, -146)
    p.setPen(outline_pen())
    p.setBrush(WHITE)
    ellipse(p, 80, 116, 35, 29)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(235, 235, 230))
    ellipse(p, 80, 122, 20, 16)  # belly
    p.restore()

    for prop in pose.behind:
        p.save()
        prop(p, t)
        p.restore()

    # arms
    draw_arm(p, 50, 104, pose.arm_l)
    draw_arm(p, 110, 104, -pose.arm_r)

    # head
    p.save()
    p.translate(80, 98)
    p.rotate(pose.head_tilt)
    p.translate(-80, -98)
    p.setPen(QPen(FUR_EDGE, 1.3))
    p.setBrush(BLACK)
    ellipse(p, 49, 37, 13, 13)
    ellipse(p, 111, 37, 13, 13)
    p.setPen(outline_pen())
    p.setBrush(WHITE)
    ellipse(p, 80, 66, 42, 36)
    p.setPen(Qt.NoPen)

    draw_eye(p, 63, 64, pose, side=1)
    draw_eye(p, 97, 64, pose, side=-1)
    if pose.blush:
        p.setBrush(PINK)
        ellipse(p, 52, 80, 6, 3.5)
        ellipse(p, 108, 80, 6, 3.5)
    p.setBrush(BLACK)
    ellipse(p, 80, 77, 4.6, 3.3)  # nose
    draw_mouth(p, 80, 81, pose.mouth)
    p.restore()

    p.restore()  # bob

    for prop in pose.front:
        p.save()
        prop(p, t)
        p.restore()


# ---------------------------------------------------------------------------------------
# Props
# ---------------------------------------------------------------------------------------


def font(px: float, bold: bool = True) -> QFont:
    f = QFont("Helvetica Neue")
    f.setPixelSize(max(1, int(px)))
    f.setBold(bold)
    return f


def laptop(screen_fn: Callable[[QPainter, QRectF, float], None] | None = None) -> Prop:
    def draw(p: QPainter, t: float) -> None:
        # base
        p.setPen(outline_pen(1.6))
        p.setBrush(QColor("#b8bcc6"))
        base = QPainterPath()
        base.moveTo(46, 138)
        base.lineTo(114, 138)
        base.lineTo(120, 146)
        base.lineTo(40, 146)
        base.closeSubpath()
        p.drawPath(base)
        # screen (back of lid faces the panda; we see the front)
        lid = QRectF(50, 106, 60, 34)
        p.setBrush(QColor("#9aa0ac"))
        p.drawRoundedRect(lid, 4, 4)
        inner = lid.adjusted(4, 4, -4, -4)
        p.setPen(Qt.NoPen)
        p.setBrush(SCREEN)
        p.drawRoundedRect(inner, 2, 2)
        if screen_fn:
            screen_fn(p, inner, t)
        else:
            p.setBrush(ACCENT)
            ellipse(p, inner.center().x(), inner.center().y(), 4, 4)

    return draw


def code_lines(p: QPainter, r: QRectF, t: float) -> None:
    n = 1 + int(t * 5) % 5  # lines appear over time
    widths = [0.7, 0.45, 0.8, 0.55, 0.35]
    indent = [0, 0.15, 0.15, 0.3, 0]
    for i in range(n):
        p.setBrush(CODE[i % len(CODE)])
        x = r.left() + 3 + r.width() * indent[i]
        w = (
            (r.width() - 6) * widths[i] * (0.4 + 0.6 * min(1, t * 5 - i))
            if i == n - 1
            else (r.width() - 6) * widths[i]
        )
        p.drawRoundedRect(QRectF(x, r.top() + 3 + i * 4.6, max(2, w), 2.6), 1.2, 1.2)


def terminal_prompt(p: QPainter, r: QRectF, t: float) -> None:
    p.setPen(QPen(QColor("#7fd1b9"), 1.6))
    p.setFont(font(9))
    p.drawText(QPointF(r.left() + 3, r.top() + 11), ">")
    p.setPen(Qt.NoPen)
    for i in range(int(t * 3) % 3 + 1):
        p.setBrush(QColor("#c8cdd8"))
        p.drawRoundedRect(
            QRectF(r.left() + 3, r.top() + 15 + i * 4, 14 + 9 * ((i * 7) % 3), 2.4), 1, 1
        )
    if int(t * 8) % 2 == 0:
        p.setBrush(QColor("#7fd1b9"))
        p.drawRect(QRectF(r.left() + 11, r.top() + 4, 5, 8))


def gear(cx: float, cy: float, r: float) -> Prop:
    def draw(p: QPainter, t: float) -> None:
        p.translate(cx, cy)
        p.rotate(t * 90)
        p.setPen(Qt.NoPen)
        p.setBrush(ACCENT)
        for i in range(8):
            p.save()
            p.rotate(i * 45)
            p.drawRoundedRect(QRectF(-r * 0.22, -r * 1.15, r * 0.44, r * 0.5), 1.5, 1.5)
            p.restore()
        ellipse(p, 0, 0, r * 0.85, r * 0.85)
        p.setBrush(QColor("white"))
        ellipse(p, 0, 0, r * 0.35, r * 0.35)

    return draw


def book(p: QPainter, t: float) -> None:
    p.setPen(outline_pen(1.6))
    p.setBrush(ACCENT)
    p.drawRoundedRect(QRectF(52, 110, 56, 30), 3, 3)
    p.setBrush(QColor("#fff8ee"))
    p.drawRect(QRectF(55, 112, 24, 26))
    p.drawRect(QRectF(81, 112, 24, 26))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, 60))
    for i in range(4):
        p.drawRect(QRectF(58, 116 + i * 5, 18, 1.6))
        p.drawRect(QRectF(84, 116 + i * 5, 18 if i != 3 else 10, 1.6))


def thought_bubble(p: QPainter, t: float) -> None:
    p.setPen(outline_pen(1.6))
    p.setBrush(QColor("white"))
    ellipse(p, 124, 34, 4, 4)
    ellipse(p, 132, 25, 5.5, 5.5)
    p.drawRoundedRect(QRectF(122, 2, 36, 18), 9, 9)
    p.setPen(Qt.NoPen)
    p.setBrush(BLACK)
    for i in range(int(t * 4) % 4):
        ellipse(p, 131 + i * 9, 11, 2.3, 2.3)


def exclamation(p: QPainter, t: float) -> None:
    s = 1 + 0.12 * math.sin(t * 2 * math.pi * 2)
    p.translate(136, 18)
    p.scale(s, s)
    p.setPen(outline_pen(1.6))
    p.setBrush(QColor("#ffcf4a"))
    ellipse(p, 0, 0, 13, 13)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#c0392b"))
    p.drawRoundedRect(QRectF(-2.2, -8, 4.4, 10.5), 2, 2)
    ellipse(p, 0, 6, 2.4, 2.4)


def question_dots(p: QPainter, t: float) -> None:
    p.setPen(outline_pen(1.4))
    p.setBrush(QColor("white"))
    p.drawRoundedRect(QRectF(118, 6, 34, 18), 9, 9)
    p.setPen(Qt.NoPen)
    for i in range(3):
        on = int(t * 3) % 3 == i
        p.setBrush(ACCENT if on else QColor("#9a9aa2"))
        ellipse(p, 127 + i * 8, 15, 2.4, 2.4)


def zzz(p: QPainter, t: float) -> None:
    for i, (size, phase) in enumerate([(9, 0.0), (12, 0.33), (15, 0.66)]):
        k = (t + phase) % 1.0
        x = 118 + i * 9 + math.sin(k * math.pi * 2) * 3
        y = 46 - k * 40
        alpha = int(255 * math.sin(k * math.pi))
        p.setPen(QPen(QColor(90, 110, 170, alpha), 1))
        p.setFont(font(size))
        p.drawText(QPointF(x, y), "z")


def confetti(seed: int = 7) -> Prop:
    rng = random.Random(seed)
    bits = [
        (rng.uniform(10, 150), rng.uniform(0, 1), rng.choice(CODE + [ACCENT]), rng.uniform(0, 360))
        for _ in range(22)
    ]

    def draw(p: QPainter, t: float) -> None:
        p.setPen(Qt.NoPen)
        for x, phase, color, rot in bits:
            k = (t + phase) % 1.0
            y = -4 + k * 110
            p.save()
            p.translate(x + math.sin((k + phase) * 6) * 5, y)
            p.rotate(rot + k * 360)
            c = QColor(color)
            c.setAlpha(int(255 * (1 - k * 0.6)))
            p.setBrush(c)
            p.drawRect(QRectF(-2.5, -1.3, 5, 2.6))
            p.restore()

    return draw


def sparkles(p: QPainter, t: float) -> None:
    for i, (x, y) in enumerate([(30, 50), (132, 60), (40, 112), (124, 112)]):
        k = (t + i * 0.25) % 1.0
        s = 5 * math.sin(k * math.pi)
        if s <= 0.3:
            continue
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#9ab8ff"))
        star = QPainterPath()
        star.moveTo(x, y - s)
        star.quadTo(x, y, x + s, y)
        star.quadTo(x, y, x, y + s)
        star.quadTo(x, y, x - s, y)
        star.quadTo(x, y, x, y - s)
        p.drawPath(star)


def heart(p: QPainter, t: float) -> None:
    k = t % 1.0
    p.translate(126, 30 - k * 14)
    s = 0.8 + 0.3 * math.sin(k * math.pi)
    p.scale(s, s)
    c = QColor("#f28fad")
    c.setAlpha(int(255 * (1 - k * 0.7)))
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    path = QPainterPath()
    path.moveTo(0, 4)
    path.cubicTo(-9, -3, -4, -10, 0, -4)
    path.cubicTo(4, -10, 9, -3, 0, 4)
    p.drawPath(path)


# ---------------------------------------------------------------------------------------
# Animations: state -> (fps, loop, frame count, pose function)
# ---------------------------------------------------------------------------------------

TAU = 2 * math.pi


def idle(t: float, i: int) -> Pose:
    return Pose(
        bob=math.sin(t * TAU) * 1.5,
        eyes="closed" if i == 6 else "open",
        squash=1 - 0.015 * math.sin(t * TAU),
    )


def greeting(t: float, i: int) -> Pose:
    return Pose(
        bob=-abs(math.sin(t * TAU)) * 2,
        eyes="happy",
        mouth="open",
        arm_r=150 + 25 * math.sin(t * TAU * 2),
        head_tilt=-4,
        front=[heart],
    )


def thinking(t: float, i: int) -> Pose:
    return Pose(
        bob=math.sin(t * TAU) * 1,
        head_tilt=7,
        look=(2.5, -2.5),
        mouth="flat",
        arm_r=128 + 6 * math.sin(t * TAU * 2),
        front=[thought_bubble],
    )


def typing_arms(t: float) -> tuple[float, float]:
    a = math.sin(t * TAU * 4)
    return 52 + 8 * a, 52 - 8 * a


def working(t: float, i: int) -> Pose:
    al, ar = typing_arms(t)
    return Pose(eyes="down", arm_l=al, arm_r=ar, mouth="flat", front=[laptop(), gear(138, 22, 10)])


def typing(t: float, i: int) -> Pose:
    al, ar = typing_arms(t)
    return Pose(eyes="down", arm_l=al, arm_r=ar, mouth="smile", front=[laptop(code_lines)])


def running(t: float, i: int) -> Pose:
    al, ar = typing_arms(t * 0.5)
    return Pose(eyes="down", arm_l=al, arm_r=ar, mouth="o", front=[laptop(terminal_prompt)])


def reading(t: float, i: int) -> Pose:
    sweep = math.sin(t * TAU)
    return Pose(
        eyes="down",
        look=(3 * sweep, 0),
        arm_l=62,
        arm_r=62,
        head_tilt=2 * sweep,
        mouth="flat",
        front=[book],
    )


def waiting(t: float, i: int) -> Pose:
    return Pose(
        bob=math.sin(t * TAU) * 1.2,
        eyes="closed" if i == 5 else "wide",
        mouth="smile",
        head_tilt=6 * math.sin(t * TAU),
        arm_l=20,
        arm_r=20,
        front=[question_dots],
    )


def needs_permission(t: float, i: int) -> Pose:
    w = math.sin(t * TAU * 2)
    return Pose(
        bob=-abs(w) * 3,
        eyes="wide",
        mouth="o",
        arm_l=150 + 20 * w,
        arm_r=150 - 20 * w,
        front=[exclamation],
    )


def done(t: float, i: int) -> Pose:
    jump = abs(math.sin(t * TAU))
    return Pose(
        bob=-jump * 14,
        squash=1 - 0.06 * (1 - jump),
        eyes="happy",
        mouth="open",
        arm_l=160 - 15 * jump,
        arm_r=160 - 15 * jump,
        front=[confetti()],
    )


def compacting(t: float, i: int) -> Pose:
    s = math.sin(t * TAU)
    return Pose(
        squash=0.94 + 0.05 * s,
        eyes="closed",
        mouth="flat",
        arm_l=70 + 10 * s,
        arm_r=70 + 10 * s,
        front=[sparkles],
    )


def sleeping(t: float, i: int) -> Pose:
    return Pose(
        bob=3 + math.sin(t * TAU) * 1.2,
        squash=0.97 + 0.02 * math.sin(t * TAU),
        head_tilt=9,
        eyes="closed",
        mouth="sleepy",
        arm_l=8,
        arm_r=8,
        front=[zzz],
    )


def roaming(t: float, i: int) -> Pose:
    """A front-facing waddle: rock side to side, bounce on each step, arms swinging."""
    w = math.sin(t * TAU)
    return Pose(
        bob=-abs(w) * 3,
        head_tilt=6 * w,
        step=w,
        arm_l=22 + 16 * w,
        arm_r=22 - 16 * w,
        eyes="closed" if i == 5 else "open",
        mouth="smile",
    )


ANIMATIONS: dict[str, tuple[float, bool, int, Callable[[float, int], Pose]]] = {
    "idle": (6, True, 8, idle),
    "greeting": (10, True, 10, greeting),
    "thinking": (6, True, 12, thinking),
    "working": (8, True, 8, working),
    "typing": (8, True, 10, typing),
    "running": (6, True, 8, running),
    "reading": (6, True, 12, reading),
    "waiting": (4, True, 8, waiting),
    "needs_permission": (8, True, 8, needs_permission),
    "done": (12, True, 12, done),
    "compacting": (6, True, 8, compacting),
    "sleeping": (3, True, 9, sleeping),
    "roaming": (8, True, 8, roaming),  # used while wandering around (see bao/roam.py)
}

WALK = {"style": "walk", "speed": 36, "faces": "front"}


Drawer = Callable[[QPainter, Pose, float], None]


def render_frame(pose: Pose, t: float, draw: Drawer | None = None) -> QImage:
    img = QImage(SIZE * RENDER_SCALE, SIZE * RENDER_SCALE, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.scale(RENDER_SCALE, RENDER_SCALE)
    (draw or draw_panda)(p, pose, t)
    p.end()
    return img


def generate(
    out: Path,
    draw: Drawer | None = None,
    char_id: str = "panda",
    name: str = "Panda",
    poses: dict[str, Callable[[float, int], Pose]] | None = None,
    roam: dict | None = None,
) -> dict[str, list[QImage]]:
    """Render every animation with ``draw`` and (re)write ``out``'s frames + manifest.

    ``poses`` replaces the pose function of some states (e.g. a bird flies instead of
    walking); ``roam`` is the manifest's roaming style (default: walk).
    """
    frames_root = out / "frames"
    if frames_root.exists():
        shutil.rmtree(frames_root)
    states = {}
    rendered: dict[str, list[QImage]] = {}
    for state, (fps, loop, count, fn) in ANIMATIONS.items():
        fn = (poses or {}).get(state, fn)
        d = frames_root / state
        d.mkdir(parents=True)
        imgs = []
        for i in range(count):
            t = i / count
            img = render_frame(fn(t, i), t, draw)
            img.save(str(d / f"{i:03d}.png"))
            imgs.append(img)
        rendered[state] = imgs
        states[state] = {"frames": f"frames/{state}", "fps": fps, "loop": loop}

    manifest_path = out / "manifest.json"
    old = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest = {
        "id": char_id,
        "name": name,
        "version": 1,
        "author": "bao",
        "size": [SIZE, SIZE],
        "fallback_state": "idle",
        "states": states,
        "roam": roam or WALK,
        "sounds": old.get("sounds", {}),  # owned by tools/gen_sounds.py
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return rendered


def contact_sheet(rendered: dict[str, list[QImage]], path: Path) -> None:
    cell = SIZE  # draw at 1x
    cols = max(len(v) for v in rendered.values())
    label_w = 120
    sheet = QImage(label_w + cols * cell, len(rendered) * cell, QImage.Format_ARGB32)
    sheet.fill(QColor("#e9e6df"))
    p = QPainter(sheet)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.setFont(font(14))
    for r, (name, imgs) in enumerate(rendered.items()):
        p.setPen(QColor("#333"))
        p.drawText(QRectF(6, r * cell, label_w - 8, cell), Qt.AlignVCenter, name)
        for c, img in enumerate(imgs):
            p.drawImage(QRectF(label_w + c * cell, r * cell, cell, cell), img)
    p.end()
    sheet.save(str(path))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--sheet", type=Path, help="write a contact-sheet preview PNG here")
    args = ap.parse_args()
    _app = QGuiApplication([])
    args.out.mkdir(parents=True, exist_ok=True)
    rendered = generate(args.out)
    total = sum(len(v) for v in rendered.values())
    print(f"wrote {total} frames for {len(rendered)} states to {args.out}")
    if args.sheet:
        contact_sheet(rendered, args.sheet)
        print(f"contact sheet: {args.sheet}")


if __name__ == "__main__":
    main()
