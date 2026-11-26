"""Generate the owl character's frames with QPainter.

    python tools/gen_owl.py                   # writes bao/characters/owl/
    python tools/gen_owl.py --sheet owl.png   # also writes a contact sheet
    python tools/gen_owl.py && python tools/gen_sounds.py --character owl  # then its hoots

A round, tawny owl that reuses the panda's poses, props and animation timings
(tools/gen_panda.py); only the body is drawn differently. Big amber eyes sit in a
heart-shaped face disc, broad barred wings stand in for arms, and it flies while roaming.
While thinking it turns its head much further than the panda does, and while sleeping
it peeks with one eye now and then.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import gen_panda as gp
from gen_panda import Pose, ellipse
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)

OUT = Path(__file__).resolve().parent.parent / "bao" / "characters" / "owl"

PLUMAGE = QColor("#9a6b43")  # warm tawny brown
PLUMAGE_DEEP = QColor("#6f4a2c")
PLUMAGE_LIGHT = QColor("#c08c5a")
FACE = QColor("#f3e4c7")  # cream face disc
FACE_RIM = QColor("#7a4f2e")
BELLY = QColor("#ecd6ad")
CHEVRON = QColor("#a87a4e")  # little V marks on the chest
WING_BAR = QColor("#e2c79a")
IRIS = QColor("#f5b52e")  # amber
IRIS_DEEP = QColor("#d9811c")
PUPIL = QColor("#1b1712")
BEAK = QColor("#e0a33a")
BEAK_DEEP = QColor("#a8701f")
TALON = QColor("#e8b04a")
EDGE = QColor("#4a2f1c")  # dark brown outline; the mid-brown fill keeps it readable on dark
BLUSH = QColor(255, 130, 150, 150)


def edge_pen(color: QColor = EDGE, w: float = 1.8) -> QPen:
    pen = QPen(color, w)
    pen.setJoinStyle(Qt.RoundJoin)
    pen.setCapStyle(Qt.RoundCap)
    return pen


def ellipse_path(cx: float, cy: float, rx: float, ry: float) -> QPainterPath:
    path = QPainterPath()
    path.addEllipse(QPointF(cx, cy), rx, ry)
    return path


def wing_path() -> QPainterPath:
    """A broad, rounded wing hinged at (0, 0), hanging down along +y with scalloped tips."""
    path = QPainterPath(QPointF(-9, -5))
    path.cubicTo(-15, 8, -14, 26, -9, 36)
    for i in range(4):  # four rounded feather tips along the bottom edge
        x0 = -9 + i * 4.5
        path.quadTo(x0 + 2.25, 42 - abs(i - 1.5) * 1.2, x0 + 4.5, 36)
    path.cubicTo(13, 26, 14, 8, 9, -5)
    path.quadTo(0, -11, -9, -5)
    path.closeSubpath()
    return path


def draw_wing(p: QPainter, sx: float, sy: float, angle: float) -> None:
    p.save()
    p.translate(sx, sy)
    p.rotate(angle)
    grad = QLinearGradient(0, -5, 0, 40)
    grad.setColorAt(0, PLUMAGE)
    grad.setColorAt(1, PLUMAGE_DEEP)
    path = wing_path()
    p.setPen(edge_pen(EDGE, 1.5))
    p.setBrush(grad)
    p.drawPath(path)
    p.save()
    p.setClipPath(path)
    p.setPen(Qt.NoPen)
    p.setBrush(WING_BAR)  # pale bars across the flight feathers
    for y in (12, 21, 30):
        for x in (-6, 0, 6):
            ellipse(p, x, y + abs(x) * 0.15, 2.3, 1.4)
    p.restore()
    p.restore()


def draw_tufts(p: QPainter) -> None:
    """Two feathery ear tufts on top of the head."""
    for side in (1, -1):
        tuft = QPainterPath(QPointF(80 - side * 18, 38))
        tuft.quadTo(80 - side * 30, 30, 80 - side * 36, 18)
        tuft.quadTo(80 - side * 34, 32, 80 - side * 38, 44)
        tuft.closeSubpath()
        p.setPen(edge_pen(EDGE, 1.6))
        p.setBrush(PLUMAGE_DEEP)
        p.drawPath(tuft)


def face_disc() -> QPainterPath:
    """Heart-shaped facial disc: two overlapping circles and a chin point."""
    chin = QPainterPath(QPointF(56, 76))
    chin.quadTo(80, 98, 104, 76)
    chin.closeSubpath()
    return ellipse_path(65, 64, 20, 19).united(ellipse_path(95, 64, 20, 19)).united(chin)


def draw_eye(p: QPainter, cx: float, cy: float, pose: Pose, eyes: str) -> None:
    lx, ly = pose.look
    if eyes in ("open", "wide", "down"):
        r = 11.5 if eyes == "wide" else 10.5
        pr = 4.6 if eyes == "wide" else 5.6  # alarmed owls have small pupils
        p.setPen(edge_pen(EDGE, 1.4))
        g = QRadialGradient(QPointF(cx - 2, cy - 2), r * 1.2)
        g.setColorAt(0, IRIS.lighter(115))
        g.setColorAt(0.7, IRIS)
        g.setColorAt(1, IRIS_DEEP)
        p.setBrush(g)
        ellipse(p, cx, cy, r, r)
        p.setPen(Qt.NoPen)
        dy = 2.5 if eyes == "down" else 0
        px, py = cx + lx * 1.1, cy + ly * 1.1 + dy
        p.setBrush(PUPIL)
        ellipse(p, px, py, pr, pr)
        p.setBrush(QColor("white"))
        ellipse(p, px - 2.2, py - 2.6, 2.1, 2.1)
        ellipse(p, px + 2.4, py + 2.2, 0.9, 0.9)
        if eyes == "down":  # half-closed lid in the face disc's colour
            p.setBrush(FACE)
            p.drawRect(QRectF(cx - r - 1.5, cy - r - 1.5, 2 * r + 3, r + 1))
            p.setPen(edge_pen(EDGE, 1.6))
            p.drawLine(QPointF(cx - r + 0.5, cy - 0.5), QPointF(cx + r - 0.5, cy - 0.5))
    else:
        p.setPen(edge_pen(EDGE, 2.4))
        p.setBrush(Qt.NoBrush)
        path = QPainterPath()
        if eyes == "happy":  # ^ ^
            path.moveTo(cx - 6, cy + 2)
            path.quadTo(cx, cy - 6, cx + 6, cy + 2)
        else:  # closed: gentle downward arc with a few lashes of feather
            path.moveTo(cx - 6.5, cy - 1)
            path.quadTo(cx, cy + 4.5, cx + 6.5, cy - 1)
        p.drawPath(path)
    p.setPen(Qt.NoPen)


def draw_beak(p: QPainter, mouth: str) -> None:
    """Small hooked beak between the eyes; the lower half drops open for open/o."""
    gape = {"open": 6.0, "o": 3.5}.get(mouth, 0.0)
    if gape:
        lower = QPainterPath(QPointF(75, 80))
        lower.quadTo(80, 82 + gape * 1.4, 85, 80)
        lower.closeSubpath()
        p.setPen(edge_pen(BEAK_DEEP, 1.2))
        p.setBrush(QColor("#7a3a2a"))
        p.drawPath(lower)
    upper = QPainterPath(QPointF(74, 74))
    upper.quadTo(80, 70, 86, 74)
    upper.quadTo(84, 82, 80, 88 - gape * 0.4)  # hooked tip
    upper.quadTo(76, 82, 74, 74)
    upper.closeSubpath()
    grad = QLinearGradient(74, 72, 86, 88)
    grad.setColorAt(0, BEAK.lighter(115))
    grad.setColorAt(1, BEAK_DEEP)
    p.setPen(edge_pen(BEAK_DEEP.darker(140), 1.2))
    p.setBrush(grad)
    p.drawPath(upper)
    if not gape and mouth == "smile":  # tiny smile lines at the beak's corners
        p.setPen(edge_pen(FACE_RIM, 1.3))
        p.setBrush(Qt.NoBrush)
        for side in (1, -1):
            curve = QPainterPath(QPointF(80 - side * 6, 79))
            curve.quadTo(80 - side * 9, 82, 80 - side * 12, 80)
            p.drawPath(curve)
    p.setPen(Qt.NoPen)


def draw_feet(p: QPainter, pose: Pose) -> None:
    p.setPen(edge_pen(TALON.darker(150), 2.2))
    for fx in (68, 92):
        if pose.flying:  # tucked up, talons dangling a little
            p.drawLine(QPointF(fx, 138), QPointF(fx - 2, 143))
            p.drawLine(QPointF(fx, 138), QPointF(fx + 2, 143))
            continue
        for dx in (-5, 0, 5):
            p.drawLine(QPointF(fx, 141), QPointF(fx + dx, 147))
    p.setPen(Qt.NoPen)


def draw_owl(p: QPainter, pose: Pose, t: float) -> None:
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    sleepy = pose.mouth == "sleepy"

    if not pose.flying:  # in the air the window itself moves: no ground shadow
        shrink = max(0.55, 1 + pose.bob / 40)
        p.setPen(Qt.NoPen)
        p.setBrush(gp.SHADOW)
        ellipse(p, 80, 150, 32 * shrink, 5 * shrink)

    p.save()
    p.translate(0, pose.bob)

    draw_feet(p, pose)

    # body (squash anchored at the feet): tawny back, pale chest with V marks
    p.save()
    p.translate(80, 146)
    p.scale(1 + (1 - pose.squash) * 0.6, pose.squash)
    p.translate(-80, -146)
    body = ellipse_path(80, 116, 33, 29)
    grad = QLinearGradient(50, 90, 110, 145)
    grad.setColorAt(0, PLUMAGE_LIGHT)
    grad.setColorAt(1, PLUMAGE_DEEP)
    p.setPen(edge_pen())
    p.setBrush(grad)
    p.drawPath(body)
    p.save()
    p.setClipPath(body)
    p.setPen(Qt.NoPen)
    p.setBrush(BELLY)
    ellipse(p, 80, 124, 21, 20)
    p.setPen(edge_pen(CHEVRON, 1.5))
    p.setBrush(Qt.NoBrush)
    for row, y in enumerate((112, 121, 130)):
        for k in range(3 - row % 2):
            x = 80 + (k - (2 - row % 2) / 2) * 11
            v = QPainterPath(QPointF(x - 3, y))
            v.lineTo(x, y + 3)
            v.lineTo(x + 3, y)
            p.drawPath(v)
    p.restore()
    p.restore()

    for prop in pose.behind:
        p.save()
        prop(p, t)
        p.restore()

    draw_wing(p, 52, 102, pose.arm_l)
    draw_wing(p, 108, 102, -pose.arm_r)

    # head
    p.save()
    p.translate(80, 98)
    p.rotate(pose.head_tilt)
    p.translate(-80, -98)

    draw_tufts(p)
    head = ellipse_path(80, 64, 40, 35)
    hgrad = QRadialGradient(QPointF(70, 44), 64)
    hgrad.setColorAt(0, PLUMAGE_LIGHT)
    hgrad.setColorAt(0.6, PLUMAGE)
    hgrad.setColorAt(1, PLUMAGE_DEEP)
    p.setPen(edge_pen())
    p.setBrush(hgrad)
    p.drawPath(head)
    p.save()
    p.setClipPath(head)
    p.setPen(Qt.NoPen)
    p.setBrush(PLUMAGE_DEEP)  # speckles on the crown
    for dx, dy in ((-14, 36), (-4, 33), (6, 33), (16, 36), (-22, 42), (24, 42)):
        ellipse(p, 80 + dx, dy, 1.7, 1.4)
    p.restore()
    disc = face_disc()
    p.setPen(edge_pen(FACE_RIM, 1.8))
    p.setBrush(FACE)
    p.drawPath(disc)
    p.setPen(Qt.NoPen)

    # asleep, the owl peeks with its right eye now and then
    peek = sleepy and 0.45 <= t < 0.7
    draw_eye(p, 65, 63, pose, pose.eyes)
    draw_eye(p, 95, 63, pose, "down" if peek else pose.eyes)
    if pose.blush:
        p.setBrush(BLUSH)
        ellipse(p, 56, 80, 5.5, 3.2)
        ellipse(p, 104, 80, 5.5, 3.2)
    draw_beak(p, pose.mouth)
    p.restore()

    p.restore()  # bob

    for prop in pose.front:
        p.save()
        prop(p, t)
        p.restore()


def thinking(t: float, i: int) -> Pose:
    """Like the panda's, but the head swivels far: owls are famous for it."""
    pose = gp.thinking(t, i)
    pose.head_tilt = 16 + 6 * math.sin(t * gp.TAU)
    return pose


def flying(t: float, i: int) -> Pose:
    """Slow, broad wingbeats while roaming, looking straight ahead."""
    beat = math.sin(t * gp.TAU * 2)
    return Pose(
        flying=True,
        bob=math.sin(t * gp.TAU * 2 + 1.2) * 3 - 4,
        arm_l=105 + 45 * beat,
        arm_r=105 + 45 * beat,
        eyes="open",
        mouth="smile",
    )


FLY = {"style": "fly", "speed": 50, "faces": "front"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--sheet", type=Path, help="write a contact-sheet preview PNG here")
    args = ap.parse_args()
    _app = QGuiApplication([])
    args.out.mkdir(parents=True, exist_ok=True)
    rendered = gp.generate(
        args.out,
        draw_owl,
        char_id="owl",
        name="Owl",
        poses={"thinking": thinking, "roaming": flying},
        roam=FLY,
    )
    total = sum(len(v) for v in rendered.values())
    print(f"wrote {total} frames for {len(rendered)} states to {args.out}")
    if args.sheet:
        gp.contact_sheet(rendered, args.sheet)
        print(f"contact sheet: {args.sheet}")


if __name__ == "__main__":
    main()
