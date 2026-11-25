"""Session tracking and state resolution. Pure Python (no Qt) so it is easy to test.

``SessionTracker.apply()`` turns hook messages into per-session states and returns
sound cues; ``tick()`` handles time-based transitions; ``resolve()`` picks the one
state the pet should show (highest priority wins, most recent breaks ties).
"""

from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from .focus import clean_info


class State(str, Enum):
    SLEEPING = "sleeping"
    IDLE = "idle"
    GREETING = "greeting"
    COMPACTING = "compacting"
    THINKING = "thinking"
    WORKING = "working"
    DONE = "done"
    WAITING = "waiting"
    NEEDS_PERMISSION = "needs_permission"


# Lowest → highest. Index is the priority.
PRIORITY: dict[State, int] = {
    s: i
    for i, s in enumerate(
        [
            State.SLEEPING,
            State.IDLE,
            State.GREETING,
            State.COMPACTING,
            State.THINKING,
            State.WORKING,
            State.DONE,
            State.WAITING,
            State.NEEDS_PERMISSION,
        ]
    )
}

TOOL_VARIANTS: dict[str, str] = {
    **dict.fromkeys(
        ["Read", "Grep", "Glob", "LS", "WebFetch", "WebSearch", "NotebookRead"], "reading"
    ),
    **dict.fromkeys(["Edit", "Write", "MultiEdit", "NotebookEdit"], "typing"),
    **dict.fromkeys(["Bash", "BashOutput", "KillShell"], "running"),
}

PET_NAME = "Bao"  # the pet speaks about itself in the third person: "Bao is thinking…"

STATE_TEXT: dict[State, str] = {
    State.SLEEPING: f"{PET_NAME} is sleeping",
    State.IDLE: f"{PET_NAME} is ready",
    State.GREETING: f"{PET_NAME} says hi!",
    State.COMPACTING: f"{PET_NAME} is tidying up…",
    State.THINKING: f"{PET_NAME} is thinking…",
    State.WORKING: f"{PET_NAME} is working…",
    State.DONE: f"{PET_NAME} is done!",
    State.WAITING: f"{PET_NAME} is waiting for you",
    State.NEEDS_PERMISSION: f"{PET_NAME} needs your permission!",
}

VARIANT_TEXT: dict[str, str] = {
    "reading": f"{PET_NAME} is reading…",
    "typing": f"{PET_NAME} is typing…",
    "running": f"{PET_NAME} is running…",
}

# Notification types (Claude Code `notification_type`) that are informational only.
IGNORED_NOTIFICATIONS = {"auth_success"}


@dataclass
class Timings:
    greeting_seconds: float = 3.0
    done_seconds: float = 3.0
    sleep_after: float = 300.0  # idle/waiting with no events → sleeping
    stale_busy_after: float = 900.0  # thinking/working with no events → idle (interrupted?)
    forget_after: float = 6 * 3600.0  # drop sessions whose SessionEnd never arrived
    permission_reminder: float = 60.0  # unanswered permission → remind once (0 = never)


@dataclass
class Session:
    session_id: str
    project: str
    state: State
    variant: str | None
    last_event_at: float
    state_since: float
    terminal: dict[str, Any] = field(default_factory=dict)  # see focus.terminal_info
    turn_started_at: float | None = None  # UserPromptSubmit of the current turn
    last_turn_seconds: float | None = None  # how long the last finished turn took
    reminded: bool = False  # the reminder for the current state was given


@dataclass(frozen=True)
class Display:
    state: State
    variant: str | None
    text: str
    project: str | None
    session_id: str | None
    session_count: int
    duration: float | None = None  # seconds the last turn took (done / waiting only)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        return d


def tool_variant(tool_name: str | None) -> str | None:
    if not tool_name:
        return None
    return TOOL_VARIANTS.get(tool_name)


def classify_notification(msg: dict[str, Any]) -> State | None:
    """Map a Notification hook to NEEDS_PERMISSION / WAITING, or None to ignore it."""
    ntype = (msg.get("notification_type") or "").lower()
    text = (msg.get("message") or "").lower()
    if ntype in IGNORED_NOTIFICATIONS:
        return None
    if ntype == "permission_prompt" or "permission" in text:
        return State.NEEDS_PERMISSION
    return State.WAITING


def format_duration(seconds: float) -> str:
    """42s, 4m 12s, 1h 05m."""
    s = max(0, round(seconds))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60:02d}s"
    return f"{s // 3600}h {s % 3600 // 60:02d}m"


def state_text(state: State, variant: str | None, duration: float | None = None) -> str:
    if state is State.DONE and duration is not None:
        return f"{PET_NAME} finished in {format_duration(duration)}!"
    if state is State.WORKING and variant in VARIANT_TEXT:
        return VARIANT_TEXT[variant]
    return STATE_TEXT[state]


def _project_name(cwd: Any) -> str:
    if not cwd or not isinstance(cwd, str):
        return ""
    return os.path.basename(cwd.rstrip("/")) or cwd


@dataclass
class SessionTracker:
    timings: Timings = field(default_factory=Timings)
    sessions: dict[str, Session] = field(default_factory=dict)

    # -- events ---------------------------------------------------------------------------

    def apply(self, msg: dict[str, Any], now: float | None = None) -> list[str]:
        """Apply one hook message. Returns sound cue names to play."""
        now = time.time() if now is None else now
        event = msg.get("event") or ""
        sid = str(msg.get("session_id") or "default")

        if event == "SessionEnd":
            return ["bye"] if self.sessions.pop(sid, None) is not None else []

        session = self.sessions.get(sid)
        if session is None:
            session = Session(sid, "", State.IDLE, None, now, now)
            self.sessions[sid] = session
        session.last_event_at = now
        project = _project_name(msg.get("cwd"))
        if project:
            session.project = project
        terminal = clean_info(msg.get("terminal"))
        if terminal:
            session.terminal = terminal

        cues: list[str] = []
        if event == "SessionStart":
            source = msg.get("source") or "startup"
            if source == "compact":
                self._set(session, State.THINKING, None, now)
            elif source == "clear":
                self._set(session, State.IDLE, None, now)
            else:
                self._set(session, State.GREETING, None, now)
                cues.append("hello")
        elif event == "UserPromptSubmit":
            self._set(session, State.THINKING, None, now)
            session.turn_started_at = now
            session.last_turn_seconds = None
        elif event == "PreToolUse":
            self._set(session, State.WORKING, tool_variant(msg.get("tool_name")), now)
        elif event in ("PostToolUse", "PostToolUseFailure"):
            self._set(session, State.THINKING, None, now)
        elif event == "Notification":
            state = classify_notification(msg)
            if state is State.NEEDS_PERMISSION:
                self._set(session, state, None, now)
                cues.append("alert")
            elif state is State.WAITING:
                self._set(session, state, None, now)
                cues.append("waiting")
        elif event == "Stop":
            self._set(session, State.DONE, None, now)
            if session.turn_started_at is not None:
                session.last_turn_seconds = now - session.turn_started_at
                session.turn_started_at = None
            cues.append("done")
        elif event == "PreCompact":
            self._set(session, State.COMPACTING, None, now)
        # SubagentStop and unknown events: keep the current state.
        return cues

    @staticmethod
    def _set(session: Session, state: State, variant: str | None, now: float) -> None:
        if session.state is not state or session.variant != variant:
            session.state = state
            session.variant = variant
            session.state_since = now
            session.reminded = False

    # -- time -----------------------------------------------------------------------------

    def tick(self, now: float | None = None) -> bool:
        """Apply time-based transitions. Returns True if anything changed."""
        now = time.time() if now is None else now
        t = self.timings
        changed = False
        for sid, s in list(self.sessions.items()):
            quiet = now - s.last_event_at
            if quiet >= t.forget_after:
                del self.sessions[sid]
                changed = True
                continue
            new: State | None = None
            if s.state is State.GREETING and now - s.state_since >= t.greeting_seconds:
                new = State.IDLE
            elif s.state is State.DONE and now - s.state_since >= t.done_seconds:
                new = State.WAITING
            elif s.state in (State.IDLE, State.WAITING) and quiet >= t.sleep_after:
                new = State.SLEEPING
            elif (
                s.state in (State.THINKING, State.WORKING, State.COMPACTING)
                and quiet >= t.stale_busy_after
            ):
                new = State.IDLE
            if new is not None:
                self._set(s, new, None, now)
                changed = True
        return changed

    def due_reminders(self, now: float | None = None) -> list[str]:
        """Sessions whose permission request has gone unanswered too long (each reported once)."""
        now = time.time() if now is None else now
        after = self.timings.permission_reminder
        if after <= 0:
            return []
        due = []
        for s in self.sessions.values():
            if (
                s.state is State.NEEDS_PERMISSION
                and not s.reminded
                and now - s.state_since >= after
            ):
                s.reminded = True
                due.append(s.session_id)
        return due

    # -- output ---------------------------------------------------------------------------

    def resolve(self) -> Display:
        if not self.sessions:
            return Display(State.SLEEPING, None, STATE_TEXT[State.SLEEPING], None, None, 0)
        best = max(self.sessions.values(), key=lambda s: (PRIORITY[s.state], s.last_event_at))
        duration = best.last_turn_seconds if best.state in (State.DONE, State.WAITING) else None
        return Display(
            state=best.state,
            variant=best.variant,
            text=state_text(best.state, best.variant, duration),
            project=best.project or None,
            session_id=best.session_id,
            session_count=len(self.sessions),
            duration=duration,
        )

    def terminal_for(self, session_id: str | None) -> dict[str, Any] | None:
        session = self.sessions.get(session_id) if session_id else None
        return dict(session.terminal) if session and session.terminal else None

    def snapshot(self) -> list[dict[str, Any]]:
        return [
            {
                "session_id": s.session_id,
                "project": s.project,
                "state": s.state.value,
                "variant": s.variant,
                "last_event_at": s.last_event_at,
                "terminal": s.terminal,
                "last_turn_seconds": s.last_turn_seconds,
            }
            for s in self.sessions.values()
        ]
