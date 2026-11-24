"""The pet application: wires IPC → SessionTracker → PetWindow (and, later, sound)."""

from __future__ import annotations

import logging
import logging.handlers
import signal
import sys
import time
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from . import focus, platform_mac
from .character import discover_characters
from .config import Config
from .ipc import EventServer, InstanceLock, send_message
from .paths import home_dir, log_path
from .sessions import Display, SessionTracker, Timings
from .sound import SoundPlayer
from .window import PetWindow

log = logging.getLogger("bao")

TICK_MS = 500


class PetController(QObject):
    """Owns the tracker. Lives on the GUI thread; the IPC thread talks to it via signals."""

    display_changed = Signal(object)  # Display
    cue = Signal(str)  # sound cue name
    nudge = Signal(str)  # session id whose permission request is still unanswered
    quit_requested = Signal()
    dnd_requested = Signal(bool)  # `bao dnd on|off`
    _incoming = Signal(object)  # dict, emitted from the IPC thread → queued to GUI thread

    def __init__(
        self, timings: Timings | None = None, quit_after: float = 0.0, config: Config | None = None
    ) -> None:
        super().__init__()
        self.config = config
        self.tracker = SessionTracker(timings or Timings())
        self.quit_after = quit_after  # seconds with no sessions (after having had one); 0 = never
        self._had_sessions = False
        self._empty_since: float | None = None
        self.display: Display = self.tracker.resolve()
        self._status: dict[str, Any] = self._build_status()
        self._incoming.connect(self.apply)
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()

    # Called on the IPC thread. Must not touch tracker state directly.
    def handle_from_thread(self, msg: dict[str, Any]) -> dict[str, Any] | None:
        cmd = msg.get("cmd")
        if cmd == "status":
            status = self._status  # immutable snapshot rebuilt on the GUI thread
            if self.config is not None:  # plain reads of simple values: safe across threads
                status = {
                    **status,
                    "do_not_disturb": {
                        "active": self.config.sounds_silenced(),
                        "manual": self.config.do_not_disturb,
                        "quiet_hours": self.config.quiet_hours,
                    },
                }
            return status
        if cmd == "play":
            self.cue.emit(str(msg.get("cue") or "done"))  # queued to the GUI thread
            return {"ok": True}
        if cmd == "dnd":
            on = msg.get("on")
            if isinstance(on, bool):
                self.dnd_requested.emit(on)  # queued to the GUI thread
            return {"ok": True}
        if cmd == "quit":
            self.quit_requested.emit()
            return {"ok": True}
        if msg.get("event"):
            self._incoming.emit(msg)
            return None
        if cmd:
            return {"ok": False, "error": f"unknown command: {cmd}"}
        return None

    def apply(self, msg: dict[str, Any]) -> None:
        log.debug(
            "event %s session=%s tool=%s",
            msg.get("event"),
            msg.get("session_id"),
            msg.get("tool_name"),
        )
        cues = self.tracker.apply(msg)
        for name in cues:
            self.cue.emit(name)
        self._refresh()

    def focus_session(self, display: Display) -> bool:
        """Bring the terminal of the session the pet is showing to the front."""
        info = self.tracker.terminal_for(display.session_id)
        if info is None:
            log.info("no terminal known for session %s", display.session_id)
            return False
        log.info("focusing terminal %s %s", info.get("app", "?"), info.get("tty", ""))
        return focus.focus_terminal(info)

    def _on_tick(self) -> None:
        if self.tracker.tick():
            self._refresh()
        self._remind()
        self._check_auto_quit(time.monotonic())

    def _remind(self) -> None:
        for sid in self.tracker.due_reminders():
            log.info("permission request in session %s still unanswered, reminding", sid)
            self.cue.emit("alert")
            self.nudge.emit(sid)

    def set_reminder_seconds(self, seconds: float) -> None:
        self.tracker.timings.permission_reminder = seconds

    def _check_auto_quit(self, now: float) -> None:
        if self.tracker.sessions:
            self._had_sessions = True
            self._empty_since = None
            return
        if not self._had_sessions or self.quit_after <= 0:
            return
        if self._empty_since is None:
            self._empty_since = now
        elif now - self._empty_since >= self.quit_after:
            log.info("no Claude sessions for %.0f min, quitting", self.quit_after / 60)
            self._had_sessions = False  # emit once
            self.quit_requested.emit()

    def _refresh(self) -> None:
        new = self.tracker.resolve()
        self._status = self._build_status(new)
        if new != self.display:
            self.display = new
            self.display_changed.emit(new)

    def _build_status(self, display: Display | None = None) -> dict[str, Any]:
        return {
            "ok": True,
            "display": (display or self.display).to_dict(),
            "sessions": self.tracker.snapshot(),
        }


def setup_logging(verbose: bool = False) -> None:
    home_dir().mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh = logging.handlers.RotatingFileHandler(log_path(), maxBytes=1_000_000, backupCount=2)
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if sys.stderr is not None and sys.stderr.isatty():
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)


def run(initial_event: dict[str, Any] | None = None, verbose: bool = False) -> int:
    setup_logging(verbose)
    lock = InstanceLock()
    if not lock.acquire():
        log.info("another pet is already running")
        if initial_event:
            try:
                send_message(initial_event, timeout=0.5)
            except OSError:
                pass
        return 0

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Claude Pet")
    app.setQuitOnLastWindowClosed(False)
    platform_mac.hide_dock_icon()

    characters = discover_characters()
    if not characters:
        log.error("no usable characters found; run tools/gen_panda.py")
        lock.release()
        return 1
    config = Config.load()
    window = PetWindow(config, characters)

    controller = PetController(
        Timings(permission_reminder=config.permission_reminder_seconds),
        quit_after=config.quit_after_minutes * 60,
        config=config,
    )
    controller.display_changed.connect(
        lambda d: log.info(
            "state → %s%s [%s] %r (%d session(s))",
            d.state.value,
            f"/{d.variant}" if d.variant else "",
            d.project or "-",
            d.text,
            d.session_count,
        )
    )
    controller.cue.connect(lambda name: log.info("sound cue: %s", name))
    controller.quit_requested.connect(app.quit)
    controller.display_changed.connect(window.set_display)
    player = SoundPlayer(config, window.character)
    controller.cue.connect(player.play)
    window.character_changed.connect(lambda _cid: player.set_character(window.character))
    window.sound_settings_changed.connect(player.apply_settings)
    window.test_sound_requested.connect(lambda: player.play("done", force=True))
    window.quit_requested.connect(app.quit)
    window.clicked.connect(controller.focus_session)
    controller.nudge.connect(lambda _sid: window.nudge())
    window.reminder_changed.connect(controller.set_reminder_seconds)
    controller.dnd_requested.connect(window.set_do_not_disturb)
    window.set_display(controller.display)
    window.show()

    server = EventServer(controller.handle_from_thread)
    server.start()
    if initial_event:
        controller.apply(initial_event)

    # Let Ctrl+C quit: Python only handles signals when the interpreter gets control.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    wake = QTimer()
    wake.start(200)
    wake.timeout.connect(lambda: None)

    log.info("bao started")
    try:
        return app.exec()
    finally:
        server.stop()
        lock.release()
        log.info("bao stopped")
