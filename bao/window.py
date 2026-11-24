"""The floating pet window: animated sprite + speech bubble, draggable, right-click menu."""

from __future__ import annotations

import logging
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
from .sessions import Display, State
from .sound import CUE_LABELS

log = logging.getLogger(__name__)

BUBBLE_H = 54  # logical px reserved above the sprite (before scaling)
MIN_W = 210
BUBBLE_SECONDS = 4.0
STICKY_BUBBLE = {State.WAITING, State.NEEDS_PERMISSION}
HIDDEN_BUBBLE = {State.SLEEPING}
SIZES = [("Small", 0.7), ("Medium", 1.0), ("Large", 1.4)]
VOLUMES = [("25%", 0.25), ("50%", 0.5), ("75%", 0.75), ("100%", 1.0)]


def load_frames(anim: Animation) -> list[QPixmap]:
    if anim.sheet:
        sheet = QPixmap(str(anim.sheet.path))
        w, h = anim.sheet.frame_size
        return [sheet.copy(QRect(i * w, 0, w, h)) for i in range(anim.sheet.count)]
    return [QPixmap(str(p)) for p in anim.frames]


class PetWindow(QWidget):
    quit_requested = Signal()
    character_changed = Signal(str)
    sound_settings_changed = Signal()
    test_sound_requested = Signal()

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
        self._play(self.character.animation_for(display.state.value, display.variant))
        if previous is None or (previous.state, previous.text, previous.project) != (
            display.state,
            display.text,
            display.project,
        ):
            self._show_bubble_for(display)
        self.update()

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
        self.character = self.characters[cid]
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
        self.config.position = [self.x(), self.y()]
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
        d = self.display
        if d is None:
            return "", ""
        sub = d.project or ""
        if d.session_count > 1:
            sub = f"{sub} · {d.session_count} sessions" if sub else f"{d.session_count} sessions"
        return d.text, sub

    # -- painting -------------------------------------------------------------------------

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        sw, sh = self._sprite_size()
        sprite_rect = QRectF((self.width() - sw) / 2, self.height() - sh, sw, sh)
        if self._frames:
            p.drawPixmap(
                sprite_rect,
                self._frames[self._frame % len(self._frames)],
                QRectF(self._frames[0].rect()),
            )
        if (self._bubble_visible or self._hover) and self.display is not None:
            self._paint_bubble(p, sprite_rect)
        p.end()

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
        title = m1.elidedText(title, Qt.ElideRight, max_w - 2 * pad)
        w = min(max_w, max(m1.horizontalAdvance(title), m2.horizontalAdvance(sub)) + 2 * pad)
        h = m1.height() + (m2.height() if sub else 0) + pad * 1.2
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
        p.drawText(QPointF(x + pad, y + pad * 0.6 + m1.ascent()), title)
        if sub:
            p.setPen(QColor("#6b6b75"))
            p.setFont(f2)
            p.drawText(QPointF(x + pad, y + pad * 0.6 + m1.height() + m2.ascent()), sub)

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
            if self._dragged:
                self._save_position()
            elif self.display is not None:  # click: show the bubble again
                self._bubble_visible = True
                self._bubble_timer.start(int(BUBBLE_SECONDS * 1000))
                self.update()

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

        bubble = QAction("Show speech bubble", menu, checkable=True)
        bubble.setChecked(self.config.show_bubble)
        bubble.toggled.connect(self._set_show_bubble)
        menu.addAction(bubble)

        menu.addSeparator()
        menu.addAction("Quit Claude Pet", self.quit_requested.emit)
        return menu

    def _set_scale(self, scale: float) -> None:
        self.config.scale = scale
        self.config.save()
        self._apply_size()
        self.update()

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

    def _set_show_bubble(self, show: bool) -> None:
        self.config.show_bubble = show
        self.config.save()
        if show and self.display:
            self._show_bubble_for(self.display)
        else:
            self._hide_bubble()
