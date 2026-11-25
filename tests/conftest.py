import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def pet_home(monkeypatch):
    # Unix socket paths are limited to ~104 bytes on macOS, so avoid pytest's long tmp_path.
    short = "/tmp" if sys.platform != "win32" and os.path.isdir("/tmp") else None
    d = Path(tempfile.mkdtemp(prefix="cpet-", dir=short))
    monkeypatch.setenv("BAO_HOME", str(d))
    monkeypatch.setenv("BAO_NO_LAUNCH", "1")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture(params=["unix", "tcp"])
def transport(request, pet_home, monkeypatch):
    """Run IPC tests over the Unix socket (macOS/Linux) and TCP (Windows' transport)."""
    if request.param == "unix" and sys.platform == "win32":
        pytest.skip("no Unix sockets on Windows")
    if request.param == "tcp":
        monkeypatch.setenv("BAO_IPC", "tcp")
    else:
        monkeypatch.delenv("BAO_IPC", raising=False)
    return request.param


# PySide6 on Python 3.10 can abort while the interpreter tears down Qt objects
# ("Fatal Python error: none_dealloc"), after every test has passed. Once pytest has
# printed its summary there is nothing left to clean up, so exit without that teardown.
_exit_status: list[int] = []


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    _exit_status.append(int(exitstatus))


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config: pytest.Config) -> None:
    if _exit_status and "PySide6" in sys.modules and not os.environ.get("BAO_TEST_FULL_EXIT"):
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(_exit_status[0])
