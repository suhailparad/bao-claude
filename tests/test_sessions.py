from bao.sessions import SessionTracker, State, Timings


def ev(event, sid="a", **kw):
    return {"event": event, "session_id": sid, "cwd": "/work/proj-" + sid, **kw}


def test_no_sessions_is_sleeping():
    d = SessionTracker().resolve()
    assert d.state is State.SLEEPING and d.session_count == 0


def test_basic_flow_and_cues():
    t = SessionTracker()
    assert t.apply(ev("SessionStart", source="startup"), now=0) == ["hello"]
    assert t.resolve().state is State.GREETING
    t.apply(ev("UserPromptSubmit"), now=1)
    assert t.resolve().state is State.THINKING
    t.apply(ev("PreToolUse", tool_name="Edit"), now=2)
    d = t.resolve()
    assert (d.state, d.variant, d.text) == (State.WORKING, "typing", "Writing code…")
    assert d.project == "proj-a"
    t.apply(ev("PostToolUse", tool_name="Edit"), now=3)
    assert t.resolve().state is State.THINKING
    assert t.apply(ev("Stop"), now=4) == ["done"]
    assert t.resolve().state is State.DONE
    assert t.apply(ev("SessionEnd"), now=5) == ["bye"]
    assert t.resolve().state is State.SLEEPING


def test_unknown_tool_has_no_variant():
    t = SessionTracker()
    t.apply(ev("PreToolUse", tool_name="mcp__x__y"), now=0)
    d = t.resolve()
    assert d.state is State.WORKING and d.variant is None and d.text == "Working…"


def test_notifications():
    t = SessionTracker()
    assert t.apply(ev("Notification", notification_type="permission_prompt"), now=0) == ["alert"]
    assert t.resolve().state is State.NEEDS_PERMISSION
    assert t.apply(ev("Notification", notification_type="idle_prompt"), now=1) == ["waiting"]
    assert t.resolve().state is State.WAITING
    # Older Claude Code: no notification_type, classify by message text.
    t.apply(ev("Notification", message="Claude needs your permission to use Bash"), now=2)
    assert t.resolve().state is State.NEEDS_PERMISSION
    assert t.apply(ev("Notification", notification_type="auth_success"), now=3) == []
    assert t.resolve().state is State.NEEDS_PERMISSION


def test_session_start_sources():
    t = SessionTracker()
    t.apply(ev("PreCompact"), now=0)
    assert t.resolve().state is State.COMPACTING
    assert t.apply(ev("SessionStart", source="compact"), now=1) == []
    assert t.resolve().state is State.THINKING
    t.apply(ev("SessionStart", source="clear"), now=2)
    assert t.resolve().state is State.IDLE


def test_subagent_stop_keeps_state():
    t = SessionTracker()
    t.apply(ev("PreToolUse", tool_name="Bash"), now=0)
    t.apply(ev("SubagentStop"), now=1)
    assert t.resolve().variant == "running"


def test_priority_across_sessions():
    t = SessionTracker()
    t.apply(ev("PreToolUse", sid="a", tool_name="Bash"), now=0)
    t.apply(ev("UserPromptSubmit", sid="b"), now=1)
    assert t.resolve().session_id == "a"  # working beats thinking
    t.apply(ev("Notification", sid="b", notification_type="permission_prompt"), now=2)
    d = t.resolve()
    assert (d.state, d.project, d.session_count) == (State.NEEDS_PERMISSION, "proj-b", 2)


def test_tie_breaks_on_most_recent():
    t = SessionTracker()
    t.apply(ev("UserPromptSubmit", sid="a"), now=0)
    t.apply(ev("UserPromptSubmit", sid="b"), now=1)
    assert t.resolve().session_id == "b"


def test_timed_transitions():
    tm = Timings(
        greeting_seconds=3, done_seconds=3, sleep_after=60, stale_busy_after=100, forget_after=1000
    )
    t = SessionTracker(tm)
    t.apply(ev("SessionStart"), now=0)
    assert not t.tick(now=2)
    assert t.tick(now=3) and t.resolve().state is State.IDLE
    t.apply(ev("Stop"), now=10)
    t.tick(now=13)
    assert t.resolve().state is State.WAITING
    t.tick(now=70)
    assert t.resolve().state is State.SLEEPING
    t.apply(ev("PreToolUse", tool_name="Read"), now=100)
    t.tick(now=200)
    assert t.resolve().state is State.IDLE  # stale busy → idle
    t.tick(now=1200)
    assert t.resolve().session_count == 0  # forgotten


def test_needs_permission_never_sleeps():
    t = SessionTracker(Timings(sleep_after=10, stale_busy_after=10, forget_after=10_000))
    t.apply(ev("Notification", notification_type="permission_prompt"), now=0)
    t.tick(now=5000)
    assert t.resolve().state is State.NEEDS_PERMISSION


def test_format_duration():
    from bao.sessions import format_duration

    assert format_duration(0.4) == "0s"
    assert format_duration(42) == "42s"
    assert format_duration(252) == "4m 12s"
    assert format_duration(3600 + 5 * 60 + 9) == "1h 05m"


def test_done_shows_turn_duration():
    t = SessionTracker(Timings(done_seconds=3))
    t.apply(ev("UserPromptSubmit"), now=100)
    t.apply(ev("PreToolUse", tool_name="Bash"), now=150)
    assert t.resolve().duration is None  # still working
    t.apply(ev("Stop"), now=352)
    d = t.resolve()
    assert (d.text, d.duration) == ("Done in 4m 12s!", 252)
    t.tick(now=356)
    d = t.resolve()
    assert d.state is State.WAITING and d.duration == 252 and d.text == "Waiting for you"
    t.apply(ev("UserPromptSubmit"), now=400)
    assert t.resolve().duration is None
    assert t.snapshot()[0]["last_turn_seconds"] is None


def test_stop_without_prompt_has_no_duration():
    t = SessionTracker()
    t.apply(ev("PreToolUse", tool_name="Read"), now=0)  # pet started mid-turn
    t.apply(ev("Stop"), now=10)
    d = t.resolve()
    assert d.duration is None and d.text == "All done!"
