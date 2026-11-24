"""The floating pet window: animated sprite + speech bubble, draggable, right-click menu."""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QContextMenuEvent,
    QFont,
    QFontMetricsF,
    QGuiApplication,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QMenu, QWidget

from . import platform_mac
from .character import Animation, Character
from .config import DEFAULT_CHARACTER, Config
from .roam import Roamer
from .sessions import Display, State, format_duration
from .sound import CUE_LABELS

log = logging.getLogger(__name__)

BUBBLE_H = 66  # logical px reserved above the sprite (before scaling): 2 text lines + 1 small
TITLE_WRAP_W = 132  # logical px: longer bubble text wraps onto a second line
TITLE_MAX_LINES = 2
MIN_W = 210
BUBBLE_SECONDS = 4.0
STICKY_BUBBLE = {State.WAITING, State.NEEDS_PERMISSION}
HIDDEN_BUBBLE = {State.SLEEPING}
ROAM_STATES = {State.IDLE, State.WAITING}  # nothing for Bao to do: wander around
ROAM_DELAY = 8.0  # seconds of staying put before the first stroll
ROAM_TICK_MS = 33
SIZES = [("Small", 0.7), ("Medium", 1.0), ("Large", 1.4)]
SHAKE_SECONDS = 0.9
SHAKE_PX = 7.0  # at scale 1
DEFAULT_REMINDER_SECONDS = 60.0
VOLUMES = [("25%", 0.25), ("50%", 0.5), ("75%", 0.75), ("100%", 1.0)]


def load_frames(anim: Animation) -> list[QPixmap]:
    if anim.sheet:
        sheet = QPixmap(str(anim.sheet.path))
        w, h = anim.sheet.frame_size
        return [sheet.copy(QRect(i * w, 0, w, h)) for i in range(anim.sheet.count)]
    return [QPixmap(str(p)) for p in anim.frames]


def wrap_text(text: str, metrics: QFontMetricsF, max_w: float, max_lines: int) -> list[str]:
    """Split ``text`` into at most ``max_lines`` lines no wider than ``max_w``.

    Breaks between words and keeps the lines balanced ("Bao is waiting / for you", not
    "Bao is waiting for / you"). Whatever still doesn't fit is elided on the last line.
    """
    words = text.split()
    if not words:
        return [""]
    width = metrics.horizontalAdvance
    if width(text) <= max_w or max_lines <= 1 or len(words) == 1:
        return [metrics.elidedText(" ".join(words), Qt.ElideRight, max_w)]
    if max_lines == 2:
        # try every break; prefer splits where both lines fit, then the most even one
        def cost(i: int) -> tuple[bool, float]:
            a, b = width(" ".join(words[:i])), width(" ".join(words[i:]))
            return (max(a, b) > max_w, max(a, b))

        i = min(range(1, len(words)), key=cost)
        rest = metrics.elidedText(" ".join(words[i:]), Qt.ElideRight, max_w)
        return [metrics.elidedText(" ".join(words[:i]), Qt.ElideRight, max_w), rest]
    # more lines: fill greedily, keep the last two balanced
    line = words.pop(0)
    while words and width(f"{line} {words[0]}") <= max_w:
        line = f"{line} {words.pop(0)}"
    return [line, *wrap_text(" ".join(words), metrics, max_w, max_lines - 1)]


class PetWindow(QWidget):
    quit_requested = Signal()
    character_changed = Signal(str)
    sound_settings_changed = Signal()
    test_sound_requested = Signal()
    clicked = Signal(object)  # Display under the click: focus that session's terminal
    reminder_changed = Signal(float)  # seconds (0 = off)

    def __init__(self, config: Config, characters: dict[str, Character]) -> None:
        super().__init__(
            None,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
        self.setWindowTitle("Claude Pet")

        self.config = config
        self.characters = characters
        self.character = self._pick_character(config.character)
        self._cache: dict[str, list[QPixmap]] = {}

        self.display: Display | None = None
        self._anim: Animation | None = None
        self._frames: list[QPixmap] = []
        self._frame = 0
        self._bubble_visible = False
        self._hover = False
        self._drag_offset: QPoint | None = None
        self._dragged = False

        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._next_frame)
        self._bubble_timer = QTimer(self)
        self._bubble_timer.setSingleShot(True)
        self._bubble_timer.timeout.connect(self._hide_bubble)
        self._shake_started: float | None = None
        self._shake_timer = QTimer(self)
        self._shake_timer.setInterval(16)
        self._shake_timer.timeout.connect(self._shake_step)
        self._roamer = Roamer(self.character.roam, config.scale)
        self._mirror = False  # sprite flipped to face the way it travels
        self._roam_timer = QTimer(self)
        self._roam_timer.setInterval(ROAM_TICK_MS)
        self._roam_timer.timeout.connect(self._roam_tick)

        self._apply_size()
        self._restore_position()

    # -- public ---------------------------------------------------------------------------

    def show(self) -> None:  # type: ignore[override]
        super().show()
        # winId() is an NSView* only on the Cocoa platform plugin; on others (offscreen,
        # minimal) treating it as one segfaults.
        if QGuiApplication.platformName() == "cocoa":
            platform_mac.float_on_all_spaces(int(self.winId()))

    def set_display(self, display: Display) -> None:
        previous = self.display
        self.display = display
        self._play(self._animation_now())
        if previous is None or (previous.state, previous.text, previous.project) != (
            display.state,
            display.text,
            display.project,
        ):
            self._show_bubble_for(display)
        self._update_roaming()
        self.update()

    def nudge(self) -> None:
        """Shake the pet and show its bubble: something still needs the user."""
        self._shake_started = time.monotonic()
        self._shake_timer.start()
        if self.display is not None:
            self._show_bubble_for(self.display)

    def _shake_offset(self) -> float:
        if self._shake_started is None:
            return 0.0
        t = time.monotonic() - self._shake_started
        if t >= SHAKE_SECONDS:
            return 0.0
        decay = 1 - t / SHAKE_SECONDS
        return SHAKE_PX * self.config.scale * decay * math.sin(t * 2 * math.pi * 7)

    def _shake_step(self) -> None:
        if self._shake_started is None or time.monotonic() - self._shake_started >= SHAKE_SECONDS:
            self._shake_started = None
            self._shake_timer.stop()
        self.update()

    # -- roaming --------------------------------------------------------------------------

    def _animation_now(self) -> Animation:
        if self._roamer.moving or self._roamer.airborne:
            return self.character.animation_for("roaming")
        d = self.display
        if d is None:
            return self.character.animation_for(self.character.fallback_state)
        return self.character.animation_for(d.state.value, d.variant)

    def _wants_roam(self) -> bool:
        d = self.display
        return bool(self.config.roam and d is not None and d.state in ROAM_STATES)

    def _update_roaming(self) -> None:
        now = time.monotonic()
        if self._wants_roam():
            if not self._roamer.active or self._roamer.phase == "returning":
                self._roamer.start((self.x(), self.y()), self._roam_bounds(), now, ROAM_DELAY)
                self._roam_timer.start()
        elif self._roamer.active:
            self._roamer.go_home(now)
            if not self._roamer.active:
                self._roam_stopped()

    def _roam_bounds(self) -> tuple[float, float, float, float]:
        screen = self.screen() or QGuiApplication.primaryScreen()
        g = screen.availableGeometry()
        return (g.left(), g.top(), g.right() - self.width() + 1, g.bottom() - self.height() + 1)

    def _roam_tick(self) -> None:
        if self._drag_offset is not None:
            return  # held by the user
        x, y = self._roamer.step(time.monotonic())
        self.move(round(x), round(y))
        facing, faces = self._roamer.facing, self._roamer.spec.faces
        if facing:
            self._mirror = (faces == "left" and facing > 0) or (faces == "right" and facing < 0)
        if not self._roamer.active:
            self._roam_stopped()
            return
        self._play(self._animation_now())
        self.update()

    def _roam_stopped(self) -> None:
        self._roam_timer.stop()
        self._mirror = False
        self._play(self._animation_now())
        self.update()

    def _snap_home(self) -> None:
        """Jump straight back home (before resizing or switching character)."""
        home = self._roamer.home if self._roamer.active else None
        self._roamer.stop()
        if home is not None:
            self.move(round(home[0]), round(home[1]))
        self._roam_stopped()

    # -- character / animation -------------------------------------------------------------

    def _pick_character(self, cid: str) -> Character:
        if cid in self.characters:
            return self.characters[cid]
        fallback = self.characters.get(DEFAULT_CHARACTER) or next(iter(self.characters.values()))
        log.warning("character %r not found, using %r", cid, fallback.id)
        return fallback

    def set_character(self, cid: str) -> None:
        if cid not in self.characters or cid == self.character.id:
            return
        self._snap_home()
        self.character = self.characters[cid]
        self._roamer = Roamer(self.character.roam, self.config.scale)
        self._cache.clear()
        self._anim = None
        self.config.character = cid
        self.config.save()
        self._apply_size()
        if self.display:
            self.set_display(self.display)
        self.character_changed.emit(cid)

    def _frames_for(self, anim: Animation) -> list[QPixmap]:
        key = anim.name
        if key not in self._cache:
            frames = [f for f in load_frames(anim) if not f.isNull()]
            if not frames:
                log.error("no loadable frames for %s/%s", self.character.id, anim.name)
            self._cache[key] = frames
        return self._cache[key]

    def _play(self, anim: Animation) -> None:
        if self._anim is not None and anim.name == self._anim.name:
            return
        self._anim = anim
        self._frames = self._frames_for(anim)
        self._frame = 0
        self._anim_timer.start(max(16, int(1000 / anim.fps)))
        self.update()

    def _next_frame(self) -> None:
        anim = self._anim
        if anim is None or not self._frames:
            return
        if self._frame + 1 < len(self._frames):
            self._frame += 1
        elif anim.loop:
            self._frame = 0
        elif anim.next:
            self._play(self.character.animations[anim.next])
            return
        else:
            self._anim_timer.stop()  # hold last frame
        self.update()

    # -- geometry -------------------------------------------------------------------------

    def _sprite_size(self) -> tuple[int, int]:
        w, h = self.character.size
        s = self.config.scale
        return round(w * s), round(h * s)

    def _bubble_height(self) -> int:
        return round(BUBBLE_H * min(1.2, max(0.85, self.config.scale)))

    def _apply_size(self) -> None:
        sw, sh = self._sprite_size()
        bottom_right = self.geometry().bottomRight() if self.isVisible() else None
        self.setFixedSize(max(sw, MIN_W), sh + self._bubble_height())
        if bottom_right is not None:  # grow up/left so the pet stays where it stands
            self.move(bottom_right.x() - self.width() + 1, bottom_right.y() - self.height() + 1)
            self._save_position()

    def _restore_position(self) -> None:
        pos = self.config.position
        if pos is not None:
            p = QPoint(*pos)
            if any(s.availableGeometry().contains(p) for s in QGuiApplication.screens()):
                self.move(p)
                return
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            g = screen.availableGeometry()
            self.move(g.right() - self.width() - 24, g.bottom() - self.height() - 24)

    def _save_position(self) -> None:
        home = self._roamer.home if self._roamer.active else None
        x, y = (round(home[0]), round(home[1])) if home else (self.x(), self.y())
        self.config.position = [x, y]
        self.config.save()

    # -- bubble ---------------------------------------------------------------------------

    def _show_bubble_for(self, display: Display) -> None:
        if not self.config.show_bubble or display.state in HIDDEN_BUBBLE:
            self._hide_bubble()
            return
        self._bubble_visible = True
        if display.state in STICKY_BUBBLE:
            self._bubble_timer.stop()
        else:
            self._bubble_timer.start(int(BUBBLE_SECONDS * 1000))
        self.update()

    def _hide_bubble(self) -> None:
        self._bubble_visible = False
        self.update()

    def _bubble_lines(self) -> tuple[str, str]:
        """(main text, small second line). The second line holds only extras, if any."""
        d = self.display
        if d is None:
            return "", ""
        extras = []
        if d.state is State.WAITING and d.duration is not None:
            extras.append(f"took {format_duration(d.duration)}")
        if d.session_count > 1:
            extras.append(f"{d.session_count} sessions")
        return d.text, " · ".join(extras)

    # -- painting -------------------------------------------------------------------------

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        sw, sh = self._sprite_size()
        sprite_rect = QRectF(
            (self.width() - sw) / 2 + self._shake_offset(), self.height() - sh, sw, sh
        )
        if self._frames:
            p.save()
            if self._mirror:
                cx = sprite_rect.center().x()
                p.translate(cx, 0)
                p.scale(-1, 1)
                p.translate(-cx, 0)
            p.drawPixmap(
                sprite_rect,
                self._frames[self._frame % len(self._frames)],
                QRectF(self._frames[0].rect()),
            )
            p.restore()
        if self.config.sounds_silenced():
            self._paint_moon(p, sprite_rect)
        if (self._bubble_visible or self._hover) and self.display is not None:
            self._paint_bubble(p, sprite_rect)
        p.end()

    def _paint_moon(self, p: QPainter, sprite: QRectF) -> None:
        """Small crescent at the sprite's top-left: sounds are off (Do Not Disturb)."""
        r = 9 * min(1.2, max(0.85, self.config.scale))
        c = QPointF(sprite.left() + r + 4, sprite.top() + r + 4)
        disc = QPainterPath()
        disc.addEllipse(c, r, r)
        bite = QPainterPath()
        bite.addEllipse(QPointF(c.x() + r * 0.55, c.y() - r * 0.35), r * 0.85, r * 0.85)
        p.setPen(QPen(QColor(40, 40, 60, 200), 1.2))
        p.setBrush(QColor("#f5c84c"))
        p.drawPath(disc.subtracted(bite))

    def _paint_bubble(self, p: QPainter, sprite: QRectF) -> None:
        title, sub = self._bubble_lines()
        if not title:
            return
        s = min(1.2, max(0.85, self.config.scale))
        f1 = QFont()
        f1.setPixelSize(round(13 * s))
        f1.setBold(True)
        f2 = QFont()
        f2.setPixelSize(round(11 * s))
        m1, m2 = QFontMetricsF(f1), QFontMetricsF(f2)
        pad = 8 * s
        max_w = self.width() - 4
        sub = m2.elidedText(sub, Qt.ElideMiddle, max_w - 2 * pad) if sub else ""
        lines = wrap_text(title, m1, min(TITLE_WRAP_W * s, max_w - 2 * pad), TITLE_MAX_LINES)
        widest = max([m1.horizontalAdvance(line) for line in lines] + [m2.horizontalAdvance(sub)])
        w = min(max_w, widest + 2 * pad)
        h = len(lines) * m1.lineSpacing() + (m2.height() if sub else 0) + pad * 1.2
        tail = 7 * s
        x = max(2.0, min(self.width() - w - 2, sprite.center().x() - w / 2))
        y = max(1.0, self._bubble_height() - h - tail - 2)
        rect = QRectF(x, y, w, h)

        urgent = self.display is not None and self.display.state is State.NEEDS_PERMISSION
        fill = QColor("#fff4d6") if urgent else QColor(255, 255, 255, 240)
        border = QColor("#d97757") if urgent else QColor(60, 60, 70, 160)

        path = QPainterPath()
        path.addRoundedRect(rect, 10 * s, 10 * s)
        cx = sprite.center().x()
        tail_path = QPainterPath()
        tail_path.moveTo(cx - tail, rect.bottom() - 1)
        tail_path.lineTo(cx, rect.bottom() + tail)
        tail_path.lineTo(cx + tail, rect.bottom() - 1)
        tail_path.closeSubpath()
        path = path.united(tail_path)
        p.setPen(QPen(border, 1.4))
        p.setBrush(fill)
        p.drawPath(path)

        p.setPen(QColor("#26262b"))
        p.setFont(f1)
        for i, line in enumerate(lines):
            p.drawText(QPointF(x + pad, y + pad * 0.6 + i * m1.lineSpacing() + m1.ascent()), line)
        if sub:
            p.setPen(QColor("#6b6b75"))
            p.setFont(f2)
            top = y + pad * 0.6 + len(lines) * m1.lineSpacing()
            p.drawText(QPointF(x + pad, top + m2.ascent()), sub)

    # -- mouse ----------------------------------------------------------------------------

    def mousePressEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if e.button() == Qt.LeftButton:
            self._drag_offset = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._dragged = False

    def mouseMoveEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_offset)
            self._dragged = True

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if e.button() == Qt.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            if self._dragged:  # dropped somewhere new: that's home now
                self._roamer.stop()
                self._roam_stopped()
                self._save_position()
                self._update_roaming()
            elif self.display is not None:  # click: show the bubble, focus the terminal
                self._bubble_visible = True
                self._bubble_timer.start(int(BUBBLE_SECONDS * 1000))
                self.update()
                self.clicked.emit(self.display)

    def enterEvent(self, _e) -> None:  # noqa: N802
        self._hover = True
        self.update()

    def leaveEvent(self, _e) -> None:  # noqa: N802
        self._hover = False
        self.update()

    # -- context menu ---------------------------------------------------------------------

    def contextMenuEvent(self, e: QContextMenuEvent) -> None:  # noqa: N802
        self.build_menu().exec(e.globalPos())

    def build_menu(self) -> QMenu:
        menu = QMenu(self)

        def radio(
            sub: QMenu,
            items: list[tuple[str, object]],
            current: object,
            on_pick: Callable[[object], None],
        ) -> None:
            group = QActionGroup(sub)
            for label, value in items:
                act = QAction(label, sub, checkable=True)
                act.setChecked(value == current)
                act.triggered.connect(lambda _=False, v=value: on_pick(v))
                group.addAction(act)
                sub.addAction(act)

        chars = menu.addMenu("Character")
        radio(
            chars,
            [(c.name, c.id) for c in self.characters.values()],
            self.character.id,
            lambda v: self.set_character(str(v)),
        )

        size = menu.addMenu("Size")
        radio(size, SIZES, self.config.scale, lambda v: self._set_scale(float(v)))  # type: ignore[arg-type]

        sound = menu.addMenu("Sound")
        mute = QAction("Mute", sound, checkable=True)
        mute.setChecked(self.config.muted)
        mute.toggled.connect(self._set_muted)
        sound.addAction(mute)
        sound.addSeparator()
        radio(sound, VOLUMES, self.config.volume, lambda v: self._set_volume(float(v)))  # type: ignore[arg-type]
        sound.addSeparator()
        for cue in [c for c in CUE_LABELS if c in self.character.sounds]:
            act = QAction(f"Play when: {CUE_LABELS[cue]}", sound, checkable=True)
            act.setChecked(cue not in self.config.muted_cues)
            act.toggled.connect(lambda on, c=cue: self._set_cue_enabled(c, on))
            sound.addAction(act)
        sound.addSeparator()
        sound.addAction("Play test sound", self.test_sound_requested.emit)

        remind = QAction("Remind me about permission requests", menu, checkable=True)
        remind.setChecked(self.config.permission_reminder_seconds > 0)
        remind.toggled.connect(self._set_reminder)
        menu.addAction(remind)
        dnd = QAction("Do Not Disturb", menu, checkable=True)
        dnd.setChecked(self.config.do_not_disturb)
        dnd.toggled.connect(self.set_do_not_disturb)
        menu.addAction(dnd)
        if self.config.quiet_hours:
            start, end = self.config.quiet_hours
            now = " (now)" if self.config.in_quiet_hours() else ""
            info = menu.addAction(f"Quiet hours {start}–{end}{now}")
            info.setEnabled(False)

        roam = QAction("Wander around when idle", menu, checkable=True)
        roam.setChecked(self.config.roam)
        roam.toggled.connect(self._set_roam)
        menu.addAction(roam)

        bubble = QAction("Show speech bubble", menu, checkable=True)
        bubble.setChecked(self.config.show_bubble)
        bubble.toggled.connect(self._set_show_bubble)
        menu.addAction(bubble)

        menu.addSeparator()
        menu.addAction("Quit Claude Pet", self.quit_requested.emit)
        return menu

    def _set_scale(self, scale: float) -> None:
        self._snap_home()
        self.config.scale = scale
        self._roamer.scale = scale
        self.config.save()
        self._apply_size()
        self._update_roaming()
        self.update()

    def _set_roam(self, on: bool) -> None:
        self.config.roam = on
        self.config.save()
        self._update_roaming()

    def _set_muted(self, muted: bool) -> None:
        self.config.muted = muted
        self.config.save()
        self.sound_settings_changed.emit()

    def _set_volume(self, volume: float) -> None:
        self.config.volume = volume
        self.config.save()
        self.sound_settings_changed.emit()

    def _set_cue_enabled(self, cue: str, enabled: bool) -> None:
        muted = set(self.config.muted_cues)
        muted.discard(cue) if enabled else muted.add(cue)
        self.config.muted_cues = sorted(muted)
        self.config.save()

    def _set_reminder(self, on: bool) -> None:
        self.config.permission_reminder_seconds = DEFAULT_REMINDER_SECONDS if on else 0.0
        self.config.save()
        self.reminder_changed.emit(self.config.permission_reminder_seconds)

    def set_do_not_disturb(self, on: bool) -> None:
        if on == self.config.do_not_disturb:
            return
        self.config.do_not_disturb = on
        self.config.save()
        log.info("do not disturb %s", "on" if on else "off")
        self.update()

    def _set_show_bubble(self, show: bool) -> None:
        self.config.show_bubble = show
        self.config.save()
        if show and self.display:
            self._show_bubble_for(self.display)
        else:
            self._hide_bubble()
