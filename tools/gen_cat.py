"""Generate the cat character's frames with QPainter.

    python tools/gen_cat.py                    # writes bao/characters/cat/
    python tools/gen_cat.py --sheet cat.png    # also writes a contact sheet preview PNG
    python tools/gen_sounds.py --character cat   # then (re)make its meows

A ginger tabby that reuses the panda's poses, props and animation timings
(tools/gen_panda.py); only the body is drawn differently.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import gen_panda as gp
from gen_panda import Pose, ellipse
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPen

OUT = Path(__file__).resolve().parent.parent / "bao" / "characters" / "cat"

GINGER = QColor("#f2a65e")
STRIPE = QColor("#d27a35")
CREAM = QColor("#fff4e4")
OUTLINE = QColor("#7a4527")  # warm brown; readable on light and dark desktops
EAR_PINK = QColor("#f6b3b8")
NOSE = QColor("#ee8a95")
IRIS = QColor("#8bcf5f")
PUPIL = QColor("#23232a")
WHISKER = QColor(122, 69, 39, 170)


def outline_pen(w: float = 2.2) -> QPen:
    pen = QPen(OUTLINE, w)
    pen.setJoinStyle(Qt.RoundJoin)
    pen.setCapStyle(Qt.RoundCap)
    return pen


def ellipse_path(cx: float, cy: float, rx: float, ry: float) -> QPainterPath:
    path = QPainterPath()
    path.addEllipse(QPointF(cx, cy), rx, ry)
    return path


def triangle(
    a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]
) -> QPainterPath:
    path = QPainterPath(QPointF(*a))
    path.lineTo(QPointF(*b))
    path.lineTo(QPointF(*c))
    path.closeSubpath()
    return path


def shrink(pts: list[tuple[float, float]], k: float) -> list[tuple[float, float]]:
    cx = sum(x for x, _ in pts) / 3
    cy = sum(y for _, y in pts) / 3
    return [(cx + (x - cx) * k, cy + (y - cy) * k) for x, y in pts]


def draw_tail(p: QPainter, t: float, sleepy: bool) -> None:
    sway = math.sin(t * gp.TAU) * (4 if sleepy else 10)
    path = QPainterPath(QPointF(104, 136))
    if sleepy:  # curled along the ground
        path.cubicTo(130, 146, 150 + sway * 0.3, 134, 140, 120)
    else:
        path.cubicTo(134, 136, 136 + sway * 0.4, 104, 136 + sway, 84)
    for color, width in ((OUTLINE, 13.5), (GINGER, 10.5)):
        pen = QPen(color, width)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
    stripes = QPen(STRIPE, 10.5)
    stripes.setCapStyle(Qt.FlatCap)
    stripes.setDashPattern([0.45, 0.75])
    stripes.setDashOffset(-1.3)
    p.setPen(stripes)
    p.drawPath(path)
    p.setPen(Qt.NoPen)


def draw_arm(p: QPainter, sx: float, sy: float, angle: float) -> None:
    p.save()
    p.translate(sx, sy)
    p.rotate(angle)
    p.setPen(outline_pen(1.6))
    p.setBrush(GINGER)
    p.drawRoundedRect(QRectF(-7.5, -6, 15, 33), 7.5, 7.5)
    p.setPen(Qt.NoPen)
    p.setBrush(CREAM)
    ellipse(p, 0, 22, 6, 4.5)
    p.restore()


def draw_eye(p: QPainter, cx: float, cy: float, pose: Pose) -> None:
    lx, ly = pose.look
    if pose.eyes in ("open", "wide", "down"):
        rx, ry = (7.2, 8.4) if pose.eyes == "wide" else (6.4, 7.6)
        eye = ellipse_path(cx, cy, rx, ry)
        p.setPen(outline_pen(1.6))
        p.setBrush(IRIS)
        p.drawPath(eye)
        p.save()
        p.setClipPath(eye)
        p.setPen(Qt.NoPen)
        p.setBrush(PUPIL)
        dy = 2.5 if pose.eyes == "down" else 0
        prx = 3.6 if pose.eyes == "wide" else 1.9  # wide = excited round pupils
        ellipse(p, cx + lx * 0.9, cy + ly * 0.9 + dy, prx, 5.6)
        p.setBrush(QColor("white"))
        ellipse(p, cx + lx * 0.6 - 2.2, cy + ly * 0.6 - 3 + dy, 1.6, 1.6)
        if pose.eyes == "down":  # half-closed lid
            p.setBrush(GINGER)
            p.drawRect(QRectF(cx - rx - 1, cy - ry - 1, 2 * rx + 2, ry * 0.95))
            p.setPen(outline_pen(1.6))
            p.drawLine(QPointF(cx - rx, cy - ry * 0.05), QPointF(cx + rx, cy - ry * 0.05))
        p.restore()
    else:
        pen = outline_pen(2.4)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        path = QPainterPath()
        if pose.eyes == "happy":  # ^ ^
            path.moveTo(cx - 5, cy + 2)
            path.quadTo(cx, cy - 5, cx + 5, cy + 2)
        else:  # closed: gentle downward arc
            path.moveTo(cx - 5, cy)
            path.quadTo(cx, cy + 4, cx + 5, cy)
        p.drawPath(path)
    p.setPen(Qt.NoPen)


def draw_whiskers(p: QPainter) -> None:
    pen = QPen(WHISKER, 1.2)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    for side in (-1, 1):
        for dy, ey in ((-2, -7), (1.5, 0), (5, 7)):
            p.drawLine(QPointF(80 + side * 15, 80 + dy), QPointF(80 + side * 44, 80 + dy + ey))
    p.setPen(Qt.NoPen)


def draw_cat(p: QPainter, pose: Pose, t: float) -> None:
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    sleepy = pose.mouth == "sleepy"

    shrink_k = max(0.55, 1 + pose.bob / 40)
    p.setPen(Qt.NoPen)
    p.setBrush(gp.SHADOW)
    ellipse(p, 80, 150, 34 * shrink_k, 5 * shrink_k)

    p.save()
    p.translate(0, pose.bob)

    draw_tail(p, t, sleepy)

    # back paws
    p.setPen(outline_pen(1.6))
    p.setBrush(CREAM)
    ellipse(p, 61, 141, 12, 8)
    ellipse(p, 99, 141, 12, 8)

    # body (squash anchored at the feet), tabby stripes clipped to it
    p.save()
    p.translate(80, 146)
    p.scale(1 + (1 - pose.squash) * 0.6, pose.squash)
    p.translate(-80, -146)
    body = ellipse_path(80, 117, 33, 28)
    p.setPen(outline_pen())
    p.setBrush(GINGER)
    p.drawPath(body)
    p.save()
    p.setClipPath(body)
    p.setPen(Qt.NoPen)
    p.setBrush(STRIPE)
    for side in (-1, 1):
        for i in range(3):
            p.save()
            p.translate(80 + side * 31, 104 + i * 10)
            p.rotate(side * -12)
            p.drawRoundedRect(QRectF(-9, -2.2, 18, 4.4), 2.2, 2.2)
            p.restore()
    p.setBrush(CREAM)
    ellipse(p, 80, 124, 19, 16)  # belly
    p.restore()
    p.restore()

    for prop in pose.behind:
        p.save()
        prop(p, t)
        p.restore()

    draw_arm(p, 52, 104, pose.arm_l)
    draw_arm(p, 108, 104, -pose.arm_r)

    # head
    p.save()
    p.translate(80, 98)
    p.rotate(pose.head_tilt)
    p.translate(-80, -98)

    for pts in ([(42, 56), (47, 17), (76, 38)], [(118, 56), (113, 17), (84, 38)]):
        p.setPen(outline_pen())
        p.setBrush(GINGER)
        p.drawPath(triangle(*pts))
        p.setPen(Qt.NoPen)
        p.setBrush(EAR_PINK)
        p.drawPath(triangle(*shrink(pts, 0.55)))

    head = ellipse_path(80, 68, 42, 34)
    p.setPen(outline_pen())
    p.setBrush(GINGER)
    p.drawPath(head)
    p.save()
    p.setClipPath(head)
    p.setPen(Qt.NoPen)
    p.setBrush(STRIPE)
    for dx, h in ((-7, 9), (0, 12), (7, 9)):  # forehead "M"
        p.drawRoundedRect(QRectF(80 + dx - 2, 33, 4, h), 2, 2)
    for side in (-1, 1):  # cheek stripes
        for i in range(2):
            p.drawRoundedRect(QRectF(80 + side * 41 - 7, 62 + i * 7, 14, 3.6), 1.8, 1.8)
    p.setBrush(CREAM)  # muzzle
    ellipse(p, 73, 82, 10, 7.5)
    ellipse(p, 87, 82, 10, 7.5)
    p.restore()

    draw_eye(p, 63, 65, pose)
    draw_eye(p, 97, 65, pose)
    if pose.blush:
        p.setBrush(gp.PINK)
        ellipse(p, 52, 79, 6, 3.5)
        ellipse(p, 108, 79, 6, 3.5)
    draw_whiskers(p)

    nose = QPainterPath(QPointF(76, 75.5))
    nose.lineTo(84, 75.5)
    nose.quadTo(80, 81.5, 80, 81.5)
    nose.closeSubpath()
    nose_pen = QPen(NOSE, 1.6)
    nose_pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(nose_pen)
    p.setBrush(NOSE)
    p.drawPath(nose)
    gp.draw_mouth(p, 80, 82, pose.mouth)
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
    rendered = gp.generate(args.out, draw_cat, char_id="cat", name="Cat")
    total = sum(len(v) for v in rendered.values())
    print(f"wrote {total} frames for {len(rendered)} states to {args.out}")
    if args.sheet:
        gp.contact_sheet(rendered, args.sheet)
        print(f"contact sheet: {args.sheet}")


if __name__ == "__main__":
    main()
