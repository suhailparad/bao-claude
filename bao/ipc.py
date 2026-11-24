"""Local IPC between the hook (client) and the pet app (server).

Protocol: Unix stream socket, one JSON object per line.
  * Event messages carry an ``"event"`` key and get no reply.
  * Command messages carry a ``"cmd"`` key ("status", "quit") and get a one-line JSON reply.

Stdlib only: the hook imports this module, so it must never import Qt.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import socket
import threading
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any

from .paths import lock_path, socket_path

PROTOCOL_VERSION = 1
MAX_LINE = 64 * 1024

log = logging.getLogger(__name__)

Message = dict[str, Any]
Handler = Callable[[Message], "Message | None"]


def send_message(
    msg: Message,
    path: Path | None = None,
    timeout: float = 0.2,
    expect_reply: bool = False,
) -> Message | None:
    """Send one message. Raises OSError if the pet isn't reachable."""
    target = str(path or socket_path())
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect(target)
        sock.sendall((json.dumps(msg) + "\n").encode("utf-8"))
        if not expect_reply:
            return None
        data = b""
        while b"\n" not in data and len(data) < MAX_LINE:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
        line = data.split(b"\n", 1)[0].strip()
        return json.loads(line) if line else None


class EventServer:
    """Accepts connections on a background thread and passes each message to ``handler``.

    ``handler`` runs on the server thread; it must hand work to the GUI thread itself
    (the Qt controller does this with a queued signal).
    """

    def __init__(self, handler: Handler, path: Path | None = None) -> None:
        self._handler = handler
        self.path = path or socket_path()
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Safe to remove: the caller holds the single-instance lock.
        if self.path.exists() or self.path.is_symlink():
            self.path.unlink()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(str(self.path))
        os.chmod(self.path, 0o600)
        sock.listen(16)
        sock.settimeout(0.5)
        self._sock = sock
        self._thread = threading.Thread(target=self._serve, name="bao-ipc", daemon=True)
        self._thread.start()
        log.info("listening on %s", self.path)

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            self._sock.close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def _serve(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except TimeoutError:
                continue
            except OSError:
                break  # socket closed by stop()
            with conn:
                conn.settimeout(1.0)
                try:
                    self._handle_conn(conn)
                except OSError as exc:
                    log.debug("client connection error: %s", exc)
                except Exception:
                    log.exception("error handling client")

    def _handle_conn(self, conn: socket.socket) -> None:
        buf = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
            if len(buf) > MAX_LINE:
                log.warning("dropping oversized message")
                return
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                self._dispatch(conn, line)
        if buf.strip():
            self._dispatch(conn, buf)

    def _dispatch(self, conn: socket.socket, line: bytes) -> None:
        if not line.strip():
            return
        try:
            msg = json.loads(line)
        except ValueError:
            log.warning("ignoring invalid JSON message")
            return
        if not isinstance(msg, dict):
            return
        reply = self._handler(msg)
        if reply is not None:
            conn.sendall((json.dumps(reply) + "\n").encode("utf-8"))


class InstanceLock:
    """Advisory file lock that keeps only one pet app running."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or lock_path()
        self._fh: IO[str] | None = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+")  # noqa: SIM115 - held open for the app's lifetime
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        fh.seek(0)
        fh.truncate()
        fh.write(str(os.getpid()))
        fh.flush()
        self._fh = fh
        return True

    def release(self) -> None:
        if self._fh is not None:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            self._fh.close()
            self._fh = None
