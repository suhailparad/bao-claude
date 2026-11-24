import io
import json
import os
import subprocess
import sys
import threading
import time

import pytest

from bao import hook
from bao.ipc import EventServer, InstanceLock, send_message
from bao.paths import endpoint_path, port_path


def start_server(handler):
    server = EventServer(handler)
    server.start()
    return server


def test_roundtrip_event_and_command(transport):
    got, seen = [], threading.Event()

    def handler(msg):
        if msg.get("cmd") == "status":
            return {"ok": True, "n": len(got)}
        got.append(msg)
        seen.set()
        return None

    server = start_server(handler)
    try:
        send_message({"event": "Stop", "session_id": "x"})
        assert seen.wait(2)
        assert got[0]["event"] == "Stop"
        assert send_message({"cmd": "status"}, expect_reply=True, timeout=1) == {"ok": True, "n": 1}
    finally:
        server.stop()
    assert not endpoint_path().exists()


def test_send_without_server_raises(transport):
    with pytest.raises(OSError):
        send_message({"event": "Stop"})


def test_instance_lock(pet_home):
    a, b = InstanceLock(), InstanceLock()
    assert a.acquire()
    assert not b.acquire()
    a.release()
    assert b.acquire()
    b.release()


def test_build_message_from_payload():
    payload = {
        "hook_event_name": "PreToolUse",
        "session_id": "s1",
        "cwd": "/p",
        "tool_name": "Bash",
        "tool_input": {"command": "secret stuff"},
    }
    msg = hook.build_message(payload)
    assert msg["event"] == "PreToolUse" and msg["tool_name"] == "Bash"
    assert "tool_input" not in msg  # never forward tool inputs


def test_hook_main_delivers(transport, monkeypatch, capsys):
    got, seen = [], threading.Event()
    server = start_server(lambda m: (got.append(m), seen.set(), None)[2])
    try:
        payload = {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "cwd": "/p"}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        assert hook.main([]) == 0
        assert seen.wait(2) and got[0]["event"] == "UserPromptSubmit"
    finally:
        server.stop()
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("stdin", ["", "not json", "[1,2]", '{"hook_event_name": "Stop"}'])
def test_hook_process_is_silent_fast_and_exits_zero(transport, stdin):
    env = {**os.environ}
    start = time.monotonic()
    proc = subprocess.run(
        [sys.executable, "-I", "-m", "bao.hook"],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    elapsed = time.monotonic() - start
    assert proc.returncode == 0
    assert proc.stdout == ""
    assert elapsed < 1.0  # includes interpreter startup; the hook itself must stay tiny


def test_build_message_adds_terminal_only_for_some_events(monkeypatch):
    monkeypatch.setattr(hook, "terminal_info", lambda: {"app": "com.apple.Terminal"})
    msg = hook.build_message({"hook_event_name": "UserPromptSubmit", "session_id": "s"})
    assert msg["terminal"] == {"app": "com.apple.Terminal"}
    assert "terminal" not in hook.build_message({"hook_event_name": "PreToolUse"})


def test_tcp_requires_the_token(pet_home, monkeypatch):
    import socket as socketlib

    monkeypatch.setenv("BAO_IPC", "tcp")
    got, seen = [], threading.Event()
    server = start_server(lambda m: (got.append(m), seen.set(), None)[2])
    try:
        data = json.loads(port_path().read_text())
        assert set(data) == {"port", "token"} and len(data["token"]) == 32
        if sys.platform != "win32":
            assert port_path().stat().st_mode & 0o077 == 0  # only the user can read it
        for bad in ({"event": "Stop"}, {"event": "Stop", "token": "nope"}):
            with socketlib.create_connection(("127.0.0.1", data["port"]), timeout=1) as s:
                s.sendall((json.dumps(bad) + "\n").encode())
        send_message({"event": "UserPromptSubmit"})  # reads the token from the port file
        assert seen.wait(2)
        assert [m["event"] for m in got] == ["UserPromptSubmit"] and "token" not in got[0]
    finally:
        server.stop()
    assert not port_path().exists()


def test_launch_pet_detaches_per_platform(monkeypatch):
    calls = []
    monkeypatch.setattr(hook.subprocess, "Popen", lambda argv, **kw: calls.append((argv, kw)))
    monkeypatch.setattr(hook.sys, "platform", "win32")
    hook.launch_pet({"event": "SessionStart"})
    monkeypatch.setattr(hook.sys, "platform", "linux")
    hook.launch_pet({"event": "SessionStart"})
    (win_argv, win), (_, posix) = calls
    assert win["creationflags"] & 0x8 and "start_new_session" not in win  # DETACHED_PROCESS
    assert posix["start_new_session"] and "creationflags" not in posix
    assert win_argv[1:5] == ["-I", "-m", "bao", "run"]
