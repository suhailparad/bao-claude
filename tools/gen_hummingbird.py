"""Generate the hummingbird character's frames with QPainter.

    python tools/gen_hummingbird.py                          # writes bao/characters/hummingbird/
    python tools/gen_hummingbird.py --sheet hummingbird.png  # also writes a contact sheet
    python tools/gen_sounds.py --character hummingbird       # then (re)make its chirps

A round, colourful hummingbird that reuses the panda's poses, props and animation timings
(tools/gen_panda.py); only the body is drawn differently. Wings stand in for arms and
buzz (faint motion-blur copies) whenever the bird is awake.
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

OUT = Path(__file__).resolve().parent.parent / "bao" / "characters" / "hummingbird"

CROWN = QColor("#1fb89a")  # iridescent teal-emerald
BACK = QColor("#2f9e5a")  # emerald
BACK_DEEP = QColor("#1d6f47")
GORGET = QColor("#e8336f")  # ruby-magenta throat
GORGET_GLINT = QColor("#ff8fb6")
BELLY = QColor("#f4f1ea")
WING = QColor("#6a4fd1")  # violet
WING_TIP = QColor("#2fa7e0")  # sky blue
TAIL = QColor("#f08a2c")  # rufous orange
TAIL_TIP = QColor("#ffcf4d")
BILL = QColor("#34343c")
BILL_EDGE = QColor("#8a8a96")  # keeps the dark bill visible on dark desktops
EYE = QColor("#1b1d24")
EDGE = QColor("#14502f")  # dark green outline; reads on light and dark desktops
LEG = QColor("#3a3a44")
BLUSH = QColor(255, 105, 150, 175)  # warmer and stronger than the panda's: reads on teal


def edge_pen(color: QColor = EDGE, w: float = 1.8) -> QPen:
    pen = QPen(color, w)
    pen.setJoinStyle(Qt.RoundJoin)
    pen.setCapStyle(Qt.RoundCap)
    return pen


def ellipse_path(cx: float, cy: float, rx: float, ry: float) -> QPainterPath:
    path = QPainterPath()
    path.addEllipse(QPointF(cx, cy), rx, ry)
    return path


def draw_tail(p: QPainter, t: float, sleepy: bool) -> None:
    """Fan of three feathers sticking out behind the body to the lower right, flicking."""
    flick = 0 if sleepy else math.sin(t * gp.TAU * 2) * 5
    for angle, length in ((-30 + flick, 24), (-55, 28), (-80 - flick, 23)):
        p.save()
        p.translate(98, 130)
        p.rotate(angle)
        feather = QPainterPath(QPointF(-5, 0))
        feather.quadTo(-7, length * 0.7, 0, length)
        feather.quadTo(7, length * 0.7, 5, 0)
        feather.closeSubpath()
        grad = QLinearGradient(0, 0, 0, length)
        grad.setColorAt(0, TAIL)
        grad.setColorAt(1, TAIL_TIP)
        p.setPen(edge_pen(TAIL.darker(170), 1.4))
        p.setBrush(grad)
        p.drawPath(feather)
        p.restore()


def wing_path(side: int) -> QPainterPath:
    """A slim, pointed wing hinged at (0, 0), hanging down along +y."""
    path = QPainterPath(QPointF(-6, -4))
    path.cubicTo(-12, 12, -6 - side * 4, 30, -side * 6, 40)
    path.cubicTo(4 - side * 2, 30, 9, 12, 6, -4)
    path.quadTo(0, -9, -6, -4)
    return path


def draw_wing(p: QPainter, sx: float, sy: float, angle: float, side: int, buzz: float) -> None:
    """Wing at ``angle`` (0 = hanging); ``buzz`` adds translucent blur copies."""
    for ghost, alpha in ((-buzz, 70), (buzz, 70), (0.0, 255)):
        p.save()
        p.translate(sx, sy)
        p.rotate(angle + ghost)
        grad = QLinearGradient(0, 0, 0, 40)
        c1, c2 = QColor(WING), QColor(WING_TIP)
        c1.setAlpha(alpha)
        c2.setAlpha(alpha)
        grad.setColorAt(0, c1)
        grad.setColorAt(1, c2)
        pen_color = QColor(WING.darker(180))
        pen_color.setAlpha(alpha)
        p.setPen(edge_pen(pen_color, 1.4) if alpha == 255 else Qt.NoPen)
        p.setBrush(grad)
        path = wing_path(side)
        p.drawPath(path)
        if alpha == 255:  # two feather lines
            p.setPen(edge_pen(QColor(255, 255, 255, 90), 1.1))
            p.drawLine(QPointF(-side * 1, 8), QPointF(-side * 4, 30))
            p.drawLine(QPointF(side * 2.5, 6), QPointF(side * 0.5, 24))
        p.restore()


def draw_eye(p: QPainter, cx: float, cy: float, pose: Pose) -> None:
    lx, ly = pose.look
    if pose.eyes in ("open", "wide", "down"):
        r = 6.6 if pose.eyes == "wide" else 5.8
        dy = 1.8 if pose.eyes == "down" else 0
        x, y = cx + lx * 0.6, cy + ly * 0.6 + dy
        p.setPen(Qt.NoPen)
        p.setBrush(EYE)
        ellipse(p, x, y, r, r * 1.08)
        p.setBrush(QColor("white"))
        ellipse(p, x - 1.9, y - 2.4, 2.0, 2.0)
        ellipse(p, x + 2.0, y + 2.2, 0.9, 0.9)
        if pose.eyes == "down":  # half-closed lid in the head's colour
            p.setBrush(CROWN)
            p.drawRect(QRectF(cx - r - 2, cy - r - 3, 2 * r + 4, r * 0.95 + 3))
            p.setPen(edge_pen(EYE, 1.6))
            p.drawLine(QPointF(cx - r + 0.5, cy - r * 0.1), QPointF(cx + r - 0.5, cy - r * 0.1))
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


def draw_bill(p: QPainter, mouth: str) -> None:
    """Long needle bill sticking out of the face to the left; it parts for open/o."""
    gape = {"open": 9.0, "o": 5.0}.get(mouth, 0.0)
    base = QPointF(58, 76)
    p.save()
    p.translate(base)
    p.rotate(196)  # pointing left and a little down
    pen = edge_pen(BILL_EDGE, 1.1)
    for sign, rot in ((1, -gape / 2), (-1, gape / 2)):
        p.save()
        p.rotate(rot)
        half = QPainterPath(QPointF(0, 0))
        half.lineTo(0, sign * 2.6)
        half.quadTo(22, sign * 1.8, 44, 0)
        half.closeSubpath()
        p.setPen(pen)
        p.setBrush(BILL)
        p.drawPath(half)
        p.restore()
    if gape:  # a peek of tongue
        p.setPen(edge_pen(QColor("#f07a8c"), 1.6))
        p.drawLine(QPointF(2, 0), QPointF(18, 0))
    p.restore()
    if not gape and mouth == "smile":  # little smile at the bill's corner
        p.setPen(edge_pen(EYE, 1.5))
        p.setBrush(Qt.NoBrush)
        path = QPainterPath(QPointF(60, 79))
        path.quadTo(66, 83, 72, 80)
        p.drawPath(path)
    p.setPen(Qt.NoPen)


def draw_hummingbird(p: QPainter, pose: Pose, t: float) -> None:
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    sleepy = pose.mouth == "sleepy"

    if not pose.flying:  # in the air the window itself moves: no ground shadow
        shrink = max(0.55, 1 + pose.bob / 40)
        p.setPen(Qt.NoPen)
        p.setBrush(gp.SHADOW)
        ellipse(p, 80, 150, 28 * shrink, 4.5 * shrink)

    p.save()
    p.translate(0, pose.bob)

    draw_tail(p, t, sleepy)

    # tiny perching feet (tucked up under the body in flight)
    p.setPen(edge_pen(LEG, 2.0))
    for fx in (70, 90):
        if pose.flying:
            p.drawLine(QPointF(fx, 136), QPointF(fx + 3, 141))
            continue
        p.drawLine(QPointF(fx, 138), QPointF(fx, 146))
        p.drawLine(QPointF(fx, 146), QPointF(fx - 4, 148))
        p.drawLine(QPointF(fx, 146), QPointF(fx + 4, 148))
    p.setPen(Qt.NoPen)

    # body (squash anchored at the feet): emerald back, pale belly
    p.save()
    p.translate(80, 146)
    p.scale(1 + (1 - pose.squash) * 0.6, pose.squash)
    p.translate(-80, -146)
    body = ellipse_path(80, 114, 30, 28)
    grad = QLinearGradient(50, 90, 110, 140)
    grad.setColorAt(0, BACK)
    grad.setColorAt(1, BACK_DEEP)
    p.setPen(edge_pen())
    p.setBrush(grad)
    p.drawPath(body)
    p.save()
    p.setClipPath(body)
    p.setPen(Qt.NoPen)
    p.setBrush(BELLY)
    ellipse(p, 80, 124, 19, 19)
    p.setBrush(QColor(BACK.lighter(130)))  # speckles where green meets the belly
    for dx, dy in ((-14, 108), (14, 108), (-18, 116), (18, 116), (-8, 104), (8, 104)):
        ellipse(p, 80 + dx, dy, 1.8, 1.8)
    p.restore()
    p.restore()

    for prop in pose.behind:
        p.save()
        prop(p, t)
        p.restore()

    buzz = 0.0 if sleepy or pose.eyes == "closed" else (16.0 if pose.flying else 9.0)
    draw_wing(p, 54, 102, pose.arm_l, 1, buzz)
    draw_wing(p, 106, 102, -pose.arm_r, -1, buzz)

    # head
    p.save()
    p.translate(80, 98)
    p.rotate(pose.head_tilt)
    p.translate(-80, -98)

    head = ellipse_path(80, 66, 37, 33)
    hgrad = QRadialGradient(QPointF(68, 46), 60)
    hgrad.setColorAt(0, CROWN.lighter(125))
    hgrad.setColorAt(0.55, CROWN)
    hgrad.setColorAt(1, BACK)
    p.setPen(edge_pen())
    p.setBrush(hgrad)
    p.drawPath(head)
    p.save()
    p.setClipPath(head)
    p.setPen(Qt.NoPen)
    # shimmering ruby gorget across the throat
    gorget = QPainterPath()
    gorget.setFillRule(Qt.WindingFill)
    gorget.addEllipse(QPointF(80, 101), 28, 14)
    ggrad = QRadialGradient(QPointF(90, 86), 26)
    ggrad.setColorAt(0, GORGET_GLINT)
    ggrad.setColorAt(0.6, GORGET)
    ggrad.setColorAt(1, GORGET.darker(130))
    p.setBrush(ggrad)
    p.drawPath(gorget)
    p.setBrush(QColor(255, 255, 255, 50))  # crown sheen
    ellipse(p, 68, 44, 14, 6)
    p.restore()

    draw_eye(p, 67, 63, pose)
    draw_eye(p, 98, 63, pose)
    if pose.blush:
        p.setBrush(BLUSH)
        ellipse(p, 82, 79, 5.5, 3.2)
        ellipse(p, 106, 76, 5.5, 3.2)
    draw_bill(p, pose.mouth)
    p.restore()

    p.restore()  # bob

    for prop in pose.front:
        p.save()
        prop(p, t)
        p.restore()


def flying(t: float, i: int) -> Pose:
    """Hovering flight while roaming: wings high and beating fast, leaning toward the bill."""
    beat = math.sin(t * gp.TAU * 4)
    return Pose(
        flying=True,
        bob=math.sin(t * gp.TAU) * 2.5 - 4,
        head_tilt=-7,
        arm_l=118 + 28 * beat,
        arm_r=118 + 28 * beat,
        eyes="open",
        look=(-2.0, 0.0),
        mouth="smile",
    )


FLY = {"style": "fly", "speed": 70, "faces": "left"}  # bill points left: mirror when going right


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--sheet", type=Path, help="write a contact-sheet preview PNG here")
    args = ap.parse_args()
    _app = QGuiApplication([])
    args.out.mkdir(parents=True, exist_ok=True)
    rendered = gp.generate(
        args.out,
        draw_hummingbird,
        char_id="hummingbird",
        name="Hummingbird",
        poses={"roaming": flying},
        roam=FLY,
    )
    total = sum(len(v) for v in rendered.values())
    print(f"wrote {total} frames for {len(rendered)} states to {args.out}")
    if args.sheet:
        gp.contact_sheet(rendered, args.sheet)
        print(f"contact sheet: {args.sheet}")


if __name__ == "__main__":
    main()
