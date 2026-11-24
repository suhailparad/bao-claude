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
from bao.paths import socket_path


def start_server(handler):
    server = EventServer(handler)
    server.start()
    return server


def test_roundtrip_event_and_command(pet_home):
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
    assert not socket_path().exists()


def test_send_without_server_raises(pet_home):
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


def test_hook_main_delivers(pet_home, monkeypatch, capsys):
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
def test_hook_process_is_silent_fast_and_exits_zero(pet_home, stdin):
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
