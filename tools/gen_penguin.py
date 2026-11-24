"""Generate the penguin character's frames with QPainter.

    python tools/gen_penguin.py                      # writes bao/characters/penguin/
    python tools/gen_penguin.py --sheet penguin.png  # also writes a contact sheet preview PNG
    python tools/gen_sounds.py --character penguin   # then (re)make its peeps and squawks

A little penguin that reuses the panda's poses, props and animation timings
(tools/gen_panda.py); only the body is drawn differently. Flippers stand in for arms.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import gen_panda as gp
from gen_panda import Pose, ellipse
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPen

OUT = Path(__file__).resolve().parent.parent / "bao" / "characters" / "penguin"

BACK = QColor("#2b3442")  # deep blue-slate rather than pure black
BACK_EDGE = QColor("#6d7a8c")  # keeps the dark back readable on dark desktops
SHEEN = QColor(255, 255, 255, 28)
BELLY = QColor("#fbfbf8")
BELLY_SHADE = QColor("#e6e9ee")
BEAK = QColor("#f5a33b")
BEAK_DARK = QColor("#c9701d")
FEET = QColor("#f39a3a")
EYE = QColor("#1d2129")
MOUTH_IN = QColor("#b4485a")


def edge_pen(color: QColor = BACK_EDGE, w: float = 1.6) -> QPen:
    pen = QPen(color, w)
    pen.setJoinStyle(Qt.RoundJoin)
    pen.setCapStyle(Qt.RoundCap)
    return pen


def ellipse_path(cx: float, cy: float, rx: float, ry: float) -> QPainterPath:
    path = QPainterPath()
    path.addEllipse(QPointF(cx, cy), rx, ry)
    return path


def draw_foot(p: QPainter, cx: float, cy: float, side: int) -> None:
    """Webbed orange foot: three rounded toes pointing slightly outward."""
    p.save()
    p.translate(cx, cy)
    p.rotate(side * 12)
    foot = QPainterPath()
    foot.setFillRule(Qt.WindingFill)  # overlapping toes add up instead of cancelling
    for dx in (-6, 0, 6):
        foot.addEllipse(QPointF(dx, 2), 5.2, 4.6)
    foot.addRoundedRect(QRectF(-9, -4, 18, 7), 3.5, 3.5)
    p.setPen(edge_pen(BEAK_DARK, 1.3))
    p.setBrush(FEET)
    p.drawPath(foot.simplified())
    p.restore()


def draw_flipper(p: QPainter, sx: float, sy: float, angle: float, side: int) -> None:
    """A flipper hinged at the shoulder; ``angle`` like the panda's arms (0 = hanging)."""
    p.save()
    p.translate(sx, sy)
    p.rotate(angle)
    path = QPainterPath(QPointF(-6.5, -5))
    path.cubicTo(-9, 10, -5 - side * 2, 26, -1 - side * 3, 33)  # outer edge to the tip
    path.cubicTo(2, 30, 8, 14, 6.5, -5)  # back up the inner edge
    path.quadTo(0, -9, -6.5, -5)
    p.setPen(edge_pen())
    p.setBrush(BACK)
    p.drawPath(path)
    p.restore()


def draw_eye(p: QPainter, cx: float, cy: float, pose: Pose) -> None:
    lx, ly = pose.look
    if pose.eyes in ("open", "wide", "down"):
        rx, ry = (5.4, 6.4) if pose.eyes == "wide" else (4.6, 5.6)
        dy = 1.8 if pose.eyes == "down" else 0
        p.setPen(Qt.NoPen)
        p.setBrush(EYE)
        ellipse(p, cx + lx * 0.6, cy + ly * 0.6 + dy, rx, ry)
        p.setBrush(QColor("white"))
        ellipse(p, cx + lx * 0.6 - 1.6, cy + ly * 0.6 - 2.2 + dy, 1.7, 1.7)
        ellipse(p, cx + lx * 0.6 + 1.8, cy + ly * 0.6 + 2.0 + dy, 0.8, 0.8)
        if pose.eyes == "down":  # sleepy-focused lid in face colour
            p.setBrush(BELLY)
            p.drawRect(QRectF(cx - rx - 2, cy - ry - 2, 2 * rx + 4, ry * 0.9 + 2))
            p.setPen(edge_pen(EYE, 1.6))
            p.drawLine(QPointF(cx - rx + 0.5, cy - ry * 0.1), QPointF(cx + rx - 0.5, cy - ry * 0.1))
    else:
        p.setPen(edge_pen(EYE, 2.3))
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


def draw_beak(p: QPainter, cx: float, cy: float, mouth: str) -> None:
    """Closed beak for smile/flat/sleepy; open for open/o (wider for 'open')."""
    gape = {"open": 6.5, "o": 3.5}.get(mouth, 0.0)
    pen = edge_pen(BEAK_DARK, 1.3)
    if gape:
        inside = QPainterPath(QPointF(cx - 7, cy))
        inside.quadTo(cx, cy + gape * 1.6, cx + 7, cy)
        inside.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(MOUTH_IN)
        p.drawPath(inside)
        lower = QPainterPath(QPointF(cx - 6, cy + 0.5))
        lower.quadTo(cx, cy + gape * 1.9, cx + 6, cy + 0.5)
        lower.quadTo(cx, cy + gape * 1.2, cx - 6, cy + 0.5)
        p.setPen(pen)
        p.setBrush(BEAK)
        p.drawPath(lower)
    upper = QPainterPath(QPointF(cx - 8, cy))
    upper.quadTo(cx - 5, cy - 6, cx, cy - 6.2)
    upper.quadTo(cx + 5, cy - 6, cx + 8, cy)
    upper.quadTo(cx, cy + (2.5 if not gape else 1.0) + 2, cx - 8, cy)
    p.setPen(pen)
    p.setBrush(BEAK)
    p.drawPath(upper)
    if not gape and mouth == "smile":  # tiny upturned corners
        p.setPen(edge_pen(BEAK_DARK, 1.2))
        p.drawLine(QPointF(cx - 8, cy), QPointF(cx - 9.5, cy - 1.5))
        p.drawLine(QPointF(cx + 8, cy), QPointF(cx + 9.5, cy - 1.5))
    p.setPen(Qt.NoPen)


def draw_penguin(p: QPainter, pose: Pose, t: float) -> None:
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)

    shrink = max(0.55, 1 + pose.bob / 40)
    p.setPen(Qt.NoPen)
    p.setBrush(gp.SHADOW)
    ellipse(p, 80, 150, 32 * shrink, 5 * shrink)

    p.save()
    p.translate(0, pose.bob)

    draw_foot(p, 66, 144, -1)
    draw_foot(p, 94, 144, 1)

    # body (squash anchored at the feet): dark back, white belly, soft sheen
    p.save()
    p.translate(80, 146)
    p.scale(1 + (1 - pose.squash) * 0.6, pose.squash)
    p.translate(-80, -146)
    body = ellipse_path(80, 113, 34, 31)
    p.setPen(edge_pen())
    p.setBrush(BACK)
    p.drawPath(body)
    p.save()
    p.setClipPath(body)
    p.setPen(Qt.NoPen)
    p.setBrush(BELLY)
    ellipse(p, 80, 119, 25, 25)
    p.setBrush(BELLY_SHADE)
    ellipse(p, 80, 135, 20, 7)
    p.restore()
    p.restore()

    for prop in pose.behind:
        p.save()
        prop(p, t)
        p.restore()

    draw_flipper(p, 50, 100, pose.arm_l, side=1)
    draw_flipper(p, 110, 100, -pose.arm_r, side=-1)

    # head
    p.save()
    p.translate(80, 98)
    p.rotate(pose.head_tilt)
    p.translate(-80, -98)

    # little head tuft, swaying a touch
    sway = math.sin(t * gp.TAU) * 2
    tuft = QPainterPath(QPointF(76, 34))
    tuft.quadTo(74 + sway, 24, 70 + sway, 22)
    tuft.quadTo(80 + sway, 24, 84, 34)
    p.setPen(edge_pen())
    p.setBrush(BACK)
    p.drawPath(tuft)

    head = ellipse_path(80, 66, 41, 35)
    p.setPen(edge_pen())
    p.setBrush(BACK)
    p.drawPath(head)
    p.save()
    p.setClipPath(head)
    p.setPen(Qt.NoPen)
    p.setBrush(SHEEN)
    ellipse(p, 66, 44, 16, 7)
    # heart-shaped white face: two eye lobes and a rounded chin
    face = QPainterPath()
    face.setFillRule(Qt.WindingFill)
    face.addEllipse(QPointF(64, 68), 16.5, 17.5)
    face.addEllipse(QPointF(96, 68), 16.5, 17.5)
    face.addEllipse(QPointF(80, 82), 22, 16)
    p.setBrush(BELLY)
    p.drawPath(face.simplified())
    p.restore()

    draw_eye(p, 65, 67, pose)
    draw_eye(p, 95, 67, pose)
    if pose.blush:
        p.setBrush(gp.PINK)
        ellipse(p, 54, 81, 6, 3.5)
        ellipse(p, 106, 81, 6, 3.5)
    draw_beak(p, 80, 82, pose.mouth)
    p.restore()

    p.restore()  # bob

    for prop in pose.front:
        p.save()
        prop(p, t)
        p.restore()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--sheet", type=Path, help="write a contact-sheet preview PNG here")
    args = ap.parse_args()
    _app = QGuiApplication([])
    args.out.mkdir(parents=True, exist_ok=True)
    rendered = gp.generate(args.out, draw_penguin, char_id="penguin", name="Penguin")
    total = sum(len(v) for v in rendered.values())
    print(f"wrote {total} frames for {len(rendered)} states to {args.out}")
    if args.sheet:
        gp.contact_sheet(rendered, args.sheet)
        print(f"contact sheet: {args.sheet}")


if __name__ == "__main__":
    main()
